# calculation/services/device_components_map.py

"""
Карта органов защиты для каждого производителя и модели устройства.
Структура:
{
    "Производитель": {
        "Модель устройства": {
            "Орган": {
                "description": "Описание",
                "calculation_function": "имя_функции" или None
            }
        }
    }
}
"""

DEVICE_COMPONENTS_MAP = {
    "ООО НПП «ЭКРА»": {
        "ШЭ 2607 081/ШЭ 2710 58х": {
            "IЛ БЛОК": {
                "description": "Уставка блокирующего ИО по вектору разности фазных токов",
                "calculation_function": "calculate_il_block"
            },
            "IЛ ОТКЛ": {
                "description": "Уставка отключающего ИО по вектору разности фазных токов",
                "calculation_function": "calculate_il_break"
            },
            "I2 БЛОК": {
                "description": "Уставка блокирующего ИО тока обратной последовательности",
                "calculation_function": "calculate_i2_block"
            },
            "I2 ОТКЛ": {
                "description": "Уставка отключающего ИО тока обратной последовательности",
                "calculation_function": "calculate_i2_break"
            },
            "3I0 БЛОК": {
                "description": "Уставка блокирующего ИО тока нулевой последовательности",
                "calculation_function": None  # Функция еще не реализована
            },
            "3I0 ОТКЛ": {
                "description": "Уставка отключающего ИО тока нулевой последовательности",
                "calculation_function": None
            },
            "DI1 БЛОК": {
                "description": "Уставка блокирующего токового органа с пуском по приращению прямой последовательности",
                "calculation_function": "calculate_di1_block"
            },
            "DI1 ОТКЛ": {
                "description": "Уставка отключающего токового органа с пуском по приращению прямой последовательности",
                "calculation_function": "calculate_di1_break"
            },
            "DI2 БЛОК": {
                "description": "Уставка блокирующего токового органа с пуском по приращению обратной последовательности",
                "calculation_function": "calculate_i2_block"  # Использует ту же функцию, что и I2 БЛОК
            },
            "DI2 ОТКЛ": {
                "description": "Уставка отключающего токового органа с пуском по приращению обратной последовательности",
                "calculation_function": "calculate_i2_break"
            },
            "U2 БЛОК": {
                "description": "Уставка блокирующего органа с пуском по напряжению обратной последовательности",
                "calculation_function": "calculate_u2_block"
            },
            "U2 ОТКЛ": {
                "description": "Уставку отключающего органа по напряжению обратной последовательности",
                "calculation_function": "calculate_u2_break"
            },
            "К МАН": {
                "description": "Орган манипуляции",
                "calculation_function": "calculate_manipulation_factor"
            },
            "УГОЛ БЛОК": {
                "description": "Орган сравнения фаз",
                "calculation_function": "calculate_blocking_angle"
            },
            "РТНП/3I0_M0": {
                "description": "Уставка органа направления мощности нулевой последовательности по току",
                "calculation_function": None
            },
            "РННП/3U0_M0": {
                "description": "Уставка органа направления мощности нулевой последовательности по напряжению",
                "calculation_function": None
            },
            "R ОТКЛ": {
                "description": "Уставка по активной составляющей",
                "calculation_function": None
            },
            "X ОТКЛ": {
                "description": "Уставка по реактивной составляющей сопротивления",
                "calculation_function": None
            },
            "R ОТВ": {
                "description": "Уставка реле сопротивления по активной составляющей",
                "calculation_function": None
            },
            "X ОТВ": {
                "description": "Уставка по реактивной составляющей сопротивления",
                "calculation_function": None
            }
        }
    },
    "ООО «Релематика»": {
        "ТОР 300 ДФЗ 54X/ТОР 300 ДФЗ 65Х": {
            "I2 БЛОК": {
                "description": "Уставка блокирующего ИО тока обратной последовательности",
                "calculation_function": "calculate_i2_block"
            },
            "I2 ОТКЛ": {
                "description": "Уставка отключающего ИО тока обратной последовательности",
                "calculation_function": "calculate_i2_break"
            },
            "DI1 БЛОК": {
                "description": "Уставка блокирующего токового органа с пуском по приращению прямой последовательности",
                "calculation_function": "calculate_di1_block"
            },
            "DI1 ОТКЛ": {
                "description": "Уставка отключающего токового органа с пуском по приращению прямой последовательности",
                "calculation_function": "calculate_di1_break"
            },
            "DI2 БЛОК": {
                "description": "Уставка блокирующего токового органа с пуском по приращению обратной последовательности",
                "calculation_function": "calculate_i2_block"
            },
            "DI2 ОТКЛ": {
                "description": "Уставка отключающего токового органа с пуском по приращению обратной последовательности",
                "calculation_function": "calculate_i2_break"
            },
            "3I0 БЛОК": {
                "description": "Уставка блокирующего ИО тока нулевой последовательности",
                "calculation_function": None
            },
            "3I0 ОТКЛ": {
                "description": "Уставка отключающего ИО тока нулевой последовательности",
                "calculation_function": None
            },
            "I20 БЛОК": {
                "description": "Уставка блокирующего ИО суммы токов обратной и нулевой последовательностей",
                "calculation_function": None
            },
            "I20 ОТКЛ": {
                "description": "Уставка отключающего ИО суммы токов обратной и нулевой последовательностей",
                "calculation_function": None
            },
            "I1 БЛОК": {
                "description": "Уставка блокирующего ИО тока прямой последовательности",
                "calculation_function": None
            },
            "I1 ОТКЛ": {
                "description": "Уставка отключающего ИО тока прямой последовательности",
                "calculation_function": None
            },
            "Iф БЛОК": {
                "description": "Уставка блокирующего ИО фазного тока",
                "calculation_function": None
            },
            "Iф ОТКЛ": {
                "description": "Уставка отключающего ИО фазного тока",
                "calculation_function": None
            },
            "DIф БЛОК": {
                "description": "Уставка блокирующего токового органа с пуском по приращению фазных токов",
                "calculation_function": None
            },
            "DIф ОТКЛ": {
                "description": "Уставка отключающего токового органа с пуском по приращению фазных токов",
                "calculation_function": None
            },
            "Iфф БЛОК": {
                "description": "Уставка блокирующего ИО разности фазных токов",
                "calculation_function": "calculate_il_block"  # Аналогично IЛ БЛОК
            },
            "Iфф ОТКЛ": {
                "description": "Уставка отключающего ИО разности фазных токов",
                "calculation_function": "calculate_il_break"
            },
            "DIфф БЛОК": {
                "description": "Уставка блокирующего ИО аварийной составляющей разности фазных токов",
                "calculation_function": None
            },
            "DIфф ОТКЛ": {
                "description": "Уставка отключающего ИО аварийной составляющей разности фазных токов",
                "calculation_function": None
            },
            "К МАН": {
                "description": "Орган манипуляции",
                "calculation_function": "calculate_manipulation_factor"
            },
            "УГОЛ БЛОК": {
                "description": "Орган сравнения фаз",
                "calculation_function": "calculate_blocking_angle"
            },
            "Z СРАБ": {
                "description": "Реле сопротивления",
                "calculation_function": None
            },
            "РТНП/3I0_M0": {
                "description": "Уставка органа направления мощности нулевой последовательности по току",
                "calculation_function": None
            },
            "РННП/3U0_M0": {
                "description": "Уставка органа направления мощности нулевой последовательности по напряжению",
                "calculation_function": None
            },
            "3I0": {
                "description": "Уставка ИО тока нулевой последовательности с контролем направления мощности",
                "calculation_function": None
            },
            "УГОЛ мч0": {
                "description": "Угол максимальной чувствительности по нулевой последовательности",
                "calculation_function": None
            },
            "3I0f1": {
                "description": "ИО тока первой гармоники",
                "calculation_function": None
            },
            "3I0f2": {
                "description": "ИО тока второй гармоники",
                "calculation_function": None
            },
            "Kf2f1": {
                "description": "ИО отношения уровня тока второй гармоники к уровню тока первой гармоники",
                "calculation_function": None
            }
        }
    },
    "ООО «НПП Бреслер»": {
        "ШЛ 2604 (Бреслер 0411.01)": {
            "I2 БЛОК": {
                "description": "Уставка блокирующего ИО тока обратной последовательности",
                "calculation_function": "calculate_i2_block"
            },
            "I2 ОТКЛ": {
                "description": "Уставка отключающего ИО тока обратной последовательности",
                "calculation_function": "calculate_i2_break"
            },
            "DI1 БЛОК": {
                "description": "Уставка блокирующего токового органа с пуском по приращению прямой последовательности",
                "calculation_function": "calculate_di1_block"
            },
            "DI1 ОТКЛ": {
                "description": "Уставка отключающего токового органа с пуском по приращению прямой последовательности",
                "calculation_function": "calculate_di1_break"
            },
            "DI2 БЛОК": {
                "description": "Уставка блокирующего токового органа с пуском по приращению обратной последовательности",
                "calculation_function": "calculate_i2_block"
            },
            "DI2 ОТКЛ": {
                "description": "Уставка отключающего токового органа с пуском по приращению обратной последовательности",
                "calculation_function": "calculate_i2_break"
            },
            "3I0 БЛОК": {
                "description": "Уставка блокирующего ИО тока нулевой последовательности",
                "calculation_function": None
            },
            "3I0 ОТКЛ": {
                "description": "Уставка отключающего ИО тока нулевой последовательности",
                "calculation_function": None
            },
            "I20 БЛОК": {
                "description": "Уставка блокирующего ИО суммы токов обратной и нулевой последовательностей",
                "calculation_function": None
            },
            "I20 ОТКЛ": {
                "description": "Уставка отключающего ИО суммы токов обратной и нулевой последовательностей",
                "calculation_function": None
            },
            "I1 БЛОК": {
                "description": "Уставка блокирующего ИО тока прямой последовательности",
                "calculation_function": None
            },
            "I1 ОТКЛ": {
                "description": "Уставка отключающего ИО тока прямой последовательности",
                "calculation_function": None
            },
            "Iф БЛОК": {
                "description": "Уставка блокирующего ИО фазного тока",
                "calculation_function": None
            },
            "Iф ОТКЛ": {
                "description": "Уставка отключающего ИО фазного тока",
                "calculation_function": None
            },
            "DIф БЛОК": {
                "description": "Уставка блокирующего токового органа с пуском по приращению фазных токов",
                "calculation_function": None
            },
            "DIф ОТКЛ": {
                "description": "Уставка отключающего токового органа с пуском по приращению фазных токов",
                "calculation_function": None
            },
            "Iфф БЛОК": {
                "description": "Уставка блокирующего ИО разности фазных токов",
                "calculation_function": "calculate_il_block"  # Аналогично IЛ БЛОК
            },
            "Iфф ОТКЛ": {
                "description": "Уставка отключающего ИО разности фазных токов",
                "calculation_function": "calculate_il_break"
            },
            "DIфф БЛОК": {
                "description": "Уставка блокирующего ИО аварийной составляющей разности фазных токов",
                "calculation_function": None
            },
            "DIфф ОТКЛ": {
                "description": "Уставка отключающего ИО аварийной составляющей разности фазных токов",
                "calculation_function": None
            },
            "К МАН": {
                "description": "Орган манипуляции",
                "calculation_function": "calculate_manipulation_factor"
            },
            "УГОЛ БЛОК": {
                "description": "Орган сравнения фаз",
                "calculation_function": "calculate_blocking_angle"
            },
            "Z СРАБ": {
                "description": "Реле сопротивления",
                "calculation_function": None
            },
            "РТНП/3I0_M0": {
                "description": "Уставка органа направления мощности нулевой последовательности по току",
                "calculation_function": None
            },
            "РННП/3U0_M0": {
                "description": "Уставка органа направления мощности нулевой последовательности по напряжению",
                "calculation_function": None
            },
            "3I0": {
                "description": "Уставка ИО тока нулевой последовательности с контролем направления мощности",
                "calculation_function": None
            },
            "УГОЛ мч0": {
                "description": "Угол максимальной чувствительности по нулевой последовательности",
                "calculation_function": None
            },
            "3I0f1": {
                "description": "ИО тока первой гармоники",
                "calculation_function": None
            },
            "3I0f2": {
                "description": "ИО тока второй гармоники",
                "calculation_function": None
            },
            "Kf2f1": {
                "description": "ИО отношения уровня тока второй гармоники к уровню тока первой гармоники",
                "calculation_function": None
            }
        }
    }
}