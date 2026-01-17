from random import shuffle
from typing import Any, Dict, List, Optional, Union
import sys

POWERFACTORY_PATH: str = r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP3\Python\3.8"
PROJECT_NAME: str = "ОДУ Сибири 1.0"

sys.path.append(POWERFACTORY_PATH)

# Lazy initialization - don't import powerfactory at module level
_powerfactory_module = None
_app = None


def _log(message: str):
    """
    Вспомогательная функция для логирования.
    Использует FaultCalculationService._log() если доступен, иначе print().
    """
    try:
        from calculation.services.fault_calculation_service import FaultCalculationService
        FaultCalculationService._log(message)
    except ImportError:
        print(message)


def _get_powerfactory_app():
    """
    Ленивая инициализация PowerFactory.
    Возвращает объект app или поднимает исключение, если PowerFactory недоступен.
    """
    global _powerfactory_module, _app

    if _app is not None:
        return _app

    if _powerfactory_module is None:
        try:
            import powerfactory  # type: ignore
            _powerfactory_module = powerfactory
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "Сервер PowerFactory недоступен, пожалуйста, обратитесь к администратору."
            )

    _app = _powerfactory_module.GetApplication()
    _app.ActivateProject(PROJECT_NAME)
    return _app


# Названия классов в PowerFactory
PF_LINE_CLASS = "*.ElmBranch"
PF_SUBSTATION_CLASS = "*.ElmSubstat"


def _get_powerfactory_object(
    app, pf_class_name: str, pf_object_name: str, max_retries: int = 3
) -> Optional[Any]:
    """
    Метод поиска объектов в модели PowerFactory
    по названию класса и имени объекта.
    Включает обработку ошибок многопоточности с повторными попытками.

    :param app: COM-объект PowerFactory.
    :param pf_class_name: Название класса в PowerFactory.
    :param pf_object_name: Имя объекта в модели PowerFactory.
    :param max_retries: Максимальное количество попыток при ошибке многопоточности.
    :return: Объект модели PowerFactory или None.
    """
    import time
    import powerfactory  # type: ignore
    
    for attempt in range(max_retries):
        try:
            pf_objects = app.GetCalcRelevantObjects(pf_class_name)
            for pf_object in pf_objects:
                try:
                    if pf_object.GetAttribute("loc_name") == pf_object_name:
                        return pf_object
                except (RuntimeError, AttributeError) as e:
                    # Ошибка при работе с объектом - пропускаем его
                    if "can't be used from other threads" in str(e):
                        # Если ошибка многопоточности при работе с объектом,
                        # пересоздаем app и пробуем снова
                        if attempt < max_retries - 1:
                            app = powerfactory.GetApplication()
                            if app:
                                time.sleep(0.1)
                                break  # Выходим из внутреннего цикла, чтобы повторить внешний
                            continue
                    # Для других ошибок - просто пропускаем объект
                    continue
            
            # Если дошли сюда, значит объект не найден
            # Но проверяем, не была ли ошибка многопоточности
            # (она могла произойти в GetCalcRelevantObjects, но не быть поймана)
            raise ValueError(f"Объект {pf_object_name} не найден")
            
        except RuntimeError as e:
            if "can't be used from other threads" in str(e):
                if attempt < max_retries - 1:
                    _log(f"[DEBUG] Ошибка многопоточности в _get_powerfactory_object (попытка {attempt + 1}/{max_retries})")
                    # Пересоздаем app и пробуем снова
                    app = powerfactory.GetApplication()
                    if app:
                        time.sleep(0.1)
                        continue
                    else:
                        raise RuntimeError(
                            "Не удалось получить приложение PowerFactory после ошибки многопоточности. "
                            "Убедитесь, что PowerFactory запущен и сервер Django работает в однопоточном режиме "
                            "(python manage.py runserver --nothreading)."
                        )
                else:
                    raise RuntimeError(
                        f"Ошибка многопоточности PowerFactory после {max_retries} попыток. "
                        f"Запустите сервер Django в однопоточном режиме: "
                        f"python manage.py runserver --nothreading"
                    )
            else:
                # Другие RuntimeError пробрасываем дальше
                raise
        except ValueError:
            # Объект не найден - это нормальная ситуация, пробрасываем дальше
            raise
        except Exception as e:
            # Для других исключений пробуем повторить
            if attempt < max_retries - 1:
                _log(f"[DEBUG] Неожиданная ошибка в _get_powerfactory_object (попытка {attempt + 1}/{max_retries}): {e}")
                app = powerfactory.GetApplication()
                if app:
                    time.sleep(0.1)
                    continue
            raise
    
    # Если дошли сюда, значит все попытки не удались
    raise ValueError(f"Объект {pf_object_name} не найден после {max_retries} попыток")


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


