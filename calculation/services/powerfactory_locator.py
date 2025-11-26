from random import shuffle
from typing import Any, Dict, List, Optional
import sys

POWERFACTORY_PATH: str = r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP3\Python\3.8"
PROJECT_NAME: str = "ОДУ Сибири 1.0"

sys.path.append(POWERFACTORY_PATH)

try:
    import powerfactory  # type: ignore
except ModuleNotFoundError:
    raise ModuleNotFoundError(
        "Сервер PowerFactory недоступен, пожалуйста, обратитесь к администратору."
    )
app = powerfactory.GetApplication()
app.ActivateProject(PROJECT_NAME)

# Названия классов в PowerFactory
PF_LINE_CLASS = "*.ElmBranch"
PF_SUBSTATION_CLASS = "*.ElmSubstat"


def _get_powerfactory_object(
    app, pf_class_name: str, pf_object_name: str
) -> Optional[Any]:
    """
    Метод поиска объектов в модели PowerFactory
    по названию класса и имени объекта.

    :param app: COM-объект PowerFactory.
    :param pf_class_name: Название класса в PowerFactory.
    :param pf_object_name: Имя объекта в модели PowerFactory.
    :return: Объект модели PowerFactory или None.
    """

    pf_objects = app.GetCalcRelevantObjects(pf_class_name)
    for pf_object in pf_objects:
        if pf_object.GetAttribute("loc_name") == pf_object_name:
            return pf_object
    raise ValueError(f"Объект {pf_object_name} не найден")


def get_pf_line(app, pf_line_name: str):
    """
    Возвращает ЛЭП в модели PowerFactory по имени.

    :param app: COM-объект PowerFactory.
    :param pf_line_name: Наименование ЛЭП в модели PowerFactory.
    :return: Объект класса ElmBranch (ЛЭП) из PowerFactory.
    """

    pf_line = _get_powerfactory_object(app, PF_LINE_CLASS, pf_line_name)
    return pf_line


def get_powerfactory_object_by_full_name(app, full_name: str):
    """
    Возвращает объект модели PowerFactory по полному имени.

    :param app: COM-объект PowerFactory.
    :param full_name: Полное имя объекта в модели PowerFactory.
    :return: Объект модели PowerFactory.
    """

    study_case = app.GetActiveStudyCase()
    obj = study_case.SearchObject(full_name)
    return obj


def get_pf_substation(app, pf_substation_name: str):
    """
    Возвращает подстанцию в модели PowerFactory по имени.

    :param app: COM-объект PowerFactory.
    :param pf_substation_name: Наименование подстанции в модели PowerFactory.
    :return: Объект класса ElmSubstat (Подстанция) из PowerFactory.
    """

    pf_substation = _get_powerfactory_object(
        app, PF_SUBSTATION_CLASS, pf_substation_name
    )
    return pf_substation


def get_pf_line_data(pf_line):
    length = round(pf_line.GetAttribute("length"), 2)
    r1 = round(pf_line.GetAttribute("R1"), 2)
    x1 = round(pf_line.GetAttribute("X1"), 2)
    r0 = round(pf_line.GetAttribute("R0"), 2)
    x0 = round(pf_line.GetAttribute("X0"), 2)

    return {"length": length, "Z1": f"{r1}+j{x1}", "Z0": f"{r0}+j{x0}"}


def _validate_branch_object(app, branch_object) -> bool:
    """
    Проверка валидности branch_object.
    Возвращает True если объект валиден, False если нет.
    """
    if not branch_object:
        app.PrintError("Ошибка: branch_object не задан")
        return False

    if branch_object.GetClassName() != "ElmBranch":
        app.PrintError(
            f"Ошибка: объект должен быть ElmBranch, а не {branch_object.GetClassName()}"
        )
        return False

    return True


def get_lines_from_branch(app, branch_object):
    """
    Возвращает все линии ElmLne, находящиеся в составе объекта ElmBranch

    Parameters:
    app: COM-объект PowerFactory
    branch_object: DataObject - объект ElmBranch

    Returns:
    list - список объектов ElmLne или пустой список, если линии не найдены
    """
    if not _validate_branch_object(app, branch_object):
        return []

    # Получаем все линии внутри ветви
    lines = branch_object.GetContents("*.ElmLne")

    # GetContents возвращает список или None
    return list(lines) if lines else []


