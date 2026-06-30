"""
Django management command для генерации изображения диаграммы вариантов использования из PlantUML.

Использование:
    python manage.py generate_use_case_diagram                    # Генерация PNG
    python manage.py generate_use_case_diagram --format svg        # Генерация SVG
    python manage.py generate_use_case_diagram --input docs/custom.puml  # Указать входной файл
    python manage.py generate_use_case_diagram --output docs/custom.png  # Указать выходной файл
"""

import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

try:
    import plantuml
except ImportError:
    plantuml = None


class Command(BaseCommand):
    help = "Генерирует изображение диаграммы вариантов использования из PlantUML файла"

    def add_arguments(self, parser):
        parser.add_argument(
            '--input', '-i',
            type=str,
            default='docs/use_case_diagram.puml',
            help='Путь к входному PlantUML файлу (по умолчанию: docs/use_case_diagram.puml)',
        )
        parser.add_argument(
            '--output', '-o',
            type=str,
            default=None,
            help='Путь к выходному файлу изображения (по умолчанию: docs/use_case_diagram.png)',
        )
        parser.add_argument(
            '--format', '-f',
            type=str,
            choices=['png', 'svg', 'eps', 'pdf'],
            default='png',
            help='Формат выходного изображения (по умолчанию: png)',
        )

    def handle(self, *args, **options):
        # Повторная попытка импорта на случай, если модуль не был импортирован при загрузке
        import sys
        import importlib
        import importlib.util
        import os
        import site
        
        # Пробуем найти модуль через importlib.util.find_spec
        plantuml = None
        spec = None
        
        try:
            spec = importlib.util.find_spec('plantuml')
            if spec and spec.origin:
                # Если нашли спецификацию, добавляем путь к родительской директории
                origin_dir = os.path.dirname(spec.origin)
                if origin_dir not in sys.path:
                    sys.path.insert(0, origin_dir)
        except Exception:
            pass
        
        # Если не нашли через find_spec, пробуем через pip show
        if spec is None or spec.origin is None:
            try:
                import subprocess
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'show', 'plantuml'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    encoding='utf-8',
                    errors='ignore'
                )
                if result.returncode == 0:
                    location = None
                    for line in result.stdout.split('\n'):
                        if line.startswith('Location:'):
                            location = line.split(':', 1)[1].strip()
                            break
                    
                    if location:
                        # Нормализуем путь
                        location = os.path.normpath(os.path.abspath(location))
                        if os.path.exists(location):
                            if location not in sys.path:
                                sys.path.insert(0, location)
            except Exception:
                pass
        
        # Добавляем пути к site-packages явно
        site_packages_paths = site.getsitepackages()
        if not site_packages_paths:
            # Для виртуального окружения используем sys.path
            site_packages_paths = [p for p in sys.path if 'site-packages' in p.lower()]
        
        # Добавляем все найденные пути к site-packages в начало sys.path
        for sp_path in site_packages_paths:
            normalized_path = os.path.normpath(os.path.abspath(sp_path))
            if os.path.exists(normalized_path) and normalized_path not in sys.path:
                sys.path.insert(0, normalized_path)
        
        # Пробуем импортировать модуль
        try:
            plantuml = importlib.import_module('plantuml')
        except ImportError:
            # Пробуем прямой импорт
            try:
                import plantuml as puml
                plantuml = puml
            except ImportError:
                pass
        
        # Если импорт не удался, используем альтернативный способ через HTTP
        use_http_fallback = plantuml is None
        
        if use_http_fallback:
            self.stdout.write(
                self.style.WARNING(
                    "Библиотека 'plantuml' не может быть импортирована. "
                    "Используется альтернативный способ через HTTP-запрос к онлайн-сервису PlantUML."
                )
            )

        # Определяем базовую директорию проекта
        base_dir = Path(settings.BASE_DIR)
        
        # Пути к файлам
        input_file = base_dir / options['input']
        output_format = options['format']
        
        # Определяем выходной файл
        if options['output']:
            output_file = base_dir / options['output']
        else:
            # Автоматически определяем имя выходного файла на основе входного
            input_stem = input_file.stem
            output_dir = input_file.parent
            output_file = output_dir / f"{input_stem}.{output_format}"

        # Проверка наличия входного файла
        if not input_file.exists():
            raise CommandError(
                f"Входной файл не найден: {input_file}\n"
                f"Текущая директория проекта: {base_dir}"
            )

        # Создание директории для выходного файла, если её нет
        output_file.parent.mkdir(parents=True, exist_ok=True)

        self.stdout.write(f"Чтение PlantUML файла: {input_file}")

        # Чтение PlantUML файла
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                puml_code = f.read()
        except Exception as e:
            raise CommandError(f"Ошибка при чтении файла {input_file}: {e}")

        self.stdout.write(f"Генерация {output_format.upper()} изображения через PlantUML...")

        # Генерация изображения через онлайн-сервис PlantUML
        try:
            if use_http_fallback:
                # Альтернативный способ через прямой HTTP-запрос
                import urllib.request
                import urllib.parse
                import zlib
                import base64
                
                # Кодируем PlantUML код в формат, который понимает сервер
                # PlantUML использует специальное кодирование: deflate + base64
                compressed = zlib.compress(puml_code.encode('utf-8'))
                encoded = base64.b64encode(compressed).decode('ascii')
                # Заменяем символы для URL-совместимости (PlantUML использует специальную кодировку)
                # Стандартная base64: A-Z, a-z, 0-9, +, /
                # PlantUML кодировка: 0-9, A-Z, a-z, -, _
                trans_table = str.maketrans(
                    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/',
                    '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_'
                )
                encoded = encoded.translate(trans_table)
                
                # Определяем URL в зависимости от формата
                format_url_map = {
                    'png': 'http://www.plantuml.com/plantuml/img/',
                    'svg': 'http://www.plantuml.com/plantuml/svg/',
                    'eps': 'http://www.plantuml.com/plantuml/eps/',
                    'pdf': 'http://www.plantuml.com/plantuml/pdf/',
                }
                
                url = format_url_map.get(output_format, format_url_map['png']) + encoded
                
                # Выполняем HTTP-запрос
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=30) as response:
                    image_data = response.read()
            else:
                # Используем библиотеку plantuml
                format_url_map = {
                    'png': 'http://www.plantuml.com/plantuml/img/',
                    'svg': 'http://www.plantuml.com/plantuml/svg/',
                    'eps': 'http://www.plantuml.com/plantuml/eps/',
                    'pdf': 'http://www.plantuml.com/plantuml/pdf/',
                }
                
                url = format_url_map.get(output_format, format_url_map['png'])
                p = plantuml.PlantUML(url=url)
                
                image_data = p.processes(puml_code)
            
            # Сохранение изображения
            with open(output_file, 'wb') as f:
                f.write(image_data)
            
            # Вывод информации о результате
            file_size = output_file.stat().st_size
            size_kb = file_size / 1024
            size_mb = file_size / (1024 * 1024)
            
            if size_mb >= 1:
                size_str = f"{size_mb:.2f} MB"
            else:
                size_str = f"{size_kb:.2f} KB"
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ Диаграмма успешно сохранена: {output_file}\n"
                    f"  Размер файла: {size_str}"
                )
            )
            
        except Exception as e:
            raise CommandError(
                f"Ошибка при генерации изображения: {e}\n\n"
                "Альтернативные способы генерации:\n"
                "1. Используйте онлайн-редактор: http://www.plantuml.com/plantuml/uml/\n"
                "2. Используйте VS Code с расширением PlantUML\n"
                f"3. Исходный файл: {input_file}"
            )