def _get_line_end_substations(branch_object, app=None) -> List[Dict[str, Any]]:
    """
    Возвращает список подстанций на концах ЛЭП с информацией о классе напряжения.
    """
    if app is None:
        app = _get_powerfactory_app()
    substations = []

    try:
        lines = get_lines_from_branch(app, branch_object)

        for line in lines:
            terminals = line.GetConnectedElements() or []

            for term in terminals:
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
                                    term_name = term.GetAttribute("loc_name")
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
                        _log(f"Ошибка при обработке терминала: {e}")
                        continue
    except Exception as e:
        _log(f"Ошибка в _get_line_end_substations: {e}")

    return substations


def _get_main_substations_with_voltage(branch_object, app=None) -> List[Dict[str, Any]]:
    """
    Возвращает подстанции на концах ЛЭП с информацией о классе напряжения.
    """
    if app is None:
        app = _get_powerfactory_app()
    substations = []

    try:
        # Получаем конечные терминалы ветви
        term0_str = str(branch_object.GetAttribute("cTerm0")).strip()
        term1_str = str(branch_object.GetAttribute("cTerm1")).strip()

        # Удалить все пробелы
        term0_clean = term0_str.replace(" ", "")
        term1_clean = term1_str.replace(" ", "")

        # Проверяем, что строки не пустые перед преобразованием в int
        if not term0_clean or not term1_clean:
            _log(f"Предупреждение: пустые терминалы для ветви {branch_object.GetAttribute('loc_name')}")
            return []
        try:
            term0 = abs(int(term0_clean))
            term1 = abs(int(term1_clean))
        except ValueError as e:
            _log(f"Ошибка преобразования терминалов в int: term0='{term0_clean}', term1='{term1_clean}', ошибка: {e}")
            return []

        end_terms = [str(term0), str(term1)]

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
                    _log(f"Ошибка при обработке терминала: {e}")
                    continue
    except Exception as e:
        _log(f"Ошибка в _get_main_substations_with_voltage: {e}")

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
        main_substations = _get_main_substations_with_voltage(branch_object, app)
        current_line_name = branch_object.GetAttribute("loc_name")

        for sub in main_substations:
            _log(f"      - {sub['name']} ({sub['voltage_kv']} кВ)")

        # Некоторые линии могут иметь одну подстанцию (тупиковые линии)
        # Это не всегда ошибка, но для ДФЗ обычно нужно 2 подстанции
        if len(main_substations) < 1:
            _log(f"У ЛЭП не найдено основных подстанций")
            return False
        elif len(main_substations) == 1:
            _log(f"У ЛЭП найдена только 1 ПС (возможно, тупиковая линия): {main_substations[0]['name']}")
            # Не возвращаем False, так как это может быть нормально
        elif len(main_substations) > 2:
            _log(f"У ЛЭП найдено {len(main_substations)} ПС вместо 2")
            # Используем первые 2 подстанции
            main_substations = main_substations[:2]

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

        # 2. Получаем все ЛЭП в модели
        all_lines = app.GetCalcRelevantObjects(PF_LINE_CLASS) or []

        parallel_count = 0
        found_parallels = []

        # 3. Проверяем каждую ЛЭП на параллельность
        for line in all_lines:
            try:
                line_name = line.GetAttribute("loc_name")

                # Пропускаем ЛЭП, которую выбрали
                if line == branch_object:
                    continue

                candidate_substations = _get_main_substations_with_voltage(line, app)
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

                    # return True
            except Exception as e:
                _log(f"Ошибка проверки ЛЭП {line_name}: {e}")
                continue
        # 4. Анализируем результат
        # Считаем параллельной если найдена хотя бы одна параллельная линия
        is_parallel = parallel_count >= 1

        return is_parallel

    except Exception as e:
        _log(f"Ошибка проверки параллельности: {e}")
        return False