def get_terms_from_branch(app, branch_object):
    """
    Возвращает терминалы ElmTerm для объекта ElmBranch

    Parameters:
    app: COM-объект PowerFactory
    branch_object: DataObject - объект ElmBranch

    Returns:
    list - список объектов ElmTerm или пустой список, если терминалы не найдены
    """
    if not _validate_branch_object(app, branch_object):
        return []

    # Получаем терминалы для Branch
    terminals = branch_object.GetContents("*.ElmTerm")

    # GetContents возвращает список или None
    return list(terminals) if terminals else []


def _get_line_end_substations(branch_object) -> List[str]:
    """
    Возвращает список имен подстанций на концах ЛЭП.
    """

    substations: List[str] = []
    result = {"main_substations": [], "branch_substations": [], "all_substations": []}

    try:
        lines = get_lines_from_branch(app, branch_object)

        for i, line in enumerate(lines):
            terminals = line.GetConnectedElements() or []

            for j, term in enumerate(terminals):
                if term.GetClassName() == "ElmTerm":
                    try:
                        iusage = term.GetAttribute("iUsage")
                        if iusage == 0:  # Шина
                            # Получаем родительский объект терминала
                            parent = term.GetParent()
                            if parent:
                                # Проверяем, что родитель - подстанция
                                if parent.GetClassName() == "ElmSubstat":
                                    substation_name = parent.GetAttribute("loc_name")
                                    if (
                                        substation_name
                                        and substation_name not in substations
                                    ):
                                        substations.append(substation_name)
                    except Exception as e:
                        print(f"Ошибка при обработке терминала: {e}")
                        continue
    except Exception as e:
        print(f"Ошибка в _get_line_end_substations: {e}")

    return substations


def _get_main_substations_with_voltage(branch_object) -> List[Dict[str, Any]]:
    """
    Возвращает подстанции на концах ЛЭП с информацией о классе напряжения.
    """
    substations = []

    try:
        # Получаем конечные терминалы ветви
        term0 = branch_object.GetAttribute("cTerm0")
        term1 = branch_object.GetAttribute("cTerm1")
        end_terms = [term0, term1]

        # Получаем имена конечных терминалов
        end_term_names = []
        for term in end_terms:
            if term:
                end_term_names.append(term)
                continue

        # Получаем все подключенные элементы
        terminals = branch_object.GetConnectedElements() or []

        # Ищем терминалы, которые являются конечными и имеют iUsage = 0 (шина)
        for term in terminals:
            if term.GetClassName() == "ElmTerm":
                try:
                    term_name = term.GetAttribute("loc_name")
                    iusage = term.GetAttribute("iUsage")

                    # Проверяем, что это конечный терминал и это шина
                    if term_name in end_term_names and iusage == 0:
                        # Получаем родительский объект терминала
                        parent = term.GetParent()
                        if parent:
                            parent_class = parent.GetClassName()
                            # Проверяем, что родитель - подстанция
                            if parent_class == "ElmSubstat":
                                substation_name = parent.GetAttribute("loc_name")
                                voltage_level = _get_voltage_level(term)
                                if substation_name:
                                    substation_info = {
                                        "name": substation_name,
                                        "voltage_kv": voltage_level,
                                        "terminal_name": term_name,
                                    }
                                    # Проверяем на дубликаты
                                    is_duplicate = any(
                                        sub["name"] == substation_name
                                        and sub["voltage_kv"] == voltage_level
                                        for sub in substations
                                    )

                                    if not is_duplicate:
                                        substations.append(substation_info)
                except Exception as e:
                    print(f"Ошибка при обработке терминала: {e}")
                    continue
    except Exception as e:
        print(f"Ошибка в _get_main_substations_with_voltage: {e}")

    return substations


def _get_voltage_level(terminal):
    """
    Возвращает класс напряжения терминала.
    """
    try:
        voltage = terminal.GetAttribute("uknom")
        if voltage and voltage > 0:
            return int(round(voltage))  # Округляем до целых
        return None
    except Exception:
        return None


