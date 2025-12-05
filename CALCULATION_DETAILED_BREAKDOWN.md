# Детальный разбор модуля Calculation по шагам

## Шаг 1: Модели данных - структура хранения

### 1.1 CalculationMeta - "Папка с расчетом"

**Что это:** Это как папка, в которой хранится вся информация об одном расчете.

```python
class CalculationMeta(models.Model):
    line = ForeignKey(Line)                    # Какая ЛЭП рассчитывается
    user = ForeignKey(User)                    # Кто сделал расчет
    calculation_number = PositiveIntegerField  # Номер расчета (автоматически)
    calculation_date = DateTimeField           # Когда сделан расчет
```

**Пример:**
- ЛЭП: "ВЛ 500 кВ Сибирь-Центр"
- Пользователь: "Иванов И.И."
- Номер: 42
- Дата: 2024-01-15 14:30:00

**Особенность:** Номер генерируется автоматически через Django signal:
```python
@receiver(pre_save, sender=CalculationMeta)
def generate_calculation_number(...):
    # Находит последний расчет
    # Присваивает следующий номер (или 1, если это первый)
```

---

### 1.2 SettingsCalculation - "Протокол расчета уставки"

**Что это:** Конкретный результат расчета для одного органа защиты.

```python
class SettingsCalculation(models.Model):
    calculation_meta = ForeignKey(CalculationMeta)      # К какому расчету относится
    protection_half_set = ForeignKey(ProtectionHalfSet) # Полукомплект 1 или 2
    component = ForeignKey(Component)                   # Какой орган (IЛ БЛОК и т.д.)
    calculation_factors = JSONField                     # Какие коэффициенты использовались
    result_value = FloatField                          # Результат (значение уставки)
```

**Пример:**
- Расчет: №42 (см. выше)
- Полукомплект: Полукомплект 1
- Орган: "IЛ БЛОК"
- Коэффициенты: `{"Коэффициент отстройки": 1.3, "Коэффициент возврата": 0.9}`
- Результат: 5000 (А)

**Связи:**
- Один CalculationMeta → много SettingsCalculation (для каждого органа каждого полукомплекта)

---

### 1.3 FaultCalculation - "Протокол расчета токов КЗ"

**Что это:** Результат расчета токов короткого замыкания для конкретной ситуации.

```python
class FaultCalculation(models.Model):
    calculation_meta = ForeignKey(CalculationMeta)      # К какому расчету относится
    protection_half_set = ForeignKey(ProtectionHalfSet) # Полукомплект 1 или 2
    fault_type = CharField                              # Вид КЗ: "К(3)", "К(1)" и т.д.
    fault_location = CharField                          # Где произошло КЗ (узел)
    network_topology = CharField                        # Схема сети (подрежим)
    fault_values = JSONField                            # Токи: I1, I2, 3I0, U2
```

**Пример:**
- Расчет: №42
- Полукомплект: Полукомплект 1
- Вид КЗ: "К(3)" (трехфазное)
- Узел КЗ: "ПС Сибирь"
- Схема: "Отключение ВЛ-1, ВЛ-2"
- Значения: `{"I1": 15000, "I2": 0, "3I0": 0, "U2": 0}` (мА)

**Связи:**
- Один CalculationMeta → много FaultCalculation (для каждого подрежима и вида КЗ)

---

### 1.4 SensitivityAnalysis - "Анализ чувствительности"

**Что это:** Проверка, насколько хорошо защита реагирует на КЗ.

```python
class SensitivityAnalysis(models.Model):
    settings_calculation = ForeignKey(SettingsCalculation)  # Какая уставка
    fault_calculation = ForeignKey(FaultCalculation)        # Какой расчет КЗ
    sensitivity_rate = FloatField                           # Коэффициент чувствительности
    status = CharField                                      # Статус (автоматически)
```

**Пример:**
- Уставка: IЛ БЛОК = 5000 А (из SettingsCalculation)
- Расчет КЗ: I1 = 15000 мА = 15 А (из FaultCalculation)
- Коэффициент: 15 / 5 = 3.0
- Статус: "Чувствительна" (≥ 2.0)

**Автоматическое определение статуса:**
```python
def save(self):
    if sensitivity_rate <= 1:
        status = 'Нечувствительна'
    elif 1 < sensitivity_rate < 2:
        status = 'Низкая чувствительность'
    else:
        status = 'Чувствительна'
```

