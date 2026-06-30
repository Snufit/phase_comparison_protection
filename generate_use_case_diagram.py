#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для генерации изображения диаграммы вариантов использования из PlantUML.
Использование: python generate_use_case_diagram.py
"""

import os
import sys
from pathlib import Path
import plantuml

# Определяем базовую директорию (директория, где находится этот скрипт)
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent

# Если скрипт запущен не из корня проекта, пытаемся найти корень проекта
if not (BASE_DIR / "docs" / "use_case_diagram.puml").exists():
    # Пытаемся найти файл в текущей рабочей директории
    cwd = Path.cwd()
    if (cwd / "docs" / "use_case_diagram.puml").exists():
        BASE_DIR = cwd
    else:
        # Ищем в родительских директориях
        for parent in cwd.parents:
            if (parent / "docs" / "use_case_diagram.puml").exists():
                BASE_DIR = parent
                break

# Пути к файлам
PUML_FILE = BASE_DIR / "docs" / "use_case_diagram.puml"
OUTPUT_DIR = BASE_DIR / "docs"
OUTPUT_FILE = OUTPUT_DIR / "use_case_diagram.png"

# Проверка наличия исходного файла
if not PUML_FILE.exists():
    print(f"Ошибка: файл {PUML_FILE} не найден")
    exit(1)

# Создание директории docs, если её нет
OUTPUT_DIR.mkdir(exist_ok=True)

print("Генерация диаграммы вариантов использования...")

# Чтение PlantUML файла
with open(PUML_FILE, 'r', encoding='utf-8') as f:
    puml_code = f.read()

# Генерация изображения через онлайн-сервис PlantUML
try:
    p = plantuml.PlantUML(url='http://www.plantuml.com/plantuml/img/')
    png_data = p.processes(puml_code)
    
    # Сохранение PNG
    with open(OUTPUT_FILE, 'wb') as f:
        f.write(png_data)
    
    print(f"✓ PNG диаграмма сохранена в {OUTPUT_FILE}")
    print(f"  Размер файла: {OUTPUT_FILE.stat().st_size / 1024:.2f} KB")
    
except Exception as e:
    print(f"Ошибка при генерации изображения: {e}")
    print("\nАльтернативные способы:")
    print("1. Используйте онлайн-редактор: http://www.plantuml.com/plantuml/uml/")
    print("2. Используйте VS Code с расширением PlantUML")
    print(f"3. Исходный файл: {PUML_FILE}")
    exit(1)