def _has_parallel_counterparts(app, branch_object) -> bool:
    """
    Определяет, есть ли у ЛЭП параллельные линии между теми же подстанциями.

    Алгоритм:
    1. Находим ОСНОВНЫЕ подстанции на концах текущей ЛЭП
    2. Ищем все ЛЭП в модели
    3. Для каждой ЛЭП проверяем, подключена ли она к тем же ОСНОВНЫМ подстанциям и которые имеют один и тот же класс напряжения
    4. Считаем количество таких ЛЭП (параллельных)
    """
    try:
        # 1. Получаем ОСНОВНЫЕ подстанции текущей ЛЭП
        main_substations = _get_main_substations_with_voltage(branch_object)
        current_line_name = branch_object.GetAttribute("loc_name")

        print(f"🔍 Поиск параллельных линий для: {current_line_name}")
        print(f"   Основные ПС с напряжением:")
        for sub in main_substations:
            print(f"      - {sub['name']} ({sub['voltage_kv']} кВ)")

        if len(main_substations) != 2:
            print(f"У ЛЭП должно быть 2 ПС, а найдено: {len(main_substations)}")
            return False

        # Нормализуем с учетом напряжения (только name и voltage_kv, без terminal_name)
        normalized_pair = tuple(
            sorted(
                [
                    {"name": sub["name"], "voltage_kv": sub["voltage_kv"]}
                    for sub in main_substations
                ],
                key=lambda x: (x["name"], x["voltage_kv"] or 0),
            )
        )
        print(f"   Нормализованная пара:")
        for sub in normalized_pair:
            print(f"      - {sub['name']} ({sub['voltage_kv']} кВ)")

        # 2. Получаем все ЛЭП в модели
        all_lines = app.GetCalcRelevantObjects(PF_LINE_CLASS) or []
        print(f"Всего ЛЭП в модели: {len(all_lines)}")

        parallel_count = 0
        found_parallels = []

        # 3. Проверяем каждую ЛЭП на параллельность
        for line in all_lines:
            try:
                line_name = line.GetAttribute("loc_name")

                # Пропускаем ЛЭП, которую выбрали
                if line == branch_object:
                    continue

                candidate_substations = _get_main_substations_with_voltage(line)
                if len(candidate_substations) != 2:
                    continue

                # Нормализуем пару подстанций для сравнения
                # Сравниваем только по имени и напряжению, игнорируя terminal_name
                candidate_normalized = tuple(
                    sorted(
                        [
                            {"name": sub["name"], "voltage_kv": sub["voltage_kv"]}
                            for sub in candidate_substations
                        ],
                        key=lambda x: (x["name"], x["voltage_kv"] or 0),
                    )
                )

                # Проверяем полное совпадение (имя ПС + напряжение)
                if candidate_normalized == normalized_pair:
                    parallel_count += 1
                    found_parallels.append(
                        {"name": line_name, "substations": candidate_substations}
                    )
                    print(f"Найдена параллельная ЛЭП: {line_name}")
                    for sub in candidate_substations:
                        print(f"        - {sub['name']} ({sub['voltage_kv']} кВ)")
                    print(f"Основные ПС: {candidate_substations}")
                    # return True
            except Exception as e:
                print(f"Ошибка проверки ЛЭП {line_name}: {e}")
                continue
        # 4. Анализируем результат
        print(f"Итог: найдено {parallel_count} параллельных линий")
        if found_parallels:
            print(f"Параллельные линии:")
            for parallel in found_parallels:
                print(f"        - {parallel['name']}")

        # Считаем параллельной если найдена хотя бы одна параллельная линия
        is_parallel = parallel_count >= 1
        print(f"Результат: {'ПАРАЛЛЕЛЬНАЯ' if is_parallel else 'ОДИНОЧНАЯ'}")

        return is_parallel

    except Exception as e:
        print(f"Ошибка проверки параллельности: {e}")
        return False


def _has_branches(app, branch_object) -> bool:
    """
    Определяет наличие ответвлений у ЛЭП.

    ЛЭП с ответвлением можно считать,
    если существует соединительный терминал (iUsage == 1), у которого
    более двух связанных элементов *.StaCubic (узлов ответвлений), то
    линия считается имеющей ответвление(я).
    """

    if not _validate_branch_object(app, branch_object):
        return []

    branch_terms = get_terms_from_branch(app, branch_object)

    for term in branch_terms:
        if not hasattr(term, "GetAttribute"):
            continue

        try:
            usage = term.GetAttribute("iUsage")
        except Exception:
            continue

        if usage != 1:
            continue

        try:
            sta_cubics = term.GetContents("*.StaCubic") or []
        except Exception:
            sta_cubics = []

        if len(sta_cubics) > 2:
            return True

    return False


def get_line_type(app, branch_object) -> str:
    """
    Возвращает тип ЛЭП:
    - 'ЛЭП с ответвлением(ями)'
    - 'Параллельная ЛЭП'
    - 'Одиночная ЛЭП'
    """

    if not _validate_branch_object(app, branch_object):
        return []

    if _has_branches(app, branch_object):
        return "ЛЭП с ответвлением(ями)"

    #    if _has_parallel_counterparts(app, branch_object):
    #        return "Параллельная ЛЭП"

    return "Одиночная ЛЭП"


