"""
Карта КЗ для проверки чувствительности органов защиты.

Определяет:
- Типы КЗ, которые необходимо моделировать для каждого органа
- Места выполнения КЗ (противоположный конец, ответвления)
- Формулы расчета чувствительности
- Требуемые значения коэффициентов чувствительности
"""

from typing import Dict, List, Optional
from math import sqrt

# Типы КЗ в PowerFactory
POWERFACTORY_FAULT_TYPES = {
    "3psc": "К(3)",  # Трехфазное КЗ
    "2psc": "К(2)",  # Двухфазное КЗ
    "2pgf": "К(1,1)",  # Двухфазное КЗ на землю
    "spgf": "К(1)",  # Однофазное КЗ на землю
}

# Места выполнения КЗ
FAULT_LOCATION_OPPOSITE_END = "opposite_end"  # Противоположный конец ЛЭП
FAULT_LOCATION_BRANCHES = "branches"  # Шины ПС ответвлений


class SensitivityFaultMap:
    """
    Карта КЗ для проверки чувствительности органов защиты.

    Определяет для каждого органа:
    - fault_types: типы КЗ для моделирования
    - fault_locations: места выполнения КЗ
    - fault_value: значение из результатов КЗ (I1, I2, U2, 3I0, 3U0, R)
    - formula: описание формулы расчета
    - k_ch_required: требуемое значение коэффициента чувствительности
    - k_sx: коэффициент схемы (для IЛ ОТКЛ)
    - use_min_value: использовать минимальное значение из всех КЗ
    - exclude_branches: исключать КЗ на ответвлениях
    """

    SENSITIVITY_FAULT_MAP: Dict[str, Dict] = {
        "IЛ ОТКЛ": {
            "description": "Органы с пуском по векторной разности фазных токов",
            "fault_types": ["К(3)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END],
            "fault_value": "I1",
            "formula": "k_ч = (k_сх * I_1^(К(3))) / IЛ ОТКЛ",
            "k_sx": sqrt(3),  # Коэффициент схемы для векторной разности
            "k_ch_required": 2.0,
            "use_min_value": False,
            "exclude_branches": True,
        },
        "DI1 ОТКЛ": {
            "description": "Органы с пуском по приращению токов прямой последовательности",
            "fault_types": ["К(3)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END],
            "fault_value": "I1",
            "formula": "k_ч = I_1^(К(3)) / DI1 ОТКЛ",
            "k_sx": 1.0,
            "k_ch_required": 2.0,
            "use_min_value": False,
            "exclude_branches": True,
        },
        "I2 ОТКЛ": {
            "description": "Органы с пуском по току обратной последовательности",
            "fault_types": ["К(2)", "К(1,1)", "К(1)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END],
            "fault_value": "I2",
            "formula": "k_ч = I_2^КЗ / I2 ОТКЛ",
            "k_sx": 1.0,
            "k_ch_required": 2.0,
            "use_min_value": False,
            "exclude_branches": True,
        },
        "DI2 ОТКЛ": {
            "description": "Органы с пуском по приращению тока обратной последовательности",
            "fault_types": ["К(2)", "К(1,1)", "К(1)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END],
            "fault_value": "I2",
            "formula": "k_ч = (I_2^КЗ - I_2н.р) / DI2 ОТКЛ",
            "k_sx": 1.0,
            "k_ch_required": 2.0,
            "use_min_value": False,
            "exclude_branches": True,
            "i2_nr": 0.0,  # Ток обратной последовательности в нагрузочном режиме
        },
        "U2 ОТКЛ": {
            "description": "Органы с пуском по напряжению обратной последовательности",
            "fault_types": ["К(2)", "К(1,1)", "К(1)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END],
            "fault_value": "U2",
            "formula": "k_ч = U_2^КЗ / U2 ОТКЛ",
            "k_sx": 1.0,
            "k_ch_required": 2.0,
            "use_min_value": False,
            "exclude_branches": True,
        },
        "3I0 ОТКЛ": {
            "description": "Орган по току нулевой последовательности",
            "fault_types": ["К(1)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END],
            "fault_value": "3I0",
            "formula": "k_ч = 3I0_КЗ_МИН / 3I0 ОТКЛ",
            "k_sx": 1.0,
            "k_ch_required": 2.0,
            "use_min_value": True,  # Использовать минимальное значение
            "exclude_branches": True,
        },
        "РТНП/3I0_M0": {
            "description": "Реле направления мощности нулевой последовательности по току",
            "fault_types": ["К(1)"],
            "fault_locations": [FAULT_LOCATION_BRANCHES],
            "fault_value": "RNM_I0",  # Специальное значение для РНМ
            "formula": "k_ч = 3I0_мин / 3I0 РНМ",
            "k_sx": 1.0,
            # Для органов РНМ принимаем k_ч = 1.5 (см. расчёт/логи и методику)
            "k_ch_required": 1.5,
            "use_min_value": True,  # Использовать минимальное значение
            "exclude_branches": False,  # Только на ответвлениях
            "requires_branches": True,  # Только для ЛЭП с ответвлениями
            "condition": "При отключении ЛЭП с противоположной стороны (режим транзита)",
        },
        "РННП/3U0_M0": {
            "description": "Реле направления мощности нулевой последовательности по напряжению",
            "fault_types": ["К(1)"],
            "fault_locations": [FAULT_LOCATION_BRANCHES],
            "fault_value": "RNM_U0",  # Специальное значение для РНМ
            "formula": "k_ч = 3U0_мин / 3U0 РНМ",
            "k_sx": 1.0,
            # Для органов РНМ принимаем k_ч = 1.5 (см. расчёт/логи и методику)
            "k_ch_required": 1.5,
            "use_min_value": True,  # Использовать минимальное значение
            "exclude_branches": False,  # Только на ответвлениях
            "requires_branches": True,  # Только для ЛЭП с ответвлениями
            "condition": "При отключении ЛЭП с противоположной стороны (режим транзита)",
        },
        "R ОТКЛ": {
            "description": "Орган по активному сопротивлению (отключение)",
            "fault_types": ["К(3)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END, FAULT_LOCATION_BRANCHES],
            "fault_value": "R",  # Специальное значение
            "formula": "R_чувст = 1.5 * (max(R_max_отв или R1_уд * L) + R_дуги * (1 + (I1^(3)_2 / I1^(3)_1)))",
            "check_formula": "R_чувст ≤ 0.7 * R_ОТКЛ_уст",
            "k_sx": 1.0,
            "k_ch_required": 1.0,  # После приведения к общему виду: k_ч = (0.7 * R_ОТКЛ) / R_чувст ≥ 1.0
            "use_min_value": False,
            "exclude_branches": False,  # Нужны оба места
            "r_dugi": 0.15,  # Сопротивление дуги (Ом)
        },
        "R ОТВ": {
            "description": "Орган по активному сопротивлению (ответвления)",
            "fault_types": ["К(3)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END, FAULT_LOCATION_BRANCHES],
            "fault_value": "R",  # Специальное значение
            "formula": "R_чувст = 1.5 * (max(R_max_отв или R1_уд * L) + R_дуги * (1 + (I1^(3)_2 / I1^(3)_1)))",
            "check_formula": "R_чувст ≤ 0.7 * R_ОТКЛ_уст",
            "k_sx": 1.0,
            "k_ch_required": 1.0,  # После приведения к общему виду: k_ч = (0.7 * R_ОТКЛ) / R_чувст ≥ 1.0
            "use_min_value": False,
            "exclude_branches": False,  # Нужны оба места
            "r_dugi": 0.15,  # Сопротивление дуги (Ом)
        },
        # Органы, которые не проверяются на чувствительность
        "K МАН": {
            "description": "Орган манипуляции",
            "fault_types": ["К(1)", "К(1,1)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END],
            "fault_value": "I1",
            "formula": "k_ч проверяется для К(1) и К(1,1) согласно расчету коэффициента манипуляции",
            "k_ch_required": 1.3,
            "check_sensitivity": True,
            "exclude_branches": True,
            "use_min_value": False,  # Не используем минимальное значение, проверяем каждое КЗ отдельно
        },
        "К МАН": {
            "description": "Орган манипуляции (кириллица)",
            "fault_types": ["К(1)", "К(1,1)"],
            "fault_locations": [FAULT_LOCATION_OPPOSITE_END],
            "fault_value": "I1",
            "formula": "k_ч проверяется для К(1) и К(1,1) согласно расчету коэффициента манипуляции",
            "k_ch_required": 1.3,
            "check_sensitivity": True,
            "exclude_branches": True,
            "use_min_value": False,  # Не используем минимальное значение, проверяем каждое КЗ отдельно
        },
        "УГОЛ БЛОК": {
            "description": "Орган сравнения фаз",
            "check_sensitivity": False,  # Не проверяется
        },
    }

    @classmethod
    def get_fault_map(cls, organ_name: str) -> Optional[Dict]:
        """
        Получает карту КЗ для указанного органа.

        :param organ_name: Название органа защиты
        :return: Словарь с параметрами карты КЗ или None, если орган не найден
        """
        return cls.SENSITIVITY_FAULT_MAP.get(organ_name)

    @classmethod
    def should_check_sensitivity(cls, organ_name: str) -> bool:
        """
        Проверяет, нужно ли проверять чувствительность для указанного органа.

        :param organ_name: Название органа защиты
        :return: True, если нужно проверять чувствительность, False иначе
        """
        fault_map = cls.get_fault_map(organ_name)
        if fault_map is None:
            return False
        return fault_map.get("check_sensitivity", True)

    @classmethod
    def get_fault_types_for_organ(cls, organ_name: str) -> List[str]:
        """
        Получает типы КЗ для указанного органа.

        :param organ_name: Название органа защиты
        :return: Список типов КЗ
        """
        fault_map = cls.get_fault_map(organ_name)
        if fault_map is None:
            return []
        return fault_map.get("fault_types", [])

    @classmethod
    def get_fault_locations_for_organ(cls, organ_name: str) -> List[str]:
        """
        Получает места выполнения КЗ для указанного органа.

        :param organ_name: Название органа защиты
        :return: Список мест выполнения КЗ
        """
        fault_map = cls.get_fault_map(organ_name)
        if fault_map is None:
            return []
        return fault_map.get("fault_locations", [])

    @classmethod
    def get_powerfactory_fault_types(cls, organ_name: str) -> List[str]:
        """
        Получает типы КЗ в формате PowerFactory для указанного органа.

        :param organ_name: Название органа защиты
        :return: Список типов КЗ в формате PowerFactory (например, ['3psc', 'spgf'])
        """
        fault_types = cls.get_fault_types_for_organ(organ_name)
        powerfactory_types = []
        for pf_type, ru_type in POWERFACTORY_FAULT_TYPES.items():
            if ru_type in fault_types:
                powerfactory_types.append(pf_type)
        return powerfactory_types

    @classmethod
    def requires_branches(cls, organ_name: str) -> bool:
        """
        Проверяет, требуются ли ответвления для проверки чувствительности.

        :param organ_name: Название органа защиты
        :return: True, если требуются ответвления
        """
        fault_map = cls.get_fault_map(organ_name)
        if fault_map is None:
            return False
        return fault_map.get("requires_branches", False)

    @classmethod
    def get_all_organs_requiring_faults(cls) -> List[str]:
        """
        Получает список всех органов, для которых нужно моделировать КЗ.

        :return: Список названий органов
        """
        organs = []
        for organ_name, fault_map in cls.SENSITIVITY_FAULT_MAP.items():
            if fault_map.get("check_sensitivity", True):
                if fault_map.get("fault_types"):
                    organs.append(organ_name)
        return organs

    @classmethod
    def get_all_required_fault_types(cls) -> List[str]:
        """
        Получает все типы КЗ, которые необходимо моделировать.

        :return: Список типов КЗ в формате PowerFactory
        """
        required_types = set()
        for organ_name in cls.get_all_organs_requiring_faults():
            types = cls.get_powerfactory_fault_types(organ_name)
            required_types.update(types)
        return sorted(list(required_types))

    @classmethod
    def get_summary(cls) -> Dict:
        """
        Получает сводную информацию о карте КЗ.

        :return: Словарь со сводной информацией
        """
        summary = {
            "total_organs": len(cls.SENSITIVITY_FAULT_MAP),
            "organs_with_sensitivity_check": len(cls.get_all_organs_requiring_faults()),
            "organs_without_sensitivity_check": [],
            "required_fault_types": cls.get_all_required_fault_types(),
            "fault_types_mapping": POWERFACTORY_FAULT_TYPES,
        }

        for organ_name, fault_map in cls.SENSITIVITY_FAULT_MAP.items():
            if not fault_map.get("check_sensitivity", True):
                summary["organs_without_sensitivity_check"].append(organ_name)

        return summary
