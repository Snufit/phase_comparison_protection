import hashlib
import json
from itertools import combinations
from typing import List, Any, Optional

from core.models import ProtectionHalfSet


def generate_half_set_submodes(
    half_set_topology,  # топология полукомплекта
    half_set_submodes_data,  # параметры генерации подрежимов
    protection_half_set: Optional[ProtectionHalfSet] = None,  # Новый параметр
    use_cache: bool = True,  # Новый параметр
):
    """
    Генерирует подрежимы с возможностью кэширования в БД.

    Args:
        half_set_topology: Список элементов топологии
        half_set_submodes_data: Параметры генерации подрежимов
        protection_half_set: Полукомплект защиты (для кэширования)
        use_cache: Использовать кэш из БД

    Returns:
        List[Dict] - список подрежимов
    """
    from calculation.models import HalfSetSubmode

    # Если есть полукомплект и включено кэширование
    if protection_half_set and use_cache:
        # Вычисляем хэш параметров генерации
        params_hash = _calculate_params_hash(half_set_submodes_data)

        # Проверяем, есть ли уже подрежимы с такими параметрами
        existing_submodes = HalfSetSubmode.objects.filter(
            protection_half_set=protection_half_set
        )

        # Проверяем, совпадают ли параметры генерации
        for submode in existing_submodes:
            if submode.generation_params:
                existing_hash = submode.generation_params.get("hash")
                if existing_hash == params_hash:
                    # Возвращаем из БД
                    return [
                        {
                            "submode_name": s.submode_name,
                            "submode_elements": s.submode_elements,
                        }
                        for s in existing_submodes
                    ]

    # Генерируем подрежимы (старая логика)
    # Подсчитать количество элементов каждого типа:
    total_lines_number = get_elements_number_by_type(half_set_topology, "ЛЭП")
    total_autotransformers_number = get_elements_number_by_type(
        half_set_topology, "АТ")
    # Определить параметры генерации (с значениями по умолчанию):
    min_outages = half_set_submodes_data.get("min_outages") or 0
    max_outages = (
        half_set_submodes_data.get("max_outages") or (
            len(half_set_topology) + 1) // 2
    )
    max_lines = (
        half_set_submodes_data.get("min_outages") or (
            total_lines_number + 1) // 2
    )
    max_autotransformers = (
        half_set_submodes_data.get("max_autotransformers")
        or total_autotransformers_number // 2
    )
    # Сгенерировать все возможные комбинации отключений:
    submodes = generate_submodes(half_set_topology, min_outages, max_outages)
    # Отфильтровать валидные подрежимы:
    valid_submodes = validate_submodes(
        submodes, max_lines, max_autotransformers)
    submodes_transformed = transform_submodes(valid_submodes)

    # Сохраняем в БД, если указан полукомплект
    if protection_half_set:
        _save_submodes_to_db(
            protection_half_set, submodes_transformed, half_set_submodes_data
        )

    return submodes_transformed


def _calculate_params_hash(params: dict) -> str:
    """Вычисляет хэш параметров генерации."""
    params_json = json.dumps(params, sort_keys=True)
    return hashlib.md5(params_json.encode()).hexdigest()


def _save_submodes_to_db(
    protection_half_set: ProtectionHalfSet,
    submodes: List[dict],
    generation_params: dict,
) -> None:
    """Сохраняет подрежимы в БД."""
    from calculation.models import HalfSetSubmode

    params_hash = _calculate_params_hash(generation_params)

    # Удаляем старые подрежимы для этого полукомплекта
    HalfSetSubmode.objects.filter(
        protection_half_set=protection_half_set).delete()

    # Создаем новые записи
    for submode in submodes:
        HalfSetSubmode.objects.create(
            protection_half_set=protection_half_set,
            submode_name=submode["submode_name"],
            submode_elements=submode["submode_elements"],
            generation_params={
                "params": generation_params, "hash": params_hash},
        )


def generate_submodes(half_set_topology: List[Any], min_outages, max_outages):
    submodes = []
    for outages in range(min_outages, max_outages + 1):
        current_combinations = combinations(half_set_topology, outages)
        submodes.extend(current_combinations)
    # ВЫХОД: List[Tuple] - список кортежей (комбинаций элементов)
    return submodes


def get_elements_number_by_type(half_set_topology, element_type: str):
    elements_number = 0
    for element in half_set_topology:
        if element.get("type") == element_type:
            elements_number += 1
    return elements_number  # int - количество элементов указанного типа


def validate_submodes(submodes, max_lines, max_autotransformers):
    valid_submodes = []
    for submode in submodes:
        lines_number = get_elements_number_by_type(submode, "ЛЭП")
        autotransformers_number = get_elements_number_by_type(submode, "АТ")
        if (
            lines_number <= max_lines
            and autotransformers_number <= max_autotransformers
        ):
            valid_submodes.append(submode)
    return valid_submodes


def get_submode_name(submode):
    if not submode:
        submode_name = "Нормальная схема"
    else:
        submode_name = []
        for element in submode:
            submode_name.append(element.get("loc_name"))
        submode_name = ", ".join(submode_name)
        submode_name = f"Отключение {submode_name}"
    return submode_name  # ВЫХОД: str - название подрежима


def transform_submodes(submodes):
    submodes_transformed = []
    for submode in submodes:
        submode_elements = []
        submode_name = get_submode_name(submode)
        for element in submode:
            submode_elements.append(element.get("full_name"))
        submode_dict = {
            "submode_elements": submode_elements,
            "submode_name": submode_name,
        }
        submodes_transformed.append(submode_dict)
    # ВЫХОД: List[Dict] - список словарей (подрежимов)
    return submodes_transformed


if __name__ == "__main__":
    topology = [
        {
            "type": "ЛЭП",
            "full_name": "full_name_ВЛ_1",
            "loc_name": "ВЛ-1",
        },
        {
            "type": "ЛЭП",
            "full_name": "full_name_ВЛ_2",
            "loc_name": "ВЛ-2",
        },
        {
            "type": "АТ",
            "full_name": "full_name_АТ_1",
            "loc_name": "АТ-1",
        },
        {
            "type": "АТ",
            "full_name": "full_name_АТ_2",
            "loc_name": "АТ-2",
        },
    ]

    test_valid_submodes = generate_half_set_submodes(topology, {})
    print(test_valid_submodes)
