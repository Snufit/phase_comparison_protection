from math import sqrt, cos, atan, radians, degrees
from typing import Callable, Dict, List, Optional, Union

from django.db.models import QuerySet

from calculation.models import (CalculationMeta, FaultCalculation,
                                SensitivityAnalysis, SettingsCalculation)
from calculation.services.sensitivity_fault_map import SensitivityFaultMap
from core.models import Component


class SensitivityAnalysisService:
    """Сервис анализа чувствительности."""

    def __init__(self, calculation_meta: CalculationMeta) -> None:
        self.calculation_meta: CalculationMeta = calculation_meta
        self.settings_calculations: QuerySet[SettingsCalculation] = (
            SettingsCalculation.objects.filter(
                calculation_meta=self.calculation_meta
            )
        )

        # Используем карту КЗ для получения обработчиков чувствительности
        # Обработчики создаются динамически на основе карты КЗ
        self.SENSITIVITY_HANDLERS: Dict[
            str, Dict[str, Union[Callable, List[str], str, float]]
        ] = self._build_sensitivity_handlers()
    
    def _build_sensitivity_handlers(self) -> Dict:
        """
        Строит словарь обработчиков чувствительности на основе карты КЗ.
        
        Returns:
            Словарь обработчиков чувствительности
        """
        handlers = {}
        
        # Маппинг типов fault_value на функции расчета
        function_map = {
            "I1": self._calculate_current_sensitivity,
            "I2": self._calculate_current_sensitivity,
            "U2": self._calculate_current_sensitivity,
            "3I0": self._calculate_3i0_sensitivity,
            "R": self._calculate_r_sensitivity,
            "RNM_I0": self._calculate_rnm_sensitivity,
            "RNM_U0": self._calculate_rnm_sensitivity,
        }
        
        # Специальные функции для органов с особыми формулами
        special_functions = {
            "IЛ ОТКЛ": self._calculate_phase_current_diff_sensitivity,
            "DI2 ОТКЛ": self._calculate_di2_sensitivity,
            "K МАН": self._calculate_manipulation_sensitivity,
            "К МАН": self._calculate_manipulation_sensitivity,
        }
        
        # Получаем все органы из карты КЗ
        for organ_name, fault_map in SensitivityFaultMap.SENSITIVITY_FAULT_MAP.items():
            # Пропускаем органы, для которых не нужно проверять чувствительность
            if not fault_map.get("check_sensitivity", True):
                continue
            
            # Пропускаем органы без типов КЗ
            if not fault_map.get("fault_types"):
                continue
            
            fault_value = fault_map.get("fault_value")
            if not fault_value:
                continue
            
            # Определяем функцию расчета
            if organ_name in special_functions:
                function = special_functions[organ_name]
            elif fault_value in function_map:
                function = function_map[fault_value]
            else:
                # Если функция не найдена, используем стандартную
                function = self._calculate_current_sensitivity
            
            handlers[organ_name] = {
                "function": function,
                "fault_types": fault_map.get("fault_types", []),
                "fault_value": fault_value,
                "k_sx": fault_map.get("k_sx", 1.0),
                "use_min_value": fault_map.get("use_min_value", False),
                "exclude_branches": fault_map.get("exclude_branches", True),
                "requires_branches": fault_map.get("requires_branches", False),
        }
        
        return handlers

    def run(self) -> None:
        for settings_calculation in self.settings_calculations:
            component = settings_calculation.component
            protection_half_set = settings_calculation.protection_half_set
            result_value = settings_calculation.result_value
            handler = self._get_handler(component)

            if handler:
                sensitivity_analysis_function = handler["function"]
                fault_types = handler["fault_types"]
                target_fault_value = handler["fault_value"]
                fault_calculations: QuerySet[FaultCalculation] = (
                    FaultCalculation.objects.filter(
                        calculation_meta=self.calculation_meta,
                        protection_half_set=protection_half_set,
                        fault_type__in=fault_types,
                    )
                )

                # Получаем дополнительные параметры из карты КЗ
                use_min_value = handler.get("use_min_value", False)
                exclude_branches = handler.get("exclude_branches", True)
                requires_branches = handler.get("requires_branches", False)
                k_sx = handler.get("k_sx", 1.0)
                
                # Проверяем требование наличия ответвлений
                if requires_branches:
                    line = self.calculation_meta.line
                    if not line or not line.branches.filter(is_active=True).exists():
                        print(f"[DEBUG] Пропущен расчет чувствительности для {component.setting_designation}: "
                              f"требуются ответвления, но их нет")
                        continue
                
                # Фильтруем КЗ по месту выполнения
                if exclude_branches:
                    fault_calculations = fault_calculations.exclude(
                        fault_location__startswith="Ответвление:"
                    )
                else:
                    # Для органов, которым нужны только ответвления
                    if requires_branches:
                        fault_calculations = fault_calculations.filter(
                            fault_location__startswith="Ответвление:"
                        )
                
                # Специальная обработка для R ОТКЛ и R ОТВ
                if target_fault_value == "R":
                    # Для R чувствительности нужна специальная логика
                    try:
                        sensitivity_rate = sensitivity_analysis_function(
                            settings_calculation, protection_half_set
                        )
                        if sensitivity_rate is not None:
                            # Создаем запись для каждого КЗ на ответвлениях
                            branch_faults = fault_calculations.filter(
                                fault_location__startswith="Ответвление:"
                            )
                            for fault_calculation in branch_faults:
                                self._save_result_to_db(
                                    settings_calculation=settings_calculation,
                                    fault_calculation=fault_calculation,
                                    sensitivity_rate=sensitivity_rate,
                                )
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        print(f"[ERROR] Ошибка при расчете чувствительности R для {component.setting_designation}: {e}")
                        continue
                # Специальная обработка для 3I0 ОТКЛ
                elif target_fault_value == "3I0":
                    # Для 3I0 ОТКЛ нужна специальная логика - находим минимальное значение
                    try:
                        sensitivity_rate = sensitivity_analysis_function(
                            settings_calculation, protection_half_set, fault_calculations
                        )
                        if sensitivity_rate is not None:
                            # Создаем запись для каждого КЗ на землю
                            for fault_calculation in fault_calculations:
                                self._save_result_to_db(
                                    settings_calculation=settings_calculation,
                                    fault_calculation=fault_calculation,
                                    sensitivity_rate=sensitivity_rate,
                                )
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        print(f"[ERROR] Ошибка при расчете чувствительности 3I0 ОТКЛ для {component.setting_designation}: {e}")
                        continue
                # Специальная обработка для РНМ (РТНП/3I0_M0 и РННП/3U0_M0)
                elif target_fault_value in ["RNM_I0", "RNM_U0"]:
                    # Для РНМ чувствительности нужна специальная логика
                    try:
                        sensitivity_rate = sensitivity_analysis_function(
                            settings_calculation, protection_half_set, target_fault_value
                        )
                        if sensitivity_rate is not None:
                            # Создаем запись для каждого КЗ на землю на ответвлениях
                            branch_faults = fault_calculations.filter(
                                fault_location__startswith="Ответвление:"
                            )
                            for fault_calculation in branch_faults:
                                self._save_result_to_db(
                                    settings_calculation=settings_calculation,
                                    fault_calculation=fault_calculation,
                                    sensitivity_rate=sensitivity_rate,
                                )
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        print(f"[ERROR] Ошибка при расчете чувствительности РНМ для {component.setting_designation}: {e}")
                        continue
                else:
                    # Обычная обработка для других органов
                    # Если нужно использовать минимальное значение, находим его
                    if use_min_value:
                        min_fault_value = None
                        min_fault_calculation = None
                        
                        for fault_calculation in fault_calculations:
                            fault_value = fault_calculation.fault_values.get(target_fault_value)
                            if fault_value and (min_fault_value is None or fault_value < min_fault_value):
                                min_fault_value = fault_value
                                min_fault_calculation = fault_calculation
                        
                        if min_fault_calculation and min_fault_value:
                            try:
                                # Для IЛ ОТКЛ используем k_sx
                                if component.setting_designation == "IЛ ОТКЛ":
                                    sensitivity_rate = sensitivity_analysis_function(
                                        result_value, min_fault_value, k_sx
                                    )
                                # Для DI2 ОТКЛ используем i2_nr из карты КЗ
                                elif component.setting_designation == "DI2 ОТКЛ":
                                    fault_map = SensitivityFaultMap.get_fault_map("DI2 ОТКЛ")
                                    i2_nr = fault_map.get("i2_nr", 0.0) if fault_map else 0.0
                                    sensitivity_rate = sensitivity_analysis_function(
                                        result_value, min_fault_value, i2_nr
                                    )
                                # Для K МАН используем специальную формулу с I2 БЛОК
                                elif component.setting_designation in ["K МАН", "К МАН"]:
                                    # Переводим I1 из мА в А
                                    min_i1_k3_a = float(min_fault_value) / 1000 if min_fault_value else 0.0
                                    sensitivity_rate = sensitivity_analysis_function(
                                        settings_calculation, protection_half_set, min_i1_k3_a
                                    )
                                else:
                                    sensitivity_rate = sensitivity_analysis_function(
                                        result_value, min_fault_value
                                    )
                                sensitivity_rate = round(sensitivity_rate, 2)
                                self._save_result_to_db(
                                    settings_calculation=settings_calculation,
                                    fault_calculation=min_fault_calculation,
                                    sensitivity_rate=sensitivity_rate,
                                )
                            except (ZeroDivisionError, ValueError, TypeError) as e:
                                print(f"[ERROR] Ошибка при расчете чувствительности для {component.setting_designation}: {e}")
                    else:
                        # Обрабатываем все КЗ
                        for fault_calculation in fault_calculations:
                            fault_value = fault_calculation.fault_values.get(target_fault_value)
                            
                            # Пропускаем, если нет значения уставки или значения КЗ
                            if result_value is None or result_value == 0:
                                print(f"[WARNING] Пропущен расчет чувствительности для {component.setting_designation}: "
                                      f"result_value={result_value}")
                                continue
                            
                            if fault_value is None or fault_value == 0:
                                print(f"[WARNING] Пропущен расчет чувствительности для {component.setting_designation}: "
                                      f"fault_value={fault_value}")
                                continue
                            
                            try:
                                # Для IЛ ОТКЛ используем k_sx
                                if component.setting_designation == "IЛ ОТКЛ":
                                    sensitivity_rate = sensitivity_analysis_function(
                                        result_value, fault_value, k_sx
                                    )
                                # Для DI2 ОТКЛ используем i2_nr из карты КЗ
                                elif component.setting_designation == "DI2 ОТКЛ":
                                    fault_map = SensitivityFaultMap.get_fault_map("DI2 ОТКЛ")
                                    i2_nr = fault_map.get("i2_nr", 0.0) if fault_map else 0.0
                                    sensitivity_rate = sensitivity_analysis_function(
                                        result_value, fault_value, i2_nr
                                    )
                                # Для K МАН используем специальную формулу с I2 БЛОК
                                elif component.setting_designation in ["K МАН", "К МАН"]:
                                    # Переводим I1 из мА в А
                                    i1_k3_a = float(fault_value) / 1000 if fault_value else 0.0
                                    sensitivity_rate = sensitivity_analysis_function(
                                        settings_calculation, protection_half_set, i1_k3_a
                                    )
                                else:
                                    sensitivity_rate = sensitivity_analysis_function(
                                        result_value, fault_value
                                    )
                                sensitivity_rate = round(sensitivity_rate, 2)
                                self._save_result_to_db(
                                    settings_calculation=settings_calculation,
                                    fault_calculation=fault_calculation,
                                    sensitivity_rate=sensitivity_rate,
                                )
                            except (ZeroDivisionError, ValueError, TypeError) as e:
                                print(f"[ERROR] Ошибка при расчете чувствительности для {component.setting_designation}: {e}")
                                continue

    def _get_handler(
        self, component: Component
    ) -> Optional[Dict[str, Union[Callable[[float, float], float], List[str], str]]]:
        """
        Метод получения данных для анализа чувствительности.

        :param component: Объект класса Component.
        :return: Словарь с данными для анализа чувствительности.
        """
        handler = self.SENSITIVITY_HANDLERS.get(component.setting_designation)
        return handler

    @staticmethod
    def _save_result_to_db(
        settings_calculation: SettingsCalculation,
        fault_calculation: FaultCalculation,
        sensitivity_rate: float,
    ) -> None:
        """
        Метод сохранения результатов анализа чувствительности в базу данных.

        :param settings_calculation: Объект класса SettingsCalculation.
        :param fault_calculation: Объект класса FaultCalculation.
        :param sensitivity_rate: Коэффициент чувствительности.
        :return: None.
        """

        SensitivityAnalysis.objects.create(
            settings_calculation=settings_calculation,
            fault_calculation=fault_calculation,
            sensitivity_rate=sensitivity_rate,
        )

    @staticmethod
    def _calculate_phase_current_diff_sensitivity(
        result_value: float, fault_value: float, k_sx: float = sqrt(3)
    ) -> float:
        """
        Рассчитывает чувствительность для органов с пуском по векторной разности фазных токов.
        
        Формула: k_ч = (k_сх * I_1^(К(3))) / IЛ ОТКЛ
        
        :param result_value: Величина уставки.
        :param fault_value: Величина тока КЗ.
        :param k_sx: Коэффициент схемы (по умолчанию √3 для векторной разности).
        :return: Коэффициент чувствительности.
        """
        # Проверка на деление на ноль
        if result_value == 0 or result_value is None:
            return 0.0

        sensitivity_rate = k_sx * fault_value / result_value
        return sensitivity_rate

    @staticmethod
    def _calculate_current_sensitivity(
        result_value: float, fault_value: float
    ) -> float:
        """
        Рассчитывает чувствительность для токовых и напряженческих органов.
        
        :param result_value: Величина уставки.
        :param fault_value: Величина тока/напряжения КЗ.
        :return: Коэффициент чувствительности.
        """
        # Проверка на деление на ноль
        if result_value == 0 or result_value is None:
            return 0.0

        sensitivity_rate = fault_value / result_value
        return sensitivity_rate
    
    @staticmethod
    def _calculate_di2_sensitivity(
        result_value: float, fault_value: float, i2_nr: float = 0.0
    ) -> float:
        """
        Рассчитывает чувствительность для органов с пуском по приращению тока обратной последовательности.
        
        Формула: k_ч = (I_2^КЗ - I_2н.р) / DI2 ОТКЛ
        
        :param result_value: Величина уставки DI2 ОТКЛ.
        :param fault_value: Величина тока обратной последовательности при КЗ (I_2^КЗ).
        :param i2_nr: Ток обратной последовательности в нагрузочном режиме (I_2н.р), по умолчанию 0.
        :return: Коэффициент чувствительности.
        """
        # Проверка на деление на ноль
        if result_value == 0 or result_value is None:
            return 0.0
        
        # Вычитаем ток небаланса
        effective_fault_value = fault_value - i2_nr
        if effective_fault_value <= 0:
            return 0.0
        
        sensitivity_rate = effective_fault_value / result_value
        return sensitivity_rate

    def _calculate_r_sensitivity(
        self, settings_calculation: SettingsCalculation, protection_half_set
    ) -> Optional[float]:
        """
        Рассчитывает чувствительность для органов R ОТКЛ и R ОТВ.
        
        Формула: R_чувст = 1.5 * (max(R_max_отв или R1_уд * L) + R_дуги * (1 + (I1^(3)_2 / I1^(3)_1)))
        
        Проверка: R_чувст ≤ 0.7 * R_ОТКЛ_уст
        
        :param settings_calculation: Объект SettingsCalculation с результатом R ОТКЛ или R ОТВ
        :param protection_half_set: Полукомплект защиты
        :return: Коэффициент чувствительности (R_чувст / (0.7 * R_ОТКЛ_уст)) или None при ошибке
        """
        try:
            # Получаем линию
            line = self.calculation_meta.line
            if not line or not line.length or not line.r1 or not line.x1:
                print(f"[WARNING] Недостаточно данных линии для расчета R чувствительности")
                return None
            
            # Параметры линии
            length = float(line.length)  # км
            r1 = float(line.r1)  # Ом
            x1 = float(line.x1)  # Ом
            
            # Удельные сопротивления (Ом/км)
            r1_specific = r1 / length if length > 0 else 0
            x1_specific = x1 / length if length > 0 else 0
            
            # Угол максимальной чувствительности
            phi_mch_rad = atan(x1_specific / r1_specific) if r1_specific != 0 else radians(90)
            phi_mch_deg = degrees(phi_mch_rad)
            
            # Получаем все полукомплекты для этой линии
            all_half_sets = line.protection_half_sets.all()
            if all_half_sets.count() < 2:
                print(f"[WARNING] Недостаточно полукомплектов для расчета R чувствительности")
                return None
            
            # Находим токи трехфазного КЗ на противоположных концах линии
            # Для текущего полукомплекта нужны токи КЗ на противоположном конце
            # I1^(3)_1 - ток КЗ на противоположном конце для полукомплекта 1 (со стороны полукомплекта 2)
            # I1^(3)_2 - ток КЗ на противоположном конце для полукомплекта 2 (со стороны полукомплекта 1)
            
            # Находим противоположный полукомплект
            opposite_half_set = None
            for half_set in all_half_sets:
                if half_set.id != protection_half_set.id:
                    opposite_half_set = half_set
                    break
            
            if not opposite_half_set:
                print(f"[WARNING] Не найден противоположный полукомплект")
                return None
            
            # Ток КЗ на противоположном конце (для текущего полукомплекта)
            i1_3_opposite = None
            fault_calc_opposite = FaultCalculation.objects.filter(
                calculation_meta=self.calculation_meta,
                protection_half_set=opposite_half_set,
                fault_type="К(3)",
            ).exclude(
                fault_location__startswith="Ответвление:"
            ).first()
            
            if fault_calc_opposite and fault_calc_opposite.fault_values:
                i1_value = fault_calc_opposite.fault_values.get("I1")
                if i1_value:
                    i1_3_opposite = float(i1_value) / 1000  # Переводим из мА в А
            
            # Ток КЗ на конце текущего полукомплекта (для расчета отношения)
            i1_3_current = None
            fault_calc_current = FaultCalculation.objects.filter(
                calculation_meta=self.calculation_meta,
                protection_half_set=protection_half_set,
                fault_type="К(3)",
            ).exclude(
                fault_location__startswith="Ответвление:"
            ).first()
            
            if fault_calc_current and fault_calc_current.fault_values:
                i1_value = fault_calc_current.fault_values.get("I1")
                if i1_value:
                    i1_3_current = float(i1_value) / 1000  # Переводим из мА в А
            
            # Определяем I1^(3)_1 и I1^(3)_2 согласно формуле
            # I1^(3)_1 - ток КЗ со стороны полукомплекта 2 (противоположный для полукомплекта 1)
            # I1^(3)_2 - ток КЗ со стороны полукомплекта 1 (противоположный для полукомплекта 2)
            # Для текущего полукомплекта: I1^(3)_1 = ток на противоположном конце, I1^(3)_2 = ток на текущем конце
            i1_3_1 = i1_3_opposite  # Ток на противоположном конце
            i1_3_2 = i1_3_current if i1_3_current else i1_3_opposite  # Ток на текущем конце, если есть
            
            if i1_3_1 is None:
                print(f"[WARNING] Не найден ток КЗ на противоположном конце")
                return None
            
            if i1_3_2 is None:
                # Если нет тока на текущем конце, используем ток на противоположном
                i1_3_2 = i1_3_1
            
            # Получаем R_max_отв - максимальное сопротивление при КЗ на шинах подстанции ответвлений
            r_max_otv = 0.0
            
            # Ищем все КЗ на ответвлениях
            branch_faults = FaultCalculation.objects.filter(
                calculation_meta=self.calculation_meta,
                protection_half_set=protection_half_set,
                fault_type="К(3)",
                fault_location__startswith="Ответвление:"
            )
            
            for branch_fault in branch_faults:
                fault_values = branch_fault.fault_values
                if not fault_values:
                    continue
                
                ua_ost_otv = fault_values.get("U1")  # Остаточное напряжение (кВ)
                i1_3_otv = fault_values.get("I1")  # Ток прямой последовательности (мА)
                
                if ua_ost_otv and i1_3_otv and i1_3_otv > 0:
                    ua_ost_otv_kv = float(ua_ost_otv)  # кВ
                    i1_3_otv_a = float(i1_3_otv) / 1000  # Переводим из мА в А
                    
                    # R_max_отв = cos(Фмч) * (UA_ост_отв / I1^(3)_отв)
                    r_otv = cos(phi_mch_rad) * (ua_ost_otv_kv * 1000) / i1_3_otv_a  # Переводим кВ в В
                    r_max_otv = max(r_max_otv, r_otv)
            
            # R1_уд * L
            r1_ud_l = r1_specific * length
            
            # max(R_max_отв или R1_уд * L)
            r_max_term = max(r_max_otv, r1_ud_l)
            
            # R_дуги - сопротивление дуги (берем из calculation_factors или используем значение по умолчанию)
            # Обычно R_дуги = 0.1-0.2 Ом, но может варьироваться
            r_dugi = 0.15  # Ом (значение по умолчанию)
            # Можно добавить в calculation_factors, если нужно
            
            # R_чувст = 1.5 * (max(R_max_отв или R1_уд * L) + R_дуги * (1 + (I1^(3)_2 / I1^(3)_1)))
            if i1_3_1 > 0:
                i_ratio = i1_3_2 / i1_3_1
            else:
                i_ratio = 1.0
            
            r_chuvst = 1.5 * (r_max_term + r_dugi * (1 + i_ratio))
            
            # Получаем значение уставки R ОТКЛ
            r_otkl_ust = settings_calculation.result_value
            if r_otkl_ust is None or r_otkl_ust == 0:
                print(f"[WARNING] Уставка R ОТКЛ равна нулю или отсутствует")
                return None
            
            # Проверка: R_чувст ≤ 0.7 * R_ОТКЛ_уст
            r_otkl_limit = 0.7 * r_otkl_ust
            
            # Коэффициент чувствительности = R_чувст / (0.7 * R_ОТКЛ_уст)
            # Если коэффициент > 1, то защита не проходит по чувствительности
            sensitivity_rate = r_chuvst / r_otkl_limit if r_otkl_limit > 0 else float('inf')
            
            print(f"[DEBUG] R чувствительность: R_чувст={r_chuvst:.2f} Ом, "
                  f"0.7*R_ОТКЛ={r_otkl_limit:.2f} Ом, коэффициент={sensitivity_rate:.2f}")
            
            return round(sensitivity_rate, 2)
            
        except Exception as e:
            print(f"[ERROR] Ошибка при расчете R чувствительности: {e}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            return None

    def _calculate_rnm_sensitivity(
        self, settings_calculation: SettingsCalculation, protection_half_set, target_fault_value: str
    ) -> Optional[float]:
        """
        Рассчитывает чувствительность для органов РНМ (РТНП/3I0_M0 и РННП/3U0_M0)
        при КЗ на землю на шинах ВН ПС ответвлений.
        
        Формулы:
        - k_ч ≥ 3I0_мин/3I0 РНМ (для РТНП)
        - k_ч ≥ 3U0_мин/3U0 РНМ (для РННП)
        - k_ч = 1.5
        
        где:
        - 3I0_мин, 3U0_мин - минимальные значения тока и напряжения нулевой последовательности
          при КЗ на землю на шинах ВН ПС ответвлений
        - 3I0 РНМ, 3U0 РНМ - первичные минимальные значения уставок из SettingsCalculation
        
        :param settings_calculation: Объект SettingsCalculation с результатом РТНП или РННП
        :param protection_half_set: Полукомплект защиты
        :param target_fault_value: "RNM_I0" для РТНП или "RNM_U0" для РННП
        :return: Коэффициент чувствительности или None при ошибке
        """
        try:
            # Проверяем, что линия имеет ответвления
            line = self.calculation_meta.line
            if not line or line.branch_count == 0:
                print(f"[DEBUG] Линия не имеет ответвлений, проверка чувствительности РНМ не требуется")
                return None
            
            # Получаем значение уставки
            rnm_ust = settings_calculation.result_value
            if rnm_ust is None or rnm_ust == 0:
                print(f"[WARNING] Уставка РНМ равна нулю или отсутствует")
                return None
            
            # Ищем все КЗ на землю (К(1)) на ответвлениях
            # Проверяем подрежимы с отключением линии с противоположной стороны
            branch_faults = FaultCalculation.objects.filter(
                calculation_meta=self.calculation_meta,
                protection_half_set=protection_half_set,
                fault_type="К(1)",
                fault_location__startswith="Ответвление:"
            )
            
            if not branch_faults.exists():
                print(f"[WARNING] Не найдены КЗ на землю на ответвлениях для расчета чувствительности РНМ")
                return None
            
            # Находим минимальные значения 3I0 или 3U0
            min_value = None
            
            for branch_fault in branch_faults:
                fault_values = branch_fault.fault_values
                if not fault_values:
                    continue
                
                if target_fault_value == "RNM_I0":
                    # Для РТНП ищем минимальный 3I0
                    i0_value = fault_values.get("3I0")
                    if i0_value:
                        i0_a = float(i0_value) / 1000  # Переводим из мА в А
                        if min_value is None or i0_a < min_value:
                            min_value = i0_a
                elif target_fault_value == "RNM_U0":
                    # Для РННП ищем минимальный 3U0
                    # Если 3U0 нет в fault_values, пытаемся получить из других источников
                    # Обычно 3U0 может быть рассчитано как U0 * 3 или получено из PowerFactory
                    # Пока используем U1 как приближение, если 3U0 нет
                    u0_value = fault_values.get("3U0")
                    if u0_value is None:
                        # Если 3U0 нет, можно попробовать использовать U1 или рассчитать
                        # Для КЗ на землю 3U0 обычно присутствует в результатах
                        # Пока пропускаем, если нет явного значения
                        continue
                    u0_kv = float(u0_value)  # кВ (если хранится в кВ)
                    if min_value is None or u0_kv < min_value:
                        min_value = u0_kv
            
            if min_value is None:
                print(f"[WARNING] Не найдены значения для расчета чувствительности РНМ ({target_fault_value})")
                return None
            
            # Коэффициент чувствительности = min_value / rnm_ust
            # k_ч должен быть ≥ 1.5
            sensitivity_rate = min_value / rnm_ust if rnm_ust > 0 else float('inf')
            
            # Проверяем условие k_ч ≥ 1.5
            k_ch_required = 1.5
            is_sensitive = sensitivity_rate >= k_ch_required
            
            print(f"[DEBUG] РНМ чувствительность ({target_fault_value}): "
                  f"min_value={min_value:.4f}, уставка={rnm_ust:.4f}, "
                  f"k_ч={sensitivity_rate:.2f}, требуется ≥ {k_ch_required}, "
                  f"проходит={'ДА' if is_sensitive else 'НЕТ'}")
            
            return round(sensitivity_rate, 2)
            
        except Exception as e:
            print(f"[ERROR] Ошибка при расчете РНМ чувствительности: {e}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            return None

    def _calculate_3i0_sensitivity(
        self, settings_calculation: SettingsCalculation, protection_half_set, fault_calculations: QuerySet[FaultCalculation]
    ) -> Optional[float]:
        """
        Рассчитывает чувствительность для органа 3I0 ОТКЛ.
        
        Формула: K_ч = 3I0_КЗ_МИН / 3I0_ОТКЛ ≥ 2
        
        где:
        - 3I0_КЗ_МИН - минимальный ток КЗ нулевой последовательности
        - 3I0_ОТКЛ - уставка отключающего токового органа
        - K_ч должен быть ≥ 2
        
        :param settings_calculation: Объект SettingsCalculation с результатом 3I0 ОТКЛ
        :param protection_half_set: Полукомплект защиты
        :param fault_calculations: QuerySet всех КЗ на землю (К(1))
        :return: Коэффициент чувствительности или None при ошибке
        """
        try:
            # Получаем значение уставки 3I0 ОТКЛ
            i0_otkl_ust = settings_calculation.result_value
            if i0_otkl_ust is None or i0_otkl_ust == 0:
                print(f"[WARNING] Уставка 3I0 ОТКЛ равна нулю или отсутствует")
                return None
            
            # Находим минимальный ток КЗ нулевой последовательности из всех КЗ на землю
            min_3i0_kz = None
            
            for fault_calculation in fault_calculations:
                fault_values = fault_calculation.fault_values
                if not fault_values:
                    continue
                
                i0_value = fault_values.get("3I0")
                if i0_value:
                    i0_a = float(i0_value) / 1000  # Переводим из мА в А
                    if min_3i0_kz is None or i0_a < min_3i0_kz:
                        min_3i0_kz = i0_a
            
            if min_3i0_kz is None:
                print(f"[WARNING] Не найдены значения 3I0 для расчета чувствительности 3I0 ОТКЛ")
                return None
            
            # Коэффициент чувствительности = 3I0_КЗ_МИН / 3I0_ОТКЛ
            # K_ч должен быть ≥ 2
            sensitivity_rate = min_3i0_kz / i0_otkl_ust if i0_otkl_ust > 0 else float('inf')
            
            # Проверяем условие k_ч ≥ 2
            k_ch_required = 2.0
            is_sensitive = sensitivity_rate >= k_ch_required
            
            print(f"[DEBUG] 3I0 ОТКЛ чувствительность: "
                  f"3I0_КЗ_МИН={min_3i0_kz:.2f} А, уставка={i0_otkl_ust:.2f} А, "
                  f"K_ч={sensitivity_rate:.2f}, требуется ≥ {k_ch_required}, "
                  f"проходит={'ДА' if is_sensitive else 'НЕТ'}")
            
            return round(sensitivity_rate, 2)
        except Exception as e:
            print(f"[ERROR] Ошибка при расчете 3I0 ОТКЛ чувствительности: {e}")
            import traceback
            print(f"[ERROR] Traceback: {traceback.format_exc()}")
            return None
    
    @staticmethod
    def _calculate_manipulation_sensitivity(
        settings_calculation: SettingsCalculation,
        protection_half_set,
        min_i1_k3: float
    ) -> float:
        """
        Рассчитывает чувствительность для органа манипуляции при симметричных КЗ.
        
        Формула: K_ч ман сим = min(I1^(3)) / (K * I2 БЛОК)
        где:
        - min(I1^(3)) - минимальный ток прямой последовательности при трехфазном КЗ
        - K - коэффициент комбинированного фильтра токов (уставка K МАН)
        - I2 БЛОК - уставка блокирующего токового органа с пуском по току обратной последовательности
        
        Коэффициент чувствительности должен быть не менее 1.3.
        
        :param settings_calculation: Объект SettingsCalculation для K МАН.
        :param protection_half_set: Полукомплект защиты.
        :param min_i1_k3: Минимальное значение I1 при трехфазном КЗ (в А).
        :return: Коэффициент чувствительности.
        """
        # Получаем значение уставки K МАН (коэффициент комбинированного фильтра)
        k_man = settings_calculation.result_value
        if k_man is None or k_man == 0:
            print(f"[WARNING] Уставка K МАН не найдена или равна 0")
            return 0.0
        
        # Получаем I2 БЛОК для того же полукомплекта
        from core.models import Component
        try:
            i2_block_component = Component.objects.get(setting_designation="I2 БЛОК")
            i2_block_calculation = SettingsCalculation.objects.filter(
                calculation_meta=settings_calculation.calculation_meta,
                protection_half_set=protection_half_set,
                component=i2_block_component
            ).first()
            
            if not i2_block_calculation or not i2_block_calculation.result_value:
                print(f"[WARNING] Уставка I2 БЛОК не найдена для полукомплекта {protection_half_set}")
                return 0.0
            
            i2_block = i2_block_calculation.result_value
        except Component.DoesNotExist:
            print(f"[WARNING] Компонент I2 БЛОК не найден")
            return 0.0
        
        # Проверка на деление на ноль
        if i2_block == 0:
            return 0.0
        
        # Формула: K_ч ман сим = min(I1^(3)) / (K * I2 БЛОК)
        denominator = k_man * i2_block
        if denominator == 0:
            return 0.0
        
        sensitivity_rate = min_i1_k3 / denominator
        sensitivity_rate = round(sensitivity_rate, 2)
        
        # Проверяем условие k_ч ≥ 1.3
        k_ch_required = 1.3
        is_sensitive = sensitivity_rate >= k_ch_required
        
        print(f"[DEBUG] K МАН чувствительность: "
              f"I1_КЗ_МИН={min_i1_k3:.2f} А, K_МАН={k_man:.2f}, I2_БЛОК={i2_block:.2f} А, "
              f"K_ч={sensitivity_rate:.2f}, требуется ≥ {k_ch_required}, "
              f"проходит={'ДА' if is_sensitive else 'НЕТ'}")
        
        return sensitivity_rate