def get_all_lines_with_indexes(app):
    """
    Выгружает все линии ElmBranch с их индексами и именами.
    """
    try:
        # Получаем все линии
        all_lines = app.GetCalcRelevantObjects("*.ElmBranch") or []

        print("ВСЕ ЛИНИИ В МОДЕЛИ:")
        print("=" * 50)

        lines_info = []
        for index, line in enumerate(all_lines):
            try:
                line_name = line.GetAttribute("loc_name")
                line_class = line.GetClassName()
                lines_info.append(
                    {
                        "index": index,
                        "name": line_name,
                        "class": line_class,
                        "object": line,
                    }
                )
                print(f"[{index:3d}] {line_name} ({line_class})")
            except Exception as e:
                print(f"[{index:3d}] Ошибка: {e}")

        print(f"Всего линий: {len(lines_info)}")
        return lines_info

    except Exception as e:
        print(f"Ошибка при получении линий: {e}")
        return []


def test_powerfactory_functions(app):
    """
    Простой тест для проверки работоспособности функций PowerFactory
    """
    print("=== ТЕСТИРОВАНИЕ ФУНКЦИЙ POWERFACTORY ===\n")

    try:
        # 1. Тест get_pf_line - получение ЛЭП по имени
        print("1. Тест get_pf_line:")
        line_name = "227"  # Замените на реальное имя ЛЭП из вашей модели
        pf_line = get_pf_line(app, line_name)
        if pf_line:
            print(f"   ✅ Найдена ЛЭП: {pf_line}")
            line_data = get_pf_line_data(pf_line)
            print(f"   📊 Данные ЛЭП: {line_data}")
        else:
            print(f"   ❌ ЛЭП '{line_name}' не найдена")
        print()

        # 2. Тест get_powerfactory_object_by_full_name
        print("2. Тест get_powerfactory_object_by_full_name:")
        full_name = "ВЛ 110 Власиха-Светлая"  # Пример полного имени
        full_name_obj = get_powerfactory_object_by_full_name(app, full_name)
        if full_name_obj:
            print(
                f"   ✅ Найден объект по полному имени: {full_name_obj.GetAttribute('loc_name')}"
            )
        else:
            print(f"   ❌ Объект '{full_name}' не найден")
        print()

        # 3. Тест get_pf_substation - получение подстанции
        print("3. Тест get_pf_substation:")
        substation_name = (
            "ПС 500 кВ Усть-Илимская ГЭС"  # Замените на реальное имя подстанции
        )
        pf_substation = get_pf_substation(app, substation_name)
        if pf_substation:
            print(f"   ✅ Найдена подстанция: {pf_substation.GetAttribute('loc_name')}")
        else:
            print(f"   ❌ Подстанция '{substation_name}' не найдена")
        print()
    except Exception:
        print("У Артема все плохо")


# Получаем список всех ElmBranch в модели
branches = app.GetCalcRelevantObjects("*.ElmBranch")


def test_branch_functions(app, index: int):
    """
    Тестирует работу всех функций поиска/анализа
    для конкретного branch_object по индексу.
    """

    branches = app.GetCalcRelevantObjects("*.ElmBranch")
    branch = branches[index]
    br_name = branch.GetAttribute("loc_name")
    print(f"\n=== ТЕСТИРОВАНИЕ BRANCH[{index}] : {br_name} ===\n")

    # --- тест 1 ---
    print("▶ Проверка валидности:")
    print(_validate_branch_object(app, branch))

    # --- тест 2 ---
    print("\n▶ Линии ElmLne внутри ветви:")
    lines = get_lines_from_branch(app, branch)
    for ln in lines:
        print(" •", ln, ln.GetAttribute("loc_name"))

    # --- тест 3 ---
    print("\n▶ Терминалы ElmTerm внутри ветви:")
    terms = get_terms_from_branch(app, branch)
    for t in terms:
        print(" •", t, "iUsage=", t.GetAttribute("iUsage"))

    # --- тест 4 ---
    print("\n▶ Подстанции на концах ЛЭП:")
    end_subs = _get_main_substations_with_voltage(branch)
    print(end_subs)

    # --- тест 5 ---
    print("\n▶ Все подстанции:")
    end_subs_and_tap = _get_line_end_substations(branch)
    print(end_subs_and_tap)

    # --- тест 6 ---
    print("\n▶ Проверка наличия ответвлений:")
    print(_has_branches(app, branch))

    # --- тест 7 ---
    print("\n▶ Определение типа ЛЭП:")
    print(get_line_type(app, branch))

    print("\n=== Тест завершён ===\n")


# Использование
# lines_info = get_all_lines_with_indexes(app)

test_branch_functions(app, index=25)
