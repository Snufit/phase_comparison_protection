#!/usr/bin/env python
"""
Скрипт для генерации PlantUML-диаграмм классов из Django-моделей и сервисов.

Использование:
    python generate_plantuml.py --models-only    # Только модели Django
    python generate_plantuml.py --services-only   # Только сервисы
    python generate_plantuml.py --all             # Все классы
"""

import os
import sys
import django
from pathlib import Path

# Настройка Django окружения
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Временно убираем django_extensions из INSTALLED_APPS, если он не установлен
# Делаем это ДО django.setup(), чтобы избежать ошибок импорта
try:
    import django_extensions
    _has_django_extensions = True
except ImportError:
    _has_django_extensions = False
    # Устанавливаем переменную окружения, которая будет использована в settings.py
    os.environ['SKIP_DJANGO_EXTENSIONS'] = '1'

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'phase_comparison_protection.settings')
django.setup()

# После setup проверяем и убираем django_extensions, если нужно
if not _has_django_extensions:
    from django.conf import settings
    if hasattr(settings, 'INSTALLED_APPS') and 'django_extensions' in settings.INSTALLED_APPS:
        settings.INSTALLED_APPS = [app for app in settings.INSTALLED_APPS if app != 'django_extensions']

import inspect
from django.apps import apps
from django.db import models


def get_model_fields(model_class):
    """Получает поля модели Django."""
    fields = []
    for field in model_class._meta.get_fields():
        if isinstance(field, models.ForeignKey):
            fields.append(f"- {field.name}: {field.related_model.__name__} (FK)")
        elif isinstance(field, models.ManyToManyField):
            fields.append(f"- {field.name}: {field.related_model.__name__} (M2M)")
        elif isinstance(field, models.OneToOneField):
            fields.append(f"- {field.name}: {field.related_model.__name__} (O2O)")
        else:
            field_type = type(field).__name__
            fields.append(f"- {field.name}: {field_type}")
    return fields


def get_class_methods(class_obj):
    """Получает методы класса."""
    methods = []
    # Получаем все методы класса (включая унаследованные)
    for name in dir(class_obj):
        if name.startswith('_'):
            continue
        try:
            attr = getattr(class_obj, name)
            if callable(attr):
                try:
                    sig = inspect.signature(attr)
                    params = []
                    for p in sig.parameters.values():
                        if p.name == 'self':
                            continue
                        param_str = p.name
                        if p.annotation != inspect.Parameter.empty:
                            if hasattr(p.annotation, '__name__'):
                                param_str += f": {p.annotation.__name__}"
                            else:
                                param_str += f": {str(p.annotation)}"
                        params.append(param_str)
                    methods.append(f"+ {name}({', '.join(params)})")
                except (ValueError, TypeError):
                    methods.append(f"+ {name}(...)")
        except Exception:
            pass
    return methods


def generate_models_diagram():
    """Генерирует PlantUML-диаграмму для Django-моделей."""
    puml = ["@startuml Django Models", ""]
    
    # Получаем все модели
    all_models = {}
    for app_config in apps.get_app_configs():
        for model in app_config.get_models():
            all_models[model.__name__] = model
    
    # Группируем по приложениям
    models_by_app = {}
    for model_name, model in all_models.items():
        app_label = model._meta.app_label
        if app_label not in models_by_app:
            models_by_app[app_label] = []
        models_by_app[app_label].append((model_name, model))
    
    # Генерируем классы
    for app_label, models_list in models_by_app.items():
        puml.append(f"package {app_label} {{")
        for model_name, model in models_list:
            puml.append(f"  class {model_name} {{")
            
            # Добавляем поля
            fields = get_model_fields(model)
            for field in fields[:10]:  # Ограничиваем количество полей для читаемости
                puml.append(f"    {field}")
            if len(fields) > 10:
                puml.append(f"    ... и еще {len(fields) - 10} полей")
            
            # Добавляем методы модели
            methods = [m for m in dir(model) if not m.startswith('_') and callable(getattr(model, m))]
            if methods:
                puml.append("    --")
                for method in methods[:5]:  # Ограничиваем количество методов
                    puml.append(f"    + {method}()")
            
            puml.append("  }")
            puml.append("")
        puml.append("}")
        puml.append("")
    
    # Генерируем связи
    puml.append("' Связи между моделями")
    for model_name, model in all_models.items():
        for field in model._meta.get_fields():
            if isinstance(field, models.ForeignKey):
                related_model = field.related_model
                puml.append(f"{model_name} --> {related_model.__name__} : {field.name}")
            elif isinstance(field, models.ManyToManyField):
                related_model = field.related_model
                puml.append(f"{model_name} --> {related_model.__name__} : {field.name}")
    
    puml.append("@enduml")
    return "\n".join(puml)


