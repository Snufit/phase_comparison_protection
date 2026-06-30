#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Простой скрипт для генерации диаграммы вариантов использования."""

import os
from pathlib import Path
import plantuml

# Используем текущую рабочую директорию
cwd = Path.cwd()
puml_file = cwd / "docs" / "use_case_diagram.puml"
output_file = cwd / "docs" / "use_case_diagram.png"

if not puml_file.exists():
    print(f"Ошибка: файл {puml_file} не найден")
    print(f"Текущая директория: {cwd}")
    exit(1)

print(f"Чтение файла: {puml_file}")
with open(puml_file, 'r', encoding='utf-8') as f:
    puml_code = f.read()

print("Генерация изображения через PlantUML...")
try:
    p = plantuml.PlantUML(url='http://www.plantuml.com/plantuml/img/')
    png_data = p.processes(puml_code)
    
    with open(output_file, 'wb') as f:
        f.write(png_data)
    
    size_kb = output_file.stat().st_size / 1024
    print(f"✓ Диаграмма сохранена: {output_file}")
    print(f"  Размер: {size_kb:.2f} KB")
except Exception as e:
    print(f"Ошибка: {e}")
    print("\nАльтернативы:")
    print("1. Онлайн: http://www.plantuml.com/plantuml/uml/")
    print("2. VS Code с расширением PlantUML")
    exit(1)
