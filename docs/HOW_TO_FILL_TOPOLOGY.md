# Как записать данные в HalfSetTopology

## Структура модели HalfSetTopology

```python
class HalfSetTopology(models.Model):
    protection_half_set = OneToOneField(ProtectionHalfSet)  # Связь с полукомплектом
    topology_data = JSONField()  # Список элементов топологии
    voltage_level = DecimalField()  # Напряжение, кВ
    last_updated = DateTimeField()  # Дата обновления (автоматически)
    topology_hash = CharField()  # MD5 хэш для проверки изменений
```

## Формат данных topology_data

`topology_data` - это **список словарей**, где каждый словарь описывает один элемент топологии:

```python
topology_data = [
    {
        'type': 'ЛЭП',  # или 'АТ'
        'full_name': 'Сеть\Сеть 500 кВ\ВЛ 500 кВ Усть-Илимская ГЭС - Братск',
        'loc_name': 'ВЛ 500 Усть-Илимская ГЭС - Братск'
    },
    {
        'type': 'ЛЭП',
        'full_name': 'Сеть\Сеть 500 кВ\ВЛ 500 кВ Братск - Иркутск',
        'loc_name': 'ВЛ 500 Братск - Иркутск'
    },
    {
        'type': 'АТ',
        'full_name': 'Сеть\Сеть 500 кВ\ПС 500 кВ Братск\АТ 500/220 Братск',
        'loc_name': 'АТ 500/220 Братск'
    },
]
```

**Поля:**
- `type` - тип элемента: `'ЛЭП'` или `'АТ'`
- `full_name` - полное имя объекта в PowerFactory (для поиска через `get_powerfactory_object_by_full_name`)
- `loc_name` - краткое имя объекта (для отображения)

---

## Способ 1: Автоматически (рекомендуется)

Данные автоматически сохраняются при вызове `TopologyAnalysisService.get_half_set_topology()`:

```python
from core.models import ProtectionHalfSet
from calculation.services.topology_analysis_service import TopologyAnalysisService
from calculation.services.powerfactory_manager import PowerFactoryManager

# Получаем полукомплект
half_set = ProtectionHalfSet.objects.get(id=1)

# Создаем сервис
topology_service = TopologyAnalysisService(half_set)

# Получаем топологию (автоматически сохранится в БД)
pf_manager = PowerFactoryManager()
app = pf_manager.get_application()
topology = topology_service.get_half_set_topology(app=app)

# Теперь данные в БД!
# Можно проверить:
from core.models import HalfSetTopology
topology_obj = HalfSetTopology.objects.get(protection_half_set=half_set)
print(topology_obj.topology_data)
```

**Что происходит:**
1. Метод `get_half_set_topology()` сначала проверяет БД
2. Если данных нет или они устарели (>30 дней) - получает из PowerFactory
3. Автоматически вызывает `_save_topology_to_db()` и сохраняет в БД

---

## Способ 2: Вручную через Django Shell

### Пример 1: Простая запись

```python
python manage.py shell
```

```python
from core.models import ProtectionHalfSet, HalfSetTopology
import hashlib
import json
from decimal import Decimal

# Получаем полукомплект
half_set = ProtectionHalfSet.objects.get(id=1)

# Подготавливаем данные топологии
topology_data = [
    {
        'type': 'ЛЭП',
        'full_name': 'Сеть\Сеть 500 кВ\ВЛ 500 кВ Усть-Илимская ГЭС - Братск',
        'loc_name': 'ВЛ 500 Усть-Илимская ГЭС - Братск'
    },
    {
        'type': 'АТ',
        'full_name': 'Сеть\Сеть 500 кВ\ПС 500 кВ Братск\АТ 500/220 Братск',
        'loc_name': 'АТ 500/220 Братск'
    },
]

# Вычисляем хэш
topology_json = json.dumps(topology_data, sort_keys=True)
topology_hash = hashlib.md5(topology_json.encode()).hexdigest()

# Получаем напряжение
voltage_level = half_set.line.voltage_level if half_set.line.voltage_level else None

# Создаем или обновляем запись
topology_obj, created = HalfSetTopology.objects.update_or_create(
    protection_half_set=half_set,
    defaults={
        'topology_data': topology_data,
        'topology_hash': topology_hash,
        'voltage_level': voltage_level,
    }
)

if created:
    print(f"Создана новая запись: {topology_obj.id}")
else:
    print(f"Обновлена существующая запись: {topology_obj.id}")
```

### Пример 2: Массовая запись для всех полукомплектов линии

```python
from core.models import Line, ProtectionHalfSet, HalfSetTopology
import hashlib
import json

# Получаем линию
line = Line.objects.get(id=1)

# Получаем все полукомплекты этой линии
half_sets = line.protection_half_sets.all()

# Примерные данные топологии (в реальности получаются из PowerFactory)
example_topology = [
    {
        'type': 'ЛЭП',
        'full_name': 'Сеть\Сеть 500 кВ\ВЛ 500 кВ Усть-Илимская ГЭС - Братск',
        'loc_name': 'ВЛ 500 Усть-Илимская ГЭС - Братск'
    },
]

for half_set in half_sets:
    # Вычисляем хэш
    topology_json = json.dumps(example_topology, sort_keys=True)
    topology_hash = hashlib.md5(topology_json.encode()).hexdigest()
    
    # Получаем напряжение
    voltage_level = line.voltage_level if line.voltage_level else None
    
    # Сохраняем
    HalfSetTopology.objects.update_or_create(
        protection_half_set=half_set,
        defaults={
            'topology_data': example_topology,
            'topology_hash': topology_hash,
            'voltage_level': voltage_level,
        }
    )
    print(f"Сохранена топология для полукомплекта: {half_set}")
```

