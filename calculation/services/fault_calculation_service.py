from typing import List, Dict, Union, Set

from calculation.models import FaultCalculation, CalculationMeta
from calculation.services.powerfactory_locator import (
    get_pf_line,
    get_pf_substation,
    get_powerfactory_object_by_full_name,
)
from calculation.services.sensitivity_fault_map import (
    SensitivityFaultMap,
    POWERFACTORY_FAULT_TYPES,
    FAULT_LOCATION_OPPOSITE_END,
    FAULT_LOCATION_BRANCHES,
)
from core.models import ProtectionHalfSet


class FaultCalculationService:
    # Постоянная конфигурация для моделирования КЗ
    FAULT_CONFIG = {
        "iopt_mde": 1,
        "iopt_cnf": 0,
        "Rf": 0,
        "Xf": 0,
        "iopt_allbus": 0,
    }

    # Виды КЗ в PowerFactory (полный список)
    FAULTS = {"3psc": "К(3)", "2psc": "К(2)", "2pgf": "К(1,1)", "spgf": "К(1)"}


    def perform_fault_calculation(
        self,
        app,
        protection_half_set: ProtectionHalfSet,
        submodes: List[Dict[str, Union[List[str], str]]],
        calculation_meta: CalculationMeta,
    ) -> None:
        """
        Выполняет расчет КЗ на противоположном конце ЛЭП.
        Использует карту КЗ для определения необходимых типов КЗ.

        Args:
            app: Объект приложения PowerFactory
            protection_half_set: Полукомплект защиты
            submodes: Список подрежимов
            calculation_meta: Мета-данные расчета
        """
        # Определяем ЛЭП и ПС полукомплекта
        line_pf_name = protection_half_set.line.pf_name
        substation_pf_name = protection_half_set.substation.pf_name

        # Находим ЛЭП и ПС в модели PowerFactory
        pf_line = get_pf_line(app, line_pf_name)
        pf_substation = get_pf_substation(app, substation_pf_name)

        # Определяем узел КЗ (противоположный конец)
        fault_terminal = self._get_fault_terminal(pf_line, pf_substation)
        fault_terminal_name = fault_terminal.GetAttribute("loc_name")

        # Получаем необходимые типы КЗ для противоположного конца из карты КЗ
        required_fault_types = self._get_required_fault_types_for_location(
            FAULT_LOCATION_OPPOSITE_END
        )

        # Получаем информацию о том, какие органы требуют эти типы КЗ
        organs_info = self._get_organs_info_for_location(
            FAULT_LOCATION_OPPOSITE_END)

        print(
            f"[DEBUG] ========== Моделирование КЗ на противоположном конце =========="
        )
        print(
            f"[DEBUG] Полукомплект: {protection_half_set} (ID: {protection_half_set.id})"
        )
        print(f"[DEBUG] ЛЭП: {line_pf_name}")
        print(f"[DEBUG] Место КЗ: {fault_terminal_name}")
        print(f"[DEBUG] Необходимые типы КЗ: {required_fault_types}")
        if organs_info:
            print(f"[DEBUG] Органы, требующие эти типы КЗ:")
            for organ_name, fault_types in organs_info.items():
                print(f"[DEBUG]   - {organ_name}: {fault_types}")
        print(f"[DEBUG] Количество подрежимов: {len(submodes)}")

        # Перебираем подрежимы
        total_faults = 0
        for idx, submode in enumerate(submodes, 1):
            # Вытаскиваем имя подрежима
            submode_name = submode.get("submode_name")

            # Список объектов
            submode_elements = []

            # Вытаскиваем список полных имен
            submode_elements_full_names = submode.get("submode_elements")

            # Итерируемся по списку полных имен
            for full_name in submode_elements_full_names:
                # Восстанавливаем объект по полному имени
                submode_element = get_powerfactory_object_by_full_name(
                    app, full_name)

                # Записываем в список объектов
                submode_elements.append(submode_element)

            # Отключаем объекты подрежима
            self._disconnect_submode_elements(submode_elements, True)

            # Выполняем расчет КЗ только для необходимых типов
            for pf_fault_type in required_fault_types:
                fault_type = self.FAULTS.get(pf_fault_type)
                if not fault_type:
                    continue

                print(f"[DEBUG] --- Подрежим: {submode_name} ---")
                print(
                    f"[DEBUG] Моделирование КЗ типа: {fault_type} ({pf_fault_type})")

                fault_values = self._execute_fault(
                    app,
                    pf_line,
                    fault_terminal,
                    pf_fault_type,
                    submode_name,
                    fault_terminal_name,
                )

                # Записываем результаты в БД
                self._save_results_to_db(
                    calculation_meta,
                    protection_half_set,
                    fault_type,
                    fault_terminal_name,
                    submode_name,
                    fault_values,
                )
                total_faults += 1

            # Включаем объекты подрежима обратно
            self._disconnect_submode_elements(submode_elements, False)

            faults_in_submode = len(required_fault_types)
            print(
                f"[DEBUG] Подрежим '{submode_name}' ({idx}/{len(submodes)}): выполнено {faults_in_submode} расчетов КЗ"
            )

        print(
            f"[DEBUG] ========== Завершено моделирование КЗ на противоположном конце =========="
        )
        print(
            f"[DEBUG] Всего выполнено расчетов КЗ: {total_faults} (подрежимов: {len(submodes)}, типов КЗ: {len(required_fault_types)})"
        )

        # Удаляем объекты, содержащие ссылки на COM
        del pf_line, pf_substation, fault_terminal, submode_elements

    def perform_branch_fault_calculation(
        self,
        app,
        protection_half_set: ProtectionHalfSet,
        submodes: List[Dict[str, Union[List[str], str]]],
        calculation_meta: CalculationMeta,
    ) -> None:
        """
        Выполняет расчет КЗ на подстанциях ответвлений.
        Использует карту КЗ для определения необходимых типов КЗ.

        Args:
            app: Объект приложения PowerFactory
            protection_half_set: Полукомплект защиты
            submodes: Список подрежимов
            calculation_meta: Мета-данные расчета
        """
        # Получаем линию
        line = protection_half_set.line
        line_pf_name = line.pf_name

        # Находим ЛЭП в модели PowerFactory
        pf_line = get_pf_line(app, line_pf_name)

        # Получаем все активные ответвления для линии
        branches = line.branches.filter(is_active=True)

        if not branches.exists():
            # Если ответвлений нет, ничего не делаем
            return

        # Получаем необходимые типы КЗ для ответвлений из карты КЗ
        required_fault_types = self._get_required_fault_types_for_location(
            FAULT_LOCATION_BRANCHES
        )

        # Получаем информацию о том, какие органы требуют эти типы КЗ
        organs_info = self._get_organs_info_for_location(
            FAULT_LOCATION_BRANCHES)

        print(f"[DEBUG] ========== Моделирование КЗ на ответвлениях ==========")
        print(
            f"[DEBUG] Полукомплект: {protection_half_set} (ID: {protection_half_set.id})"
        )
        print(f"[DEBUG] ЛЭП: {line_pf_name}")
        print(f"[DEBUG] Количество активных ответвлений: {branches.count()}")
        print(f"[DEBUG] Необходимые типы КЗ: {required_fault_types}")
        if organs_info:
            print(f"[DEBUG] Органы, требующие эти типы КЗ:")
            for organ_name, fault_types in organs_info.items():
                print(f"[DEBUG]   - {organ_name}: {fault_types}")
        print(f"[DEBUG] Количество подрежимов: {len(submodes)}")

        # Перебираем подрежимы
        total_faults = 0
        for idx, submode in enumerate(submodes, 1):
            # Вытаскиваем имя подрежима
            submode_name = submode.get("submode_name")

            # Список объектов
            submode_elements = []

            # Вытаскиваем список полных имен
            submode_elements_full_names = submode.get("submode_elements")

            # Итерируемся по списку полных имен
            for full_name in submode_elements_full_names:
                # Восстанавливаем объект по полному имени
                submode_element = get_powerfactory_object_by_full_name(
                    app, full_name)
                # Записываем в список объектов
                submode_elements.append(submode_element)

            # Отключаем объекты подрежима
            self._disconnect_submode_elements(submode_elements, True)

            # Для каждого ответвления выполняем расчет КЗ
            for branch in branches:
                # Получаем имя подстанции ответвления
                branch_substation_name = branch.pf_name_substation

                print(
                    f"[DEBUG] Обработка ответвления: {branch_substation_name}")

                if not branch_substation_name:
                    # Если имя подстанции не указано, пропускаем
                    print(
                        f"[DEBUG] Пропущено ответвление: имя подстанции не указано")
                    continue

                try:
                    # Находим подстанцию в PowerFactory
                    pf_branch_substation = get_pf_substation(app, branch_substation_name)

                    if not pf_branch_substation:
                        print(
                            f"[ERROR] Не найдена подстанция '{branch_substation_name}' в PowerFactory"
                        )
                        continue

                    print(
                        f"[DEBUG] Найдена подстанция '{branch_substation_name}' в PowerFactory"
                    )

                    # Находим терминал на подстанции ответвления, подключенный к линии
                    branch_terminal = FaultCalculationService._get_branch_terminal(
                        pf_line, pf_branch_substation
                    )

                    if not branch_terminal:
                        # Если терминал не найден, пропускаем это ответвление
                        print(
                            f"[WARNING] Терминал на подстанции '{branch_substation_name}' не найден, пропускаем ответвление"
                        )
                        continue

                    branch_terminal_name = branch_terminal.GetAttribute(
                        "loc_name")
                    print(
                        f"[DEBUG] Найден терминал '{branch_terminal_name}' на подстанции '{branch_substation_name}'"
                    )

                    # Используем специальный формат fault_location для идентификации
                    fault_location = f"Ответвление: {branch_substation_name}"

                    # Выполняем расчет КЗ для всех необходимых типов
                    print(
                        f"[DEBUG] Начинаем расчет КЗ для ответвления '{branch_substation_name}': {len(required_fault_types)} типов"
                    )
                    for pf_fault_type in required_fault_types:
                        fault_type = self.FAULTS.get(pf_fault_type)
                        if not fault_type:
                            print(
                                f"[DEBUG] Пропущен тип КЗ {pf_fault_type}: не найден в словаре FAULTS"
                            )
                            continue

                        print(
                            f"[DEBUG] --- Подрежим: {submode_name}, Ответвление: {branch_substation_name} ---"
                        )
                        print(
                            f"[DEBUG] Моделирование КЗ типа: {fault_type} ({pf_fault_type})"
                        )

                        try:
                            fault_values = self._execute_fault(
                                app,
                                pf_line,
                                branch_terminal,
                                pf_fault_type,
                                submode_name,
                                fault_location,
                            )

                            # Записываем результаты в БД
                            self._save_results_to_db(
                                calculation_meta,
                                protection_half_set,
                                fault_type,
                                fault_location,
                                submode_name,
                                fault_values,
                            )
                            total_faults += 1
                            print(
                                f"[DEBUG] ✓ Успешно выполнено и сохранено КЗ {fault_type} на ответвлении {branch_substation_name}"
                            )
                        except Exception as e:
                            import traceback

                            print(
                                f"[ERROR] Ошибка при выполнении КЗ {fault_type} на ответвлении {branch_substation_name}: {e}"
                            )
                            print(
                                f"[ERROR] Traceback: {traceback.format_exc()}")
                            # Продолжаем для следующего типа КЗ
                            continue

                except Exception as e:
                    # Если не удалось выполнить расчет для этого ответвления, пропускаем
                    # Логируем ошибку, но продолжаем для других ответвлений
                    import traceback

                    print(
                        f"[ERROR] Ошибка при расчете КЗ на ответвлении {branch_substation_name}: {e}"
                    )
                    print(f"[ERROR] Traceback: {traceback.format_exc()}")
                    continue

            # Включаем объекты подрежима обратно
            self._disconnect_submode_elements(submode_elements, False)

            faults_in_submode = len(required_fault_types) * branches.count()
            print(
                f"[DEBUG] Подрежим '{submode_name}' ({idx}/{len(submodes)}): выполнено {faults_in_submode} расчетов КЗ "
                f"({len(required_fault_types)} типов × {branches.count()} ответвлений)"
            )

        print(
            f"[DEBUG] ========== Завершено моделирование КЗ на ответвлениях =========="
        )
        print(
            f"[DEBUG] Всего выполнено расчетов КЗ: {total_faults} "
            f"(подрежимов: {len(submodes)}, типов КЗ: {len(required_fault_types)}, ответвлений: {branches.count()})"
        )

        # Удаляем объекты, содержащие ссылки на COM
        del pf_line, submode_elements

    @staticmethod
    def _save_results_to_db(
        calculation_meta: CalculationMeta,
        protection_half_set: ProtectionHalfSet,
        fault_type: str,
        fault_location,
        submode_name,
        fault_values,
    ) -> None:
        """
        Сохраняет результаты расчета КЗ в БД.

        Args:
            calculation_meta: Мета-данные расчета
            protection_half_set: Полукомплект защиты
            fault_type: Тип КЗ (например, 'К(3)')
            fault_location: Место КЗ (может быть строкой или объектом терминала)
            submode_name: Название подрежима
            fault_values: Словарь с результатами расчета
        """
        # Если fault_location - объект терминала, получаем его имя
        if hasattr(fault_location, "GetAttribute"):
            fault_location_str = fault_location.GetAttribute("loc_name")
        else:
            # Если это уже строка, используем как есть
            fault_location_str = str(fault_location)

        FaultCalculation.objects.create(
            calculation_meta=calculation_meta,
            protection_half_set=protection_half_set,
            fault_type=fault_type,
            fault_location=fault_location_str,
            network_topology=submode_name,
            fault_values=fault_values,
        )

        print(
            f"[DEBUG] ✓ Сохранено в БД: {fault_type} на {fault_location_str}, подрежим '{submode_name}'"
        )

    @staticmethod
    def _get_fault_terminal(pf_line, pf_substation):
        # Определяем узлы подключения защищаемой ЛЭП
        line_terminals = pf_line.GetConnectedElements()
        for terminal in line_terminals:
            # Определяем подстанцию, которой принадлежит узел
            substation = terminal.GetParent()

            # Возвращаем терминал противоположной подстанции
            if substation != pf_substation:
                return terminal

    @staticmethod
    def _get_branch_terminal(pf_line, pf_branch_substation):
        """
        Находит терминал на подстанции ответвления, подключенный к линии.

        Args:
            pf_line: Объект линии в PowerFactory
            pf_branch_substation: Объект подстанции ответвления в PowerFactory

        Returns:
            Терминал на подстанции ответвления или None, если не найден
        """
        if not pf_branch_substation:
            return None

        # Получаем имя подстанции ответвления для сравнения
        branch_substation_name = pf_branch_substation.GetAttribute("loc_name")
        if not branch_substation_name:
            print(f"[DEBUG] У подстанции ответвления нет имени (loc_name)")
            return None

        print(
            f"[DEBUG] Поиск терминала на подстанции '{branch_substation_name}' для линии '{pf_line.GetAttribute('loc_name')}'"
        )

        # Сначала пробуем найти терминал напрямую через GetConnectedElements на линии
        line_terminals = pf_line.GetConnectedElements()
        if line_terminals:
            print(f"[DEBUG] Найдено терминалов на линии: {len(line_terminals)}")
            for terminal in line_terminals:
                try:
                    # Определяем подстанцию, которой принадлежит узел
                    substation = terminal.GetParent()

                    if not substation:
                        continue

                    # Сравниваем по имени подстанции (более надежно, чем сравнение объектов)
                    substation_name = substation.GetAttribute("loc_name")

                    print(
                        f"[DEBUG] Проверка терминала '{terminal.GetAttribute('loc_name')}' на подстанции '{substation_name}'"
                    )

                    # Возвращаем терминал, если он принадлежит подстанции ответвления
                    if substation_name == branch_substation_name:
                        print(
                            f"[DEBUG] ✓ Найден терминал '{terminal.GetAttribute('loc_name')}' на подстанции '{substation_name}'"
                        )
                        return terminal
                except Exception as e:
                    print(f"[DEBUG] Ошибка при проверке терминала: {e}")
                    continue

        # Если терминал не найден напрямую, ищем все терминалы на подстанции ответвления
        # и проверяем их связь с линией через промежуточные объекты
        print(f"[DEBUG] Поиск терминалов на подстанции '{branch_substation_name}'...")
        try:
            substation_terminals = pf_branch_substation.GetContents("*.ElmTerm")
            if not substation_terminals:
                print(f"[DEBUG] На подстанции '{branch_substation_name}' нет терминалов")
                return None

            print(f"[DEBUG] Найдено терминалов на подстанции: {len(substation_terminals)}")

            # Получаем все связанные элементы с линией для проверки связи
            line_connected_elements = pf_line.GetConnectedElements() or []

            # Проверяем каждый терминал на подстанции
            for terminal in substation_terminals:
                try:
                    terminal_name = terminal.GetAttribute("loc_name")
                    print(f"[DEBUG] Проверка терминала '{terminal_name}' на подстанции '{branch_substation_name}'")

                    # Получаем все связанные элементы терминала
                    terminal_connected = terminal.GetConnectedElements() or []

                    # Проверяем, связан ли терминал с линией через промежуточные объекты
                    # Ищем общие связанные элементы или проверяем прямое подключение
                    for connected_elem in terminal_connected:
                        # Если терминал связан с элементом, который также связан с линией
                        if connected_elem in line_connected_elements:
                            print(
                                f"[DEBUG] ✓ Найден терминал '{terminal_name}' на подстанции '{branch_substation_name}', "
                                f"связанный с линией через промежуточный объект"
                            )
                            return terminal

                    # Также проверяем прямое подключение терминала к линии
                    if pf_line in terminal_connected:
                        print(
                            f"[DEBUG] ✓ Найден терминал '{terminal_name}' на подстанции '{branch_substation_name}', "
                            f"напрямую подключенный к линии"
                        )
                        return terminal

                except Exception as e:
                    print(f"[DEBUG] Ошибка при проверке терминала: {e}")
                    continue

        except Exception as e:
            print(f"[DEBUG] Ошибка при получении терминалов подстанции: {e}")

        print(
            f"[DEBUG] ✗ Терминал на подстанции '{branch_substation_name}' не найден"
        )
        return None

    def _execute_fault(
        self,
        app,
        pf_line,
        fault_terminal,
        fault_type: str,
        submode_name: str = None,
        fault_location: str = None,
    ) -> Dict[str, float]:
        # Конфигурация КЗ
        fault = app.GetFromStudyCase("ComShc")
        fault.SetAttribute("iopt_mde", self.FAULT_CONFIG["iopt_mde"])
        fault.SetAttribute("iopt_cnf", self.FAULT_CONFIG["iopt_cnf"])
        fault.SetAttribute("iopt_shc", fault_type)
        fault.SetAttribute("Rf", self.FAULT_CONFIG["Rf"])
        fault.SetAttribute("Xf", self.FAULT_CONFIG["Xf"])
        fault.SetAttribute("iopt_allbus", self.FAULT_CONFIG["iopt_allbus"])
        fault.SetAttribute("shcobj", fault_terminal)

        # Моделирование КЗ
        fault.Execute()

        # Инициализируем результаты
        pos_sequence_current = 0
        neg_sequence_current = 0
        triple_zero_sequence_current = 0
        neg_sequence_voltage = 0
        pos_sequence_voltage = 0  # Остаточное напряжение прямой последовательности
        zero_sequence_voltage = 0  # Напряжение нулевой последовательности

        if pf_line.HasAttribute("m:I1:0"):
            pos_sequence_current = pf_line.GetAttribute("m:I1:0")
        if pf_line.HasAttribute("m:I2:0"):
            neg_sequence_current = pf_line.GetAttribute("m:I2:0")
        if pf_line.HasAttribute("m:I0x3:0"):
            triple_zero_sequence_current = pf_line.GetAttribute("m:I0x3:0")
        if pf_line.HasAttribute("n:U2:0"):
            neg_sequence_voltage = pf_line.GetAttribute("n:U2:0")
        if pf_line.HasAttribute("n:U1:0"):
            pos_sequence_voltage = pf_line.GetAttribute("n:U1:0")
        # Получаем напряжение нулевой последовательности (для расчета 3U0)
        if pf_line.HasAttribute("n:U0:0"):
            zero_sequence_voltage = pf_line.GetAttribute("n:U0:0")

        # ВАЖНО: PowerFactory возвращает значения токов в кА (килоамперах) и напряжений в кВ (киловольтах)
        # Преобразуем кА → А (умножаем на 1000)
        # Все значения токов КЗ должны быть в А (амперах)
        # Все значения напряжений КЗ должны быть в кВ (киловольтах)
        
        results = {
            "I1": round(pos_sequence_current * 1000, 2),  # кА → А
            "I2": round(neg_sequence_current * 1000, 2),  # кА → А
            "3I0": round(triple_zero_sequence_current * 1000, 2),  # кА → А
            "U2": round(neg_sequence_voltage, 2),  # Напряжение обратной последовательности (кВ)
            "U1": round(
                pos_sequence_voltage, 2
            ),  # Остаточное напряжение прямой последовательности (кВ)
            "3U0": round(3 * zero_sequence_voltage, 2)
            if zero_sequence_voltage > 0
            else 0,  # Утроенное напряжение нулевой последовательности (кВ)
        }

        # Логируем полученные значения КЗ
        fault_type_ru = self.FAULTS.get(fault_type, fault_type)
        location_str = fault_location if fault_location else "не указано"
        submode_str = submode_name if submode_name else "не указано"

        print(f"[DEBUG] Результаты КЗ {fault_type_ru}:")
        print(f"[DEBUG]   Место: {location_str}")
        print(f"[DEBUG]   Подрежим: {submode_str}")
        # Значения из PowerFactory в кА, преобразуем для отображения
        i1_ka = pos_sequence_current
        i1_a = i1_ka * 1000  # кА → А
        i2_ka = neg_sequence_current
        i2_a = i2_ka * 1000  # кА → А
        i0_ka = triple_zero_sequence_current
        i0_a = i0_ka * 1000  # кА → А
        print(
            f"[DEBUG]   I1 = {results['I1']:.2f} А ({i1_ka:.3f} кА)")
        print(
            f"[DEBUG]   I2 = {results['I2']:.2f} А ({i2_ka:.3f} кА)")
        print(
            f"[DEBUG]   3I0 = {results['3I0']:.2f} А ({i0_ka:.3f} кА)")
        print(f"[DEBUG]   U2 = {results['U2']:.2f} кВ")
        print(f"[DEBUG]   U1 = {results['U1']:.2f} кВ")
        print(f"[DEBUG]   3U0 = {results['3U0']:.2f} кВ")

        # Удаляем ссылку на COM
        del fault

        return results

    @staticmethod
    def _get_required_fault_types_for_location(location: str) -> Set[str]:
        """
        Получает необходимые типы КЗ в формате PowerFactory для указанного места.

        Args:
            location: Место выполнения КЗ (FAULT_LOCATION_OPPOSITE_END или FAULT_LOCATION_BRANCHES)

        Returns:
            Множество типов КЗ в формате PowerFactory (например, {'3psc', 'spgf', '2psc'})
        """
        required_types = set()

        # Получаем все органы, для которых нужно проверять чувствительность
        organs_requiring_faults = SensitivityFaultMap.get_all_organs_requiring_faults()

        for organ_name in organs_requiring_faults:
            fault_map = SensitivityFaultMap.get_fault_map(organ_name)
            if not fault_map:
                continue

            # Проверяем, нужно ли моделировать КЗ в этом месте для этого органа
            fault_locations = fault_map.get("fault_locations", [])
            if location not in fault_locations:
                continue

            # Получаем типы КЗ для этого органа
            fault_types = fault_map.get("fault_types", [])

            # Преобразуем типы КЗ в формат PowerFactory
            for pf_type, ru_type in POWERFACTORY_FAULT_TYPES.items():
                if ru_type in fault_types:
                    required_types.add(pf_type)

        return required_types

    @staticmethod
    def _get_organs_info_for_location(location: str) -> Dict[str, List[str]]:
        """
        Получает информацию о том, какие органы требуют какие типы КЗ для указанного места.

        Args:
            location: Место выполнения КЗ (FAULT_LOCATION_OPPOSITE_END или FAULT_LOCATION_BRANCHES)

        Returns:
            Словарь {название_органа: [список_типов_КЗ]}
        """
        organs_info = {}

        # Получаем все органы, для которых нужно проверять чувствительность
        organs_requiring_faults = SensitivityFaultMap.get_all_organs_requiring_faults()

        for organ_name in organs_requiring_faults:
            fault_map = SensitivityFaultMap.get_fault_map(organ_name)
            if not fault_map:
                continue

            # Проверяем, нужно ли моделировать КЗ в этом месте для этого органа
            fault_locations = fault_map.get("fault_locations", [])
            if location not in fault_locations:
                continue

            # Получаем типы КЗ для этого органа
            fault_types = fault_map.get("fault_types", [])
            if fault_types:
                organs_info[organ_name] = fault_types

        return organs_info

    @staticmethod
    def _disconnect_submode_elements(submode_elements, disconnect: bool) -> None:
        if disconnect:
            for element in submode_elements:
                element.SwitchOff()
        else:
            for element in submode_elements:
                element.SwitchOn()