def _has_branches(
    app,
    branch_object,
    return_branch_substations: bool = False,
    check_substations: bool = True,
) -> Union[bool, List[Dict[str, Any]]]:
    """
    Определяет наличие ответвлений у ЛЭП.

    ЛЭП с ответвлением можно считать:
    1. Если существует соединительный терминал (iUsage == 1), у которого
       более двух связанных элементов *.StaCubic (узлов ответвлений)
    2. Если есть подстанции, которые есть в _get_line_end_substations,
       но отсутствуют в _get_main_substations_with_voltage (подстанции ответвлений)

    Args:
        app: COM-объект PowerFactory
        branch_object: Объект ElmBranch
        return_branch_substations: Если True, возвращает список подстанций ответвлений.
                                  Если False, возвращает только булево значение.
        check_substations: Если True, выполняется проверка №2 (сравнение подстанций).
                          Если False, проверка №2 не выполняется.

    Returns:
        Если return_branch_substations=False: bool - есть ли ответвления
        Если return_branch_substations=True: List[Dict] - список подстанций ответвлений
    """

    if not _validate_branch_object(app, branch_object):
        return [] if return_branch_substations else False

    found_branch_substations = []
    has_branches_by_terminals = False

    # Проверка 1: по соединительным терминалам
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
            has_branches_by_terminals = True
            break

    # Проверка 2: сравнение основных подстанций и всех подстанций на концах ЛЭП
    if check_substations:
        try:
            main_substations = _get_main_substations_with_voltage(branch_object, app)
            all_substations = _get_line_end_substations(branch_object, app)

            # Создаем множества для сравнения (по имени и напряжению)
            main_substations_set = {
                (sub["name"], sub["voltage_kv"]) for sub in main_substations
            }
            all_substations_set = {
                (sub["name"], sub["voltage_kv"]) for sub in all_substations
            }

            # Если есть подстанции, которые есть во всех, но не в основных - это ответвления
            branch_substations_keys = all_substations_set - main_substations_set

            if branch_substations_keys:
                # Находим полную информацию о подстанциях ответвлений
                for sub in all_substations:
                    key = (sub["name"], sub["voltage_kv"])
                    if key in branch_substations_keys:
                        found_branch_substations.append(sub)
        except Exception as e:
            _log(f"Ошибка при проверке ответвлений через подстанции: {e}")

    # Определяем, есть ли ответвления (через проверку 1 или проверку 2)
    has_branches = has_branches_by_terminals or len(found_branch_substations) > 0

    if return_branch_substations:
        return found_branch_substations if has_branches else []
    return has_branches


def get_line_type(app, branch_object) -> str:
    """
    Возвращает тип ЛЭП.

    Примеры:
    - 'Одиночная ЛЭП' - обычная ЛЭП без ответвлений и без параллельных линий
    - 'Одиночная ЛЭП с ответвлением' - ЛЭП с одним ответвлением, но без параллельных линий
    - 'Одиночная ЛЭП с ответвлениями' - ЛЭП с несколькими ответвлениями, но без параллельных линий
    - 'Параллельная ЛЭП' - параллельная ЛЭП без ответвлений
    - 'Параллельная ЛЭП с ответвлением' - параллельная ЛЭП с одним ответвлением
    - 'Параллельная ЛЭП с ответвлениями' - параллельная ЛЭП с несколькими ответвлениями
    """

    if not _validate_branch_object(app, branch_object):
        return "Одиночная ЛЭП"

    # Получаем информацию об ответвлениях и параллельности
    has_branches = _has_branches(app, branch_object)
    is_parallel = _has_parallel_counterparts(app, branch_object)

    # Определяем форму склонения для ответвлений
    branch_text = ""
    if has_branches:
        # Получаем список подстанций ответвлений для определения количества
        branch_substations = _has_branches(
            app, branch_object, return_branch_substations=True, check_substations=True
        )
        if len(branch_substations) == 1:
            branch_text = " с ответвлением"
        elif len(branch_substations) > 1:
            branch_text = " с ответвлениями"
        else:
            # Ответвления найдены только через проверку по терминалам, количество неизвестно
            branch_text = " с ответвлением(ями)"

    # Формируем тип ЛЭП в зависимости от комбинации признаков
    if is_parallel:
        return f"Параллельная ЛЭП{branch_text}"

    if has_branches:
        return f"Одиночная ЛЭП{branch_text}"

    return "Одиночная ЛЭП"


