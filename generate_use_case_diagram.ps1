# Скрипт для генерации изображения диаграммы вариантов использования из PlantUML
# Использование: .\generate_use_case_diagram.ps1

# Переход в директорию скрипта
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

# Путь к исходному файлу
$pumlFile = "docs\use_case_diagram.puml"
$outputDir = "docs"

# Проверка наличия исходного файла
if (-not (Test-Path $pumlFile)) {
    Write-Host "Ошибка: файл $pumlFile не найден" -ForegroundColor Red
    exit 1
}

# Создание директории docs, если её нет
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Path $outputDir | Out-Null
}

Write-Host "Генерация диаграммы вариантов использования..." -ForegroundColor Green

# Попытка 1: Использование PlantUML JAR (если установлен)
$plantumlJar = "plantuml.jar"
$plantumlPath = Get-ChildItem -Path $env:USERPROFILE, "C:\Program Files", "C:\tools" -Recurse -Filter $plantumlJar -ErrorAction SilentlyContinue | Select-Object -First 1

if ($plantumlPath -and (Test-Path $plantumlPath.FullName)) {
    Write-Host "Использование PlantUML JAR: $($plantumlPath.FullName)" -ForegroundColor Yellow
    try {
        java -jar $plantumlPath.FullName -tpng -o (Resolve-Path $outputDir).Path $pumlFile
        Write-Host "✓ PNG диаграмма сохранена в $outputDir\use_case_diagram.png" -ForegroundColor Green
        exit 0
    } catch {
        Write-Host "Ошибка при использовании JAR: $_" -ForegroundColor Red
    }
}

# Попытка 2: Использование Python библиотеки plantuml (если установлена)
try {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        Write-Host "Попытка использования Python библиотеки plantuml..." -ForegroundColor Yellow
        
        # Проверка установки библиотеки
        $checkLib = python -c "import plantuml" 2>&1
        if ($LASTEXITCODE -eq 0) {
            # Генерация через Python
            $pythonScript = @"
import plantuml
from pathlib import Path

puml_file = Path('$pumlFile')
output_dir = Path('$outputDir')

# Чтение PlantUML файла
with open(puml_file, 'r', encoding='utf-8') as f:
    puml_code = f.read()

# Генерация изображения через онлайн-сервис
p = plantuml.PlantUML(url='http://www.plantuml.com/plantuml/img/')
png_data = p.processes(puml_code)

# Сохранение PNG
output_file = output_dir / 'use_case_diagram.png'
with open(output_file, 'wb') as f:
    f.write(png_data)

print(f'✓ PNG диаграмма сохранена в {output_file}')
"@
            $pythonScript | python
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✓ PNG диаграмма сохранена в $outputDir\use_case_diagram.png" -ForegroundColor Green
                exit 0
            }
        }
    }
} catch {
    Write-Host "Python библиотека plantuml не установлена" -ForegroundColor Yellow
}

# Попытка 3: Использование онлайн-сервиса через curl
Write-Host "Попытка использования онлайн-сервиса PlantUML..." -ForegroundColor Yellow

try {
    # Чтение PlantUML файла
    $pumlContent = Get-Content $pumlFile -Raw -Encoding UTF8
    
    # Кодирование в формат PlantUML (deflate + base64)
    # Используем Python для кодирования
    $encodeScript = @"
import zlib
import base64
import sys

puml_code = sys.stdin.read()
compressed = zlib.compress(puml_code.encode('utf-8'))
encoded = base64.b64encode(compressed).decode('ascii')
# PlantUML использует специальную кодировку
plantuml_chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_'
result = ''.join(plantuml_chars[(ord(c) >> (i % 6)) & 63] for i, c in enumerate(encoded))
print(result)
"@
    
    $encoded = $pumlContent | python -c $encodeScript
    
    if ($encoded) {
        $url = "http://www.plantuml.com/plantuml/png/$encoded"
        $outputFile = "$outputDir\use_case_diagram.png"
        
        # Скачивание изображения
        Invoke-WebRequest -Uri $url -OutFile $outputFile -ErrorAction Stop
        Write-Host "✓ PNG диаграмма сохранена в $outputFile" -ForegroundColor Green
        exit 0
    }
} catch {
    Write-Host "Ошибка при использовании онлайн-сервиса: $_" -ForegroundColor Red
}

# Если ничего не сработало, предлагаем альтернативы
Write-Host "`nНе удалось автоматически сгенерировать изображение." -ForegroundColor Yellow
Write-Host "Альтернативные способы:" -ForegroundColor Yellow
Write-Host "1. Установите PlantUML JAR файл и поместите его в PATH" -ForegroundColor Cyan
Write-Host "2. Установите Python библиотеку: pip install plantuml" -ForegroundColor Cyan
Write-Host "3. Используйте онлайн-редактор: http://www.plantuml.com/plantuml/uml/" -ForegroundColor Cyan
Write-Host "4. Используйте VS Code с расширением PlantUML" -ForegroundColor Cyan
Write-Host "`nИсходный файл: $pumlFile" -ForegroundColor White