---

## Способ 3: Через Django Management Command

Используй готовую команду `fill_topology_example.py`:

```bash
# Для конкретного полукомплекта
python manage.py fill_topology_example --half-set-id 1

# Для всех полукомплектов линии
python manage.py fill_topology_example --line-id 1
```

---

## Способ 4: Прямое использование update_or_create

```python
from core.models import HalfSetTopology, ProtectionHalfSet
import hashlib
import json

half_set = ProtectionHalfSet.objects.get(id=1)

topology_data = [
    {'type': 'ЛЭП', 'full_name': '...', 'loc_name': '...'},
    # ... другие элементы
]

# Вычисляем хэш
topology_hash = hashlib.md5(
    json.dumps(topology_data, sort_keys=True).encode()
).hexdigest()

# Записываем
HalfSetTopology.objects.update_or_create(
    protection_half_set=half_set,
    defaults={
        'topology_data': topology_data,
        'topology_hash': topology_hash,
        'voltage_level': half_set.line.voltage_level,
    }
)
```

---

## Важные моменты

### 1. Хэш вычисляется автоматически

Хэш нужен для быстрой проверки, изменилась ли топология. Вычисляется так:

```python
import hashlib
import json

topology_json = json.dumps(topology_data, sort_keys=True)
topology_hash = hashlib.md5(topology_json.encode()).hexdigest()
```

**Важно:** `sort_keys=True` - чтобы порядок элементов не влиял на хэш!

### 2. Напряжение берется из Line

```python
voltage_level = half_set.line.voltage_level
```

Если у линии нет напряжения, можно указать `None` или конкретное значение.

### 3. update_or_create vs create

- **`update_or_create`** - создаст новую запись или обновит существующую (рекомендуется)
- **`create`** - создаст новую запись, но выдаст ошибку, если уже существует

### 4. Связь OneToOne

У каждого `ProtectionHalfSet` может быть **только одна** запись `HalfSetTopology`. Если попытаться создать вторую - получишь ошибку.

---

## Проверка записанных данных

```python
from core.models import HalfSetTopology, ProtectionHalfSet

# Получаем полукомплект
half_set = ProtectionHalfSet.objects.get(id=1)

# Получаем топологию
try:
    topology_obj = HalfSetTopology.objects.get(protection_half_set=half_set)
    print(f"Топология найдена:")
    print(f"  - ID: {topology_obj.id}")
    print(f"  - Элементов: {len(topology_obj.topology_data)}")
    print(f"  - Напряжение: {topology_obj.voltage_level} кВ")
    print(f"  - Обновлено: {topology_obj.last_updated}")
    print(f"  - Хэш: {topology_obj.topology_hash}")
    print(f"\nЭлементы топологии:")
    for element in topology_obj.topology_data:
        print(f"    - {element['type']}: {element['loc_name']}")
except HalfSetTopology.DoesNotExist:
    print("Топология не найдена")
```

---

## Пример полного скрипта

```python
from core.models import ProtectionHalfSet, HalfSetTopology
import hashlib
import json

def save_topology_manually(half_set_id: int, topology_data: list):
    """
    Сохраняет топологию для полукомплекта вручную.
    
    Args:
        half_set_id: ID полукомплекта защиты
        topology_data: Список словарей с элементами топологии
    """
    try:
        half_set = ProtectionHalfSet.objects.get(id=half_set_id)
    except ProtectionHalfSet.DoesNotExist:
        print(f"Полукомплект с ID {half_set_id} не найден")
        return
    
    # Вычисляем хэш
    topology_json = json.dumps(topology_data, sort_keys=True)
    topology_hash = hashlib.md5(topology_json.encode()).hexdigest()
    
    # Получаем напряжение
    voltage_level = half_set.line.voltage_level if half_set.line.voltage_level else None
    
    # Сохраняем
    topology_obj, created = HalfSetTopology.objects.update_or_create(
        protection_half_set=half_set,
        defaults={
            'topology_data': topology_data,
            'topology_hash': topology_hash,
            'voltage_level': voltage_level,
        }
    )
    
    if created:
        print(f"✓ Создана топология для {half_set} (ID: {topology_obj.id})")
    else:
        print(f"↻ Обновлена топология для {half_set} (ID: {topology_obj.id})")
    
    return topology_obj

# Использование:
topology = [
    {'type': 'ЛЭП', 'full_name': '...', 'loc_name': 'ВЛ-1'},
    {'type': 'АТ', 'full_name': '...', 'loc_name': 'АТ-1'},
]
save_topology_manually(half_set_id=1, topology_data=topology)
```