**Связи:**
- Одна уставка (SettingsCalculation) → много анализов чувствительности
- Один расчет КЗ (FaultCalculation) → много анализов чувствительности
- Это связь "многие ко многим" через промежуточную модель

---

## Шаг 2: Работа с PowerFactory - подключение и поиск объектов

### 2.1 PowerFactoryManager - "Менеджер подключения"

**Что делает:** Управляет подключением к программе PowerFactory.

```python
class PowerFactoryManager:
    POWERFACTORY_PATH = r"C:\Program Files\DIgSILENT\PowerFactory 2021 SP3\Python\3.8"
    PROJECT_NAME = "NewHope"
    
    def get_application(self):
        # 1. Добавляет путь к PowerFactory в sys.path
        # 2. Импортирует модуль powerfactory
        # 3. Получает COM-объект приложения
        # 4. Активирует проект
        # 5. Возвращает объект app
```

**Процесс подключения:**
1. Добавление пути: `sys.path.append(POWERFACTORY_PATH)`
2. Импорт: `import powerfactory`
3. Получение приложения: `app = powerfactory.GetApplication()`
4. Активация проекта: `app.ActivateProject(PROJECT_NAME)`

**Обработка ошибок:**
- Если PowerFactory не установлен → `ModuleNotFoundError`
- Если проект не найден → `RuntimeError`
- Если приложение не получено → `RuntimeError`

---

### 2.2 powerfactory_locator - "Поиск объектов в модели"

**Что делает:** Находит объекты (ЛЭП, подстанции) в модели PowerFactory по имени.

**Ключевые функции:**

#### 2.2.1 `get_pf_line(app, name)`
Находит ЛЭП по локальному имени.

**Процесс:**
1. Получает все ЛЭП: `app.GetCalcRelevantObjects('*.ElmBranch')`
2. Ищет по атрибуту `loc_name`
3. Возвращает объект или выбрасывает ошибку

#### 2.2.2 `get_pf_substation(app, name)`
Находит подстанцию по локальному имени.

**Процесс:** Аналогично поиску ЛЭП, но для класса `*.ElmSubstat`

#### 2.2.3 `get_powerfactory_object_by_full_name(app, full_name)`
Находит объект по полному имени (используется для восстановления объектов из подрежимов).

**Процесс:**
1. Получает активный case: `app.GetActiveStudyCase()`
2. Ищет объект: `study_case.SearchObject(full_name)`
3. Возвращает объект

#### 2.2.4 `get_pf_line_data(pf_line)`
Извлекает параметры ЛЭП для отображения.

**Возвращает:**
```python
{
    'length': 120.5,           # Длина в км
    'Z1': '10.5+j25.3',        # Сопротивление прямой последовательности
    'Z0': '15.2+j35.1'         # Сопротивление нулевой последовательности
}
```

---

## Шаг 3: Анализ топологии - какие элементы рядом

### 3.1 TopologyAnalysisService - "Что вокруг защищаемой ЛЭП"

**Что делает:** Определяет, какие ЛЭП и АТ подключены к той же подстанции на том же уровне напряжения.

**Инициализация:**
```python
service = TopologyAnalysisService(protection_half_set)
# protection_half_set содержит информацию о ЛЭП и подстанции
```

**Основной метод:** `get_half_set_topology(app)`

**Пошаговый алгоритм:**

#### Шаг 3.1.1: Получение базовых данных
```python
line_pf_name = self.half_set.line.pf_name           # Имя ЛЭП в PowerFactory
substation_pf_name = self.half_set.substation.pf_name  # Имя подстанции
```

#### Шаг 3.1.2: Поиск объектов в PowerFactory
```python
pf_line = get_pf_line(app, line_pf_name)
pf_substation = get_pf_substation(app, substation_pf_name)
```

#### Шаг 3.1.3: Определение уровня напряжения
```python
voltage_level = self._get_pf_line_voltage_level(pf_line)
# Получает терминалы ЛЭП и берет напряжение первого терминала
```

#### Шаг 3.1.4: Поиск смежных ЛЭП
```python
def _get_substation_lines(app, pf_protected_line, pf_substation, voltage_level):
    # 1. Получает все ЛЭП в модели
    # 2. Для каждой ЛЭП (кроме защищаемой):
    #    - Получает терминалы ЛЭП
    #    - Проверяет, подключена ли к нашей подстанции
    #    - Проверяет, совпадает ли уровень напряжения
    #    - Если да - добавляет в список
```

