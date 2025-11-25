from django.core.management import BaseCommand

from calculation.services.powerfactory_locator import extract_all_lines_with_branches
from calculation.services.powerfactory_manager import PowerFactoryManager


class Command(BaseCommand):
    """
    Команда для извлечения всех ЛЭП с ответвлениями из проекта PowerFactory.

    Запуск:
        python manage.py extract_lines
    """

    help = 'Извлекает все ЛЭП с ответвлениями из проекта PowerFactory'

    def handle(self, *args, **options):
        """Метод извлечения ЛЭП из PowerFactory."""
        
        try:
            # Подключаемся к PowerFactory
            pf_manager = PowerFactoryManager()
            app = pf_manager.get_application()
            
            self.stdout.write(self.style.SUCCESS('Подключение к PowerFactory успешно'))
            
            # Извлекаем все ЛЭП с ответвлениями
            self.stdout.write('Извлечение ЛЭП из проекта PowerFactory...')
            lines_data = extract_all_lines_with_branches(app)
            
            self.stdout.write(self.style.SUCCESS(f'\nНайдено ЛЭП: {len(lines_data)}'))
            
            # Выводим информацию о ЛЭП
            lines_with_branches = [line for line in lines_data if line['has_branches']]
            lines_without_branches = [line for line in lines_data if not line['has_branches']]
            
            self.stdout.write(f'\nЛЭП с ответвлениями: {len(lines_with_branches)}')
            self.stdout.write(f'ЛЭП без ответвлений: {len(lines_without_branches)}')
            
            # Детальная информация о ЛЭП с ответвлениями
            if lines_with_branches:
                self.stdout.write('\n' + '='*80)
                self.stdout.write(self.style.WARNING('ЛЭП С ОТВЕТВЛЕНИЯМИ:'))
                self.stdout.write('='*80)
                
                for line_data in lines_with_branches:
                    self.stdout.write(f"\nЛЭП: {line_data['pf_name']}")
                    self.stdout.write(f"  Длина: {line_data['length']} км" if line_data['length'] else "  Длина: не указана")
                    self.stdout.write(f"  Напряжение: {line_data['voltage']} кВ" if line_data['voltage'] else "  Напряжение: не указано")
                    self.stdout.write(f"  Количество терминалов: {line_data['terminals_count']}")
                    self.stdout.write(f"  Количество ответвлений: {line_data['branch_count']}")
                    
                    if line_data['main_substations']:
                        self.stdout.write("  Основные подстанции:")
                        for sub in line_data['main_substations']:
                            self.stdout.write(f"    - {sub['name']}")
                    
                    if line_data['branches']:
                        self.stdout.write("  Ответвления:")
                        for branch in line_data['branches']:
                            self.stdout.write(f"    - Подстанция: {branch['substation_name']}")
                            self.stdout.write(f"      Напряжение: {branch['voltage']} кВ" if branch['voltage'] else "      Напряжение: не указано")
            
            # Краткая информация о ЛЭП без ответвлений
            if lines_without_branches:
                self.stdout.write('\n' + '='*80)
                self.stdout.write(self.style.SUCCESS('ЛЭП БЕЗ ОТВЕТВЛЕНИЙ:'))
                self.stdout.write('='*80)
                
                for line_data in lines_without_branches[:10]:  # Показываем первые 10
                    self.stdout.write(f"  - {line_data['pf_name']}")
                
                if len(lines_without_branches) > 10:
                    self.stdout.write(f"  ... и еще {len(lines_without_branches) - 10} ЛЭП")
            
            self.stdout.write('\n' + '='*80)
            self.stdout.write(self.style.SUCCESS('Извлечение данных завершено успешно'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка при извлечении данных: {str(e)}'))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))

