# Скрипт для генерации диаграммы моделей Django
# Использование: .\generate_models_diagram.ps1

# Переход в директорию скрипта
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Добавление Graphviz в PATH
$env:Path += ";C:\Program Files\Graphviz\bin"

# Проверка наличия manage.py
if (-not (Test-Path "manage.py")) {
    Write-Host "Ошибка: manage.py не найден в текущей директории: $(Get-Location)" -ForegroundColor Red
    exit 1
}

# Проверка виртуального окружения
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Предупреждение: виртуальное окружение не найдено" -ForegroundColor Yellow
}

# Создание директории docs, если её нет
if (-not (Test-Path "docs")) {
    New-Item -ItemType Directory -Path "docs" | Out-Null
}

Write-Host "Генерация диаграммы моделей..." -ForegroundColor Green

# Генерация PNG диаграммы
try {
    python manage.py graph_models -a -o docs/models_diagram.png
    Write-Host "✓ PNG диаграмма сохранена в docs/models_diagram.png" -ForegroundColor Green
} catch {
    Write-Host "Ошибка при генерации PNG: $_" -ForegroundColor Red
    Write-Host "Попробуйте PlantUML формат:" -ForegroundColor Yellow
    python manage.py graph_models -a -o docs/models_diagram.puml --format puml
}
