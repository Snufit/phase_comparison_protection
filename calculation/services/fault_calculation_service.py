from typing import List, Dict, Union

from calculation.models import FaultCalculation, CalculationMeta
from calculation.services.powerfactory_locator import get_pf_line, get_pf_substation, get_powerfactory_object_by_full_name
from core.models import ProtectionHalfSet


class FaultCalculationService:

    # Постоянная конфигурация для моделирования КЗ
    FAULT_CONFIG = {
        'iopt_mde': 1,
        'iopt_cnf': 0,
        'Rf': 0,
        'Xf': 0,
        'iopt_allbus': 0,
    }

    # Виды КЗ
    FAULTS = {
        '3psc': 'К(3)',
        # '2psc': 'К(2)',
        # '2pgf': 'К(1,1)',
        'spgf': 'К(1)'
    }

    def perform_fault_calculation(
        self,
        app,
        protection_half_set: ProtectionHalfSet,
        submodes: List[Dict[str, Union[List[str], str]]],
        calculation_meta: CalculationMeta
    ) -> None:

        # Определяем ЛЭП и ПС полукомплекта
        line_pf_name = protection_half_set.line.pf_name
        substation_pf_name = protection_half_set.substation.pf_name

        # Находим ЛЭП и ПС в модели PowerFactory
        pf_line = get_pf_line(app, line_pf_name)
        pf_substation = get_pf_substation(app, substation_pf_name)

        # Определяем узел КЗ
        fault_terminal = self._get_fault_terminal(pf_line, pf_substation)
        fault_terminal_name = fault_terminal.GetAttribute('loc_name')

        # Перебираем подрежимы
        for submode in submodes:

            # Вытаскиваем имя подрежима
            submode_name = submode.get('submode_name')

            # Список объектов
            submode_elements = []

            # Вытаскиваем список полных имен
            submode_elements_full_names = submode.get('submode_elements')

            # Итерируемся по списку полных имен
            for full_name in submode_elements_full_names:

                # Восстанавливаем объект по полному имени
                submode_element = get_powerfactory_object_by_full_name(
                    app, full_name
                )

                # Записываем в список объектов
                submode_elements.append(submode_element)

            # Отключаем объекты подрежима
            self._disconnect_submode_elements(submode_elements, True)

            # Выполняем расчет КЗ
            for pf_fault_type, fault_type in self.FAULTS.items():
                fault_values = self._execute_fault(
                    app, pf_line, fault_terminal, pf_fault_type
                )

                # Записываем результаты в БД
                self._save_results_to_db(
                    calculation_meta,
                    protection_half_set,
                    fault_type,
                    fault_terminal_name,
                    submode_name,
                    fault_values
                )

            # Включаем объекты подрежима обратно
            self._disconnect_submode_elements(submode_elements, False)

        # Удаляем объекты, содержащие ссылки на COM
        del pf_line, pf_substation, fault_terminal, submode_elements

    def perform_branch_fault_calculation(
        self,
        app,
        protection_half_set: ProtectionHalfSet,
        submodes: List[Dict[str, Union[List[str], str]]],
        calculation_meta: CalculationMeta
    ) -> None:
        """
        Выполняет расчет КЗ на подстанциях ответвлений для расчета X откл отв.
        
        Если подстанций ответвлений несколько, моделирует КЗ на всех и выбирает
        максимальные значения U1/I1 для расчета X откл отв.
        
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
        
        # Перебираем подрежимы
        for submode in submodes:
            # Вытаскиваем имя подрежима
            submode_name = submode.get('submode_name')
            
            # Список объектов
            submode_elements = []
            
            # Вытаскиваем список полных имен
            submode_elements_full_names = submode.get('submode_elements')
            
            # Итерируемся по списку полных имен
            for full_name in submode_elements_full_names:
                # Восстанавливаем объект по полному имени
                submode_element = get_powerfactory_object_by_full_name(
                    app, full_name
                )
                # Записываем в список объектов
                submode_elements.append(submode_element)
            
            # Отключаем объекты подрежима
            self._disconnect_submode_elements(submode_elements, True)
            
            # Для каждого ответвления выполняем расчет КЗ
            for branch in branches:
                # Получаем имя подстанции ответвления
                branch_substation_name = branch.pf_name_substation
                
                if not branch_substation_name:
                    # Если имя подстанции не указано, пропускаем
                    continue
                
                try:
                    # Находим подстанцию в PowerFactory
                    pf_branch_substation = get_pf_substation(app, branch_substation_name)
                    
                    # Находим терминал на подстанции ответвления, подключенный к линии
                    branch_terminal = self._get_branch_terminal(pf_line, pf_branch_substation)
                    
                    if not branch_terminal:
                        # Если терминал не найден, пропускаем это ответвление
                        continue
                    
                    branch_terminal_name = branch_terminal.GetAttribute('loc_name')
                    
                    # Выполняем расчет КЗ только для трехфазного КЗ (для расчета X откл отв)
                    fault_values = self._execute_fault(
                        app, pf_line, branch_terminal, '3psc'
                    )
                    
                    # Записываем результаты в БД с пометкой, что это КЗ на ответвлении
                    # Используем специальный формат fault_location для идентификации
                    fault_location = f"Ответвление: {branch_substation_name}"
                    
                    self._save_results_to_db(
                        calculation_meta,
                        protection_half_set,
                        'К(3)',  # Только трехфазное КЗ для расчета X откл отв
                        fault_location,
                        submode_name,
                        fault_values
                    )
                    
                except Exception as e:
                    # Если не удалось выполнить расчет для этого ответвления, пропускаем
                    # Логируем ошибку, но продолжаем для других ответвлений
                    print(f"Ошибка при расчете КЗ на ответвлении {branch_substation_name}: {e}")
                    continue
            
            # Включаем объекты подрежима обратно
            self._disconnect_submode_elements(submode_elements, False)
        
        # Удаляем объекты, содержащие ссылки на COM
        del pf_line, submode_elements

    @staticmethod
    def _save_results_to_db(
        calculation_meta: CalculationMeta,
        protection_half_set: ProtectionHalfSet,
        fault_type: str,
        fault_location,
        submode_name,
        fault_values
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
        if hasattr(fault_location, 'GetAttribute'):
            fault_location_str = fault_location.GetAttribute('loc_name')
        else:
            # Если это уже строка, используем как есть
            fault_location_str = str(fault_location)
        
        FaultCalculation.objects.create(
            calculation_meta=calculation_meta,
            protection_half_set=protection_half_set,
            fault_type=fault_type,
            fault_location=fault_location_str,
            network_topology=submode_name,
            fault_values=fault_values
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
        # Определяем узлы подключения защищаемой ЛЭП
        line_terminals = pf_line.GetConnectedElements()
        for terminal in line_terminals:
            # Определяем подстанцию, которой принадлежит узел
            substation = terminal.GetParent()
            
            # Возвращаем терминал, если он принадлежит подстанции ответвления
            if substation == pf_branch_substation:
                return terminal
        
        return None

    def _execute_fault(
        self, app, pf_line, fault_terminal, fault_type: str
    ) -> Dict[str, float]:

        # Конфигурация КЗ
        fault = app.GetFromStudyCase('ComShc')
        fault.SetAttribute('iopt_mde', self.FAULT_CONFIG['iopt_mde'])
        fault.SetAttribute('iopt_cnf', self.FAULT_CONFIG['iopt_cnf'])
        fault.SetAttribute('iopt_shc', fault_type)
        fault.SetAttribute('Rf', self.FAULT_CONFIG['Rf'])
        fault.SetAttribute('Xf', self.FAULT_CONFIG['Xf'])
        fault.SetAttribute('iopt_allbus', self.FAULT_CONFIG['iopt_allbus'])
        fault.SetAttribute('shcobj', fault_terminal)

        # Моделирование КЗ
        fault.Execute()

        # Инициализируем результаты
        pos_sequence_current = 0
        neg_sequence_current = 0
        triple_zero_sequence_current = 0
        neg_sequence_voltage = 0
        pos_sequence_voltage = 0  # Остаточное напряжение прямой последовательности

        if pf_line.HasAttribute('m:I1:0'):
            pos_sequence_current = pf_line.GetAttribute('m:I1:0')
        if pf_line.HasAttribute('m:I2:0'):
            neg_sequence_current = pf_line.GetAttribute('m:I2:0')
        if pf_line.HasAttribute('m:I0x3:0'):
            triple_zero_sequence_current = pf_line.GetAttribute('m:I0x3:0')
        if pf_line.HasAttribute('n:U2:0'):
            neg_sequence_voltage = pf_line.GetAttribute('n:U2:0')
        if pf_line.HasAttribute('n:U1:0'):
            pos_sequence_voltage = pf_line.GetAttribute('n:U1:0')

        results = {
            'I1': round(pos_sequence_current * 1000, 0),
            'I2': round(neg_sequence_current * 1000, 0),
            '3I0': round(triple_zero_sequence_current * 1000, 0),
            'U2': round(neg_sequence_voltage, 0),
            'U1': round(pos_sequence_voltage, 0)  # Остаточное напряжение прямой последовательности
        }

        # Удаляем ссылку на COM
        del fault

        return results

    @staticmethod
    def _disconnect_submode_elements(submode_elements, disconnect: bool) -> None:
        if disconnect:
            for element in submode_elements:
                element.SwitchOff()
        else:
            for element in submode_elements:
                element.SwitchOn()