**Результат для ЛЭП:**
```python
{
    'type': 'ЛЭП',
    'full_name': 'Network Model\Substation\Line1',
    'loc_name': 'ВЛ-500'
}
```

#### Шаг 3.1.5: Поиск автотрансформаторов
```python
def _get_substation_autotransformers(pf_substation, voltage_level):
    # 1. Получает все АТ на подстанции: pf_substation.GetContents('*.ElmTr3')
    # 2. Для каждого АТ:
    #    - Проверяет напряжение ВН
    #    - Если совпадает с уровнем напряжения ЛЭП - добавляет в список
```

**Результат для АТ:**
```python
{
    'type': 'АТ',
    'full_name': 'Network Model\Substation\Autotransformer1',
    'loc_name': 'АТ-500/220'
}
```

#### Шаг 3.1.6: Объединение результатов
```python
half_set_topology = substation_lines + substation_autotransformers
return half_set_topology  # Список словарей
```

**Пример результата:**
```python
[
    {'type': 'ЛЭП', 'full_name': '...', 'loc_name': 'ВЛ-1'},
    {'type': 'ЛЭП', 'full_name': '...', 'loc_name': 'ВЛ-2'},
    {'type': 'АТ', 'full_name': '...', 'loc_name': 'АТ-1'}
]
```

**Зачем это нужно:**
Эти элементы будут использоваться для генерации подрежимов - различных схем работы сети с отключенными элементами.

---

## Шаг 4: Генерация подрежимов - всевозможные схемы сети

### 4.1 SubmodesGenerator - "Генератор комбинаций отключений"

**Что делает:** Генерирует все возможные комбинации отключения элементов топологии.

**Входные данные:**
1. `half_set_topology` - список элементов (ЛЭП и АТ)
2. `half_set_submodes_data` - ограничения из формы:
   - `min_outages` - минимум отключений
   - `max_outages` - максимум отключений
   - `max_lines` - максимум отключенных ЛЭП
   - `max_autotransformers` - максимум отключенных АТ

**Основная функция:** `generate_half_set_submodes()`

**Алгоритм работы:**

#### Шаг 4.1.1: Подготовка данных
```python
total_lines_number = количество_ЛЭП_в_топологии()
total_autotransformers_number = количество_АТ_в_топологии()

min_outages = из_формы или 0
max_outages = из_формы или (len(topology) + 1) // 2
max_lines = из_формы или (total_lines_number + 1) // 2
max_autotransformers = из_формы или total_autotransformers_number // 2
```

#### Шаг 4.1.2: Генерация комбинаций
```python
def generate_submodes(topology, min_outages, max_outages):
    submodes = []
    for outages in range(min_outages, max_outages + 1):
        # Генерирует все комбинации из N элементов
        combinations = itertools.combinations(topology, outages)
        submodes.extend(combinations)
    return submodes
```

**Пример:**
Если топология = [ЛЭП-1, ЛЭП-2, АТ-1], то:
- outages=0: [] (нормальная схема)
- outages=1: [(ЛЭП-1,), (ЛЭП-2,), (АТ-1,)]
- outages=2: [(ЛЭП-1, ЛЭП-2), (ЛЭП-1, АТ-1), (ЛЭП-2, АТ-1)]
- outages=3: [(ЛЭП-1, ЛЭП-2, АТ-1)]

#### Шаг 4.1.3: Валидация подрежимов
```python
def validate_submodes(submodes, max_lines, max_autotransformers):
    valid_submodes = []
    for submode in submodes:
        lines_count = количество_ЛЭП_в_подрежиме(submode)
        at_count = количество_АТ_в_подрежиме(submode)
        
        if lines_count <= max_lines and at_count <= max_autotransformers:
            valid_submodes.append(submode)
    
    return valid_submodes
```

**Пример:**
Если max_lines=1, max_autotransformers=0:
- ✅ (ЛЭП-1,) - валиден (1 ЛЭП ≤ 1)
- ❌ (ЛЭП-1, ЛЭП-2) - невалиден (2 ЛЭП > 1)
- ❌ (АТ-1,) - невалиден (1 АТ > 0)

#### Шаг 4.1.4: Преобразование в формат для расчетов
```python
def transform_submodes(submodes):
    transformed = []
    for submode in submodes:
        # Формирует название подрежима
        if not submode:
            submode_name = 'Нормальная схема'
        else:
            names = [element['loc_name'] for element in submode]
            submode_name = f'Отключение {", ".join(names)}'
        
        # Извлекает полные имена для отключения
        submode_elements = [element['full_name'] for element in submode]
        
        transformed.append({
            'submode_name': submode_name,
            'submode_elements': submode_elements
        })
    
    return transformed
```

