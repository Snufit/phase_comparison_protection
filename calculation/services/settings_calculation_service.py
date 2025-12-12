from math import sqrt
from typing import Callable, Dict, Tuple

from calculation.models import CalculationMeta, FaultCalculation, SettingsCalculation
from core.models import Component, ProtectionHalfSet


class SettingsCalculationService:
    def __init__(
        self, calculation_meta: CalculationMeta, calculation_factors: Dict[str, float]
    ):
        # Определяем словарь коэффициентов
        self.calculation_factors = calculation_factors or {}

        # Определяем мета-данные расчета
        self.calculation_meta = calculation_meta

        # Определяем линию и полукомплекты защиты
        self.line = calculation_meta.line
        self.protection_half_sets = self.line.protection_half_sets.all()

        # Используем параметры ТТ/ТН из линии напрямую
        # Для ТТ: используем ratio из связанного трансформатора
        self.current_transformer_ratio = self.line.ct.ratio if self.line.ct else 1000
        # Для ТН: используем calculate_ratio с напряжением ЛЭП из PowerFactory
        # (ratio в VoltageTransformer вычисляется на основе primary_voltage,
        # но для использования с ЛЭП нужно использовать напряжение ЛЭП)
        self.voltage_transformer_factor = (
            self.line.vt.calculate_ratio(self.line.voltage_level)
            if self.line.vt and self.line.voltage_level
            else 5000
        )

        # Коэффициент чувствительности токовых органов
        self.current_sensitivity_rate = 2

        # Карта расчетных функций органов
        self.CALCULATION_MAP = {
            "IЛ БЛОК": self.calculate_il_block,
            "IЛ ОТКЛ": self.calculate_il_break,
            "I2 БЛОК": self.calculate_i2_block,
            "I2 ОТКЛ": self.calculate_i2_break,
            "DI1 БЛОК": self.calculate_di1_block,
            "DI1 ОТКЛ": self.calculate_di1_break,
            "DI2 БЛОК": self.calculate_i2_block,
            "DI2 ОТКЛ": self.calculate_i2_break,
            "U2 БЛОК": self.calculate_u2_block,
            "U2 ОТКЛ": self.calculate_u2_break,
            "K МАН": self.calculate_manipulation_factor,
            "УГОЛ БЛОК": self.calculate_blocking_angle,
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
        # Первичное значение - это результат расчета
        primary_value = result_value

        # Определяем тип органа для правильного перевода во вторичные величины
        setting_designation = component.setting_designation

        # Для токовых органов (IЛ, I2, DI1, DI2, K МАН) делим на коэффициент ТТ
        if any(
            prefix in setting_designation
            for prefix in ["IЛ", "I2", "DI1", "DI2", "K МАН"]
        ):
            secondary_value = primary_value / self.current_transformer_ratio
        # Для напряженческих органов (U2) делим на коэффициент ТН
        elif "U2" in setting_designation:
            secondary_value = primary_value / self.voltage_transformer_factor
        # Для угла блокировки значения одинаковые
        elif "УГОЛ" in setting_designation:
            secondary_value = primary_value
        else:
            # По умолчанию считаем токовым органом
            secondary_value = primary_value / self.current_transformer_ratio

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
        calculation_function = self.CALCULATION_MAP.get(component.setting_designation)
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

    # refactor
    def calculate_manipulation_factor(self) -> Tuple[float, Dict[str, float]]:
        manipulation_grading_factor = self.calculation_factors.get(
            "manipulation_grading_factor", 1.5
        )
        fault_calculations = FaultCalculation.objects.filter(
            protection_half_set__in=self.protection_half_sets,
            fault_type__in=["К(1)", "К(1,1)"],
        )
        manipulation_factors = []
        for fault_calculation in fault_calculations:
            if fault_calculation.fault_type == "К(1,1)":
                manipulation_factor = manipulation_grading_factor * (
                    (
                        fault_calculation.fault_values.get("I1")
                        + self.line.current_capacity
                    )
                    / 1
                )
                manipulation_factors.append(manipulation_factor)
            elif fault_calculation.fault_type == "К(1)":
                manipulation_factor = manipulation_grading_factor * (
                    self.line.current_capacity / 1
                )
                manipulation_factors.append(manipulation_factor)
        max_manipulating_factor = max(manipulation_factors)
        calculation_factors = {"Коэффициент отстройки": manipulation_grading_factor}
        return max_manipulating_factor, calculation_factors

    def calculate_il_block(self) -> Tuple[float, Dict[str, float]]:
        il_grading_factor = self.calculation_factors.get("il_grading_factor", 1.3)
        il_reset_factor = self.calculation_factors.get("il_reset_factor", 0.9)
        il_block_value = (
            sqrt(3) * il_grading_factor / il_reset_factor * self.line.current_capacity
        )
        calculation_factors = {
            "Коэффициент отстройки": il_grading_factor,
            "Коэффициент возврата": il_reset_factor,
        }
        return il_block_value, calculation_factors

    def calculate_il_break(self) -> Tuple[float, Dict[str, float]]:
        il_block_value = self.calculate_il_block()[0]
        il_matching_factor = self.calculation_factors.get("il_matching_factor", 1.4)
        il_break_value = il_matching_factor * il_block_value
        calculation_factors = {"Коэффициент согласования": il_matching_factor}
        return il_break_value, calculation_factors

    def calculate_di1_break(self) -> Tuple[float, Dict[str, float]]:
        fault_calculations = FaultCalculation.objects.filter(
            protection_half_set__in=self.protection_half_sets, fault_type="К(3)"
        )

        pos_sequence_currents = []
        for fault_calculation in fault_calculations:
            pos_sequence_current = fault_calculation.fault_values.get("I1")
            if pos_sequence_current != 0:
                pos_sequence_currents.append(fault_calculation.fault_values.get("I1"))

        min_i1 = min(pos_sequence_currents)
        di1_break_value = min_i1 / self.current_sensitivity_rate
        calculation_factors = {
            "Коэффициент чувствительности": self.current_sensitivity_rate
        }

        return di1_break_value, calculation_factors

    def calculate_di1_block(self) -> Tuple[float, Dict[str, float]]:
        di1_break_value = self.calculate_di1_break()[0]
        di1_matching_factor = self.calculation_factors.get("di1_matching_factor", 1.4)
        di1_block_value = di1_break_value / di1_matching_factor
        calculation_factors = {"Коэффициент согласования": di1_matching_factor}
        return di1_block_value, calculation_factors

    def calculate_i2_block(self) -> Tuple[float, Dict[str, float]]:
        i2_imbalance_factor = self.calculation_factors.get("i2_imbalance_factor", 0.05)
        i2_grading_factor = self.calculation_factors.get("i2_grading_factor", 1.3)
        i2_reset_factor = self.calculation_factors.get("i2_reset_factor", 0.9)
        i2_imbalance_current = i2_imbalance_factor * self.line.current_capacity
        i2_block_value = i2_grading_factor / i2_reset_factor * i2_imbalance_current
        calculation_factors = {
            "Коэффициент небаланса": i2_imbalance_factor,
            "Коэффициент отстройки": i2_grading_factor,
            "Коэффициент возврата": i2_reset_factor,
        }
        return i2_block_value, calculation_factors

    def calculate_i2_break(self) -> Tuple[float, Dict[str, float]]:
        i2_block_value = self.calculate_i2_block()[0]
        i2_matching_factor = self.calculation_factors.get("i2_matching_factor", 1.4)
        i2_break_value = i2_matching_factor * i2_block_value
        calculation_factors = {"Коэффициент согласования": i2_matching_factor}
        return i2_break_value, calculation_factors

    # hardcode
    def calculate_u2_block(self) -> Tuple[float, Dict[str, float]]:
        """Рассчитывает уставку блокировки по напряжению обратной последовательности."""
        u2_grading_factor = self.calculation_factors.get("u2_grading_factor", 1.3)
        u2_reset_factor = self.calculation_factors.get("u2_reset_factor", 0.9)
        u2_imbalance_voltage = self.calculation_factors.get("u2_imbalance_voltage", 1.5)

        # Используем уже вычисленный коэффициент трансформации ТН
        vt_ratio = self.voltage_transformer_factor

        u2_block_value = (
            u2_grading_factor
            / u2_reset_factor
            * (u2_imbalance_voltage * vt_ratio)
            / 1000
        )
        calculation_factors = {
            "Коэффициент отстройки": u2_grading_factor,
            "Коэффициент возврата": u2_reset_factor,
            "Напряжение небаланса": u2_imbalance_voltage,
        }
        return u2_block_value, calculation_factors

    def calculate_u2_break(self) -> Tuple[float, Dict[str, float]]:
        u2_block_value = self.calculate_u2_block()[0]
        u2_matching_factor = self.calculation_factors.get("u2_matching_factor", 2.0)
        u2_break_value = u2_matching_factor * u2_block_value
        calculation_factors = {"Коэффициент согласования": u2_matching_factor}
        return u2_break_value, calculation_factors

    def run(self) -> None:
        for protection_half_set in self.protection_half_sets:
            components = protection_half_set.protection_device.components.all()

            for component in components:
                calculation_function = self.get_calculation_function(component)

                if calculation_function:
                    result, factors = calculation_function()
                    result = round(result, 0)
                    self.save_result_to_db(
                        protection_half_set=protection_half_set,
                        component=component,
                        calculation_factors=factors,
                        result_value=result,
                    )

                else:
                    print(f"\tОтсутствует расчетный модуль для органа {component}")
