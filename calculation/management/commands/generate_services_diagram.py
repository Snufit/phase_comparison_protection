"""
Django management команда для генерации PlantUML-диаграммы для calculation/services.
"""

from django.core.management.base import BaseCommand
from pathlib import Path
import inspect
import ast
import os


class Command(BaseCommand):
    help = 'Генерирует PlantUML-диаграмму для calculation/services'

    def handle(self, *args, **options):
        BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
        SERVICES_DIR = BASE_DIR / "calculation" / "services"

        def get_class_methods(class_obj):
            """Получает методы класса с их сигнатурами."""
            methods = []
            for name, obj in inspect.getmembers(class_obj, inspect.ismethod):
                if name.startswith('_') and name not in ['__init__', '__str__', '__repr__']:
                    continue
                try:
                            sig = inspect.signature(obj)
                            params = []
                            for p in sig.parameters.values():
                                if p.name == 'self':
                                    continue
                                param_str = p.name
                                if p.annotation != inspect.Parameter.empty:
                                    if hasattr(p.annotation, '__name__'):
                                        param_str += f": {p.annotation.__name__}"
                                    else:
                                        # Упрощаем сложные типы для PlantUML
                                        ann_str = str(p.annotation)
                                        # Убираем длинные пути модулей
                                        if 'typing.' in ann_str:
                                            ann_str = ann_str.replace('typing.', '')
                                        if len(ann_str) > 30:
                                            ann_str = ann_str[:27] + "..."
                                        param_str += f": {ann_str}"
                                if p.default != inspect.Parameter.empty:
                                    default_val = p.default
                                    # Обрабатываем значения по умолчанию
                                    if isinstance(default_val, str):
                                        # Экранируем кавычки и обрезаем длинные строки
                                        default_val = str(default_val).replace('"', '\\"')
                                        if len(default_val) > 20:
                                            default_val = default_val[:17] + "..."
                                        default_val = f'"{default_val}"'
                                    else:
                                        default_val = str(default_val)
                                    param_str += f" = {default_val}"
                                params.append(param_str)
                            methods.append(f"+ {name}({', '.join(params)})")
                except (ValueError, TypeError):
                    methods.append(f"+ {name}(...)")
            
            # Также получаем статические методы и методы класса
            for name, obj in inspect.getmembers(class_obj):
                if name.startswith('_') and name not in ['__init__', '__str__', '__repr__']:
                    continue
                if inspect.isfunction(obj) or inspect.ismethod(obj):
                    if name not in [m.split('(')[0].replace('+ ', '') for m in methods]:
                        try:
                            sig = inspect.signature(obj)
                            params = []
                            for p in sig.parameters.values():
                                if p.name == 'self' or p.name == 'cls':
                                    continue
                                param_str = p.name
                                if p.annotation != inspect.Parameter.empty:
                                    if hasattr(p.annotation, '__name__'):
                                        param_str += f": {p.annotation.__name__}"
                                    else:
                                        param_str += f": {str(p.annotation)}"
                                if p.default != inspect.Parameter.empty:
                                    param_str += f" = {p.default}"
                                params.append(param_str)
                            # Проверяем тип метода альтернативным способом
                            # inspect.isstaticmethod может отсутствовать в некоторых версиях Python
                            is_static = False
                            try:
                                # Проверяем через дескриптор класса
                                descriptor = getattr(class_obj, name, None)
                                if descriptor is not None:
                                    is_static = isinstance(descriptor, staticmethod)
                            except:
                                pass
                            # Если не staticmethod, проверяем classmethod
                            is_class = False
                            if not is_static:
                                try:
                                    descriptor = getattr(class_obj, name, None)
                                    if descriptor is not None:
                                        is_class = isinstance(descriptor, classmethod)
                                except:
                                    pass
                            prefix = "{static}" if is_static else ("{classmethod}" if is_class else "")
                            methods.append(f"+ {prefix} {name}({', '.join(params)})")
                        except (ValueError, TypeError):
                            pass
            
            return methods

        def get_class_attributes(class_obj):
            """Получает атрибуты класса (константы, конфигурации)."""
            attributes = []
            for name in dir(class_obj):
                if name.startswith('_'):
                    continue
                try:
                    attr = getattr(class_obj, name)
                    if not callable(attr) and not inspect.isclass(attr):
                        if isinstance(attr, (str, int, float, bool)):
                            attr_str = str(attr)
                            # Экранируем специальные символы для PlantUML
                            # Заменяем обратные слеши на прямые
                            attr_str = attr_str.replace('\\', '/')
                            # Обрезаем длинные строки
                            if len(attr_str) > 40:
                                attr_str = attr_str[:37] + "..."
                            # Обертываем строки в кавычки для PlantUML
                            if isinstance(attr, str):
                                # Экранируем кавычки внутри строки
                                attr_str = attr_str.replace('"', '\\"')
                                attr_str = f'"{attr_str}"'
                            attributes.append(f"~ {name}: {type(attr).__name__} = {attr_str}")
                        elif isinstance(attr, dict):
                            if len(attr) > 0:
                                keys = list(attr.keys())[:2]  # Уменьшаем количество ключей
                                # Упрощаем представление словаря
                                dict_items = []
                                for k in keys:
                                    v = attr[k]
                                    v_str = str(v)
                                    if len(v_str) > 20:
                                        v_str = v_str[:17] + "..."
                                    # Экранируем кавычки
                                    v_str = v_str.replace('"', '\\"')
                                    dict_items.append(f'"{k}": "{v_str}"')
                                attr_str = "{" + ", ".join(dict_items) + "}"
                                if len(attr) > 2:
                                    attr_str += "..."
                                attributes.append(f"~ {name}: dict = {attr_str}")
                except Exception:
                    pass
            return attributes[:5]

        def analyze_imports(file_path):
            """Анализирует импорты из calculation.services в файле."""
            imports = set()
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read(), filename=str(file_path))
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module and node.module.startswith('calculation.services'):
                            for alias in node.names:
                                imports.add(alias.name)
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.startswith('calculation.services'):
                                imports.add(alias.name.split('.')[-1])
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Ошибка при анализе импортов {file_path}: {e}"))
            
            return imports

        # Словарь для хранения классов и их зависимостей
        services_info = {}
        
        # Собираем информацию о всех классах
        for py_file in sorted(SERVICES_DIR.glob("*.py")):
            if py_file.name.startswith("__"):
                continue
            
            module_name = f"calculation.services.{py_file.stem}"
            try:
                module = __import__(module_name, fromlist=[py_file.stem])
                
                # Анализируем импорты
                imports = analyze_imports(py_file)
                
                # Находим классы в модуле
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if obj.__module__ == module_name:
                        methods = get_class_methods(obj)
                        attributes = get_class_attributes(obj)
                        
                        services_info[name] = {
                            'class': obj,
                            'module': py_file.stem,
                            'methods': methods,
                            'attributes': attributes,
                            'imports': imports,
                        }
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Ошибка при импорте {module_name}: {e}"))
        
        # Генерируем PlantUML диаграмму
        puml = ["@startuml Services Diagram", ""]
        # Убираем директивы, которые могут не поддерживаться старыми версиями PlantUML
        # puml.append("!theme plain")  # Не поддерживается в старых версиях
        # puml.append("skinparam classAttributeIconSize 0")  # Может вызывать проблемы
        # puml.append("skinparam backgroundColor #FFFFFF")  # Может вызывать проблемы
        puml.append("")
        
        # Группируем по модулям
        modules = {}
        for service_name, info in services_info.items():
            module_name = info['module']
            if module_name not in modules:
                modules[module_name] = []
            modules[module_name].append((service_name, info))
        
        # Генерируем классы, сгруппированные по модулям
        puml.append("package \"calculation.services\" {")
        puml.append("")
        
        for module_name, services_list in sorted(modules.items()):
            puml.append(f"  package \"{module_name}\" {{")
            
            for service_name, info in services_list:
                puml.append(f"    class {service_name} {{")
                
                # Добавляем атрибуты (константы)
                if info['attributes']:
                    for attr in info['attributes']:
                        puml.append(f"      {attr}")
                    if info['methods']:
                        puml.append("      --")
                
                # Добавляем методы
                for method in info['methods'][:25]:
                    puml.append(f"      {method}")
                if len(info['methods']) > 25:
                    puml.append(f"      ... и еще {len(info['methods']) - 25} методов")
                
                puml.append("    }")
                puml.append("")
            
            puml.append("  }")
            puml.append("")
        
        puml.append("}")
        puml.append("")
        
        # Генерируем зависимости между сервисами
        puml.append("' Зависимости между сервисами")
        puml.append("")
        
        for service_name, info in services_info.items():
            for imported in info['imports']:
                if imported in services_info:
                    puml.append(f"{service_name} ..> {imported} : uses")
        
        # Добавляем зависимости для вспомогательных модулей
        puml.append("")
        puml.append("' Вспомогательные модули (функции и константы)")
        puml.append("")
        
        function_modules = {}
        for py_file in sorted(SERVICES_DIR.glob("*.py")):
            if py_file.name.startswith("__"):
                continue
            
            module_name = f"calculation.services.{py_file.stem}"
            try:
                module = __import__(module_name, fromlist=[py_file.stem])
                
                functions = [name for name, obj in inspect.getmembers(module, inspect.isfunction)
                            if obj.__module__ == module_name]
                
                constants = []
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        tree = ast.parse(f.read(), filename=str(py_file))
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                            const_name = node.targets[0].id
                            if const_name.isupper() and const_name not in ['__all__']:
                                constants.append(const_name)
                except Exception:
                    pass
                
                if functions or constants:
                    function_modules[py_file.stem] = {
                        'functions': functions[:10],
                        'constants': constants[:5]
                    }
            except Exception:
                pass
        
        if function_modules:
            puml.append("package \"Вспомогательные модули\" {")
            for module_name, data in function_modules.items():
                puml.append(f"  object {module_name} {{")
                if data['constants']:
                    for const in data['constants']:
                        puml.append(f"    {const}")
                    if data['functions']:
                        puml.append("    --")
                for func in data['functions']:
                    puml.append(f"    {func}()")
                puml.append("  }")
            puml.append("}")
            puml.append("")
        
        puml.append("@enduml")
        
        # Сохраняем в файл
        output_dir = BASE_DIR / "docs"
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / "services_diagram.puml"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(puml))
        
        self.stdout.write(self.style.SUCCESS(f"✓ Диаграмма сохранена в {output_file}"))
        self.stdout.write(f"  Откройте файл в PlantUML или используйте онлайн-редактор:")
        self.stdout.write(f"  http://www.plantuml.com/plantuml/uml/")
