from math import sqrt, atan, tan, cos, sin, radians, degrees
from decimal import Decimal
from typing import Callable, Dict, Tuple

from calculation.models import CalculationMeta, FaultCalculation, SettingsCalculation
from core.models import Component, ProtectionHalfSet


class SettingsCalculationService:
    def __init__(
        self,
        calculation_meta: CalculationMeta,
        calculation_factors: Dict[str, float],
        enabled_organs: Dict[str, bool] = None,
    ):
        # Определяем словарь коэффициентов
        self.calculation_factors = calculation_factors or {}
        # Словарь состояния включения/отключения органов (для необязательных органов)
        self.enabled_organs = enabled_organs or {}

        # Определяем мета-данные расчета
        self.calculation_meta = calculation_meta

        # Определяем линию и полукомплекты защиты
        self.line = calculation_meta.line
        self.protection_half_sets = self.line.protection_half_sets.all()

        # Используем load_current из calculation_factors, если он задан, иначе из модели Line
        self.load_current = self.calculation_factors.get(
            "load_current",
            self.line.current_capacity if self.line.current_capacity else 2000,
        )

        # Используем параметры ТТ/ТН из линии напрямую
        # Для ТТ: используем ratio из связанного трансформатора
        self.current_transformer_ratio = self.line.ct.ratio if self.line.ct else 1000
        # Для ТН: используем calculate_ratio с напряжением ЛЭП из PowerFactory
        # calculate_ratio возвращает относительный коэффициент (например, 1.27 для 220 кВ DELTA)
        # Умножаем на 1000 для получения абсолютного коэффициента трансформации в вольтах
        # (например, 1270 для 220 кВ DELTA или 2200 для 220 кВ STAR)
        if self.line.vt and self.line.voltage_level:
            relative_ratio = self.line.vt.calculate_ratio(
                self.line.voltage_level)
            self.voltage_transformer_factor = relative_ratio * 1000
        else:
            self.voltage_transformer_factor = 5000

        # Коэффициент чувствительности токовых органов
        self.current_sensitivity_rate = 2

        # Карта расчетных функций органов
        # Поддерживаем оба варианта названия: "К МАН" (кириллица) и "K МАН" (латиница)
        self.CALCULATION_MAP = {
            "IЛ БЛОК": self.calculate_il_block,
            "IЛ ОТКЛ": self.calculate_il_break,
            "I2 БЛОК": self.calculate_i2_block,
            "I2 ОТКЛ": self.calculate_i2_break,
            "3I0 БЛОК": self.calculate_3i0_block,
            "3I0 ОТКЛ": self.calculate_3i0_break,
            "DI1 БЛОК": self.calculate_di1_block,
            "DI1 ОТКЛ": self.calculate_di1_break,
            "DI2 БЛОК": self.calculate_di2_block,
            "DI2 ОТКЛ": self.calculate_di2_break,
            "U2 БЛОК": self.calculate_u2_block,
            "U2 ОТКЛ": self.calculate_u2_break,
            "K МАН": self.calculate_manipulation_factor,  # Латиница
            # Кириллица (для совместимости)
            "К МАН": self.calculate_manipulation_factor,
            "УГОЛ БЛОК": self.calculate_blocking_angle,
            "РТНП/3I0_M0": self.calculate_rtnp,
            "РННП/3U0_M0": self.calculate_rnnp,
            "R ОТКЛ": self.calculate_r_break,
            "X ОТКЛ": self.calculate_x_break,
            "R ОТВ": self.calculate_r_otv,
            "X ОТВ": self.calculate_x_otv,
        }

    def save_result_to_db(
        self,
        protection_half_set: ProtectionHalfSet,
        component: Component,
        calculation_factors: Dict[str, float],
        result_value: float,
    ) -> None:
        """
        Сохраняет результат расчета в БД с первичными и вторичными величинами.

        Args:
            protection_half_set: Полукомплект защиты
            component: Орган защиты
            calculation_factors: Расчетные коэффициенты
            result_value: Результат расчета (в первичных величинах)
        """
        # Проверяем, что calculation_meta установлен
        if not hasattr(self, "calculation_meta") or not self.calculation_meta:
            raise ValueError(
                "calculation_meta не установлен в SettingsCalculationService"
            )

        # Первичное значение - это результат расчета
        primary_value = result_value

        # Определяем тип органа для правильного перевода во вторичные величины
        setting_designation = component.setting_designation

        # Для токовых органов (IЛ, I2, 3I0, DI1, DI2, K МАН, РТНП) делим на коэффициент ТТ
        if any(
            prefix in setting_designation
            for prefix in ["IЛ", "I2", "3I0", "DI1", "DI2", "K МАН", "РТНП"]
        ):
            secondary_value = primary_value / self.current_transformer_ratio
        # Для напряженческих органов (U2, РННП) делим на коэффициент ТН
        elif "U2" in setting_designation or "РННП" in setting_designation:
            secondary_value = primary_value / self.voltage_transformer_factor
        # Для угла блокировки значения одинаковые
        elif "УГОЛ" in setting_designation:
            secondary_value = primary_value
        # Для органов сопротивления (R ОТКЛ, X ОТКЛ, R ОТВ, X ОТВ) значения одинаковые (в Ом)
        elif any(
            prefix in setting_designation
            for prefix in ["R ОТКЛ", "X ОТКЛ", "R ОТВ", "X ОТВ"]
        ):
            secondary_value = primary_value
        else:
            # По умолчанию считаем токовым органом
            secondary_value = primary_value / self.current_transformer_ratio

        # Логируем сохранение для диагностики
        print(
            f"[DEBUG] Сохранение результата: Орган={component.setting_designation}, Полукомплект={protection_half_set}, CalculationMeta ID={self.calculation_meta.id}, Значение={result_value}"
        )

        SettingsCalculation.objects.create(
            calculation_meta=self.calculation_meta,
            protection_half_set=protection_half_set,
            component=component,
            calculation_factors=calculation_factors,
            result_value=result_value,  # Оставляем для обратной совместимости
            primary_value=primary_value,
            secondary_value=secondary_value,
        )

    def get_calculation_function(self, component: Component) -> Callable[[], float]:
        calculation_function = self.CALCULATION_MAP.get(
            component.setting_designation)
        return calculation_function

    def calculate_blocking_angle(self) -> Tuple[float, Dict[str, float]]:
        """Рассчитывает угол блокировки в зависимости от длины ЛЭП."""
        if self.line.length < 60:
            blocking_angle = 50
        elif 60 <= self.line.length < 150:
            blocking_angle = 60
        else:
            blocking_angle = 65
        return blocking_angle, {}

    def calculate_manipulation_factor(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает коэффициент манипуляции для каждого полукомплекта по условию
        обеспечения преимущественного сравнения токов манипуляции по току обратной
        последовательности при КЗ на землю на противоположном конце защищаемой ЛЭП.

        При двухфазном КЗ на землю (К(1,1)):
        K_М ≥ k_н * ((I_1^К(1,1) + I_ДДРТ) / I_2^К(1,1))

        При однофазном КЗ (К(1)):
        K_М ≥ k_н * (I_ДДРТ / I_2^К(1))

        где:
        - k_н = 1.5 - коэффициент надежности манипуляции
        - I_ДДРТ - длительно допустимый рабочий ток защищаемой ЛЭП (load_current, в А)
        - I_1^К(1,1) - ток прямой последовательности при двухфазном КЗ на землю
          на противоположном конце (в мА, переводим в А)
        - I_2^К(1,1) - ток обратной последовательности при двухфазном КЗ на землю
          на противоположном конце (в мА, переводим в А)
        - I_2^К(1) - ток обратной последовательности при однофазном КЗ
          на противоположном конце (в мА, переводим в А)

        Коэффициент манипуляции выбирается по максимальному значению из двух условий.
        """
        k_n = self.calculation_factors.get("manipulation_grading_factor", 1.5)

        # Получаем расчеты КЗ на противоположном конце (perform_fault_calculation создает их)
        fault_calculations = FaultCalculation.objects.filter(
            protection_half_set__in=self.protection_half_sets,
            fault_type__in=["К(1)", "К(1,1)"],
            calculation_meta=self.calculation_meta,
        )

        manipulation_factors = []

        for fault_calculation in fault_calculations:
            fault_type = fault_calculation.fault_type
            fault_values = fault_calculation.fault_values or {}

            if fault_type == "К(1,1)":
                # Формула для двухфазного КЗ на землю: K_М ≥ k_н * ((I_1^К(1,1) + I_ДДРТ) / I_2^К(1,1))
                i1_k11 = fault_values.get("I1", 0)  # в мА
                i2_k11 = fault_values.get("I2", 0)  # в мА

                if i2_k11 and i2_k11 != 0:
                    # Переводим токи из мА в А
                    i1_k11_a = i1_k11 / 1000
                    i2_k11_a = i2_k11 / 1000

                    manipulation_factor = k_n * (
                        (i1_k11_a + self.load_current) / i2_k11_a
                    )
                manipulation_factors.append(manipulation_factor)

            elif fault_type == "К(1)":
                # Формула для однофазного КЗ: K_М ≥ k_н * (I_ДДРТ / I_2^К(1))
                i2_k1 = fault_values.get("I2", 0)  # в мА

                if i2_k1 and i2_k1 != 0:
                    # Переводим ток из мА в А
                    i2_k1_a = i2_k1 / 1000

                    manipulation_factor = k_n * (self.load_current / i2_k1_a)
                manipulation_factors.append(manipulation_factor)

        if not manipulation_factors:
            # Если расчетов нет, возвращаем значение по умолчанию
            return 0.0, {"Коэффициент надежности манипуляции": k_n}

        # Выбираем максимальное значение из всех условий
        # Округление до стандартных значений выполняется в методе run()
        max_manipulation_factor = max(manipulation_factors)

        calculation_factors = {
            "Коэффициент надежности манипуляции": k_n,
        }

        return max_manipulation_factor, calculation_factors

    def calculate_il_block(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку блокирующего органа по фазному току (с пуском по векторной разности фазных токов).

        Формула: Iл блок ≥ k_сх ∙ k_отс/k_в ∙ I_ДДРТ
        где:
        - k_сх = √3 - коэффициент схемы для органов с пуском по векторной разности фазных токов
        - k_отс = 1.2-1.3 - коэффициент отстройки (по умолчанию 1.3)
        - k_в - коэффициент возврата (зависит от производителя: ЭКРА = 0.9, Релематика/Бреслер = 0.95)
        - I_ДДРТ - длительно допустимый рабочий ток защищаемой ЛЭП (load_current)
        """
        il_grading_factor = self.calculation_factors.get(
            "il_grading_factor", 1.3)
        # Определяем коэффициент возврата в зависимости от производителя
        il_reset_factor = self.calculation_factors.get(
            "il_reset_factor", self._get_reset_factor(default_value=0.9)
        )
        k_sx = sqrt(
            3
        )  # Коэффициент схемы для органов с пуском по векторной разности фазных токов

        # Формула: Iл блок = k_сх ∙ k_отс/k_в ∙ I_ДДРТ
        il_block_value = k_sx * il_grading_factor / il_reset_factor * self.load_current

        calculation_factors = {
            "Коэффициент отстройки": il_grading_factor,
            "Коэффициент возврата": il_reset_factor,
        }
        return il_block_value, calculation_factors

    def calculate_il_break(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку отключающего органа по фазному току.

        Формула: I_откл ≥ k_согл ∙ I_бл
        где:
        - k_согл = 1.4-2.0 - коэффициент согласования (по умолчанию 1.4)
        - I_бл - уставка блокирующего органа (Iл блок)

        Дополнительно учитывается коэффициент ответвлений K_отв = 2 для линий с ответвлениями.
        """
        il_block_value = self.calculate_il_block()[0]
        il_matching_factor = self.calculation_factors.get(
            "il_matching_factor", 1.4)

        # Формула: I_откл = k_согл ∙ I_бл
        il_break_value = il_matching_factor * il_block_value

        # Проверяем наличие ответвлений и применяем коэффициент ответвлений K_отв = 2
        k_otv = 1.0
        has_branches = False
        if self.line:
            # Проверяем наличие активных ответвлений
            if self.line.branch_count and self.line.branch_count > 0:
                has_branches = True
            elif hasattr(self.line, "branches"):
                has_branches = self.line.branches.filter(
                    is_active=True).exists()

        if has_branches:
            k_otv = 2.0
            il_break_value = il_break_value * k_otv
            print(
                f"[DEBUG] Для IЛ ОТКЛ применен коэффициент ответвления = {k_otv}")

        calculation_factors = {
            "Коэффициент согласования": il_matching_factor,
        }
        # Не добавляем коэффициент ответвления в calculation_factors

        return il_break_value, calculation_factors

    def calculate_di1_break(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку отключающего органа по приращению тока прямой последовательности
        (обеспечение чувствительности).

        Формула: DI_1откл = (I_1^(К(3)))/k_ч
        где:
        - I_1^(К(3)) - ток прямой последовательности, протекающий через рассматриваемый полукомплект
          при трехфазном КЗ на противоположном конце защищаемой ЛЭП (берется минимальный из всех
          подрежимов сети для обеспечения чувствительности во всех режимах)
        - k_ч = 2 - требуемый коэффициент чувствительности
        """
        # Получаем все расчеты трехфазных КЗ для полукомплектов защиты
        fault_calculations = FaultCalculation.objects.filter(
            protection_half_set__in=self.protection_half_sets, fault_type="К(3)"
        )

        pos_sequence_currents = []
        for fault_calculation in fault_calculations:
            pos_sequence_current = fault_calculation.fault_values.get("I1")
            if pos_sequence_current and pos_sequence_current != 0:
                pos_sequence_currents.append(pos_sequence_current)

        if not pos_sequence_currents:
            # Если расчетов нет, возвращаем 0
            return 0.0, {}

        # Берем минимальный ток для обеспечения чувствительности во всех режимах сети
        min_i1 = min(pos_sequence_currents)  # в мА

        # Формула: DI_1откл = (I_1^(К(3)))/k_ч
        # Переводим из мА в А
        di1_break_value = min_i1 / self.current_sensitivity_rate / 1000

        return di1_break_value, {}

    def calculate_di1_block(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку блокирующего органа по приращению тока прямой последовательности
        (согласование с отключающим).

        Формула: DI_1бл ≤ (DI_1откл)/k_согл
        где:
        - DI_1откл - уставка отключающего органа
        - k_согл = 1.4-2.0 - коэффициент согласования (по умолчанию 1.4)

        Примечание: Формула определяет максимальное значение DI_1бл (верхняя граница),
        поэтому используем равенство для расчета конкретного значения уставки.
        """
        di1_break_value, _ = self.calculate_di1_break()
        di1_matching_factor = self.calculation_factors.get(
            "di1_matching_factor", 1.4)

        # Формула: DI_1бл = (DI_1откл)/k_согл
        di1_block_value = di1_break_value / di1_matching_factor

        calculation_factors = {"Коэффициент согласования": di1_matching_factor}
        return di1_block_value, calculation_factors

    def calculate_di2_block(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку блокирующего органа по приращению тока обратной последовательности
        (отстройка от тока небаланса).

        Формула: DI2 БЛОК = k_отс/k_в * I_2нб
        где:
        - I_2нб = k_2нб * I_ДДРТ - ток небаланса обратной последовательности, обусловленный
          погрешностями трансформаторов тока и фильтров токов обратной последовательности
        - k_2нб = 0.05 - коэффициент небаланса по току обратной последовательности
        - I_ДДРТ - длительно допустимый рабочий ток защищаемой ЛЭП (load_current)
        - k_отс = 1.2-1.3 - коэффициент отстройки (по умолчанию 1.3)
        - k_в - коэффициент возврата (принимается по техническим данным защиты,
          зависит от производителя: ЭКРА = 0.9, Релематика/Бреслер = 0.95)
        """
        di2_imbalance_factor = self.calculation_factors.get(
            "di2_imbalance_factor", 0.05
        )
        di2_grading_factor = self.calculation_factors.get(
            "di2_grading_factor", 1.3)

        # Определяем коэффициент возврата в зависимости от производителя
        di2_reset_factor = self._get_reset_factor(default_value=0.9)

        # Ток небаланса обратной последовательности: I_2нб = k_2нб * I_ДДРТ
        i2_imbalance_current = di2_imbalance_factor * self.load_current

        # Формула: DI_2бл = k_отс/k_в * I_2нб
        di2_block_value = di2_grading_factor / di2_reset_factor * i2_imbalance_current

        calculation_factors = {
            "Коэффициент небаланса": di2_imbalance_factor,
            "Коэффициент отстройки": di2_grading_factor,
            "Коэффициент возврата": di2_reset_factor,
        }
        return di2_block_value, calculation_factors

    def calculate_di2_break(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку отключающего органа по приращению тока обратной последовательности
        (согласование с блокирующим).

        Формула: DI2 ОТКЛ = k_согл * I2 БЛОК
        где:
        - I2 БЛОК - уставка блокирующего органа
        - k_согл = 1.4-2.0 - коэффициент согласования (по умолчанию 1.4)
        """
        i2_block_value = self.calculate_i2_block()[0]
        di2_matching_factor = self.calculation_factors.get(
            "di2_matching_factor", 1.4)

        # Формула: DI_2откл = k_согл * I_2бл
        di2_break_value = di2_matching_factor * i2_block_value

        calculation_factors = {
            "Коэффициент согласования": di2_matching_factor,
        }
        return di2_break_value, calculation_factors

    def _get_reset_factor(self, default_value: float = 0.9) -> float:
        """
        Определяет коэффициент возврата в зависимости от производителя устройства защиты.

        Правила:
        - ЭКРА: k_в = 0.9
        - Релематика и Бреслер: k_в = 0.95
        - По умолчанию: используется значение default_value (обычно 0.9, для 3I0 БЛОК может быть 0.95)

        Args:
            default_value: Значение коэффициента возврата по умолчанию (по умолчанию 0.9)

        Returns:
            Коэффициент возврата (float)
        """
        # Пытаемся получить производителя из текущего полукомплекта
        # Если self.current_protection_half_set не установлен, используем значение по умолчанию
        if (
            hasattr(self, "current_protection_half_set")
            and self.current_protection_half_set
        ):
            protection_device = self.current_protection_half_set.protection_device
            if protection_device and protection_device.manufacturer_fk:
                manufacturer_name = protection_device.manufacturer_fk.name

                # Проверяем название производителя
                if manufacturer_name and "ЭКРА" in manufacturer_name.upper():
                    return 0.9
                elif manufacturer_name and (
                    "РЕЛЕМАТИКА" in manufacturer_name.upper()
                    or "БРЕСЛЕР" in manufacturer_name.upper()
                ):
                    return 0.95

        # Значение по умолчанию
        return default_value

    def calculate_i2_block(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку блокирующего органа по току обратной последовательности
        (отстройка от тока небаланса).

        Формула: I_2бл ≥ k_отс/k_в * (I_2нб + I_(2н.р))
        где:
        - I_2нб = k_2нб * I_ДДРТ - ток небаланса обратной последовательности
          k_2нб = 0.05 - коэффициент небаланса по току обратной последовательности
          I_ДДРТ - длительно допустимый рабочий ток защищаемой ЛЭП (load_current)
        - I_(2н.р) - ток обратной последовательности, обусловленный несимметрией
          в системе в нагрузочном режиме (по умолчанию 0 при отсутствии несимметрии)
        - k_отс = 1.2-1.3 - коэффициент отстройки (по умолчанию 1.3)
        - k_в - коэффициент возврата (зависит от производителя: ЭКРА = 0.9, Релематика/Бреслер = 0.95)
        """
        i2_imbalance_factor = self.calculation_factors.get(
            "i2_imbalance_factor", 0.05)
        i2_grading_factor = self.calculation_factors.get(
            "i2_grading_factor", 1.3)
        # Ток обратной последовательности в нагрузочном режиме (по умолчанию 0)
        i2_load_current = self.calculation_factors.get("i2_load_current", 0.0)

        # Определяем коэффициент возврата в зависимости от производителя
        i2_reset_factor = self.calculation_factors.get(
            "i2_reset_factor", self._get_reset_factor(default_value=0.9)
        )

        # Ток небаланса обратной последовательности: I_2нб = k_2нб * I_ДДРТ
        i2_imbalance_current = i2_imbalance_factor * self.load_current

        # Формула: I_2бл = k_отс/k_в * (I_2нб + I_(2н.р))
        i2_block_value = (
            i2_grading_factor
            / i2_reset_factor
            * (i2_imbalance_current + i2_load_current)
        )

        calculation_factors = {
            "Коэффициент небаланса": i2_imbalance_factor,
            "Коэффициент отстройки": i2_grading_factor,
            "Коэффициент возврата": i2_reset_factor,
        }

        if i2_load_current > 0:
            calculation_factors["Ток I_(2н.р)"] = i2_load_current

        return i2_block_value, calculation_factors

    def calculate_i2_break(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку отключающего органа по току обратной последовательности
        (согласование с блокирующим).

        Формула: I_2откл ≥ k_согл * I_2бл
        где:
        - I_2бл - уставка блокирующего органа
        - k_согл = 1.4-2.0 - коэффициент согласования (по умолчанию 1.4)

        Дополнительно учитывается коэффициент ответвлений K_отв = 2 для линий с ответвлениями.
        """
        i2_block_value = self.calculate_i2_block()[0]
        i2_matching_factor = self.calculation_factors.get(
            "i2_matching_factor", 1.4)

        # Формула: I_2откл = k_согл * I_2бл
        i2_break_value = i2_matching_factor * i2_block_value

        # Проверяем наличие ответвлений и применяем коэффициент ответвлений K_отв = 2
        k_otv = 1.0
        has_branches = False
        if self.line:
            # Проверяем наличие активных ответвлений
            if self.line.branch_count and self.line.branch_count > 0:
                has_branches = True
            elif hasattr(self.line, "branches"):
                has_branches = self.line.branches.filter(
                    is_active=True).exists()

        if has_branches:
            k_otv = 2.0
            i2_break_value = i2_break_value * k_otv
            print(
                f"[DEBUG] Для I2 ОТКЛ применен коэффициент ответвления = {k_otv}")

        calculation_factors = {
            "Коэффициент согласования": i2_matching_factor,
        }

        return i2_break_value, calculation_factors

    def calculate_3i0_block(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку блокирующего ИО тока нулевой последовательности.

        Формула: 3I0 БЛОК = K_ОТС * 3I0_НБ_РАСЧ / K_Возвр
        где 3I0_НБ_РАСЧ = k_0нб * I_нагр
        k_0нб - коэффициент небаланса (0.05)
        I_нагр - длительно допустимый рабочий ток по ЛЭП (current_capacity)
        """
        i0_imbalance_factor = self.calculation_factors.get(
            "i0_imbalance_factor", 0.05)
        i0_block_grading_factor = self.calculation_factors.get(
            "i0_block_grading_factor", 1.2
        )
        # Определяем коэффициент возврата в зависимости от производителя (для 3I0 БЛОК по умолчанию 0.95)
        i0_block_reset_factor = self.calculation_factors.get(
            "i0_block_reset_factor", self._get_reset_factor(default_value=0.9)
        )

        # Ток небаланса нулевой последовательности
        i0_imbalance_current = i0_imbalance_factor * self.load_current

        # Уставка блокирующего органа
        i0_block_value = (
            i0_block_grading_factor / i0_block_reset_factor * i0_imbalance_current
        )

        calculation_factors = {
            "Коэффициент небаланса": i0_imbalance_factor,
            "Коэффициент отстройки": i0_block_grading_factor,
            "Коэффициент возврата": i0_block_reset_factor,
        }
        return i0_block_value, calculation_factors

    def calculate_3i0_break(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку отключающего ИО тока нулевой последовательности.

        Формула: 3I0 ОТКЛ = K_ОТС * 3I0_БЛОК
        где:
        - K_ОТС = 1.5-2.0 - коэффициент отстройки (по умолчанию 1.5)
        - 3I0_БЛОК - уставка блокирующего органа
        """
        i0_block_value = self.calculate_3i0_block()[0]
        i0_break_grading_factor = self.calculation_factors.get(
            "i0_break_grading_factor", 1.5
        )

        # Формула: 3I0 ОТКЛ = K_ОТС * 3I0_БЛОК
        i0_break_value = i0_break_grading_factor * i0_block_value

        calculation_factors = {
            "Коэффициент отстройки": i0_break_grading_factor,
        }
        return i0_break_value, calculation_factors

    def calculate_u2_block(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку блокирующего органа по напряжению обратной последовательности
        (отстройка от напряжения небаланса).

        Формула: U_2бл ≥ k_отс/k_в * (U_2нб + U_(2н.р))
        где:
        - U_2нб - напряжение небаланса обратной последовательности, обусловленное
          погрешностями ТН и фильтра напряжения обратной последовательности
          (в расчетах может быть принято значение U_2нб, не превышающее 1,5-2 В фазных вторичных)
        - U_2н.р - напряжение обратной последовательности, обусловленное несимметрией
          в системе в нагрузочном режиме (по умолчанию 0 при отсутствии несимметрии)
        - k_отс = 1.2-1.3 - коэффициент отстройки (по умолчанию 1.3)
        - k_в - коэффициент возврата (принимается по техническим данным защиты,
          зависит от производителя: ЭКРА = 0.9, Релематика/Бреслер = 0.95)
        """
        u2_grading_factor = self.calculation_factors.get(
            "u2_grading_factor", 1.3)
        # Определяем коэффициент возврата в зависимости от производителя
        u2_reset_factor = self.calculation_factors.get(
            "u2_reset_factor", self._get_reset_factor(default_value=0.9)
        )
        # Напряжение небаланса обратной последовательности (1.5-2 В фазных вторичных)
        u2_imbalance_voltage = self.calculation_factors.get(
            "u2_imbalance_voltage", 1.5)
        # Напряжение обратной последовательности в нагрузочном режиме (по умолчанию 0)
        u2_load_voltage = self.calculation_factors.get("u2_load_voltage", 0.0)

        # U_2нб и U_(2н.р) задаются во вторичных вольтах (В)
        # Формула: U_2бл = k_отс/k_в * (U_2нб + U_(2н.р))
        # Результат во вторичных вольтах, переводим в первичные кВ для сохранения в БД
        u2_block_value_secondary = (
            u2_grading_factor
            / u2_reset_factor
            * (u2_imbalance_voltage + u2_load_voltage)
        )

        # Переводим из вторичных вольт в первичные кВ для сохранения в БД
        # В save_result_to_db будет обратное преобразование для secondary_value
        vt_ratio = self.voltage_transformer_factor
        if vt_ratio and vt_ratio > 0:
            u2_block_value = u2_block_value_secondary * vt_ratio / 1000  # в кВ
        else:
            # Если коэффициент трансформации не задан, используем значение по умолчанию
            u2_block_value = u2_block_value_secondary * 5000 / 1000  # в кВ

        calculation_factors = {
            "Коэффициент отстройки": u2_grading_factor,
            "Коэффициент возврата": u2_reset_factor,
            "Напряжение небаланса (В)": u2_imbalance_voltage,
        }

        if u2_load_voltage > 0:
            calculation_factors["Напряжение U_2н.р (В)"] = u2_load_voltage

        return u2_block_value, calculation_factors

    def calculate_u2_break(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку отключающего органа по напряжению обратной последовательности
        (согласование с блокирующим).

        Формула: U_2откл ≥ k_согл * U_2бл
        где:
        - U_2бл - уставка блокирующего органа
        - k_согл = 1.4-2.0 - коэффициент согласования (по умолчанию 1.4)
        """
        u2_block_value = self.calculate_u2_block()[0]
        u2_matching_factor = self.calculation_factors.get(
            "u2_matching_factor", 1.4)

        # Формула: U_2откл = k_согл * U_2бл
        u2_break_value = u2_matching_factor * u2_block_value

        calculation_factors = {"Коэффициент согласования": u2_matching_factor}
        return u2_break_value, calculation_factors

    def calculate_rtnp(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку реле направления мощности нулевой последовательности по току.

        Формула: 3I0_РНМ ≥ k_отс/k_в * (I_0нб + 3I0н.р)
        где:
        - I_0нб = k_0нб * I_нагр (ток небаланса)
        - k_0нб - коэффициент небаланса (0.05)
        - I_нагр - длительно допустимый рабочий ток по ЛЭП (current_capacity)
        - 3I0н.р = 0 (при отсутствии несимметрии)
        - k_отс - коэффициент отстройки (1.25)
        - k_в - коэффициент возврата (0.9)
        """
        rtnp_imbalance_factor = self.calculation_factors.get(
            "rtnp_imbalance_factor", 0.05
        )
        rtnp_grading_factor = self.calculation_factors.get(
            "rtnp_grading_factor", 1.25)
        # Определяем коэффициент возврата в зависимости от производителя
        rtnp_reset_factor = self.calculation_factors.get(
            "rtnp_reset_factor", self._get_reset_factor(default_value=0.9)
        )

        # Ток небаланса нулевой последовательности
        i0_imbalance_current = rtnp_imbalance_factor * self.load_current

        # Утроенный ток нулевой последовательности при несимметрии (значение задается пользователем через calculation_factors)
        i0_asymmetry = self.calculation_factors.get("i0_asymmetry", 0.0)

        # Уставка реле направления мощности
        rtnp_value = (
            rtnp_grading_factor
            / rtnp_reset_factor
            * (i0_imbalance_current + i0_asymmetry)
        )

        calculation_factors = {
            "Коэффициент небаланса": rtnp_imbalance_factor,
            "Коэффициент отстройки": rtnp_grading_factor,
            "Коэффициент возврата": rtnp_reset_factor,
        }
        return rtnp_value, calculation_factors

    def calculate_rnnp(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку реле направления мощности нулевой последовательности по напряжению.

        Формула: 3U0_РНМ ≥ k_отс/k_в * (U_0нб + 3U0н.р)
        где:
        - U_0нб - напряжение небаланса (1.5-2 В вторичных, переводим в первичные через ТН)
        - 3U0н.р = 0 (при отсутствии несимметрии)
        - k_отс - коэффициент отстройки (1.25)
        - k_в - коэффициент возврата (0.9)
        """
        rnnp_grading_factor = self.calculation_factors.get(
            "rnnp_grading_factor", 1.25)
        # Определяем коэффициент возврата в зависимости от производителя
        rnnp_reset_factor = self.calculation_factors.get(
            "rnnp_reset_factor", self._get_reset_factor(default_value=0.9)
        )
        rnnp_imbalance_voltage_secondary = self.calculation_factors.get(
            "rnnp_imbalance_voltage", 1.5
        )  # В вторичных величинах (В)

        # Используем коэффициент трансформации ТН для перевода в первичные величины
        vt_ratio = self.voltage_transformer_factor

        # Напряжение небаланса в первичных величинах (кВ)
        u0_imbalance_primary = (
            rnnp_imbalance_voltage_secondary * vt_ratio) / 1000

        # Утроенное напряжение нулевой последовательности при несимметрии (значение задается пользователем через calculation_factors)
        u0_asymmetry = self.calculation_factors.get("u0_asymmetry", 0.0)

        # Уставка реле направления мощности (в первичных величинах, кВ)
        rnnp_value = (
            rnnp_grading_factor
            / rnnp_reset_factor
            * (u0_imbalance_primary + u0_asymmetry)
        )

        calculation_factors = {
            "Коэффициент отстройки": rnnp_grading_factor,
            "Коэффициент возврата": rnnp_reset_factor,
            "Напряжение небаланса (вторичное, В)": rnnp_imbalance_voltage_secondary,
        }
        return rnnp_value, calculation_factors

    def calculate_r_break(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку по активной составляющей сопротивления.

        Формула: R откл = (Rраб мин − Xраб мин/tan(Фмч))/k надежности

        где:
        - R раб мин = (0,9∙Uном) / (√3 ∙ I раб ∙ cos(Фн - угол нагрузки))
        - X раб мин = (0,9∙Uном) / (√3 ∙ I раб ∙ sin(Фн))
        - Фмч = arctg(X1уд/R1уд) - угол максимальной чувствительности
        - X1уд = X1/L, R1уд = R1/L - удельные сопротивления
        - I раб - максимальный рабочий ток ДДТН (current_capacity)
        - k надежности - коэффициент надежности (1.6)
        """
        r_break_reliability_factor = self.calculation_factors.get(
            "r_break_reliability_factor", 1.6
        )
        load_angle_deg = self.calculation_factors.get("load_angle", 30.0)
        load_angle_rad = radians(load_angle_deg)

        # Получаем параметры линии
        voltage_nom = float(self.line.voltage_level)  # кВ
        current_work = (
            self.load_current
        )  # А (используем значение из формы или из модели)
        length = float(self.line.length)  # км

        # Проверяем наличие сопротивлений
        if not self.line.r1 or not self.line.x1 or length == 0:
            raise ValueError(
                f"Для расчета R ОТКЛ необходимо наличие r1, x1 и длины линии. "
                f"Текущие значения: r1={self.line.r1}, x1={self.line.x1}, length={length}"
            )

        r1 = float(self.line.r1)  # Ом
        x1 = float(self.line.x1)  # Ом

        # Удельные сопротивления (Ом/км)
        r1_specific = r1 / length
        x1_specific = x1 / length

        # Здесь определяется угол максимальной чувствительности защитного органа.
        # Физически это угол arctg(X1уд/R1уд) в радианах и градусах, где X1уд и R1уд — удельные параметры линии.
        # Если r1_specific = 0, угол считается равным 90° (π/2).
        phi_mch_rad = (
            atan(x1_specific / r1_specific) if r1_specific != 0 else radians(90)
        )
        # Здесь просто переводим рассчитанный угол максимальной чувствительности из радиан в градусы.
        phi_mch_deg = degrees(phi_mch_rad)

        # R раб мин = (0,9∙Uном) / (√3 ∙ I раб ∙ cos(Фн - угол нагрузки))
        # Принимаем Фн = 0 (угол нагрузки задается отдельно)
        # Uном в кВ, переводим в В для расчета
        voltage_nom_v = voltage_nom * 1000  # В
        r_work_min = (0.9 * voltage_nom_v) / (
            sqrt(3) * current_work * cos(load_angle_rad)
        )

        # X раб мин = (0,9∙Uном) / (√3 ∙ I раб ∙ sin(Фн))
        # Принимаем Фн = 0, поэтому sin(Фн) = sin(0) = 0
        # Но в формуле указано sin(Фн), возможно имеется в виду sin(угол нагрузки)
        # Используем sin(угол нагрузки) для расчета
        x_work_min = (
            (0.9 * voltage_nom_v) / (sqrt(3) * current_work * sin(load_angle_rad))
            if sin(load_angle_rad) != 0
            else 0
        )

        # R откл = (Rраб мин − Xраб мин/tan(Фмч))/k надежности
        tan_phi_mch = tan(phi_mch_rad) if tan(
            phi_mch_rad) != 0 else float("inf")
        r_break_value = (
            r_work_min - x_work_min / tan_phi_mch
        ) / r_break_reliability_factor

        calculation_factors = {
            "Коэффициент надежности": r_break_reliability_factor,
            "Угол нагрузки, град": load_angle_deg,
            "Угол максимальной чувствительности, град": round(phi_mch_deg, 2),
        }
        return r_break_value, calculation_factors

    def calculate_x_break(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку по реактивной составляющей сопротивления.

        Формула: X откл = max(X откл отв, X откл L уст)

        где:
        - X откл отв = 1,5 ∙ sin(Фмч) ∙ max(UA ост отв/I1 отв)
        - Если L ≥ 150 км: X откл L уст = 1,5 ∙ X1уд ∙ L
        - Если L < 150 км: X откл L уст = 2 ∙ X1уд ∙ L
        - Фмч = arctg(X1уд/R1уд) - угол максимальной чувствительности
        - X1уд = X1/L, R1уд = R1/L - удельные сопротивления
        """
        x_break_branch_factor = self.calculation_factors.get(
            "x_break_branch_factor", 1.5
        )

        # Получаем параметры линии
        length = float(self.line.length)  # км

        # Проверяем наличие сопротивлений
        if not self.line.r1 or not self.line.x1 or length == 0:
            raise ValueError(
                f"Для расчета X ОТКЛ необходимо наличие r1, x1 и длины линии. "
                f"Текущие значения: r1={self.line.r1}, x1={self.line.x1}, length={length}"
            )

        r1 = float(self.line.r1)  # Ом
        x1 = float(self.line.x1)  # Ом

        # Удельные сопротивления (Ом/км)
        r1_specific = r1 / length
        x1_specific = x1 / length

        # Угол максимальной чувствительности (в радианах)
        phi_mch_rad = (
            atan(x1_specific / r1_specific) if r1_specific != 0 else radians(90)
        )
        phi_mch_deg = degrees(phi_mch_rad)

        # Расчет X откл L уст по длине линии
        if length >= 150:
            x_break_length = 1.5 * x1_specific * length
        else:
            x_break_length = 2.0 * x1_specific * length

        # Расчет X откл отв по ответвлениям
        # ВАЖНО: Расчет КЗ на подстанциях ответвлений еще не реализован.
        # Текущие расчеты КЗ выполняются только на противоположной стороне полукомплекта.
        # Поэтому X откл отв будет равен 0, и используется только X откл L уст.
        # TODO: Реализовать расчет КЗ на подстанциях ответвлений для корректного расчета X откл отв
        x_break_branch = 0.0

        # Проверяем наличие ответвлений у линии
        has_branches = self.line.branches.filter(is_active=True).exists()

        if has_branches:
            # Ищем расчеты КЗ на подстанциях ответвлений
            # КЗ на ответвлениях помечаются в fault_location как "Ответвление: <название ПС>"
            try:
                # Получаем расчеты КЗ для трехфазного КЗ на ответвлениях
                fault_calculations = FaultCalculation.objects.filter(
                    protection_half_set__in=self.protection_half_sets,
                    fault_type="К(3)",
                    calculation_meta=self.calculation_meta,
                    fault_location__startswith="Ответвление:",
                )

                # Ищем максимальное значение UA ост отв/I1 отв
                # UA ост отв - остаточное напряжение прямой последовательности при трехфазном КЗ
                # на подстанции ответвления
                max_ua_i1_ratio = 0.0

                for fault_calc in fault_calculations:
                    fault_values = fault_calc.fault_values
                    # А - ток прямой последовательности
                    i1 = fault_values.get("I1", 0)

                    if i1 == 0:
                        continue

                    # Используем остаточное напряжение прямой последовательности (U1)
                    u1_residual = fault_values.get(
                        "U1", 0
                    )  # В - остаточное напряжение прямой последовательности

                    if u1_residual > 0 and i1 > 0:
                        ua_i1_ratio = u1_residual / i1
                        max_ua_i1_ratio = max(max_ua_i1_ratio, ua_i1_ratio)

                if max_ua_i1_ratio > 0:
                    x_break_branch = (
                        x_break_branch_factor *
                        sin(phi_mch_rad) * max_ua_i1_ratio
                    )
            except Exception:
                # Если не удалось получить данные, используем только расчет по длине
                pass

        # Выбираем максимальное значение
        x_break_value = max(x_break_length, x_break_branch)

        calculation_factors = {
            "Коэффициент для расчета по ответвлениям": x_break_branch_factor,
            "Угол максимальной чувствительности, град": round(phi_mch_deg, 2),
            "X откл по длине линии, Ом": round(x_break_length, 2),
            "X откл по ответвлениям, Ом": round(x_break_branch, 2),
        }
        return x_break_value, calculation_factors

    def calculate_r_otv(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку реле сопротивления по активной составляющей.

        Формула: R ОТВ = R ОТКЛ
        """
        # Просто берем значение из R ОТКЛ
        r_break_value, _ = self.calculate_r_break()

        # Не добавляем примечание в calculation_factors
        return r_break_value, {}

    def calculate_x_otv(self) -> Tuple[float, Dict[str, float]]:
        """
        Рассчитывает уставку по реактивной составляющей сопротивления для ответвлений.

        Формула: X ОТВ = min(Xотв КЗ уст, Xтр БНТ уст)

        где:
        - Xотв КЗ уст - отстройка от КЗ за трансформаторами ответвления (TODO: реализовать позже)
        - Xтр БНТ уст - отстройка от броска намагничивающего тока

        Xтр БНТ уст = Cb ∙ (X_(тр экв)^((1)) + Xс) − Xс

        где:
        - Cb - коэффициент броска (зависит от напряжения и типа стали)
        - X_(тр экв)^((1)) - эквивалентное сопротивление трансформатора
        - Xс - сопротивление системы
        """
        # Получаем параметры линии
        length = float(self.line.length)  # км
        voltage_nom = float(self.line.voltage_level)  # кВ

        # Проверяем наличие сопротивлений
        if not self.line.r1 or not self.line.x1 or length == 0:
            raise ValueError(
                f"Для расчета X ОТВ необходимо наличие r1, x1 и длины линии. "
                f"Текущие значения: r1={self.line.r1}, x1={self.line.x1}, length={length}"
            )

        x1 = float(self.line.x1)  # Ом
        x1_specific = x1 / length  # Ом/км

        # Получаем максимальный ток трехфазного КЗ (I3) в кА
        max_i3_ka = 0.0
        try:
            fault_calculations = FaultCalculation.objects.filter(
                protection_half_set__in=self.protection_half_sets,
                fault_type="К(3)",
                calculation_meta=self.calculation_meta,
            )

            for fault_calc in fault_calculations:
                i1 = fault_calc.fault_values.get("I1", 0)  # А
                i1_ka = i1 / 1000  # кА
                max_i3_ka = max(max_i3_ka, i1_ka)
        except Exception:
            # Если не удалось получить данные, используем значение по умолчанию
            pass

        if max_i3_ka == 0:
            # Если не нашли ток КЗ, используем приблизительное значение
            # Можно использовать ток нагрузки как базу
            max_i3_ka = self.load_current / 1000 * 10  # Приблизительно

        # Рассчитываем сопротивление системы Xс
        # Xс = (Uном - (X1уд ∙ L) ∙ I3) / I3
        # Переписываем: Xс = Uном / I3 - X1уд ∙ L
        x_system = (
            (voltage_nom / max_i3_ka - x1_specific * length) if max_i3_ka > 0 else 0
        )

        # Получаем все активные ответвления
        branches = self.line.branches.filter(is_active=True)

        # Xотв КЗ уст - пока не реализовано, используем большое значение
        x_otv_kz = float("inf")

        # Xтр БНТ уст - рассчитываем для каждого ответвления и выбираем минимальное
        x_tr_bnt_values = []

        for branch in branches:
            try:
                # Получаем данные о трансформаторах на ответвлении
                # TODO: Реализовать получение данных из PowerFactory
                # Пока используем метод-заглушку, который можно будет заменить
                transformer_data = self._get_branch_transformer_data(branch)

                if not transformer_data:
                    # Если нет данных о трансформаторах, пропускаем ответвление
                    continue

                # Рассчитываем Xтр БНТ уст для этого ответвления
                x_tr_bnt = self._calculate_x_tr_bnt(
                    transformer_data, x1_specific, length, voltage_nom, x_system
                )

                if x_tr_bnt is not None:
                    x_tr_bnt_values.append(x_tr_bnt)

            except Exception as e:
                # Если ошибка при расчете для ответвления, пропускаем
                # Логируем ошибку, но продолжаем для других ответвлений
                print(
                    f"Ошибка при расчете Xтр БНТ уст для ответвления {branch}: {e}")
                continue

        # Если не удалось рассчитать Xтр БНТ уст для ответвлений,
        # используем только Xотв КЗ уст (который пока не реализован)
        if not x_tr_bnt_values:
            # Если нет данных для расчета, используем значение по умолчанию
            # или можно использовать X ОТКЛ как приближение
            x_otv_value = (
                self.calculate_x_break()[0] * 0.85
            )  # Используем коэффициент надежности
            calculation_factors = {
                "Коэффициент надежности": 0.85,
                "Примечание": "Расчет выполнен без учета трансформаторов ответвлений (данные недоступны)",
            }
            return x_otv_value, calculation_factors

        # Выбираем минимальное значение Xтр БНТ уст
        x_tr_bnt_min = min(x_tr_bnt_values)

        # X ОТВ = min(Xотв КЗ уст, Xтр БНТ уст)
        x_otv_value = min(x_otv_kz, x_tr_bnt_min)

        calculation_factors = {
            "Xс (сопротивление системы), Ом": round(x_system, 2),
            "Максимальный ток КЗ (I3), кА": round(max_i3_ka, 2),
            "Xтр БНТ уст, Ом": round(x_tr_bnt_min, 2) if x_tr_bnt_values else None,
            "Примечание": "Xотв КЗ уст не реализован, используется только Xтр БНТ уст"
            if x_otv_kz == float("inf")
            else "Использовано минимальное значение",
        }
        return x_otv_value, calculation_factors

    def _get_branch_transformer_data(self, branch):
        """
        Получает данные о трансформаторах на подстанции ответвления.

        TODO: Реализовать получение данных из PowerFactory.
        Должен возвращать список словарей с параметрами трансформаторов:
        {
            'power_mva': float,  # Номинальная мощность, МВА
            'uk_percent': float,  # Напряжение КЗ, %
            'voltage_nom_kv': float,  # Номинальное напряжение, кВ
            'rpn_range_kv': float,  # Диапазон РПН, кВ
            'is_autotransformer': bool,  # Является ли автотрансформатором
            'steel_type': str,  # 'cold' или 'hot' (холоднокатаная/горячекатаная)
            'branch_length_km': float,  # Длина ответвления, км
            'distance_to_first_branch_km': float,  # Расстояние от первого ответвления до ПС, км
        }

        Args:
            branch: Объект LineBranch

        Returns:
            Список словарей с данными о трансформаторах или None
        """
        # TODO: Реализовать получение данных из PowerFactory
        # Пока возвращаем None, что означает отсутствие данных
        return None

    def _calculate_x_tr_bnt(
        self, transformer_data_list, x1_specific, line_length, voltage_nom, x_system
    ):
        """
        Рассчитывает Xтр БНТ уст для трансформаторов на ответвлении.

        Формула: Xтр БНТ уст = Cb ∙ (X_(тр экв)^((1)) + Xс) − Xс

        Args:
            transformer_data_list: Список данных о трансформаторах
            x1_specific: Удельное реактивное сопротивление ВЛ, Ом/км
            line_length: Длина основной линии, км
            voltage_nom: Номинальное напряжение линии, кВ
            x_system: Сопротивление системы, Ом

        Returns:
            Значение Xтр БНТ уст в Ом или None
        """
        if not transformer_data_list:
            return None

        # Для одного ответвления с одним трансформатором:
        # X_(тр экв)^((1)) = (X_(тр отв)^((1)) + X1уд ∙ Lотв-тр) + X1уд ∙ Lотв1-пст1

        # Пока берем первый трансформатор (для упрощения)
        # TODO: Реализовать расчет для нескольких трансформаторов параллельно
        transformer = transformer_data_list[0]

        # Рассчитываем X_(тр отв)^((1))
        x_tr_otv = self._calculate_x_tr_otv(transformer)

        if x_tr_otv is None:
            return None

        # Получаем длины
        branch_length = transformer.get("branch_length_km", 0)
        distance_to_first_branch = transformer.get(
            "distance_to_first_branch_km", 0)

        # X_(тр экв)^((1)) = (X_(тр отв)^((1)) + X1уд ∙ Lотв-тр) + X1уд ∙ Lотв1-пст1
        x_tr_equiv = (
            x_tr_otv + x1_specific * branch_length
        ) + x1_specific * distance_to_first_branch

        # Определяем коэффициент броска Cb
        cb = self._get_surge_coefficient(
            voltage_nom, transformer.get("steel_type", "cold")
        )

        if cb is None:
            return None

        # Xтр БНТ уст = Cb ∙ (X_(тр экв)^((1)) + Xс) − Xс
        x_tr_bnt = cb * (x_tr_equiv + x_system) - x_system

        return x_tr_bnt

    def _calculate_x_tr_otv(self, transformer):
        """
        Рассчитывает сопротивление трансформатора ответвления при КЗ(1).

        Формула: X_(тр отв)^((1)) = Xтр %^(1) ∙ (Uном тр отв - UРПН тр отв)^2 / (100 ∙ Sном тр отв)

        где Xтр %^(1) = (A + Uкз тр отв) / B

        Args:
            transformer: Словарь с данными о трансформаторе

        Returns:
            Значение X_(тр отв)^((1)) в Ом или None
        """
        power_mva = transformer.get("power_mva")
        uk_percent = transformer.get("uk_percent")
        voltage_nom_kv = transformer.get("voltage_nom_kv")
        rpn_range_kv = transformer.get("rpn_range_kv", 0)
        is_autotransformer = transformer.get("is_autotransformer", False)

        if not all([power_mva, uk_percent, voltage_nom_kv]):
            return None

        # Определяем коэффициенты A и B
        if is_autotransformer:
            # Для автотрансформатора
            if power_mva <= 125:
                a = 25.7
                b = 1.3
            else:
                a = 35.0
                b = 1.28
        else:
            # Для трансформатора
            if power_mva <= 60:
                a = 12.7
                b = 1.35
            else:
                a = 21.4
                b = 1.35

        # Xтр %^(1) = (A + Uкз тр отв) / B
        x_tr_percent = (a + uk_percent) / b

        # X_(тр отв)^((1)) = Xтр %^(1) ∙ (Uном тр отв - UРПН тр отв)^2 / (100 ∙ Sном тр отв)
        voltage_diff = voltage_nom_kv - rpn_range_kv
        x_tr_otv = (x_tr_percent * (voltage_diff**2)) / (100 * power_mva)

        return x_tr_otv

    def _get_surge_coefficient(self, voltage_nom, steel_type="cold"):
        """
        Определяет коэффициент броска Cb в зависимости от напряжения и типа стали.

        Args:
            voltage_nom: Номинальное напряжение линии, кВ
            steel_type: Тип стали ('cold' - холоднокатаная, 'hot' - горячекатаная)

        Returns:
            Коэффициент броска Cb или None
        """
        voltage_nom_float = float(voltage_nom)

        if voltage_nom_float == 110:
            if steel_type == "cold":
                return 1.75
            elif steel_type == "hot":
                return 2.65
        elif voltage_nom_float == 220:
            if steel_type == "cold":
                return 1.55
            elif steel_type == "hot":
                return 2.5

        # Для других напряжений возвращаем значение по умолчанию
        return 1.75 if steel_type == "cold" else 2.65

    def run(self) -> None:
        print(f"[DEBUG] SettingsCalculationService.run() начат")
        print(
            f"[DEBUG] Количество полукомплектов: {self.protection_half_sets.count()}")
        print(f"[DEBUG] calculation_factors: {self.calculation_factors}")

        # Специальная обработка для коэффициента манипуляции:
        # Сначала собираем все рассчитанные значения для всех полукомплектов,
        # затем выбираем максимальное, округляем и применяем одинаковое значение для всех
        manipulation_factor_values = []
        manipulation_factor_components = (
            []
        )  # Список (protection_half_set, component) для K МАН

        total_saved = 0
        for protection_half_set in self.protection_half_sets:
            # Сохраняем текущий полукомплект для доступа в функциях расчета
            self.current_protection_half_set = protection_half_set

            protection_device = protection_half_set.protection_device
            print(f"[DEBUG] Полукомплект: {protection_half_set}")
            print(
                f"[DEBUG] Устройство защиты: {protection_device} (ID: {protection_device.id})"
            )

            components = protection_device.components.all()
            print(
                f"[DEBUG] Компонентов у устройства '{protection_device}': {components.count()}"
            )

            if components.count() == 0:
                print(
                    f"[WARNING] У устройства защиты '{protection_device}' нет связанных компонентов!"
                )
                print(
                    f"[WARNING] Необходимо добавить компоненты к устройству защиты через админ-панель Django или команду управления."
                )
                # Продолжаем для следующего полукомплекта
                continue

            for component in components:
                # Пропускаем необязательные органы, если они отключены
                # Необязательные органы: U2 БЛОК, U2 ОТКЛ, 3I0 БЛОК, 3I0 ОТКЛ, DI1 БЛОК, DI1 ОТКЛ, DI2 БЛОК, DI2 ОТКЛ
                organ_name = component.setting_designation
                toggleable_organs = [
                    "U2 БЛОК",
                    "U2 ОТКЛ",
                    "3I0 БЛОК",
                    "3I0 ОТКЛ",
                    "DI1 БЛОК",
                    "DI1 ОТКЛ",
                    "DI2 БЛОК",
                    "DI2 ОТКЛ",
                ]
                if organ_name in toggleable_organs:
                    # Проверяем, включен ли орган
                    # Для 3I0 органов на ЛЭП с ответвлениями по умолчанию True, иначе False
                    if organ_name in ["3I0 БЛОК", "3I0 ОТКЛ"]:
                        # Проверяем, есть ли у линии ответвления
                        has_branches = self.line.branches.filter(
                            is_active=True
                        ).exists()
                        if has_branches:
                            # На ЛЭП с ответвлениями 3I0 важен, по умолчанию включен
                            is_enabled = self.enabled_organs.get(
                                organ_name, True)
                        else:
                            # На ЛЭП без ответвлений по умолчанию выключен
                            is_enabled = self.enabled_organs.get(
                                organ_name, False)
                    else:
                        # Для остальных органов по умолчанию False
                        is_enabled = self.enabled_organs.get(organ_name, False)

                    if not is_enabled:
                        print(
                            f"[DEBUG] Орган {organ_name} отключен, пропускаем расчет")
                        continue

                calculation_function = self.get_calculation_function(component)

                if calculation_function:
                    try:
                        # Для коэффициента манипуляции собираем значения, но не сохраняем сразу
                        if component.setting_designation in ["K МАН", "К МАН"]:
                            result, factors = calculation_function()
                            manipulation_factor_values.append(result)
                            manipulation_factor_components.append(
                                (protection_half_set, component, factors)
                            )
                            print(
                                f"[DEBUG] Собрано значение K МАН для {component.setting_designation}: {result}"
                            )
                        else:
                            result, factors = calculation_function()
                            result = round(result, 0)
                            self.save_result_to_db(
                                protection_half_set=protection_half_set,
                                component=component,
                                calculation_factors=factors,
                                result_value=result,
                            )
                            total_saved += 1
                            print(
                                f"[DEBUG] Сохранен результат для {component.setting_designation}: {result}"
                            )
                    except Exception as e:
                        print(
                            f"[ERROR] Ошибка при расчете для {component.setting_designation}: {e}"
                        )
                        import traceback

                        print(f"[ERROR] Traceback: {traceback.format_exc()}")
                else:
                    print(
                        f"[WARNING] Отсутствует расчетный модуль для органа {component.setting_designation}"
                    )

        # Обрабатываем коэффициент манипуляции: выбираем максимальное значение и округляем
        if manipulation_factor_values:
            max_manipulation_factor = max(manipulation_factor_values)

            # Округляем до стандартных значений:
            # Если K ≤ 6, то K = 6
            # Если 6 < K ≤ 8, то K = 8
            # Если 8 < K ≤ 10, то K = 10
            # Если K > 10, то K = 10 (максимальное значение)
            if max_manipulation_factor <= 6:
                final_manipulation_factor = 6.0
            elif max_manipulation_factor <= 8:
                final_manipulation_factor = 8.0
            elif max_manipulation_factor <= 10:
                final_manipulation_factor = 10.0
            else:
                # Если коэффициент больше 10, приравниваем к 10
                final_manipulation_factor = 10.0

            print(
                f"[DEBUG] Максимальное значение K МАН: {max_manipulation_factor}, округлено до: {final_manipulation_factor}"
            )

            # Применяем одинаковое значение для всех полукомплектов
            for (
                protection_half_set,
                component,
                factors,
            ) in manipulation_factor_components:
                # Обновляем factors с информацией о рассчитанном и округленном значении
                updated_factors = factors.copy()
                updated_factors["Рассчитанное значение"] = max_manipulation_factor
                updated_factors["Округленное значение"] = final_manipulation_factor

                result = round(final_manipulation_factor, 0)
                self.save_result_to_db(
                    protection_half_set=protection_half_set,
                    component=component,
                    calculation_factors=updated_factors,
                    result_value=result,
                )
                total_saved += 1
                print(
                    f"[DEBUG] Сохранен результат K МАН для {component.setting_designation}: {result} (одинаковое для всех полукомплектов)"
                )

        # Очищаем текущий полукомплект после завершения
        if hasattr(self, "current_protection_half_set"):
            delattr(self, "current_protection_half_set")

        print(f"[DEBUG] Всего сохранено результатов: {total_saved}")

        # Проверяем, сколько должно быть результатов
        expected_results = 0
        for protection_half_set in self.protection_half_sets:
            protection_device = protection_half_set.protection_device
            components = protection_device.components.all()
            for component in components:
                organ_name = component.setting_designation
                # Проверяем, должен ли орган быть рассчитан
                if organ_name in ["K МАН", "К МАН"]:
                    # K МАН обрабатывается отдельно
                    continue
                toggleable_organs = [
                    "U2 БЛОК",
                    "U2 ОТКЛ",
                    "3I0 БЛОК",
                    "3I0 ОТКЛ",
                    "DI1 БЛОК",
                    "DI1 ОТКЛ",
                    "DI2 БЛОК",
                    "DI2 ОТКЛ",
                ]
                if organ_name in toggleable_organs:
                    if organ_name in ["3I0 БЛОК", "3I0 ОТКЛ"]:
                        has_branches = self.line.branches.filter(
                            is_active=True
                        ).exists()
                        is_enabled = self.enabled_organs.get(
                            organ_name, True if has_branches else False
                        )
                    else:
                        is_enabled = self.enabled_organs.get(organ_name, False)
                    if not is_enabled:
                        continue
                expected_results += 1

        # Добавляем K МАН (по одному на полукомплект)
        k_man_count = sum(
            1
            for hs in self.protection_half_sets
            for comp in hs.protection_device.components.all()
            if comp.setting_designation in ["K МАН", "К МАН"]
        )
        if k_man_count > 0:
            expected_results += len(
                self.protection_half_sets
            )  # K МАН сохраняется для каждого полукомплекта

        print(
            f"[DEBUG] Ожидалось результатов: {expected_results}, фактически сохранено: {total_saved}"
        )
        if expected_results != total_saved:
            print(
                f"[WARNING] Несоответствие: ожидалось {expected_results} результатов, сохранено {total_saved}"
            )
