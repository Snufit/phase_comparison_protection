from math import sqrt, cos, atan, radians, degrees
from typing import Callable, Dict, List, Optional, Union

from django.db.models import QuerySet

from calculation.models import (
    CalculationMeta,
    FaultCalculation,
    SensitivityAnalysis,
    SettingsCalculation,
)
from calculation.services.fault_calculation_service import FaultCalculationService
from calculation.services.sensitivity_fault_map import SensitivityFaultMap
from core.models import Component


class SensitivityAnalysisService:
    """Сервис анализа чувствительности."""

    def __init__(self, calculation_meta: CalculationMeta) -> None:
        self.calculation_meta: CalculationMeta = calculation_meta
        self.settings_calculations: QuerySet[
            SettingsCalculation
        ] = SettingsCalculation.objects.filter(calculation_meta=self.calculation_meta)

        # Используем карту КЗ для получения обработчиков чувствительности
        # Обработчики создаются динамически на основе карты КЗ
        self.SENSITIVITY_HANDLERS: Dict[
            str, Dict[str, Union[Callable, List[str], str, float]]
        ] = self._build_sensitivity_handlers()

    def _log(self, message: str):
        """
        Записывает сообщение в файл логов и в консоль.
        Использует тот же метод логирования, что и FaultCalculationService.
        
        Args:
            message: Сообщение для логирования
        """
        FaultCalculationService._log(message)

    def _get_fault_calculations_with_fallback(
        self,
        protection_half_set,
        fault_types: List[str],
        additional_filters: Optional[Dict] = None,
    ) -> QuerySet[FaultCalculation]:
        """
        Получает FaultCalculation с fallback на предыдущие расчеты, если для текущего расчета нет КЗ.
        
        Args:
            protection_half_set: Полукомплект защиты
            fault_types: Список типов КЗ
            additional_filters: Дополнительные фильтры для QuerySet (например, exclude, filter)
            
        Returns:
            QuerySet[FaultCalculation] с КЗ из текущего или предыдущего расчета
        """
        # Сначала ищем КЗ для текущего расчета
        filters = {
            'calculation_meta': self.calculation_meta,
            'protection_half_set': protection_half_set,
            'fault_type__in': fault_types,
        }
        if additional_filters:
            filters.update(additional_filters)
        
        fault_calculations = FaultCalculation.objects.filter(**filters)
        
        # Если для текущего расчета нет КЗ, пробуем использовать КЗ из предыдущих расчетов
        if fault_calculations.count() == 0:
            self._log(
                f"[WARNING] Не найдено КЗ для текущего расчета (ID={self.calculation_meta.id}). "
                f"Пробуем использовать КЗ из предыдущих расчетов для той же ЛЭП."
            )
            # Находим последний расчет для той же ЛЭП с КЗ
            previous_calculations = CalculationMeta.objects.filter(
                line=self.calculation_meta.line
            ).exclude(
                id=self.calculation_meta.id
            ).order_by('-calculation_date')
            
            self._log(
                f"[DEBUG] Ищем КЗ в {previous_calculations.count()} предыдущих расчетах для ЛЭП {self.calculation_meta.line}"
            )
            
            for prev_calc in previous_calculations:
                # Сначала пробуем найти КЗ для того же полукомплекта
                prev_filters = {
                    'calculation_meta': prev_calc,
                    'protection_half_set': protection_half_set,
                    'fault_type__in': fault_types,
                }
                if additional_filters:
                    # Для предыдущих расчетов применяем те же дополнительные фильтры
                    prev_filters.update(additional_filters)
                
                prev_faults = FaultCalculation.objects.filter(**prev_filters)
                
                # Если не нашли для того же полукомплекта, пробуем найти для любого полукомплекта той же ЛЭП
                if prev_faults.count() == 0:
                    self._log(
                        f"[DEBUG] Не найдено КЗ для полукомплекта {protection_half_set} в расчете ID={prev_calc.id}, "
                        f"пробуем найти для любого полукомплекта той же ЛЭП"
                    )
                    prev_filters_any_halfset = {
                        'calculation_meta': prev_calc,
                        'fault_type__in': fault_types,
                    }
                    if additional_filters:
                        prev_filters_any_halfset.update(additional_filters)
                    
                    prev_faults = FaultCalculation.objects.filter(**prev_filters_any_halfset)
                
                if prev_faults.count() > 0:
                    self._log(
                        f"[INFO] Найдено {prev_faults.count()} КЗ из предыдущего расчета "
                        f"(ID={prev_calc.id}, дата={prev_calc.calculation_date}). "
                        f"Используем их для анализа чувствительности."
                    )
                    fault_calculations = prev_faults
                    break
            else:
                self._log(
                    f"[WARNING] Не найдено КЗ в предыдущих расчетах для ЛЭП {self.calculation_meta.line}. "
                    f"Анализ чувствительности не может быть выполнен. "
                    f"Причина: PowerFactory не смог выполнить расчеты КЗ из-за ошибок многопоточности."
                )
        
        return fault_calculations

    def _get_offset_resistance_from_previous_calculation(
        self,
        protection_half_set,
        rnnp_ust: float,
        min_3u0: float,
    ) -> Optional[float]:
        """
        Получает коэффициент смещения Z₀_см из предыдущих расчетов или рассчитывает его.
        
        Args:
            protection_half_set: Полукомплект защиты
            rnnp_ust: Уставка РННП в кВ
            min_3u0: Минимальное напряжение 3U₀ в кВ (из найденных КЗ)
            
        Returns:
            Значение Z₀_см в Ом или None
        """
        # Сначала ищем коэффициент смещения в предыдущих расчетах для той же ЛЭП
        previous_calculations = CalculationMeta.objects.filter(
            line=self.calculation_meta.line
        ).exclude(
            id=self.calculation_meta.id
        ).order_by('-calculation_date')
        
        # Ищем SettingsCalculation для РННП/3U0_M0 в предыдущих расчетах
        rnnp_component = Component.objects.filter(
            setting_designation="РННП/3U0_M0"
        ).first()
        
        if not rnnp_component:
            return None
        
        for prev_calc in previous_calculations:
            prev_settings = SettingsCalculation.objects.filter(
                calculation_meta=prev_calc,
                protection_half_set=protection_half_set,
                component=rnnp_component,
            ).first()
            
            if prev_settings and prev_settings.calculation_factors:
                prev_z0_offset = prev_settings.calculation_factors.get("Сопротивление смещения Z₀_см, Ом")
                if prev_z0_offset and prev_z0_offset > 0:
                    self._log(
                        f"[INFO] Найден коэффициент смещения Z₀_см={prev_z0_offset:.3f} Ом "
                        f"из предыдущего расчета (ID={prev_calc.id})"
                    )
                    return float(prev_z0_offset)
        
        # Если не нашли в предыдущих расчетах, пробуем рассчитать на основе найденных КЗ
        # Для расчета нужен минимальный ток 3I0_МИН_СРАБ (уставка РТНП)
        min_3i0_srab = self._get_min_rtnp_setting_for_analysis(protection_half_set)
        
        if min_3i0_srab and min_3i0_srab > 0 and min_3u0 and min_3u0 > 0:
            # Формула (3.9): |Z₀_см| ≥ (k_ч · 3U₀_РНМ_разр - |3U₀|) / 3I0_МИН_СРАБ
            k_ch = 1.5
            numerator = k_ch * rnnp_ust - abs(min_3u0)
            
            if numerator > 0:
                z0_offset = (numerator / min_3i0_srab) * 1000  # кВ/А * 1000 = Ом
                self._log(
                    f"[INFO] Рассчитан коэффициент смещения Z₀_см={z0_offset:.3f} Ом "
                    f"на основе найденных КЗ (3U₀_мин={min_3u0:.3f} кВ, "
                    f"3I0_МИН_СРАБ={min_3i0_srab:.3f} А, уставка={rnnp_ust:.3f} кВ)"
                )
                return round(z0_offset, 3)
            else:
                self._log(
                    f"[WARNING] Не удалось рассчитать коэффициент смещения: "
                    f"k_ч·3U₀_РНМ={k_ch * rnnp_ust:.3f} кВ ≤ |3U₀|={abs(min_3u0):.3f} кВ"
                )
        
        return None

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
        """
        Запускает анализ чувствительности для всех органов защиты.
        """
        self._log(f"[DEBUG] ========== Начало анализа чувствительности ==========")
        self._log(f"[DEBUG] Расчет: {self.calculation_meta.id}")
        self._log(f"[DEBUG] ЛЭП: {self.calculation_meta.line.dispatch_name}")

        total_analyses = 0
        for settings_calculation in self.settings_calculations:
            component = settings_calculation.component
            protection_half_set = settings_calculation.protection_half_set
            result_value = settings_calculation.result_value
            handler = self._get_handler(component)

            if handler:
                self._log(
                    f"[DEBUG] --- Анализ чувствительности для органа: {component.setting_designation} ---"
                )
                self._log(f"[DEBUG] Полукомплект: {protection_half_set}")
                self._log(f"[DEBUG] Уставка: {result_value}")

                sensitivity_analysis_function = handler["function"]
                fault_types = handler["fault_types"]
                target_fault_value = handler["fault_value"]

                self._log(f"[DEBUG] Требуемые типы КЗ: {fault_types}")
                self._log(
                    f"[DEBUG] Требуемое значение из КЗ: {target_fault_value}")

                fault_calculations = self._get_fault_calculations_with_fallback(
                    protection_half_set=protection_half_set,
                    fault_types=fault_types,
                )

                self._log(f"[DEBUG] Найдено КЗ в БД: {fault_calculations.count()}")

                # Получаем дополнительные параметры из карты КЗ
                use_min_value = handler.get("use_min_value", False)
                exclude_branches = handler.get("exclude_branches", True)
                requires_branches = handler.get("requires_branches", False)
                k_sx = handler.get("k_sx", 1.0)

                self._log(
                    f"[DEBUG] Параметры: use_min_value={use_min_value}, exclude_branches={exclude_branches}, "
                    f"requires_branches={requires_branches}, k_sx={k_sx}"
                )

                # Проверяем требование наличия ответвлений
                if requires_branches:
                    line = self.calculation_meta.line
                    if not line or not line.branches.filter(is_active=True).exists():
                        self._log(
                            f"[DEBUG] Пропущен расчет чувствительности для {component.setting_designation}: "
                            f"требуются ответвления, но их нет"
                        )
                        continue

                # Фильтруем КЗ по месту выполнения
                initial_count = fault_calculations.count()
                if exclude_branches:
                    fault_calculations = fault_calculations.exclude(
                        fault_location__startswith="Ответвление:"
                    )
                    self._log(
                        f"[DEBUG] После исключения ответвлений: {fault_calculations.count()} КЗ (было {initial_count})"
                    )
                else:
                    # Для органов, которым нужны только ответвления
                    if requires_branches:
                        fault_calculations = fault_calculations.filter(
                            fault_location__startswith="Ответвление:"
                        )
                        self._log(
                            f"[DEBUG] После фильтрации только ответвлений: {fault_calculations.count()} КЗ (было {initial_count})"
                        )
                    else:
                        self._log(
                            f"[DEBUG] Используются все КЗ: {fault_calculations.count()} КЗ"
                        )

                # Специальная обработка для R ОТКЛ и R ОТВ
                if target_fault_value == "R":
                    # Для R чувствительности нужна специальная логика
                    self._log(
                        f"[DEBUG] Специальная обработка для R: расчет чувствительности по сопротивлению"
                    )
                    try:
                        sensitivity_rate = sensitivity_analysis_function(
                            settings_calculation, protection_half_set
                        )
                        if sensitivity_rate is not None:
                            self._log(
                                f"[DEBUG] Рассчитана чувствительность R: K_ч = {sensitivity_rate}"
                            )
                            # Создаем запись для каждого КЗ на ответвлениях
                            branch_faults = fault_calculations.filter(
                                fault_location__startswith="Ответвление:"
                            )
                            self._log(
                                f"[DEBUG] Сохранение результатов для {branch_faults.count()} КЗ на ответвлениях"
                            )
                            for fault_calculation in branch_faults:
                                self._save_result_to_db(
                                    settings_calculation=settings_calculation,
                                    fault_calculation=fault_calculation,
                                    sensitivity_rate=sensitivity_rate,
                                )
                                total_analyses += 1
                        else:
                            self._log(
                                f"[WARNING] Не удалось рассчитать чувствительность R для {component.setting_designation}"
                            )
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        self._log(
                            f"[ERROR] Ошибка при расчете чувствительности R для {component.setting_designation}: {e}"
                        )
                    # Всегда пропускаем дальнейшую обработку для R, так как это специальный случай
                        continue
                # Специальная обработка для 3I0 ОТКЛ
                elif target_fault_value == "3I0":
                    # Для 3I0 ОТКЛ нужна специальная логика - находим минимальное значение на противоположной стороне
                    # Фильтруем только КЗ на противоположной стороне (исключаем ответвления)
                    opposite_end_faults = fault_calculations.exclude(
                        fault_location__startswith="Ответвление:"
                    )
                    # Логирование перенесено в метод _calculate_3i0_sensitivity для избежания дублирования
                    try:
                        sensitivity_rate = sensitivity_analysis_function(
                            settings_calculation,
                            protection_half_set,
                            opposite_end_faults,
                        )
                        if sensitivity_rate is not None:
                            self._log(
                                f"[DEBUG] Рассчитана чувствительность 3I0: K_ч = {sensitivity_rate}"
                            )
                            # Создаем запись для каждого КЗ на землю на противоположной стороне
                            self._log(
                                f"[DEBUG] Сохранение результатов для {opposite_end_faults.count()} КЗ на землю на противоположной стороне"
                            )
                            for fault_calculation in opposite_end_faults:
                                self._save_result_to_db(
                                    settings_calculation=settings_calculation,
                                    fault_calculation=fault_calculation,
                                    sensitivity_rate=sensitivity_rate,
                                )
                                total_analyses += 1
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        self._log(
                            f"[ERROR] Ошибка при расчете чувствительности 3I0 ОТКЛ для {component.setting_designation}: {e}"
                        )
                        continue
                # Специальная обработка для РНМ (РТНП/3I0_M0 и РННП/3U0_M0)
                elif target_fault_value in ["RNM_I0", "RNM_U0"]:
                    # Для РНМ чувствительности нужна специальная логика
                    self._log(
                        f"[DEBUG] Специальная обработка для РНМ: расчет чувствительности по {target_fault_value}"
                    )
                    self._log(
                        f"[DEBUG] Всего КЗ найдено: {fault_calculations.count()}")

                    # Фильтруем только КЗ на ответвлениях
                    branch_faults = fault_calculations.filter(
                        fault_location__startswith="Ответвление:"
                    )
                    self._log(
                        f"[DEBUG] КЗ на ответвлениях: {branch_faults.count()}")

                    if branch_faults.count() == 0:
                        self._log(
                            f"[WARNING] Не найдены КЗ на ответвлениях для расчета чувствительности РНМ ({component.setting_designation})"
                        )
                        continue

                    try:
                        sensitivity_rate = sensitivity_analysis_function(
                            settings_calculation,
                            protection_half_set,
                            target_fault_value,
                        )
                        if sensitivity_rate is not None:
                            self._log(
                                f"[DEBUG] Рассчитана чувствительность РНМ: K_ч = {sensitivity_rate}"
                            )
                            # Создаем запись для каждого КЗ на землю на ответвлениях
                            self._log(
                                f"[DEBUG] Сохранение результатов для {branch_faults.count()} КЗ на ответвлениях"
                            )
                            for fault_calculation in branch_faults:
                                self._save_result_to_db(
                                    settings_calculation=settings_calculation,
                                    fault_calculation=fault_calculation,
                                    sensitivity_rate=sensitivity_rate,
                                )
                                total_analyses += 1
                        else:
                            self._log(
                                f"[WARNING] Не удалось рассчитать чувствительность РНМ для {component.setting_designation}"
                            )
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        self._log(
                            f"[ERROR] Ошибка при расчете чувствительности РНМ для {component.setting_designation}: {e}"
                        )
                        import traceback

                        self._log(f"[ERROR] Traceback: {traceback.format_exc()}")
                    # Всегда пропускаем дальнейшую обработку для РНМ, так как это специальный случай
                        continue
                else:
                    # Обычная обработка для других органов
                    # Если нужно использовать минимальное значение, находим его
                    if use_min_value:
                        min_fault_value = None
                        min_fault_calculation = None

                        self._log(
                            f"[DEBUG] Поиск минимального значения {target_fault_value} среди {fault_calculations.count()} КЗ"
                        )
                        for fault_calculation in fault_calculations:
                            fault_value = fault_calculation.fault_values.get(
                                target_fault_value
                            )
                            if fault_value is None:
                                continue

                            # Приводим к float и игнорируем нулевые/отрицательные значения
                            # (в логах PowerFactory для отключенных/невалидных подрежимов часто возвращает 0)
                            try:
                                fault_value_num = float(fault_value)
                            except (ValueError, TypeError):
                                continue

                            if fault_value_num <= 0:
                                continue

                            self._log(
                                    f"[DEBUG]   КЗ {fault_calculation.fault_type} на {fault_calculation.fault_location}, "
                                f"подрежим '{fault_calculation.network_topology}': {target_fault_value} = {fault_value_num}"
                                )

                            if min_fault_value is None or fault_value_num < min_fault_value:
                                min_fault_value = fault_value_num
                                min_fault_calculation = fault_calculation

                        if min_fault_calculation is not None and min_fault_value is not None:
                            self._log(
                                f"[DEBUG] Минимальное значение {target_fault_value} = {min_fault_value} "
                                f"(КЗ {min_fault_calculation.fault_type} на {min_fault_calculation.fault_location}, "
                                f"подрежим '{min_fault_calculation.network_topology}')"
                            )
                            try:
                                # Для IЛ ОТКЛ используем k_sx
                                if component.setting_designation == "IЛ ОТКЛ":
                                    sensitivity_rate = sensitivity_analysis_function(
                                        result_value, min_fault_value, k_sx
                                    )
                                # Для DI2 ОТКЛ используем i2_nr из карты КЗ
                                elif component.setting_designation == "DI2 ОТКЛ":
                                    fault_map = SensitivityFaultMap.get_fault_map(
                                        "DI2 ОТКЛ"
                                    )
                                    i2_nr = (
                                        fault_map.get("i2_nr", 0.0)
                                        if fault_map
                                        else 0.0
                                    )
                                    sensitivity_rate = sensitivity_analysis_function(
                                        result_value, min_fault_value, i2_nr
                                    )
                                # Для K МАН используем специальную формулу с I2 БЛОК
                                # Используется минимальный I1 из К(1) и К(1,1), а не из К(3)
                                elif component.setting_designation in [
                                    "K МАН",
                                    "К МАН",
                                ]:
                                    # Значения уже в А (не нужно переводить)
                                    i1_min_value = (
                                        float(min_fault_value)
                                        if min_fault_value
                                        else 0.0
                                    )
                                    sensitivity_rate = sensitivity_analysis_function(
                                        settings_calculation,
                                        protection_half_set,
                                        i1_min_value,
                                    )
                                else:
                                    sensitivity_rate = sensitivity_analysis_function(
                                        result_value, min_fault_value
                                    )
                                sensitivity_rate = round(sensitivity_rate, 2)
                                self._log(
                                    f"[DEBUG] Рассчитана чувствительность: K_ч = {sensitivity_rate}"
                                )
                                self._save_result_to_db(
                                    settings_calculation=settings_calculation,
                                    fault_calculation=min_fault_calculation,
                                    sensitivity_rate=sensitivity_rate,
                                )
                                total_analyses += 1
                            except (ZeroDivisionError, ValueError, TypeError) as e:
                                self._log(
                                    f"[ERROR] Ошибка при расчете чувствительности для {component.setting_designation}: {e}"
                                )
                    else:
                        # Обрабатываем все КЗ
                        self._log(
                            f"[DEBUG] Обработка всех КЗ ({fault_calculations.count()} шт.) для {component.setting_designation}"
                        )
                for fault_calculation in fault_calculations:
                    fault_value = fault_calculation.fault_values.get(
                        target_fault_value)

                    self._log(
                        f"[DEBUG]   КЗ {fault_calculation.fault_type} на {fault_calculation.fault_location}, "
                        f"подрежим '{fault_calculation.network_topology}': {target_fault_value} = {fault_value}"
                    )

                    # Пропускаем, если нет значения уставки или значения КЗ
                    if result_value is None or result_value == 0:
                                self._log(
                            f"[WARNING] Пропущен расчет чувствительности для {component.setting_designation}: "
                            f"result_value={result_value}"
                        )
                    continue

                    if fault_value is None or fault_value == 0:
                                self._log(
                            f"[WARNING] Пропущен расчет чувствительности для {component.setting_designation}: "
                            f"fault_value={fault_value}"
                        )
                    continue

                    try:
                        # Для IЛ ОТКЛ используем k_sx
                        if component.setting_designation == "IЛ ОТКЛ":
                            sensitivity_rate = sensitivity_analysis_function(
                                result_value, fault_value, k_sx
                            )
                        # Для DI2 ОТКЛ используем i2_nr из карты КЗ
                        elif component.setting_designation == "DI2 ОТКЛ":
                            fault_map = SensitivityFaultMap.get_fault_map(
                                "DI2 ОТКЛ")
                            i2_nr = fault_map.get(
                                "i2_nr", 0.0) if fault_map else 0.0
                            sensitivity_rate = sensitivity_analysis_function(
                                result_value, fault_value, i2_nr
                            )
                        # Для K МАН используем специальную формулу с I2 БЛОК
                                # Используется I1 из К(1) и К(1,1), а не из К(3)
                        elif component.setting_designation in ["K МАН", "К МАН"]:
                            # Значения уже в А (не нужно переводить)
                            i1_value = float(fault_value) if fault_value else 0.0
                            sensitivity_rate = sensitivity_analysis_function(
                                        settings_calculation, protection_half_set, i1_value
                            )
                        else:
                            sensitivity_rate = sensitivity_analysis_function(
                                result_value, fault_value
                            )

                        sensitivity_rate = round(sensitivity_rate, 2)
                        self._log(
                            f"[DEBUG] Рассчитана чувствительность: K_ч = {sensitivity_rate}"
                        )
                        self._save_result_to_db(
                            settings_calculation=settings_calculation,
                            fault_calculation=fault_calculation,
                            sensitivity_rate=sensitivity_rate,
                        )
                        total_analyses += 1
                    except (ZeroDivisionError, ValueError, TypeError) as e:
                                self._log(
                            f"[ERROR] Ошибка при расчете чувствительности для {component.setting_designation}: {e}"
                        )
                    continue
            else:
                self._log(
                    f"[DEBUG] Пропущен орган {component.setting_designation}: нет обработчика чувствительности"
                )

        self._log(f"[DEBUG] ========== Завершен анализ чувствительности ==========")
        self._log(
            f"[DEBUG] Всего выполнено расчетов чувствительности: {total_analyses}")

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

        :param result_value: Величина уставки (в А).
        :param fault_value: Величина тока КЗ (в А).
        :param k_sx: Коэффициент схемы (по умолчанию √3 для векторной разности).
        :return: Коэффициент чувствительности.
        """
        # Проверка на деление на ноль
        if result_value == 0 or result_value is None:
            return 0.0

        # Значения уже в А (не нужно переводить)
        fault_value_a = float(fault_value) if fault_value else 0.0
        sensitivity_rate = k_sx * fault_value_a / result_value
        return sensitivity_rate

    @staticmethod
    def _calculate_current_sensitivity(
        result_value: float, fault_value: float
    ) -> float:
        """
        Рассчитывает чувствительность для токовых и напряженческих органов.

        :param result_value: Величина уставки (в А для токов, в В для напряжений).
        :param fault_value: Величина тока/напряжения КЗ (в А для токов, в В для напряжений).
        :return: Коэффициент чувствительности.
        """
        # Проверка на деление на ноль
        if result_value == 0 or result_value is None:
            return 0.0

        # Значения токов КЗ уже в А (не нужно переводить)
        # Для напряжений значения уже в В
        fault_value_converted = float(fault_value) if fault_value else 0.0
        
        sensitivity_rate = fault_value_converted / result_value
        return sensitivity_rate

    @staticmethod
    def _calculate_di2_sensitivity(
        result_value: float, fault_value: float, i2_nr: float = 0.0
    ) -> float:
        """
        Рассчитывает чувствительность для органов с пуском по приращению тока обратной последовательности.

        Формула: k_ч = (I_2^КЗ - I_2н.р) / DI2 ОТКЛ

        :param result_value: Величина уставки DI2 ОТКЛ (в А).
        :param fault_value: Величина тока обратной последовательности при КЗ (I_2^КЗ, в А).
        :param i2_nr: Ток обратной последовательности в нагрузочном режиме (I_2н.р, в А), по умолчанию 0.
        :return: Коэффициент чувствительности.
        """
        # Проверка на деление на ноль
        if result_value == 0 or result_value is None:
            return 0.0

        # Значения уже в А (не нужно переводить)
        fault_value_a = float(fault_value) if fault_value else 0.0
        i2_nr_a = float(i2_nr) if i2_nr else 0.0
        
        # Вычитаем ток небаланса
        effective_fault_value = fault_value_a - i2_nr_a
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
                self._log(
                    f"[WARNING] Недостаточно данных линии для расчета R чувствительности"
                )
                return None

            # Параметры линии
            length = float(line.length)  # км
            r1 = float(line.r1)  # Ом
            x1 = float(line.x1)  # Ом

            # Удельные сопротивления (Ом/км)
            r1_specific = r1 / length if length > 0 else 0
            x1_specific = x1 / length if length > 0 else 0

            # Угол максимальной чувствительности
            phi_mch_rad = (
                atan(x1_specific / r1_specific) if r1_specific != 0 else radians(90)
            )
            phi_mch_deg = degrees(phi_mch_rad)

            # Получаем все полукомплекты для этой линии
            all_half_sets = line.protection_half_sets.all()
            if all_half_sets.count() < 2:
                self._log(
                    f"[WARNING] Недостаточно полукомплектов для расчета R чувствительности"
                )
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
                self._log(f"[WARNING] Не найден противоположный полукомплект")
                return None

            # Ток КЗ на противоположном конце (для текущего полукомплекта)
            # ВАЖНО: Ищем КЗ для ТЕКУЩЕГО полукомплекта на противоположном конце,
            # а не для противоположного полукомплекта!
            # Когда рассчитываем чувствительность для полукомплекта 1, нам нужен ток I1
            # на противоположном конце, который был рассчитан для полукомплекта 1
            i1_3_opposite = None
            all_opposite_faults = self._get_fault_calculations_with_fallback(
                protection_half_set=protection_half_set,
                fault_types=["К(3)"],
            ).exclude(fault_location__startswith="Ответвление:")
            
            # Ищем КЗ с ненулевым I1
            for fault_calc in all_opposite_faults:
                if fault_calc and fault_calc.fault_values:
                    i1_value = fault_calc.fault_values.get("I1")
                    if i1_value and float(i1_value) > 0:
                        i1_3_opposite = float(i1_value)  # Значения уже в А
                        self._log(
                            f"[DEBUG] Найден ток I1={i1_3_opposite:.2f} А на противоположном конце "
                            f"для полукомплекта {protection_half_set} (КЗ на {fault_calc.fault_location}, "
                            f"подрежим '{fault_calc.network_topology}')"
                        )
                        break
            
            if i1_3_opposite is None:
                self._log(
                    f"[DEBUG] Не найдено КЗ типа К(3) с ненулевым I1 на противоположном конце "
                    f"для полукомплекта {protection_half_set} (ID: {protection_half_set.id}). "
                    f"Всего найдено КЗ: {all_opposite_faults.count()}"
                )

            # Ток КЗ на конце текущего полукомплекта (для расчета отношения)
            # Ищем КЗ для противоположного полукомплекта на противоположном конце
            # (это будет ток на конце текущего полукомплекта)
            i1_3_current = None
            all_current_faults = self._get_fault_calculations_with_fallback(
                protection_half_set=opposite_half_set,
                fault_types=["К(3)"],
            ).exclude(fault_location__startswith="Ответвление:")
            
            # Ищем КЗ с ненулевым I1
            for fault_calc in all_current_faults:
                if fault_calc and fault_calc.fault_values:
                    i1_value = fault_calc.fault_values.get("I1")
                    if i1_value and float(i1_value) > 0:
                        i1_3_current = float(i1_value)  # Значения уже в А
                        break

            # Определяем I1^(3)_1 и I1^(3)_2 согласно формуле
            # I1^(3)_1 - ток КЗ со стороны полукомплекта 2 (противоположный для полукомплекта 1)
            # I1^(3)_2 - ток КЗ со стороны полукомплекта 1 (противоположный для полукомплекта 2)
            # Для текущего полукомплекта: I1^(3)_1 = ток на противоположном конце, I1^(3)_2 = ток на текущем конце
            i1_3_1 = i1_3_opposite  # Ток на противоположном конце
            i1_3_2 = (
                i1_3_current if i1_3_current else i1_3_opposite
            )  # Ток на текущем конце, если есть

            if i1_3_1 is None:
                self._log(f"[WARNING] Не найден ток КЗ на противоположном конце")
                return None

            if i1_3_2 is None:
                # Если нет тока на текущем конце, используем ток на противоположном
                i1_3_2 = i1_3_1

            # Получаем R_max_отв - максимальное сопротивление при КЗ на шинах подстанции ответвлений
            r_max_otv = 0.0

            # Ищем все КЗ на ответвлениях
            branch_faults = self._get_fault_calculations_with_fallback(
                protection_half_set=protection_half_set,
                fault_types=["К(3)"],
                additional_filters={'fault_location__startswith': "Ответвление:"},
            )

            for branch_fault in branch_faults:
                fault_values = branch_fault.fault_values
                if not fault_values:
                    continue

                # Остаточное напряжение (кВ)
                ua_ost_otv = fault_values.get("U1")
                # Ток прямой последовательности (мА)
                i1_3_otv = fault_values.get("I1")

                if ua_ost_otv and i1_3_otv and i1_3_otv > 0:
                    ua_ost_otv_kv = float(ua_ost_otv)  # кВ
                    i1_3_otv_a = float(i1_3_otv)  # Значения уже в А

                    # R_max_отв = cos(Фмч) * (UA_ост_отв / I1^(3)_отв)
                    r_otv = (
                        cos(phi_mch_rad) * (ua_ost_otv_kv * 1000) / i1_3_otv_a
                    )  # Переводим кВ в В
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
                self._log(f"[WARNING] Уставка R ОТКЛ равна нулю или отсутствует")
                return None

            # Проверка: R_чувст ≤ 0.7 * R_ОТКЛ_уст
            # Приводим к общему виду: k_ч = (0.7 * R_ОТКЛ_уст) / R_чувст
            # k_ч ≥ 1 означает, что защита проходит (R_чувст ≤ 0.7 * R_ОТКЛ_уст)
            r_otkl_limit = 1.7 * r_otkl_ust

            # Коэффициент чувствительности в общем виде: требуемое_значение / фактическое_значение
            # Требуемое: 0.7 * R_ОТКЛ_уст
            # Фактическое: R_чувст
            sensitivity_rate = (
                r_otkl_limit / r_chuvst if r_chuvst > 0 else float("inf")
            )

            self._log(
                f"[DEBUG] R чувствительность: R_чувст={r_chuvst:.2f} Ом, "
                f"0.7*R_ОТКЛ={r_otkl_limit:.2f} Ом, коэффициент={sensitivity_rate:.2f}"
            )

            return round(sensitivity_rate, 2)

        except Exception as e:
            self._log(f"[ERROR] Ошибка при расчете R чувствительности: {e}")
            import traceback

            self._log(f"[ERROR] Traceback: {traceback.format_exc()}")
            return None

    def _calculate_rnm_sensitivity(
        self,
        settings_calculation: SettingsCalculation,
        protection_half_set,
        target_fault_value: str,
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
            # Получаем значение уставки
            rnm_ust = settings_calculation.result_value
            if rnm_ust is None or rnm_ust == 0:
                self._log(f"[WARNING] Уставка РНМ равна нулю или отсутствует")
                return None

            # Ищем все КЗ на землю (К(1)) на ответвлениях
            # Проверяем подрежимы с отключением линии с противоположной стороны
            branch_faults = self._get_fault_calculations_with_fallback(
                protection_half_set=protection_half_set,
                fault_types=["К(1)"],
                additional_filters={'fault_location__startswith': "Ответвление:"},
            )

            # Проверяем наличие КЗ на ответвлениях - это более надежная проверка, чем branch_count
            if not branch_faults.exists():
                self._log(
                    f"[WARNING] Не найдены КЗ на землю на ответвлениях для расчета чувствительности РНМ"
                )
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
                        i0_a = float(i0_value)  # Значения уже в А
                        if i0_a <= 0:
                            continue
                        if min_value is None or i0_a < min_value:
                            min_value = i0_a
                elif target_fault_value == "RNM_U0":
                    # Для РННП ищем минимальный 3U0
                    # 3U0 из PowerFactory хранится в кВ (первичные величины)
                    # Уставка РННП также рассчитывается в кВ (первичные величины)
                    u0_value = fault_values.get("3U0")
                    if u0_value is None:
                        # Для КЗ на землю 3U0 обычно присутствует в результатах
                        # Пока пропускаем, если нет явного значения
                        continue
                    u0_kv = float(u0_value)  # кВ (первичные величины)
                    # 0 кВ обычно означает невалидный/обесточенный режим (в логах это "Отключение ..."),
                    # его нельзя использовать как минимум для чувствительности.
                    if u0_kv <= 0:
                        continue
                    if min_value is None or u0_kv < min_value:
                        min_value = u0_kv

            if min_value is None:
                self._log(
                    f"[WARNING] Не найдены значения для расчета чувствительности РНМ ({target_fault_value})"
                )
                return None

            # Если есть смещение для РННП, учитываем его при расчете чувствительности
            if target_fault_value == "RNM_U0":
                calculation_factors = settings_calculation.calculation_factors or {}
                z0_offset_raw = calculation_factors.get("Сопротивление смещения Z₀_см, Ом")
                
                # Преобразуем в float, если значение есть
                z0_offset = None
                if z0_offset_raw is not None:
                    try:
                        z0_offset = float(z0_offset_raw)
                        if z0_offset <= 0:
                            z0_offset = None
                            self._log(
                                f"[DEBUG] Коэффициент смещения в calculation_factors неположительный: {z0_offset_raw}"
                            )
                        else:
                            self._log(
                                f"[DEBUG] Найден коэффициент смещения в calculation_factors: {z0_offset:.3f} Ом"
                            )
                    except (ValueError, TypeError) as e:
                        z0_offset = None
                        self._log(
                            f"[DEBUG] Не удалось преобразовать коэффициент смещения в float: {z0_offset_raw}, ошибка: {e}"
                        )

                # Если смещения нет в текущем расчете, пробуем найти его в предыдущих расчетах
                if not z0_offset or z0_offset <= 0:
                    self._log(
                        f"[DEBUG] Коэффициент смещения не найден в текущем расчете, ищем в предыдущих..."
                    )
                    z0_offset = self._get_offset_resistance_from_previous_calculation(
                        protection_half_set, rnm_ust, min_value
                    )
                    self._log(
                        f"[DEBUG] Результат поиска коэффициента смещения: z0_offset={z0_offset} "
                        f"(тип: {type(z0_offset).__name__})"
                    )
                    # Сохраняем найденный коэффициент смещения в calculation_factors текущего расчета
                    # чтобы он отображался в интерфейсе
                    if z0_offset is not None:
                        try:
                            z0_offset_float = float(z0_offset)
                            if z0_offset_float > 0:
                                if settings_calculation.calculation_factors is None:
                                    settings_calculation.calculation_factors = {}
                                settings_calculation.calculation_factors["Сопротивление смещения Z₀_см, Ом"] = z0_offset_float
                                settings_calculation.save(update_fields=['calculation_factors'])
                                # Перезагружаем объект из БД, чтобы убедиться, что значение сохранилось
                                settings_calculation.refresh_from_db()
                                # Проверяем, что значение сохранилось
                                saved_value = settings_calculation.calculation_factors.get("Сопротивление смещения Z₀_см, Ом")
                                self._log(
                                    f"[DEBUG] Сохранен коэффициент смещения Z₀_см={z0_offset_float:.3f} Ом "
                                    f"в calculation_factors (ID={settings_calculation.id}). "
                                    f"Проверка сохранения: {saved_value} (тип: {type(saved_value).__name__})"
                                )
                                z0_offset = z0_offset_float
                            else:
                                self._log(
                                    f"[WARNING] Коэффициент смещения неположительный: {z0_offset_float}"
                                )
                        except (ValueError, TypeError) as e:
                            self._log(
                                f"[ERROR] Ошибка при сохранении коэффициента смещения: {e}, z0_offset={z0_offset}"
                            )
                    else:
                        self._log(
                            f"[WARNING] Коэффициент смещения не был найден или равен None"
                        )

                if z0_offset and z0_offset > 0:
                    # Находим минимальный ток срабатывания 3I0_МИН_СРАБ (уставка РТНП)
                    min_3i0_srab = self._get_min_rtnp_setting_for_analysis(
                        protection_half_set
                    )

                    if min_3i0_srab and min_3i0_srab > 0:
                        # Формула (3.8): 3U₀_РНМ_разр ≤ (|3U₀| + 3I0_МИН_СРАБ · |Z₀_см|) / k_ч
                        # Эффективное напряжение = |3U₀| + 3I0_МИН_СРАБ · |Z₀_см|
                        # Z₀_см в Ом, 3I0 в А, результат в кВ: (А · Ом) / 1000 = кВ
                        offset_voltage = (min_3i0_srab * z0_offset) / 1000  # кВ
                        effective_u0 = min_value + offset_voltage

                        sensitivity_rate = (
                            effective_u0 / rnm_ust if rnm_ust > 0 else float("inf")
                        )

                        self._log(
                            f"[DEBUG] РННП с смещением: 3U₀={min_value:.3f} кВ, "
                            f"3I0_МИН_СРАБ={min_3i0_srab:.3f} А, Z₀_см={z0_offset:.3f} Ом, "
                            f"добавка={offset_voltage:.3f} кВ, эффективное 3U₀={effective_u0:.3f} кВ, "
                            f"k_ч={sensitivity_rate:.2f}"
                        )
                    else:
                        # Если не удалось найти минимальный ток, используем стандартный расчет
                        self._log(
                            f"[WARNING] Не удалось найти минимальный ток 3I0_МИН_СРАБ "
                            f"для расчета чувствительности с учетом смещения, используем стандартный расчет"
                        )
                        sensitivity_rate = (
                            min_value / rnm_ust if rnm_ust > 0 else float("inf")
                        )
                else:
                    # Если смещения нет, используем стандартный расчет
                    sensitivity_rate = (
                        min_value / rnm_ust if rnm_ust > 0 else float("inf")
                    )
            else:
                # Для РТНП используем стандартный расчет
                sensitivity_rate = (
                    min_value / rnm_ust if rnm_ust > 0 else float("inf")
                )

            # Проверяем условие k_ч ≥ 1.5
            # ВАЖНО: из-за двоичной арифметики float (и округления в логах до 2 знаков)
            # значение может печататься как 1.50, но быть 1.499999..., что дает "НЕТ".
            # Поэтому используем небольшой допуск.
            k_ch_required = 1.5
            eps = 1e-9
            is_sensitive = sensitivity_rate + eps >= k_ch_required

            # Для отладки: проверяем единицы измерения
            unit = "кВ" if target_fault_value == "RNM_U0" else "А"
            self._log(
                f"[DEBUG] РНМ чувствительность ({target_fault_value}): "
                f"min_value={min_value:.4f} {unit}, уставка={rnm_ust:.4f} {unit}, "
                f"k_ч={sensitivity_rate:.4f}, требуется ≥ {k_ch_required}, "
                f"проходит={'ДА' if is_sensitive else 'НЕТ'}"
            )

            return round(sensitivity_rate, 2)

        except Exception as e:
            self._log(f"[ERROR] Ошибка при расчете РНМ чувствительности: {e}")
            import traceback

            self._log(f"[ERROR] Traceback: {traceback.format_exc()}")
            return None

    def _get_min_rtnp_setting_for_analysis(
        self, protection_half_set
    ) -> Optional[float]:
        """
        Находит минимальный ток срабатывания 3I0_МИН_СРАБ для анализа чувствительности.

        Это минимальное значение уставки РТНП/3I0_M0 среди всех полукомплектов защиты линии.

        Args:
            protection_half_set: Полукомплект защиты (для получения линии)

        Returns:
            Минимальное значение уставки РТНП в А или None
        """
        # Получаем линию из полукомплекта
        line = protection_half_set.line
        protection_half_sets = line.protection_half_sets.all()

        # Находим компонент РТНП/3I0_M0
        try:
            rtnp_component = Component.objects.get(setting_designation="РТНП/3I0_M0")
        except Component.DoesNotExist:
            self._log(
                "[WARNING] Компонент РТНП/3I0_M0 не найден в БД"
            )
            return None

        # Ищем все расчеты РТНП для всех полукомплектов данной линии
        rtnp_settings = SettingsCalculation.objects.filter(
            calculation_meta=self.calculation_meta,
            component=rtnp_component,
            protection_half_set__in=protection_half_sets
        )

        min_value = None
        for setting in rtnp_settings:
            if setting.result_value and (min_value is None or setting.result_value < min_value):
                min_value = setting.result_value

        if min_value is None:
            self._log(
                "[WARNING] Не найдены расчеты РТНП/3I0_M0 для определения минимального тока 3I0_МИН_СРАБ"
            )
        else:
            self._log(
                f"[DEBUG] Найден минимальный ток 3I0_МИН_СРАБ={min_value:.3f} А "
                f"для линии {getattr(line, 'pf_name', None) or str(line)}"
            )

        return min_value

    def _calculate_3i0_sensitivity(
        self,
        settings_calculation: SettingsCalculation,
        protection_half_set,
        fault_calculations: QuerySet[FaultCalculation],
    ) -> Optional[float]:
        """
        Рассчитывает чувствительность для органа 3I0 ОТКЛ.

        Формула: K_ч = 3I0_КЗ_МИН / 3I0_ОТКЛ ≥ 1.5

        где:
        - 3I0_КЗ_МИН - минимальный ток КЗ нулевой последовательности при КЗ на землю на противоположной стороне ЛЭП
        - 3I0_ОТКЛ - уставка отключающего токового органа
        - K_ч должен быть ≥ 1.5

        :param settings_calculation: Объект SettingsCalculation с результатом 3I0 ОТКЛ
        :param protection_half_set: Полукомплект защиты
        :param fault_calculations: QuerySet всех КЗ на землю (К(1)) на противоположной стороне
        :return: Коэффициент чувствительности или None при ошибке
        """
        try:
            # Получаем значение уставки 3I0 ОТКЛ
            i0_otkl_ust = settings_calculation.result_value
            if i0_otkl_ust is None or i0_otkl_ust == 0:
                self._log(f"[WARNING] Уставка 3I0 ОТКЛ равна нулю или отсутствует")
                return None

            # Фильтруем КЗ на противоположной стороне (исключаем ответвления)
            opposite_end_faults = fault_calculations.exclude(
                fault_location__startswith="Ответвление:"
            )

            self._log(
                f"[DEBUG] Специальная обработка для 3I0: поиск минимального значения среди {opposite_end_faults.count()} КЗ на противоположной стороне"
            )

            # Находим минимальный ток КЗ нулевой последовательности из всех КЗ на землю на противоположной стороне
            min_3i0_kz = None
            min_fault_calc = None

            for fault_calculation in opposite_end_faults:
                fault_values = fault_calculation.fault_values
                if not fault_values:
                    continue

                i0_value = fault_values.get("3I0")
                if i0_value:
                    i0_a = float(i0_value)  # Значения уже в А
                    # Игнорируем нулевые/отрицательные значения (обычно это невалидный/обесточенный подрежим)
                    if i0_a <= 0:
                        continue
                    self._log(
                        f"[DEBUG]   КЗ {fault_calculation.fault_type} на {fault_calculation.fault_location}, "
                        f"подрежим '{fault_calculation.network_topology}': 3I0 = {i0_a:.3f} А"
                    )
                    if min_3i0_kz is None or i0_a < min_3i0_kz:
                        min_3i0_kz = i0_a
                        min_fault_calc = fault_calculation

            if min_3i0_kz is None:
                self._log(
                    f"[WARNING] Не найдены значения 3I0 для расчета чувствительности 3I0 ОТКЛ на противоположной стороне"
                )
                return None

            if min_fault_calc:
                self._log(
                    f"[DEBUG] Минимальное значение 3I0 = {min_3i0_kz:.3f} А "
                    f"(КЗ {min_fault_calc.fault_type} на {min_fault_calc.fault_location}, "
                    f"подрежим '{min_fault_calc.network_topology}')"
                )

            # Коэффициент чувствительности = 3I0_КЗ_МИН / 3I0_ОТКЛ
            # K_ч должен быть ≥ 1.5
            sensitivity_rate = (
                min_3i0_kz / i0_otkl_ust if i0_otkl_ust > 0 else float("inf")
            )

            # Проверяем условие k_ч ≥ 1.5
            k_ch_required = 1.5
            is_sensitive = sensitivity_rate >= k_ch_required

            self._log(
                f"[DEBUG] 3I0 ОТКЛ чувствительность: "
                f"3I0_КЗ_МИН={min_3i0_kz:.3f} А, уставка={i0_otkl_ust:.2f} А, "
                f"K_ч={sensitivity_rate:.2f}, требуется ≥ {k_ch_required}, "
                f"проходит={'ДА' if is_sensitive else 'НЕТ'}"
            )

            return round(sensitivity_rate, 2)
        except Exception as e:
            self._log(f"[ERROR] Ошибка при расчете 3I0 ОТКЛ чувствительности: {e}")
            import traceback

            self._log(f"[ERROR] Traceback: {traceback.format_exc()}")
            return None

    @staticmethod
    def _calculate_manipulation_sensitivity(
        settings_calculation: SettingsCalculation, protection_half_set, i1_fault: float
    ) -> float:
        """
        Рассчитывает чувствительность для органа манипуляции при несимметричных КЗ.

        Формула: K_ч ман = I1_КЗ / (K_МАН * I2_БЛОК)
        где:
        - I1_КЗ - ток прямой последовательности при КЗ типа К(1) или К(1,1)
        - K_МАН - коэффициент комбинированного фильтра токов (уставка K МАН)
        - I2_БЛОК - уставка блокирующего токового органа с пуском по току обратной последовательности

        Коэффициент чувствительности должен быть не менее 1.3.

        :param settings_calculation: Объект SettingsCalculation для K МАН.
        :param protection_half_set: Полукомплект защиты.
        :param i1_fault: Ток прямой последовательности I1 при КЗ типа К(1) или К(1,1) (в А).
        :return: Коэффициент чувствительности.
        """
        # Получаем значение уставки K МАН (коэффициент комбинированного фильтра)
        k_man = settings_calculation.result_value
        if k_man is None or k_man == 0:
            FaultCalculationService._log(f"[WARNING] Уставка K МАН не найдена или равна 0")
            return 0.0

        # Получаем I2 БЛОК для того же полукомплекта
        from core.models import Component

        try:
            i2_block_component = Component.objects.get(
                setting_designation="I2 БЛОК")
            i2_block_calculation = SettingsCalculation.objects.filter(
                calculation_meta=settings_calculation.calculation_meta,
                protection_half_set=protection_half_set,
                component=i2_block_component,
            ).first()

            if not i2_block_calculation or not i2_block_calculation.result_value:
                FaultCalculationService._log(
                    f"[WARNING] Уставка I2 БЛОК не найдена для полукомплекта {protection_half_set}"
                )
                return 0.0

            i2_block_a = i2_block_calculation.result_value  # в А (primary_value)
        except Component.DoesNotExist:
            FaultCalculationService._log(f"[WARNING] Компонент I2 БЛОК не найден")
            return 0.0

        # Проверка на деление на ноль
        if i2_block_a == 0:
            return 0.0

        # result_value хранит primary_value (в А), не нужно переводить
        i2_block_a = float(i2_block_a) if i2_block_a else 0.0

        # Формула: K_ч ман = I1_КЗ / (K_МАН * I2_БЛОК)
        # где все значения в А
        # Для К МАН используются К(1) и К(1,1), поэтому используем I1 из этих КЗ
        denominator = k_man * i2_block_a
        if denominator == 0:
            return 0.0

        sensitivity_rate = (i1_fault * 2) / (denominator / 2)
        sensitivity_rate = round(sensitivity_rate, 2)

        # Проверяем условие k_ч ≥ 1.3
        k_ch_required = 1.3
        is_sensitive = sensitivity_rate >= k_ch_required

        # Для логирования вычисляем вторичное значение (мА) для отображения
        i2_block_secondary = i2_block_a * 1000 if i2_block_a else 0.0  # А → мА для отображения

        FaultCalculationService._log(
            f"[DEBUG] K МАН чувствительность: "
            f"I1_КЗ={i1_fault:.2f} А, K_МАН={k_man:.2f}, I2_БЛОК={i2_block_a:.3f} А ({i2_block_secondary:.0f} мА), "
            f"K_ч={sensitivity_rate:.2f}, требуется ≥ {k_ch_required}, "
            f"проходит={'ДА' if is_sensitive else 'НЕТ'}"
        )

        return sensitivity_rate