**Пример результата:**
```python
[
    {
        'submode_name': 'Нормальная схема',
        'submode_elements': []
    },
    {
        'submode_name': 'Отключение ВЛ-1',
        'submode_elements': ['Network Model\Substation\Line1']
    },
    {
        'submode_name': 'Отключение ВЛ-1, ВЛ-2',
        'submode_elements': ['Network Model\Substation\Line1', 'Network Model\Substation\Line2']
    }
]
```

**Зачем это нужно:**
Для каждого подрежима будет выполнен расчет токов КЗ, чтобы проверить работу защиты в различных схемах сети.

---

## Шаг 5: Расчет токов короткого замыкания

### 5.1 FaultCalculationService - "Расчет токов КЗ"

**Что делает:** Выполняет расчет токов короткого замыкания в PowerFactory для каждого подрежима и вида КЗ.

**Инициализация:**
```python
service = FaultCalculationService()
# Не требует параметров при создании
```

**Основной метод:** `perform_fault_calculation(app, protection_half_set, submodes, calculation_meta)`

**Пошаговый алгоритм:**

#### Шаг 5.1.1: Подготовка данных
```python
# Определяет защищаемую ЛЭП и подстанцию
line_pf_name = protection_half_set.line.pf_name
substation_pf_name = protection_half_set.substation.pf_name

# Находит объекты в PowerFactory
pf_line = get_pf_line(app, line_pf_name)
pf_substation = get_pf_substation(app, substation_pf_name)
```

#### Шаг 5.1.2: Определение узла КЗ
```python
def _get_fault_terminal(pf_line, pf_substation):
    # Получает терминалы защищаемой ЛЭП
    line_terminals = pf_line.GetConnectedElements()
    
    # Находит терминал противоположной подстанции
    for terminal in line_terminals:
        substation = terminal.GetParent()
        if substation != pf_substation:
            return terminal  # Это узел, где будет КЗ
```

**Логика:** КЗ моделируется на противоположной подстанции (не на той, где установлен полукомплект).

#### Шаг 5.1.3: Цикл по подрежимам
```python
for submode in submodes:
    # Для каждого подрежима выполняются расчеты
```

#### Шаг 5.1.4: Подготовка подрежима
```python
# Извлекает полные имена элементов для отключения
submode_elements_full_names = submode.get('submode_elements')

# Восстанавливает объекты PowerFactory по полным именам
submode_elements = []
for full_name in submode_elements_full_names:
    element = get_powerfactory_object_by_full_name(app, full_name)
    submode_elements.append(element)

# Отключает элементы
for element in submode_elements:
    element.SwitchOff()
```

**Важно:** Элементы отключаются временно, потом будут включены обратно.

#### Шаг 5.1.5: Расчет для каждого вида КЗ
```python
FAULTS = {
    '3psc': 'К(3)',  # Трехфазное КЗ
    'spgf': 'К(1)'   # Однофазное КЗ
}

for pf_fault_type, fault_type in FAULTS.items():
    # Выполняет расчет
    fault_values = self._execute_fault(app, pf_line, fault_terminal, pf_fault_type)
    
    # Сохраняет результаты
    self._save_results_to_db(...)
```

#### Шаг 5.1.6: Выполнение расчета КЗ в PowerFactory
```python
def _execute_fault(self, app, pf_line, fault_terminal, fault_type):
    # 1. Получает объект расчета КЗ
    fault = app.GetFromStudyCase('ComShc')
    
    # 2. Настраивает параметры
    fault.SetAttribute('iopt_mde', 1)        # Метод: MDE
    fault.SetAttribute('iopt_cnf', 0)        # Конфигурация
    fault.SetAttribute('iopt_shc', fault_type)  # Вид КЗ: '3psc' или 'spgf'
    fault.SetAttribute('Rf', 0)              # Сопротивление замыкания = 0
    fault.SetAttribute('Xf', 0)              # Реактивность замыкания = 0
    fault.SetAttribute('iopt_allbus', 0)     # Не на всех шинах
    fault.SetAttribute('shcobj', fault_terminal)  # Узел КЗ
    
    # 3. Выполняет расчет
    fault.Execute()
    
    # 4. Извлекает результаты из защищаемой ЛЭП
    pos_sequence_current = pf_line.GetAttribute('m:I1:0')      # Ток прямой последовательности
    neg_sequence_current = pf_line.GetAttribute('m:I2:0')      # Ток обратной последовательности
    triple_zero_sequence_current = pf_line.GetAttribute('m:I0x3:0')  # 3*I0
    neg_sequence_voltage = pf_line.GetAttribute('n:U2:0')      # Напряжение обратной последовательности
    
    # 5. Формирует результат
    results = {
        'I1': round(pos_sequence_current * 1000, 0),      # мА
        'I2': round(neg_sequence_current * 1000, 0),      # мА
        '3I0': round(triple_zero_sequence_current * 1000, 0),  # мА
        'U2': round(neg_sequence_voltage, 0)              # В
    }
    
    return results
```

