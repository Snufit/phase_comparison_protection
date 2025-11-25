from itertools import combinations
from typing import List, Any


def generate_half_set_submodes(
    half_set_topology,
    half_set_submodes_data
):

    total_lines_number = get_elements_number_by_type(
        half_set_topology, 'ЛЭП'
    )
    total_autotransformers_number = get_elements_number_by_type(
        half_set_topology, 'АТ'
    )

    min_outages = half_set_submodes_data.get('min_outages') or 0
    max_outages = half_set_submodes_data.get('max_outages') or (len(half_set_topology) + 1) // 2
    max_lines = half_set_submodes_data.get('min_outages') or (total_lines_number + 1) // 2
    max_autotransformers = (
        half_set_submodes_data.get('max_autotransformers') or total_autotransformers_number // 2
    )

    submodes = generate_submodes(
        half_set_topology, min_outages, max_outages
    )
    valid_submodes = validate_submodes(
        submodes, max_lines, max_autotransformers
    )
    submodes_transformed = transform_submodes(valid_submodes)

    return submodes_transformed


def generate_submodes(half_set_topology: List[Any], min_outages, max_outages):
    submodes = []
    for outages in range(min_outages, max_outages + 1):
        current_combinations = combinations(
            half_set_topology, outages
        )
        submodes.extend(current_combinations)
    return submodes


def get_elements_number_by_type(half_set_topology, element_type: str):
    elements_number = 0
    for element in half_set_topology:
        if element.get('type') == element_type:
            elements_number += 1
    return elements_number


def validate_submodes(submodes, max_lines, max_autotransformers):
    valid_submodes = []
    for submode in submodes:
        lines_number = get_elements_number_by_type(submode, 'ЛЭП')
        autotransformers_number = get_elements_number_by_type(submode, 'АТ')
        if (
            lines_number <= max_lines
            and autotransformers_number <= max_autotransformers
        ):
            valid_submodes.append(submode)
    return valid_submodes


def get_submode_name(submode):
    if not submode:
        submode_name = 'Нормальная схема'
    else:
        submode_name = []
        for element in submode:
            submode_name.append(element.get('loc_name'))
        submode_name = ', '.join(submode_name)
        submode_name = f'Отключение {submode_name}'
    return submode_name


def transform_submodes(submodes):
    submodes_transformed = []
    for submode in submodes:
        submode_elements = []
        submode_name = get_submode_name(submode)
        for element in submode:
            submode_elements.append(element.get('full_name'))
        submode_dict = {
            'submode_elements': submode_elements,
            'submode_name': submode_name
        }
        submodes_transformed.append(submode_dict)
    return submodes_transformed


if __name__ == "__main__":

    topology = [
        {
            'type': 'ЛЭП',
            'full_name': 'full_name_ВЛ_1',
            'loc_name': 'ВЛ-1',
        },
        {
            'type': 'ЛЭП',
            'full_name': 'full_name_ВЛ_2',
            'loc_name': 'ВЛ-2',
        },
        {
            'type': 'АТ',
            'full_name': 'full_name_АТ_1',
            'loc_name': 'АТ-1',
        },
        {
            'type': 'АТ',
            'full_name': 'full_name_АТ_2',
            'loc_name': 'АТ-2',
        },
    ]

    test_valid_submodes = generate_half_set_submodes(topology, {})
    print(test_valid_submodes)