# Конфигурационный словарь
# Сопоставление органов защиты с их коэффициентами и функциями расчета
SETTINGS_CALCULATION_MAP = {
    'IЛ БЛОК': { # НАЗВАНИЕ_ОРГАНА
        'calculation_factors': { # Коэффициенты расчета
            'il_grading_factor': { # НАЗВАНИЕ_КОЭФФИЦИЕНТА
                'label': 'Коэффициент отстройки', # Название для пользователя
                'default_value': 1.3 # значение_по_умолчанию
            },
            'il_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            }
        },
        'calculation_function': 'calculate_il_block'
    },
    'IЛ ОТКЛ': {
        'calculation_factors': {
            'il_matching_factor': {
                'label': 'Коэффициент согласования',
                'default_value': 1.4
            }
        },
        'calculation_function': 'calculate_il_break'
    },
    'I2 БЛОК': {
        'calculation_factors': {
            'i2_imbalance_factor': {
                'label': 'Коэффициент небаланса',
                'default_value': 0.05
            },
            'i2_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.3
            },
            'i2_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            }
        },
        'calculation_function': 'calculate_i2_block'
    },
    'I2 ОТКЛ': {
        'calculation_factors': {
            'i2_matching_factor': {
                'label': 'Коэффициент согласования',
                'default_value': 1.4
            }
        },
        'calculation_function': 'calculate_i2_break'
    },
    '3I0 БЛОК': {
        'calculation_factors': {
            'i0_imbalance_factor': {
                'label': 'Коэффициент небаланса',
                'default_value': 0.05
            },
            'i0_block_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.2
            },
            'i0_block_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            }
        },
        'calculation_function': 'calculate_3i0_block'
    },
    '3I0 ОТКЛ': {
        'calculation_factors': {
            'i0_break_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.5
            }
        },
        'calculation_function': 'calculate_3i0_break'
    },
    'DI1 БЛОК': {
        'calculation_factors': {
            'di1_matching_factor': {
                'label': 'Коэффициент согласования',
                'default_value': 1.4
            }
        },
        'calculation_function': 'calculate_di1_block'
    },
    'DI1 ОТКЛ': {
        'calculation_factors': {},
        'calculation_function': 'calculate_di1_break'
    },
    'DI2 БЛОК': {
        'calculation_factors': {
            'di2_imbalance_factor': {
                'label': 'Коэффициент небаланса',
                'default_value': 0.05
            },
            'di2_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.3
            },
            'di2_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            }
        },
        'calculation_function': 'calculate_di2_block'
    },
    'DI2 ОТКЛ': {
        'calculation_factors': {
            'di2_matching_factor': {
                'label': 'Коэффициент согласования',
                'default_value': 1.4
            }
        },
        'calculation_function': 'calculate_di2_break'
    },
    'U2 БЛОК': {
        'calculation_factors': {
            'u2_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.3
            },
            'u2_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            },
            'u2_imbalance_voltage': {
                'label': 'Напряжение небаланса U_2нб (В, фазных вторичных, 1.5-2 В)',
                'default_value': 1.5
            },
            'u2_load_voltage': {
                'label': 'Напряжение U_2н.р (В, фазных вторичных, в нагрузочном режиме)',
                'default_value': 0.0
            }
        },
        'calculation_function': 'calculate_u2_block'
    },
    'U2 ОТКЛ': {
        'calculation_factors': {
            'u2_matching_factor': {
                'label': 'Коэффициент согласования',
                'default_value': 1.4
            }
        },
        'calculation_function': 'calculate_u2_break'
    },
    'K МАН': {
        'calculation_factors': {},
        'calculation_function': 'calculate_manipulation_factor'
    },
    'УГОЛ БЛОК': {
        'calculation_factors': {},
        'calculation_function': 'calculate_blocking_angle'
    },
    'РТНП/3I0_M0': {
        'calculation_factors': {
            'rtnp_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.25
            },
            'rtnp_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            },
            'rtnp_imbalance_factor': {
                'label': 'Коэффициент небаланса',
                'default_value': 0.05
            }
        },
        'calculation_function': 'calculate_rtnp'
    },
    'РННП/3U0_M0': {
        'calculation_factors': {
            'rnnp_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.25
            },
            'rnnp_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            },
            'rnnp_imbalance_voltage': {
                'label': 'Напряжение небаланса (вторичное, В)',
                'default_value': 1.5
            }
        },
        'calculation_function': 'calculate_rnnp'
    },
    'R ОТКЛ': {
        'calculation_factors': {
            'r_break_reliability_factor': {
                'label': 'Коэффициент надежности',
                'default_value': 1.6
            },
            'load_angle': {
                'label': 'Угол нагрузки, град',
                'default_value': 30.0
            }
        },
        'calculation_function': 'calculate_r_break'
    },
    'X ОТКЛ': {
        'calculation_factors': {
            'x_break_branch_factor': {
                'label': 'Коэффициент для расчета по ответвлениям',
                'default_value': 1.5
            }
        },
        'calculation_function': 'calculate_x_break'
    },
    'R ОТВ': {
        'calculation_factors': {},
        'calculation_function': 'calculate_r_otv'
    },
    'X ОТВ': {
        'calculation_factors': {
            'x_otv_reliability_factor': {
                'label': 'Коэффициент надежности',
                'default_value': 0.85
            }
        },
        'calculation_function': 'calculate_x_otv'
    }
}