**Что означают атрибуты:**
- `m:I1:0` - Измеренное значение тока прямой последовательности в момент времени 0
- `m:I2:0` - Ток обратной последовательности
- `m:I0x3:0` - Ток нулевой последовательности, умноженный на 3
- `n:U2:0` - Нормализованное напряжение обратной последовательности

#### Шаг 5.1.7: Сохранение результатов
```python
FaultCalculation.objects.create(
    calculation_meta=calculation_meta,
    protection_half_set=protection_half_set,
    fault_type='К(3)',  # или 'К(1)'
    fault_location='ПС Сибирь',  # Имя узла
    network_topology='Отключение ВЛ-1',  # Название подрежима
    fault_values={'I1': 15000, 'I2': 0, '3I0': 0, 'U2': 0}
)
```

#### Шаг 5.1.8: Включение элементов обратно
```python
# После всех расчетов для подрежима
for element in submode_elements:
    element.SwitchOn()  # Включаем обратно
```

**Важно:** Элементы должны быть включены перед переходом к следующему подрежиму.

**Пример работы:**
1. Подрежим: "Отключение ВЛ-1"
   - Отключается ВЛ-1
   - Расчет К(3): I1 = 15000 мА
   - Расчет К(1): I1 = 8000 мА, I2 = 8000 мА, 3I0 = 9000 мА
   - Включается ВЛ-1
2. Подрежим: "Отключение ВЛ-2"
   - Отключается ВЛ-2
   - Расчет К(3): I1 = 12000 мА
   - И т.д.

**Зачем это нужно:**
Результаты используются для:
1. Расчетов уставок (например, DI1 использует минимальный ток К(3))
2. Анализа чувствительности (сравнение уставки с током КЗ)

---

## Шаг 6: Расчет параметров настройки защиты

### 6.1 SettingsCalculationService - "Расчет уставок"

**Что делает:** Рассчитывает значения уставок для всех органов защиты на основе коэффициентов и результатов расчетов КЗ.

**Инициализация:**
```python
service = SettingsCalculationService(calculation_meta, calculation_factors)
# calculation_meta - мета-данные расчета
# calculation_factors - словарь с коэффициентами из формы
```

**Основной метод:** `run()`

**Алгоритм работы:**

#### Шаг 6.1.1: Цикл по полукомплектам
```python
for protection_half_set in self.protection_half_sets:
    # Получает все органы защиты для данного полукомплекта
    components = protection_half_set.protection_device.components.all()
```

#### Шаг 6.1.2: Цикл по органам защиты
```python
for component in components:
    # Определяет функцию расчета
    calculation_function = self.get_calculation_function(component)
    
    if calculation_function:
        # Выполняет расчет
        result, factors = calculation_function()
        
        # Сохраняет результат
        self.save_result_to_db(...)
```

#### Шаг 6.1.3: Определение функции расчета
```python
def get_calculation_function(self, component):
    # Карта: название органа → функция расчета
    CALCULATION_MAP = {
        "IЛ БЛОК": self.calculate_il_block,
        "IЛ ОТКЛ": self.calculate_il_break,
        "I2 БЛОК": self.calculate_i2_block,
        # ... и т.д.
    }
    
    # Получает название органа
    setting_designation = component.setting_designation
    
    # Возвращает функцию расчета
    return CALCULATION_MAP.get(setting_designation)
```

### 6.2 Примеры расчетных функций