def get_all_lines_with_indexes(app):
    """
    Выгружает все линии ElmBranch с их индексами и именами.
    """
    try:
        # Получаем все линии
        all_lines = app.GetCalcRelevantObjects("*.ElmBranch") or []

        _log("ВСЕ ЛИНИИ В МОДЕЛИ:")
        _log("=" * 50)

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
                _log(f"[{index:3d}] {line_name} ({line_class})")
            except Exception as e:
                _log(f"[{index:3d}] Ошибка: {e}")

        _log(f"Всего линий: {len(lines_info)}")
        return lines_info

    except Exception as e:
        _log(f"Ошибка при получении линий: {e}")
        return []


def test_powerfactory_functions(app):
    """
    Простой тест для проверки работоспособности функций PowerFactory
    """
    _log("=== ТЕСТИРОВАНИЕ ФУНКЦИЙ POWERFACTORY ===\n")

    try:
        # 1. Тест get_pf_line - получение ЛЭП по имени
        _log("1. Тест get_pf_line:")
        line_name = "227"  # Замените на реальное имя ЛЭП из вашей модели
        pf_line = get_pf_line(app, line_name)
        if pf_line:
            _log(f"   ✅ Найдена ЛЭП: {pf_line}")
            line_data = get_pf_line_data(pf_line)
            _log(f"   📊 Данные ЛЭП: {line_data}")
        else:
            _log(f"   ❌ ЛЭП '{line_name}' не найдена")
        _log("")

        # 2. Тест get_powerfactory_object_by_full_name
        _log("2. Тест get_powerfactory_object_by_full_name:")
        full_name = "ВЛ 110 Власиха-Светлая"  # Пример полного имени
        full_name_obj = get_powerfactory_object_by_full_name(app, full_name)
        if full_name_obj:
            _log(
                f"   ✅ Найден объект по полному имени: {full_name_obj.GetAttribute('loc_name')}"
            )
        else:
            _log(f"   ❌ Объект '{full_name}' не найден")
        _log("")

        # 3. Тест get_pf_substation - получение подстанции
        _log("3. Тест get_pf_substation:")
        substation_name = (
            "ПС 500 кВ Усть-Илимская ГЭС"  # Замените на реальное имя подстанции
        )
        pf_substation = get_pf_substation(app, substation_name)
        if pf_substation:
            _log(f"   ✅ Найдена подстанция: {pf_substation.GetAttribute('loc_name')}")
        else:
            _log(f"   ❌ Подстанция '{substation_name}' не найдена")
        _log("")
    except Exception:
        _log("У Артема все плохо")


# Получаем список всех ElmBranch в модели (ленивая инициализация)
# branches = app.GetCalcRelevantObjects("*.ElmBranch")  # Закомментировано для работы без PowerFactory


def test_branch_functions(app, index: int):
    """
    Тестирует работу всех функций поиска/анализа
    для конкретного branch_object по индексу.
    """

    branches = app.GetCalcRelevantObjects("*.ElmBranch")
    branch = branches[index]
    br_name = branch.GetAttribute("loc_name")
    _log(f"\n=== ТЕСТИРОВАНИЕ BRANCH[{index}] : {br_name} ===\n")

    # --- тест 1 ---
    _log("▶ Проверка валидности:")
    _log(str(_validate_branch_object(app, branch)))

    # --- тест 2 ---
    _log("\n▶ Линии ElmLne внутри ветви:")
    lines = get_lines_from_branch(app, branch)
    for ln in lines:
        _log(f" • {ln} {ln.GetAttribute('loc_name')}")

    # --- тест 3 ---
    _log("\n▶ Терминалы ElmTerm внутри ветви:")
    terms = get_terms_from_branch(app, branch)
    for t in terms:
        _log(f" • {t} iUsage= {t.GetAttribute('iUsage')}")

    # --- тест 4 ---
    _log("\n▶ Подстанции на концах ЛЭП:")
    end_subs = _get_main_substations_with_voltage(branch, app)
    _log(str(end_subs))

    # --- тест 5 ---
    _log("\n▶ Все подстанции:")
    end_subs_and_tap = _get_line_end_substations(branch, app)
    _log(str(end_subs_and_tap))

    # --- тест 6 ---
    _log("\n▶ Проверка наличия ответвлений:")
    _log(str(_has_branches(app, branch)))

    # --- тест 7 ---
    _log("\n▶ Определение типа ЛЭП:")
    _log(str(get_line_type(app, branch)))

    _log("\n=== Тест завершён ===\n")


# Использование
# lines_info = get_all_lines_with_indexes(app)

# app = _get_powerfactory_app()
# test_branch_functions(app, index=258)  # Закомментировано для работы без PowerFactory
