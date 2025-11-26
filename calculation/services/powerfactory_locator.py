from typing import Any, List, Optional
import sys

POWERFACTORY_PATH: str = (
    r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP3\Python\3.8"
)
PROJECT_NAME: str = "ОДУ Сибири 1.0"

sys.path.append(POWERFACTORY_PATH)

try:
    import powerfactory  # type: ignore
except ModuleNotFoundError:
    raise ModuleNotFoundError(
        'Сервер PowerFactory недоступен, пожалуйста, обратитесь к администратору.'
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
    result = {
        'main_substations': [],
        'branch_substations': [],
        'all_substations': []
    }

    try:
        lines = get_lines_from_branch(app, branch_object)

        for i, line in enumerate(lines):
            terminals = line.GetConnectedElements() or []

            for j, term in enumerate(terminals):
                if (term.GetClassName() == "ElmTerm"):
                    try:
                        iusage = term.GetAttribute('iUsage')
                        if iusage == 0:  # Шина
                            # Получаем родительский объект терминала
                            parent = term.GetParent()
                            if parent:
                                # Проверяем, что родитель - подстанция
                                if parent.GetClassName() == "ElmSubstat":
                                    substation_name = parent.GetAttribute("loc_name")
                                    if substation_name and substation_name not in substations:
                                        substations.append(substation_name)
                    except Exception as e:
                        print(f"Ошибка при обработке терминала: {e}")
                        continue
    except Exception as e:
        print(f"Ошибка в _get_line_end_substations: {e}")

    return substations


def _get_main_substations_only(branch_object) -> List[str]:
    """
    Возвращает ТОЛЬКО подстанции на концах основной ЛЭП (iUsage = 0)
    """
    substations: List[str] = []
    af = 234233243
    try:
        term0 = branch_object.GetAttribute('cTerm0')
        term1 = branch_object.GetAttribute('cTerm1')
        end_terms = [term0, term1]
        print(f"   term0 тип: {type(term0)}, значение: {term0}")
        print(f"   term1 тип: {type(term1)}, значение: {term1}")
        end_term_names = []
        for i, term in enumerate(end_terms):
            if term:
                end_term_names.append(term)
                print(f"Концевой терминал {i + 1}: {term}")
                continue

        terminals = branch_object.GetConnectedElements() or []

        for j, term in enumerate(terminals):
            if term.GetClassName() == "ElmTerm":
                try:
                    term_name = term.GetAttribute('loc_name')
                    iusage = term.GetAttribute('iUsage')
                    print(f"{j + 1}: {term_name}")
                    if term_name in end_term_names and iusage == 0:  # Шина
                        # Получаем родительский объект терминала
                        parent = term.GetParent()
                        if parent:
                            parent_name = parent.GetAttribute('loc_name')
                            parent_class = parent.GetClassName()
                            # Проверяем, что родитель - подстанция
                            if parent_class == "ElmSubstat":
                                substation_name = parent_name
                                if substation_name and substation_name not in substations:
                                    substations.append(substation_name)
                except Exception as e:
                    print(f"Ошибка при обработке терминала: {e}")
                    continue
    except Exception as e:
        print(f"Ошибка в _get_main_substations_only: {e}")

    return substations


def _has_parallel_counterparts(app, branch_object) -> bool:  # В разработке
    """
    Определяет, есть ли у ЛЭП параллельные линии между теми же подстанциями.

    Алгоритм:
    1. Находим подстанции на концах текущей ЛЭП
    2. Ищем все ЛЭП в модели
    3. Для каждой ЛЭП проверяем, подключена ли она к тем же подстанциям
    4. Считаем количество таких ЛЭП (параллельных)
    """

    end_substations = _get_line_end_substations(branch_object)
    if len(end_substations) != 2:
        return False

    normalized_pair = tuple(sorted(end_substations))

    try:
        all_lines = app.GetCalcRelevantObjects(PF_LINE_CLASS) or []
    except Exception:
        return False

    parallels = 0
    for line in all_lines:
        try:
            if line == branch_object:
                parallels += 1
                continue

            candidate_substations = _get_line_end_substations(line)
            if len(candidate_substations) != 2:
                continue

            if tuple(sorted(candidate_substations)) == normalized_pair:
                parallels += 1

            if parallels >= 2:  # текущая линия + хотя бы одна параллельная
                return True
        except Exception:
            continue

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
            print(f"   ✅ Найден объект по полному имени: {full_name_obj.GetAttribute('loc_name')}")
        else:
            print(f"   ❌ Объект '{full_name}' не найден")
        print()

        # 3. Тест get_pf_substation - получение подстанции
        print("3. Тест get_pf_substation:")
        substation_name = "ПС 500 кВ Усть-Илимская ГЭС"  # Замените на реальное имя подстанции
        pf_substation = get_pf_substation(app, substation_name)
        if pf_substation:
            print(f"   ✅ Найдена подстанция: {pf_substation.GetAttribute('loc_name')}")
        else:
            print(f"   ❌ Подстанция '{substation_name}' не найдена")
        print()
    except Exception:
        print('У Артема все х********')


# Получаем список всех ElmBranch в модели
branches = app.GetCalcRelevantObjects("*.ElmBranch")

# Выбираем конкретный branch_object по индексу
idx = 26  # индекс можно менять вручную
branch = branches[idx]

print(f"Тестируем ElmBranch: {branch}, loc_name={branch.GetAttribute('loc_name')}")


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
    end_subs = _get_main_substations_only(branch)
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


test_branch_functions(app, index=25)