#### 6.2.1 IЛ БЛОК (Блокировка по фазному току)
```python
def calculate_il_block(self):
    # Коэффициенты из формы
    il_grading_factor = self.calculation_factors.get("il_grading_factor", 1.3)
    il_reset_factor = self.calculation_factors.get("il_reset_factor", 0.9)
    
    # Формула
    il_block_value = (
        sqrt(3) * il_grading_factor / il_reset_factor * self.line.current_capacity
    )
    
    # Коэффициенты для сохранения
    calculation_factors = {
        "Коэффициент отстройки": il_grading_factor,
        "Коэффициент возврата": il_reset_factor,
    }
    
    return il_block_value, calculation_factors
```

**Формула:** `√3 × Kотст / Kвозвр × Iраб`

**Пример:** √3 × 1.3 / 0.9 × 2000 = 5005 А

#### 6.2.2 IЛ ОТКЛ (Отключение по фазному току)
```python
def calculate_il_break(self):
    # Использует значение блокировки
    il_block_value = self.calculate_il_block()[0]
    
    # Коэффициент согласования
    il_matching_factor = self.calculation_factors.get("il_matching_factor", 1.4)
    
    # Формула
    il_break_value = il_matching_factor * il_block_value
    
    calculation_factors = {"Коэффициент согласования": il_matching_factor}
    return il_break_value, calculation_factors
```

**Формула:** `Kсогл × IЛ БЛОК`

**Пример:** 1.4 × 5005 = 7007 А

#### 6.2.3 DI1 ОТКЛ (Отключение по дифференциальному току)
```python
def calculate_di1_break(self):
    # Получает все расчеты КЗ для трехфазных КЗ
    fault_calculations = FaultCalculation.objects.filter(
        protection_half_set__in=self.protection_half_sets,
        fault_type="К(3)"
    )
    
    # Извлекает токи прямой последовательности
    pos_sequence_currents = []
    for fault_calculation in fault_calculations:
        i1 = fault_calculation.fault_values.get("I1")
        if i1 != 0:
            pos_sequence_currents.append(i1)
    
    # Находит минимальный ток
    min_i1 = min(pos_sequence_currents)  # в мА
    
    # Формула (коэффициент чувствительности = 2)
    di1_break_value = min_i1 / self.current_sensitivity_rate / 1000  # Переводим в А
    
    calculation_factors = {
        "Коэффициент чувствительности": self.current_sensitivity_rate
    }
    
    return di1_break_value, calculation_factors
```

**Формула:** `min(I1 всех К(3)) / Kчувств`

**Пример:** min(15000, 12000, 18000) / 2 / 1000 = 6 А

**Логика:** Берется минимальный ток КЗ, чтобы обеспечить чувствительность в худшем случае.

#### 6.2.4 I2 БЛОК (Блокировка по обратному току)
```python
def calculate_i2_block(self):
    # Коэффициенты
    i2_imbalance_factor = self.calculation_factors.get("i2_imbalance_factor", 0.05)
    i2_grading_factor = self.calculation_factors.get("i2_grading_factor", 1.3)
    i2_reset_factor = self.calculation_factors.get("i2_reset_factor", 0.9)
    
    # Ток небаланса
    i2_imbalance_current = i2_imbalance_factor * self.line.current_capacity
    
    # Формула
    i2_block_value = i2_grading_factor / i2_reset_factor * i2_imbalance_current
    
    calculation_factors = {
        "Коэффициент небаланса": i2_imbalance_factor,
        "Коэффициент отстройки": i2_grading_factor,
        "Коэффициент возврата": i2_reset_factor,
    }
    
    return i2_block_value, calculation_factors
```

**Формула:** `Kотст / Kвозвр × Kнебаланса × Iраб`

**Пример:** 1.3 / 0.9 × 0.05 × 2000 = 144 А

**Логика:** Защита отстраивается от небаланса токов при нормальной работе.

#### 6.2.5 УГОЛ БЛОК (Угол блокировки)
```python
def calculate_blocking_angle(self):
    if self.line.length < 60:
        blocking_angle = 50
    elif 60 <= self.line.length < 150:
        blocking_angle = 60
    else:
        blocking_angle = 65
    
    return blocking_angle
```

**Логика:** Зависит от длины ЛЭП. Чем длиннее ЛЭП, тем больше угол.

**Зачем это нужно:**
Все эти уставки будут использоваться для анализа чувствительности - проверки, сработает ли защита при различных видах КЗ.

---

## Шаг 7: Анализ чувствительности

### 7.1 SensitivityAnalysisService - "Проверка чувствительности"

**Что делает:** Сравнивает рассчитанные уставки с токами КЗ и определяет, насколько хорошо защита реагирует на повреждения.