def generate_services_diagram():
    """Генерирует PlantUML-диаграмму для сервисов."""
    puml = ["@startuml Services", ""]
    puml.append("' Services")
    puml.append("")
    
    # Импортируем сервисы
    services_path = BASE_DIR / "calculation" / "services"
    services = []
    
    for py_file in services_path.glob("*.py"):
        if py_file.name.startswith("__"):
            continue
        
        module_name = f"calculation.services.{py_file.stem}"
        try:
            module = __import__(module_name, fromlist=[py_file.stem])
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if obj.__module__ == module_name:
                    services.append((name, obj))
        except Exception as e:
            print(f"Ошибка при импорте {module_name}: {e}")
    
    # Генерируем классы
    puml.append("package calculation.services {")
    for service_name, service_class in services:
        puml.append(f"  class {service_name} {{")
        
        # Добавляем методы
        methods = get_class_methods(service_class)
        for method in methods[:15]:  # Ограничиваем количество методов
            puml.append(f"    {method}")
        if len(methods) > 15:
            puml.append(f"    ... и еще {len(methods) - 15} методов")
        
        puml.append("  }")
        puml.append("")
    puml.append("}")
    puml.append("")
    
    # Генерируем связи (упрощенно)
    puml.append("' Зависимости между сервисами")
    for service_name, service_class in services:
        # Анализируем импорты в классе
        source = inspect.getsource(service_class)
        for other_name, other_class in services:
            if service_name != other_name and other_name in source:
                puml.append(f"{service_name} ..> {other_name} : uses")
    
    puml.append("@enduml")
    return "\n".join(puml)


def generate_combined_diagram():
    """Генерирует комбинированную диаграмму."""
    models_diagram = generate_models_diagram()
    services_diagram = generate_services_diagram()
    
    # Объединяем диаграммы
    combined = ["@startuml Complete Project Diagram", ""]
    combined.append("' Django Models")
    combined.append("")
    
    # Извлекаем содержимое из диаграммы моделей (без @startuml и @enduml)
    models_content = models_diagram.split("@startuml")[1] if "@startuml" in models_diagram else models_diagram
    models_content = models_content.split("@enduml")[0].strip()
    # Убираем заголовок "Django Models" если он есть
    if models_content.startswith("Django Models"):
        models_content = models_content.replace("Django Models", "", 1).strip()
    combined.append(models_content)
    combined.append("")
    
    combined.append("' Services")
    combined.append("")
    
    # Извлекаем содержимое из диаграммы сервисов (без @startuml и @enduml)
    services_content = services_diagram.split("@startuml")[1] if "@startuml" in services_diagram else services_diagram
    services_content = services_content.split("@enduml")[0].strip()
    # Убираем заголовок "Services" если он есть
    if services_content.startswith("Services"):
        services_content = services_content.replace("Services", "", 1).strip()
    combined.append(services_content)
    combined.append("")
    combined.append("@enduml")
    
    return "\n".join(combined)


def main():
    """Главная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Генерация PlantUML-диаграмм из Django-проекта')
    parser.add_argument('--models-only', action='store_true', help='Генерировать только диаграмму моделей')
    parser.add_argument('--services-only', action='store_true', help='Генерировать только диаграмму сервисов')
    parser.add_argument('--all', action='store_true', help='Генерировать полную диаграмму')
    parser.add_argument('--output', '-o', default='diagram.puml', help='Имя выходного файла')
    
    args = parser.parse_args()
    
    if args.models_only:
        diagram = generate_models_diagram()
        output_file = 'models_diagram.puml'
    elif args.services_only:
        diagram = generate_services_diagram()
        output_file = 'services_diagram.puml'
    elif args.all:
        diagram = generate_combined_diagram()
        output_file = args.output
    else:
        # По умолчанию - все
        diagram = generate_combined_diagram()
        output_file = args.output
    
    # Сохраняем в файл
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(diagram)
    
    print(f"✓ Диаграмма сохранена в {output_file}")
    print(f"  Откройте файл в PlantUML или используйте онлайн-редактор: http://www.plantuml.com/plantuml/uml/")


if __name__ == "__main__":
    main()
