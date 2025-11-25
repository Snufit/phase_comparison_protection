SETTINGS_CALCULATION_MAP = {
    'IЛ БЛОК': {
        'calculation_factors': {
            'phase_current_diff_block_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.3
            },
            'phase_current_diff_block_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            }
        },
        'calculation_function': '_calculate_phase_current_diff_block'
    },
    'IЛ ОТКЛ': {
        'calculation_factors': {
            'phase_current_diff_break_matching_factor': {
                'label': 'Коэффициент согласования',
                'default_value': 1.4
            }
        },
        'calculation_function': '_calculate_phase_current_diff_break'
    },
    'I2 БЛОК': {
        'calculation_factors': {
            'neg_sequence_current_block_imbalance_factor': {
                'label': 'Коэффициент небаланса',
                'default_value': 0.05
            },
            'neg_sequence_current_block_grading_factor': {
                'label': 'Коэффициент небаланса',
                'default_value': 1.3
            },
            'neg_sequence_current_block_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            }
        },
        'calculation_function': '_calculate_neg_sequence_current_block'
    },
    'I2 ОТКЛ': {
        'calculation_factors': {
            'neg_sequence_current_break_matching_factor': {
                'label': 'Коэффициент согласования',
                'default_value': 1.4
            }
        },
        'calculation_function': '_calculate_neg_sequence_current_break'
    },
    'DI1 БЛОК': {
        'calculation_factors': {
            'pos_sequence_current_increment_block_matching_factor': {
                'label': 'Коэффициент согласования',
                'default_value': 1.4
            }
        },
        'calculation_function':
            '_calculate_pos_sequence_current_increment_block'
    },
    'DI1 ОТКЛ': {
        'calculation_function':
            '_calculate_pos_sequence_current_increment_break'
    },
    'DI2 БЛОК': {
        'calculation_function': '_calculate_neg_sequence_current_block'
    },
    'DI2 ОТКЛ': {
        'calculation_function': '_calculate_neg_sequence_current_break'
    },
    'U2 БЛОК': {
        'calculation_factors': {
            'neg_sequence_voltage_block_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.3
            },
            'neg_sequence_voltage_block_reset_factor': {
                'label': 'Коэффициент возврата',
                'default_value': 0.9
            },
            'neg_sequence_imbalance_voltage': {
                'label': 'Напряжение небаланса',
                'default_value': 1.5
            },
        },
        'calculation_function': '_calculate_neg_sequence_voltage_block'
    },
    'U2 ОТКЛ': {
        'calculation_factors': {
            'neg_sequence_voltage_break_matching_factor': {
                'label': 'Коэффициент согласования',
                'default_value': 2.0
            }
        },
        'calculation_function': '_calculate_neg_sequence_voltage_break'
    },
    'K МАН': {
        'calculation_factors': {
            'manipulation_grading_factor': {
                'label': 'Коэффициент отстройки',
                'default_value': 1.5
            }
        },
        'calculation_function': '_calculate_manipulation_factor'
    },
    'УГОЛ БЛОК': {
        'calculation_function': '_calculate_blocking_angle'
    }
}