**Инициализация:**
```python
service = SensitivityAnalysisService(calculation_meta)
# calculation_meta - мета-данные расчета
```

**Основной метод:** `run()`

**Алгоритм работы:**

#### Шаг 7.1.1: Получение всех расчетов уставок
```python
settings_calculations = SettingsCalculation.objects.filter(
    calculation_meta=self.calculation_meta
)
```

#### Шаг 7.1.2: Цикл по расчетам уставок
```python
for settings_calculation in settings_calculations:
    component = settings_calculation.component  # Какой орган
    protection_half_set = settings_calculation.protection_half_set
    result_value = settings_calculation.result_value  # Значение уставки
    
    # Определяет обработчик для данного органа
    handler = self._get_handler(component)
```

#### Шаг 7.1.3: Определение обработчика
```python
SENSITIVITY_HANDLERS = {
    "IЛ ОТКЛ": {
        "function": _calculate_phase_current_diff_sensitivity,
        "fault_types": ["К(3)"],
        "fault_value": "I1"
    },
    "I2 ОТКЛ": {
        "function": _calculate_current_sensitivity,
        "fault_types": ["К(2)", "К(1,1)", "К(1)"],
        "fault_value": "I2"
    },
    "DI1 ОТКЛ": {
        "function": _calculate_current_sensitivity,
        "fault_types": ["К(3)"],
        "fault_value": "I1"
    },
    # ... и т.д.
}

def _get_handler(self, component):
    return SENSITIVITY_HANDLERS.get(component.setting_designation)
```

**Обработчик содержит:**
- Функцию расчета чувствительности
- Какие виды КЗ учитывать
- Какое значение из fault_values использовать (I1, I2, U2)

#### Шаг 7.1.4: Получение расчетов КЗ
```python
if handler:
    fault_types = handler["fault_types"]  # ["К(3)"] или ["К(2)", "К(1,1)", "К(1)"]
    target_fault_value = handler["fault_value"]  # "I1" или "I2" или "U2"
    
    # Получает все расчеты КЗ с нужными видами
    fault_calculations = FaultCalculation.objects.filter(
        calculation_meta=self.calculation_meta,
        protection_half_set=protection_half_set,
        fault_type__in=fault_types
    )
```

#### Шаг 7.1.5: Расчет коэффициента чувствительности
```python
for fault_calculation in fault_calculations:
    # Извлекает значение тока/напряжения
    fault_value = fault_calculation.fault_values.get(target_fault_value)
    
    # Вызывает функцию расчета
    sensitivity_analysis_function = handler["function"]
    sensitivity_rate = sensitivity_analysis_function(result_value, fault_value)
    
    # Сохраняет результат
    self._save_result_to_db(...)
```

### 7.2 Формулы чувствительности

#### 7.2.1 Для фазного тока (IЛ ОТКЛ)
```python
def _calculate_phase_current_diff_sensitivity(result_value, fault_value):
    # result_value - уставка в А
    # fault_value - ток КЗ в мА
    
    sensitivity_rate = sqrt(3) * fault_value / result_value
    return sensitivity_rate
```

**Формула:** `√3 × IКЗ / Iуставка`

**Пример:** √3 × 15000 мА / 7007 А = 3.7

**Логика:** Учитывается, что при трехфазном КЗ токи в трех фазах суммируются.

#### 7.2.2 Для остальных органов
```python
def _calculate_current_sensitivity(result_value, fault_value):
    # result_value - уставка
    # fault_value - значение из КЗ (ток в мА или напряжение в В)
    
    sensitivity_rate = fault_value / result_value
    return sensitivity_rate
```

**Формула:** `Значение_КЗ / Уставка`

**Пример для DI1 ОТКЛ:**
- Уставка: 6 А
- Ток КЗ: 15000 мА = 15 А
- Чувствительность: 15 / 6 = 2.5

**Пример для I2 ОТКЛ:**
- Уставка: 200 А
- Ток КЗ: 8000 мА = 8 А
- Чувствительность: 8 / 200 = 0.04 (НЕЧУВСТВИТЕЛЬНА!)

### 7.3 Интерпретация результатов

**Коэффициент чувствительности показывает:**
- Во сколько раз значение при КЗ больше уставки
- Если > 1 - защита сработает
- Если < 1 - защита НЕ сработает

**Статусы:**
- ≤ 1.0 → "Нечувствительна" (защита не сработает)
- 1.0 - 2.0 → "Низкая чувствительность" (сработает, но недостаточно надежно)
- ≥ 2.0 → "Чувствительна" (нормальная работа)

