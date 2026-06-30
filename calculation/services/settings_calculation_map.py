# Конфигурационный словарь
# Сопоставление органов защиты с их коэффициентами и функциями расчета
SETTINGS_CALCULATION_MAP = {
    "IЛ БЛОК": {  # НАЗВАНИЕ_ОРГАНА
        "calculation_factors": {  # Коэффициенты расчета
            "il_grading_factor": {  # НАЗВАНИЕ_КОЭФФИЦИЕНТА
                "label": "Коэффициент отстройки",  # Название для пользователя
                "default_value": 1.3,  # значение_по_умолчанию
                "min": 1.2,
                "max": 2.0,
                "step": 0.1,
            },
            "il_reset_factor": {
                "label": "Коэффициент возврата",
                "default_value": 0.9,
                "min": 0.9,
                "max": 0.95,
                "step": 0.05,
            },
        },
        "calculation_function": "calculate_il_block",
        "unit": "А",  # Единица измерения - Амперы
    },
    "IЛ ОТКЛ": {
        "calculation_factors": {
            "il_matching_factor": {
                "label": "Коэффициент согласования",
                "default_value": 1.4,
                "min": 1.4,
                "max": 2.0,
                "step": 0.1,
            }
        },
        "calculation_function": "calculate_il_break",
        "unit": "А",  # Единица измерения - Амперы
    },
    "I2 БЛОК": {
        "calculation_factors": {
            "i2_imbalance_factor": {
                "label": "Коэффициент небаланса",
                "default_value": 0.05,
                "min": 0.02,
                "max": 0.05,
                "step": 0.01,
            },
            "i2_grading_factor": {
                "label": "Коэффициент отстройки",
                "default_value": 1.3,
                "min": 1.2,
                "max": 2.0,
                "step": 0.1,
            },
            "i2_reset_factor": {
                "label": "Коэффициент возврата",
                "default_value": 0.9,
                "min": 0.9,
                "max": 0.95,
                "step": 0.05,
            },
        },
        "calculation_function": "calculate_i2_block",
        "unit": "А",  # Единица измерения - Амперы
    },
    "I2 ОТКЛ": {
        "calculation_factors": {
            "i2_matching_factor": {
                "label": "Коэффициент согласования",
                "default_value": 1.4,
                "min": 1.4,
                "max": 2.0,
                "step": 0.1,
            }
        },
        "calculation_function": "calculate_i2_break",
        "unit": "А",  # Единица измерения - Амперы
    },
    "3I0 БЛОК": {
        "calculation_factors": {
            "i0_imbalance_factor": {
                "label": "Коэффициент небаланса",
                "default_value": 0.05,
                "min": 0.02,
                "max": 0.05,
                "step": 0.01,
            },
            "i0_block_grading_factor": {
                "label": "Коэффициент отстройки",
                "default_value": 1.2,
                "min": 1.2,
                "max": 2.0,
                "step": 0.1,
            },
            "i0_block_reset_factor": {
                "label": "Коэффициент возврата",
                "default_value": 0.9,
                "min": 0.9,
                "max": 0.95,
                "step": 0.05,
            },
        },
        "calculation_function": "calculate_3i0_block",
        "unit": "А",  # Единица измерения - Амперы
    },
    "3I0 ОТКЛ": {
        "calculation_factors": {
            "i0_break_grading_factor": {
                "label": "Коэффициент отстройки",
                "default_value": 1.5,
                "min": 1.2,
                "max": 2.0,
                "step": 0.1,
            }
        },
        "calculation_function": "calculate_3i0_break",
        "unit": "А",  # Единица измерения - Амперы
    },
    "DI1 БЛОК": {
        "calculation_factors": {
            "di1_matching_factor": {
                "label": "Коэффициент согласования",
                "default_value": 1.4,
                "min": 1.4,
                "max": 2.0,
                "step": 0.1,
            }
        },
        "calculation_function": "calculate_di1_block",
        "unit": "А",  # Единица измерения - Амперы
    },
    "DI1 ОТКЛ": {
        "calculation_factors": {},
        "calculation_function": "calculate_di1_break",
        "unit": "А",  # Единица измерения - Амперы
    },
    "DI2 БЛОК": {
        "calculation_factors": {
            "di2_imbalance_factor": {
                "label": "Коэффициент небаланса",
                "default_value": 0.05,
                "min": 0.02,
                "max": 0.05,
                "step": 0.01,
            },
            "di2_grading_factor": {
                "label": "Коэффициент отстройки",
                "default_value": 1.3,
                "min": 1.2,
                "max": 2.0,
                "step": 0.1,
            },
            "di2_reset_factor": {
                "label": "Коэффициент возврата",
                "default_value": 0.9,
                "min": 0.9,
                "max": 0.95,
                "step": 0.05,
            },
        },
        "calculation_function": "calculate_di2_block",
        "unit": "А",  # Единица измерения - Амперы
    },
    "DI2 ОТКЛ": {
        "calculation_factors": {
            "di2_matching_factor": {
                "label": "Коэффициент согласования",
                "default_value": 1.4,
                "min": 1.4,
                "max": 2.0,
                "step": 0.1,
            }
        },
        "calculation_function": "calculate_di2_break",
        "unit": "А",  # Единица измерения - Амперы
    },
    "U2 БЛОК": {
        "calculation_factors": {
            "u2_grading_factor": {
                "label": "Коэффициент отстройки",
                "default_value": 1.3,
                "min": 1.2,
                "max": 2.0,
                "step": 0.1,
            },
            "u2_reset_factor": {
                "label": "Коэффициент возврата",
                "default_value": 0.9,
                "min": 0.9,
                "max": 0.95,
                "step": 0.05,
            },
        },
        "calculation_function": "calculate_u2_block",
        "unit": "В",  # Единица измерения - Вольты
    },
    "U2 ОТКЛ": {
        "calculation_factors": {
            "u2_matching_factor": {
                "label": "Коэффициент согласования",
                "default_value": 1.4,
                "min": 1.4,
                "max": 2.0,
                "step": 0.1,
            }
        },
        "calculation_function": "calculate_u2_break",
        "unit": "В",  # Единица измерения - Вольты
    },
    "K МАН": {
        "calculation_factors": {},
        "calculation_function": "calculate_manipulation_factor",
        "unit": "о.е.",  # Относительные единицы
    },
    "К МАН": {  # Кириллический вариант для совместимости
        "calculation_factors": {},
        "calculation_function": "calculate_manipulation_factor",
        "unit": "о.е.",  # Относительные единицы
    },
    "УГОЛ БЛОК": {
        "calculation_factors": {},
        "calculation_function": "calculate_blocking_angle",
        "unit": "град",  # Единица измерения - Градусы
    },
    "РТНП/3I0_M0": {
        "calculation_factors": {
            "rtnp_grading_factor": {
                "label": "Коэффициент отстройки",
                "default_value": 1.25,
                "min": 1.2,
                "max": 2.0,
                "step": 0.05,
            },
            "rtnp_reset_factor": {
                "label": "Коэффициент возврата",
                "default_value": 0.9,
                "min": 0.9,
                "max": 0.95,
                "step": 0.05,
            },
            "rtnp_imbalance_factor": {
                "label": "Коэффициент небаланса",
                "default_value": 0.05,
                "min": 0.02,
                "max": 0.05,
                "step": 0.01,
            },
        },
        "calculation_function": "calculate_rtnp",
        "unit": "А",  # Единица измерения - Амперы
    },
    "РННП/3U0_M0": {
        "calculation_factors": {
            "rnnp_grading_factor": {
                "label": "Коэффициент отстройки",
                "default_value": 1.25,
                "min": 1.2,
                "max": 2.0,
                "step": 0.05,
            },
            "rnnp_reset_factor": {
                "label": "Коэффициент возврата",
                "default_value": 0.9,
                "min": 0.9,
                "max": 0.95,
                "step": 0.05,
            },
            "rnnp_imbalance_voltage": {
                "label": "Напряжение небаланса (вторичное, В)",
                "default_value": 1.5,
                "min": 1.5,
                "max": 2.0,
                "step": 0.1,
            },
            "rnnp_offset_resistance": {
                "label": "Сопротивление смещения Z₀_см, Ом",
                "default_value": None,
                "min": 0.0,
                "max": 100.0,
                "step": 0.01,
            },
        },
        "calculation_function": "calculate_rnnp",
        "unit": "В",  # Единица измерения - Вольты
    },
    "R ОТКЛ": {
        "calculation_factors": {
            "r_break_reliability_factor": {
                "label": "Коэффициент надежности",
                "default_value": 1.6,
                "min": 1.2,
                "max": 2.0,
                "step": 0.1,
            },
            "load_angle": {
                "label": "Угол нагрузки, град",
                "default_value": 30.0,
                "min": 0.0,
                "max": 90.0,
                "step": 1.0,
            },
        },
        "calculation_function": "calculate_r_break",
        "unit": "Ом",  # Единица измерения - Омы
    },
    "X ОТКЛ": {
        "calculation_factors": {},
        "calculation_function": "calculate_x_break",
        "unit": "Ом",  # Единица измерения - Омы
    },
    "R ОТВ": {
        "calculation_factors": {},
        "calculation_function": "calculate_r_otv",
        "unit": "Ом",  # Единица измерения - Омы
    },
    "X ОТВ": {
        "calculation_factors": {
            "x_otv_reliability_factor": {
                "label": "Коэффициент надежности",
                "default_value": 0.85,
                "min": 0.5,
                "max": 1.0,
                "step": 0.05,
            }
        },
        "calculation_function": "calculate_x_otv",
        "unit": "Ом",  # Единица измерения - Омы
    },
}
