from math import sqrt
from typing import Callable, Dict, List, Optional, Union

from django.db.models import QuerySet

from calculation.models import (CalculationMeta, FaultCalculation,
                                SensitivityAnalysis, SettingsCalculation)
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

        self.SENSITIVITY_HANDLERS: Dict[
            str, Dict[str, Union[Callable[[float, float], float], List[str], str]]
        ] = {
            "IЛ ОТКЛ": {
                "function": self._calculate_phase_current_diff_sensitivity,
                "fault_types": ["К(3)"],
                "fault_value": "I1",
            },
            "I2 ОТКЛ": {
                "function": self._calculate_current_sensitivity,
                "fault_types": ["К(2)", "К(1,1)", "К(1)"],
                "fault_value": "I2",
            },
            "DI1 ОТКЛ": {
                "function": self._calculate_current_sensitivity,
                "fault_types": ["К(3)"],
                "fault_value": "I1",
            },
            "DI2 ОТКЛ": {
                "function": self._calculate_current_sensitivity,
                "fault_types": ["К(2)", "К(1,1)", "К(1)"],
                "fault_value": "I2",
            },
            "U2 ОТКЛ": {
                "function": self._calculate_current_sensitivity,
                "fault_types": ["К(2)", "К(1,1)", "К(1)"],
                "fault_value": "U2",
            },
        }

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

                for fault_calculation in fault_calculations:
                    fault_value = fault_calculation.fault_values.get(target_fault_value)
                    sensitivity_rate = sensitivity_analysis_function(
                        result_value, fault_value
                    )
                    sensitivity_rate = round(sensitivity_rate, 2)
                    self._save_result_to_db(
                        settings_calculation=settings_calculation,
                        fault_calculation=fault_calculation,
                        sensitivity_rate=sensitivity_rate,
                    )

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
        result_value: float, fault_value: float
    ) -> float:
        """
        :param result_value: Величина уставки.
        :param fault_value: Величина тока КЗ.
        :return: Коэффициент чувствительности.
        """

        sensitivity_rate = sqrt(3) * fault_value / result_value
        return sensitivity_rate

    @staticmethod
    def _calculate_current_sensitivity(
        result_value: float, fault_value: float
    ) -> float:
        """
        :param result_value: Величина уставки.
        :param fault_value: Величина тока КЗ.
        :return: Коэффициент чувствительности.
        """

        sensitivity_rate = fault_value / result_value
        return sensitivity_rate