**Автоматическое определение статуса:**
```python
def save(self):
    if self.sensitivity_rate <= 1:
        self.status = 'Нечувствительна'
    elif 1 < self.sensitivity_rate < 2:
        self.status = 'Низкая чувствительность'
    else:
        self.status = 'Чувствительна'
    super().save()
```

### 7.4 Сохранение результатов
```python
SensitivityAnalysis.objects.create(
    settings_calculation=settings_calculation,  # Какая уставка
    fault_calculation=fault_calculation,        # Какой расчет КЗ
    sensitivity_rate=2.5,                       # Коэффициент
    # status устанавливается автоматически при save()
)
```

**Пример результата:**
- Уставка: IЛ ОТКЛ = 7007 А
- Расчет КЗ: К(3) в нормальной схеме, I1 = 15000 мА
- Чувствительность: 3.7
- Статус: "Чувствительна"

**Зачем это нужно:**
Анализ чувствительности показывает инженеру:
1. Работает ли защита во всех режимах
2. В каких случаях чувствительность недостаточна
3. Нужно ли корректировать уставки

---

## Шаг 8: Общий поток работы (итоговый)

### 8.1 Последовательность операций

```
1. Пользователь открывает страницу расчета
   ↓
2. Выбирает ЛЭП из списка
   ↓
3. Система анализирует топологию:
   - Находит смежные ЛЭП и АТ
   - Определяет уровень напряжения
   - Сохраняет в сессию
   ↓
4. Пользователь настраивает параметры подрежимов:
   - Минимум/максимум отключений
   - Максимум ЛЭП/АТ
   ↓
5. Система генерирует подрежимы:
   - Все комбинации отключений
   - Валидация по ограничениям
   - Сохранение в сессию
   ↓
6. Пользователь вводит коэффициенты расчета
   ↓
7. Пользователь запускает расчет
   ↓
8. Создается CalculationMeta (регистрация расчета)
   ↓
9. Подключение к PowerFactory
   ↓
10. Расчет токов КЗ:
    Для каждого полукомплекта:
      Для каждого подрежима:
        Отключить элементы
        Для каждого вида КЗ:
          Выполнить расчет
          Извлечь токи
          Сохранить в БД
        Включить элементы
   ↓
11. Освобождение COM-объекта PowerFactory
   ↓
12. Расчет параметров настройки:
    Для каждого полукомплекта:
      Для каждого органа:
        Определить функцию расчета
        Выполнить расчет
        Сохранить результат
   ↓
13. Анализ чувствительности:
    Для каждой уставки:
      Для каждого расчет КЗ:
        Рассчитать коэффициент
        Сохранить результат
   ↓
14. Перенаправление на страницу результатов
```

### 8.2 Пример полного расчета

**Исходные данные:**
- ЛЭП: "ВЛ 500 кВ Сибирь-Центр"
- Топология: 3 ЛЭП, 1 АТ
- Подрежимы: нормальная схема, отключение ВЛ-1, отключение ВЛ-2

**Результаты расчетов КЗ:**
1. К(3), нормальная схема: I1 = 15000 мА
2. К(3), отключение ВЛ-1: I1 = 12000 мА
3. К(3), отключение ВЛ-2: I1 = 10000 мА
4. К(1), нормальная схема: I2 = 8000 мА, U2 = 5000 В
5. ... (еще 3 расчета К(1))

**Расчет уставок:**
- IЛ БЛОК = 5000 А
- IЛ ОТКЛ = 7000 А
- DI1 ОТКЛ = 5 А (min(15000, 12000, 10000) / 2 / 1000)
- I2 БЛОК = 144 А
- ... (еще органы)

**Анализ чувствительности:**
- IЛ ОТКЛ vs К(3) нормальная: 3.7 → "Чувствительна"
- IЛ ОТКЛ vs К(3) отключение ВЛ-1: 3.0 → "Чувствительна"
- DI1 ОТКЛ vs К(3) нормальная: 3.0 → "Чувствительна"
- I2 ОТКЛ vs К(1) нормальная: 0.06 → "Нечувствительна" ⚠️
- ... (еще анализы)

**Выводы:**
- Большинство органов работают хорошо
- I2 ОТКЛ нечувствительна - нужно проверить настройки

---

Это полный разбор модуля calculation! Каждый шаг можно изучить подробнее, посмотрев соответствующий код.

