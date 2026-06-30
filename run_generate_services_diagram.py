#!/usr/bin/env python
"""
Простая обертка для запуска генерации диаграммы сервисов.
Использует Django management команду.
"""
import os
import sys
from pathlib import Path

# Определяем корневую директорию проекта
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'phase_comparison_protection.settings')

import django
django.setup()

# Запускаем команду
from django.core.management import call_command

if __name__ == "__main__":
    call_command('generate_services_diagram')
