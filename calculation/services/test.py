import sys

POWERFACTORY_PATH: str = r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP3\Python\3.8"
PROJECT_NAME: str = "ОДУ Сибири 1.0"
PF_LINE_CLASS = "*.ElmBranch"
PF_SUBSTATION_CLASS = "*.ElmSubstat"

sys.path.append(POWERFACTORY_PATH)  # добавляем путь к API PowerFactory в sys.path
import powerfactory  # type: ignore # импортируем модуль powerfactory

app = powerfactory.GetApplication()  # получаем приложение PowerFactory
app.ActivateProject(PROJECT_NAME)  # активируем проект
print(app)  # выводим приложение

branches = app.GetCalcRelevantObjects("*.ElmBranch")  # получаем все линии


def get_lines_from_branch(branch_object):
    """
    Возвращает все линии ElmLne, находящиеся в составе объекта ElmBranch

    Parameters:
    branch_object: DataObject - объект ElmBranch

    Returns:
    list - список объектов ElmLne или пустой список, если линии не найдены
    """
    if not branch_object:
        app.PrintError("Ошибка: branch_object не задан")
        return []

    if branch_object.GetClassName() != "ElmBranch":
        app.PrintError(
            f"Ошибка: объект должен быть ElmBranch, а не {branch_object.GetClassName()}"
        )
        return []

    # Получаем все линии внутри ветви
    lines = branch_object.GetContents("*.ElmLne")

    return lines


def get_terms_from_line(line):
    """
    Возвращает терминалы ElmTerm для одной линии ElmLne

    Parameters:
    line: DataObject - объект ElmLne

    Returns:
    dict - словарь с терминалами: {"terms": список терминалов с iUsage=1, "terms_bus": список терминалов с iUsage=0 или 2}
    """
    terms = []
    terms_bus = []

    if not line:
        return {"terms": terms, "terms_bus": terms_bus}

    try:
        # Получаем терминалы для линии
        terminals = line.GetConnectedElements()

        if terminals:
            for term in terminals:
                if term.GetClassName() == "ElmTerm":
                    i_usage = term.GetAttribute("iUsage")
                    if i_usage == 1:
                        # Соединительные узлы Branch
                        terms.append(term)
                    elif i_usage == 0 or i_usage == 2:
                        # Терминалы линии
                        terms_bus.append(term)

    except Exception as e:
        app.PrintError(
            f"Ошибка при получении терминалов для линии {line.GetAttribute('loc_name')}: {e}"
        )

    return {"terms": terms, "terms_bus": terms_bus}


def get_terms_from_lines(lines):
    """
    Возвращает все терминалы ElmTerm из списка линий ElmLne

    Parameters:
    lines: list - список объектов ElmLne

    Returns:
    dict - словарь, где ключ - линия, значение - словарь с терминалами: {"terms": [...], "terms_bus": [...]}
    """
    lines_terms = {}

    if not lines:
        app.PrintError("Ошибка: список линий пуст")
        return lines_terms

    try:
        # Перебираем все линии в списке
        for line in lines:
            lines_terms[line] = get_terms_from_line(line)

    except Exception as e:
        app.PrintError(f"Ошибка при получении терминалов: {e}")

    return lines_terms


# Пример использования
if branches:
    example_branch = branches[20]  # берем ветвь из списка
    branch_name = example_branch.GetAttribute("loc_name")
    lines = get_lines_from_branch(example_branch)  # получаем линии внутри ветви

    print(f"\nВетвь: {branch_name}")
    print(f"Найдено линий: {len(lines) if lines else 0}\n")

    if lines:
        lines_terms = get_terms_from_lines(lines)  # получаем терминалы для всех линий

        for i, line in enumerate(lines, 1):
            line_name = line.GetAttribute("loc_name")
            line_terms = lines_terms.get(line, {"terms": [], "terms_bus": []})

            print(f"Линия {i}: {line_name}")

            # Выводим соединительные узлы Branch (iUsage=1)
            if line_terms["terms"]:
                print(f"  Соединительные узлы Branch ({len(line_terms['terms'])}):")
                for j, term in enumerate(line_terms["terms"], 1):
                    term_name = term.GetAttribute("loc_name")
                    voltage = term.GetUnom()
                    print(f"    {j}. {term_name} (напряжение: {voltage} кВ)")

            # Выводим шины и внутренние узлы (iUsage=0 или 2)
            if line_terms["terms_bus"]:
                print(f"  Шины и внутренние узлы ({len(line_terms['terms_bus'])}):")
                for j, term in enumerate(line_terms["terms_bus"], 1):
                    term_name = term.GetAttribute("loc_name")
                    voltage = term.GetUnom()
                    print(f"    {j}. {term_name} (напряжение: {voltage} кВ)")

            if not line_terms["terms"] and not line_terms["terms_bus"]:
                print("  Терминалы не найдены")

            print()  # пустая строка между линиями
    else:
        print("В ветви не найдено линий ElmLne")
else:
    print("Не найдено ветвей ElmBranch")
