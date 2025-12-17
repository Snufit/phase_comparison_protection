# Руководство по созданию записей в БД

Это руководство описывает различные способы создания записей для моделей:
- `LineType` (Тип ЛЭП)
- `Substation` (Подстанция)
- `Line` (ЛЭП)
- `LineBranch` (Ответвление ЛЭП)

## Способы создания записей

### 1. Через Django Admin (Веб-интерфейс)

Самый простой способ для ручного ввода данных.

#### Шаги:
1. Запустите сервер разработки:
   ```bash
   python manage.py runserver
   ```

2. Откройте в браузере: `http://127.0.0.1:8000/admin/`

3. Войдите с учетными данными суперпользователя

4. В разделе "Core" вы найдете:
   - **Типы ЛЭП** (LineType)
   - **Подстанции** (Substation)
   - **ЛЭП** (Line)
   - **Ответвления ЛЭП** (LineBranch)

5. Нажмите "Добавить" для создания новой записи

#### Преимущества:
- ✅ Удобный графический интерфейс
- ✅ Валидация данных
- ✅ Поиск и фильтрация
- ✅ Связи между моделями через выпадающие списки

---

### 2. Через команду управления Django

Автоматическое создание записей через командную строку.

#### Команда: `create_line_data`

```bash
# Создать все записи (типы ЛЭП, подстанции, ЛЭП)
python manage.py create_line_data

# Создать только типы ЛЭП
python manage.py create_line_data --line-type-only

# Создать ЛЭП с ответвлениями
python manage.py create_line_data --with-branches

# Очистить существующие записи перед созданием
python manage.py create_line_data --clear
```

#### Что создается:
- **Типы ЛЭП**: Одиночная, Параллельная, С ответвлениями, Двухцепная
- **Подстанции**: 4 примера подстанций
- **ЛЭП**: 2 примера ЛЭП
- **Ответвления**: При использовании `--with-branches`

---

### 3. Программное создание (Python код)

Используйте в Django shell, views, командах управления или скриптах импорта.

#### Запуск Django Shell:
```bash
python manage.py shell
```

#### Примеры использования:

```python
from core.models import Line, LineBranch, LineType, Substation

# 1. Создание типа ЛЭП
line_type = LineType.objects.create(type_code="Одиночная ЛЭП")

# 2. Создание подстанции
substation = Substation.objects.create(
    dispatch_name="ПС 500 кВ Ново-Анжерская",
    pf_name="ПС Ново-Анжерская"
)

# 3. Создание ЛЭП
line = Line.objects.create(
    dispatch_name="ВЛ 500 кВ Ново-Анжерская - Томская",
    pf_name="ВЛ 527",
    line_type=line_type,
    voltage_level=500.0,
    length=150.5,
    current_capacity=2000.0,
)

# 4. Создание ответвления
branch = LineBranch.objects.create(
    line=line,
    substation=substation,
    dispatch_name="Ответвление ВЛ 500 кВ - ПС Северная",
    pf_name="ВЛ_527_branch_Северная",
    length=25.0,
    is_active=True,
)
```

#### Подробные примеры:
См. файл `core/examples/create_records_examples.py` с полными примерами всех способов создания.

---

## Структура моделей и связи

### LineType (Тип ЛЭП)
- `type_code` - Наименование типа ЛЭП (уникальное)

### Substation (Подстанция)
- `dispatch_name` - Диспетчерское наименование (уникальное)
- `pf_name` - Наименование в PowerFactory (опционально)

### Line (ЛЭП)
- `dispatch_name` - Диспетчерское наименование (уникальное)
- `pf_name` - Наименование в PowerFactory (опционально)
- `line_type` - Связь с LineType (ForeignKey)
- `voltage_level` - Номинальное напряжение, кВ
- `length` - Длина ЛЭП, км
- `current_capacity` - ДДТН, А
- `ct` - Трансформатор тока (ForeignKey, опционально)
- `vt` - Трансформатор напряжения (ForeignKey, опционально)
- И другие поля...

### LineBranch (Ответвление ЛЭП)
- `line` - Связь с Line (ForeignKey)
- `substation` - Связь с Substation (ForeignKey)
- `dispatch_name` - Диспетчерское наименование (опционально)
- `pf_name` - Наименование в PowerFactory (уникальное)
- `length` - Длина ответвления, км
- `is_active` - Активно ли ответвление
- `protection_recommendation` - Рекомендация по защите (опционально)

---

## Порядок создания записей

При создании записей важно соблюдать порядок из-за внешних ключей:

1. **Сначала**: `LineType` (не зависит от других моделей)
2. **Затем**: `Substation` (не зависит от других моделей)
3. **Потом**: `Line` (требует `LineType`)
4. **В конце**: `LineBranch` (требует `Line` и `Substation`)

---

## Полезные методы Django ORM

### get_or_create()
Создает запись только если она не существует:
```python
line_type, created = LineType.objects.get_or_create(
    type_code="Одиночная ЛЭП"
)
```

### bulk_create()
Массовое создание записей (быстрее для больших объемов):
```python
substations = [
    Substation(dispatch_name="ПС 1"),
    Substation(dispatch_name="ПС 2"),
]
Substation.objects.bulk_create(substations, ignore_conflicts=True)
```

### update()
Массовое обновление:
```python
Line.objects.filter(voltage_level=220.0).update(current_capacity=1500.0)
```

---

## Проверка созданных записей

### Через Django Shell:
```python
from core.models import Line, LineBranch, LineType, Substation

# Количество записей
print(f"Типов ЛЭП: {LineType.objects.count()}")
print(f"Подстанций: {Substation.objects.count()}")
print(f"ЛЭП: {Line.objects.count()}")
print(f"Ответвлений: {LineBranch.objects.count()}")

# Список всех записей
for line in Line.objects.all():
    print(f"ЛЭП: {line.dispatch_name}, Напряжение: {line.voltage_level} кВ")
```

### Через Django Admin:
Откройте `/admin/core/` и просмотрите все созданные записи.

---

## Импорт данных из PowerFactory

Для автоматического импорта данных из PowerFactory используйте команду:

```bash
python manage.py extract_lines
```

Эта команда извлекает информацию о ЛЭП из активного проекта PowerFactory.

---

## Устранение проблем

### Ошибка: "Foreign key constraint failed"
**Причина**: Попытка создать запись с несуществующим внешним ключом.

**Решение**: Сначала создайте связанные записи (см. "Порядок создания записей").

### Ошибка: "UNIQUE constraint failed"
**Причина**: Попытка создать запись с дублирующимся уникальным значением.

**Решение**: Используйте `get_or_create()` вместо `create()`.

### Ошибка: "NOT NULL constraint failed"
**Причина**: Не указано обязательное поле.

**Решение**: Проверьте, что все обязательные поля заполнены (см. структуру моделей выше).

---

## Дополнительные ресурсы

- **Примеры кода**: `core/examples/create_records_examples.py`
- **Команда создания**: `core/management/commands/create_line_data.py`
- **Админ-интерфейс**: `core/admin.py`
- **Модели**: `core/models.py`

