from django.core.management import BaseCommand
from core.models import Component, ProtectionDevice, Manufacturer
from calculation.services.device_components_map import DEVICE_COMPONENTS_MAP


class Command(BaseCommand):
    help = "Заполняет БД компонентами (органами ДФЗ) и связывает их с устройствами защиты по производителям"

    def add_arguments(self, parser):
        parser.add_argument(
            '--manufacturer',
            type=str,
            help='Название производителя (например: "ООО НПП «ЭКРА»" или "ЭКРА")',
        )
        parser.add_argument(
            '--device-model',
            type=str,
            help='Модель устройства защиты для заполнения (если не указано, заполняет все модели производителя)',
        )
        parser.add_argument(
            '--all-manufacturers',
            action='store_true',
            help='Обработать все производители из DEVICE_COMPONENTS_MAP',
        )

    def handle(self, *args, **options):
        # Определяем, какие производители обрабатывать
        manufacturers_to_process = []
        
        if options.get('all_manufacturers'):
            # Обрабатываем всех производителей из DEVICE_COMPONENTS_MAP
            manufacturers_to_process = list(DEVICE_COMPONENTS_MAP.keys())
        elif options.get('manufacturer'):
            # Ищем производителя по названию (с учетом возможных вариантов)
            manufacturer_name = options['manufacturer']
            found_manufacturer = None
            
            # Прямое совпадение
            if manufacturer_name in DEVICE_COMPONENTS_MAP:
                found_manufacturer = manufacturer_name
            else:
                # Поиск по частичному совпадению (например, "ЭКРА" -> "ООО НПП «ЭКРА»")
                for key in DEVICE_COMPONENTS_MAP.keys():
                    if manufacturer_name.upper() in key.upper() or key.upper() in manufacturer_name.upper():
                        found_manufacturer = key
                        break
            
            if found_manufacturer:
                manufacturers_to_process = [found_manufacturer]
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"\nПроизводитель '{manufacturer_name}' не найден в DEVICE_COMPONENTS_MAP.\n"
                        f"Доступные производители: {', '.join(DEVICE_COMPONENTS_MAP.keys())}"
                    )
                )
                return
        else:
            # По умолчанию обрабатываем ЭКРА
            if "ООО НПП «ЭКРА»" in DEVICE_COMPONENTS_MAP:
                manufacturers_to_process = ["ООО НПП «ЭКРА»"]
            else:
                self.stdout.write(
                    self.style.ERROR(
                        "\nНе указан производитель. Используйте --manufacturer или --all-manufacturers"
                    )
                )
                return

        total_created_components = 0
        total_processed_devices = 0

        # Обрабатываем каждого производителя
        for manufacturer_name in manufacturers_to_process:
            self.stdout.write(
                self.style.SUCCESS(f"\n{'='*60}\nОбработка производителя: {manufacturer_name}\n{'='*60}\n")
            )

            # Получаем модели устройств для этого производителя
            manufacturer_models = DEVICE_COMPONENTS_MAP.get(manufacturer_name, {})
            
            if not manufacturer_models:
                self.stdout.write(
                    self.style.WARNING(f"  Нет моделей устройств для производителя '{manufacturer_name}'")
                )
                continue

            # Определяем, какие модели обрабатывать
            models_to_process = []
            if options.get('device_model'):
                # Ищем конкретную модель
                found_model = None
                for model_key in manufacturer_models.keys():
                    if options['device_model'] in model_key or model_key in options['device_model']:
                        found_model = model_key
                        break
                
                if found_model:
                    models_to_process = [found_model]
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  Модель '{options['device_model']}' не найдена для производителя '{manufacturer_name}'.\n"
                            f"  Доступные модели: {', '.join(manufacturer_models.keys())}"
                        )
                    )
                    continue
            else:
                # Обрабатываем все модели производителя
                models_to_process = list(manufacturer_models.keys())

            # Собираем все уникальные компоненты для всех моделей производителя
            all_components_for_manufacturer = set()
            for model_name in models_to_process:
                model_components = manufacturer_models.get(model_name, {})
                all_components_for_manufacturer.update(model_components.keys())

            self.stdout.write(f"  Создание компонентов для производителя '{manufacturer_name}'...")

            # Создаем компоненты
            created_components = 0
            for comp_name in sorted(all_components_for_manufacturer):
                component_data = None
                # Ищем описание компонента в любой из моделей
                for model_name in models_to_process:
                    if comp_name in manufacturer_models.get(model_name, {}):
                        component_data = manufacturer_models[model_name][comp_name]
                        break
                
                description = component_data.get('description', f'Орган защиты {comp_name}') if component_data else f'Орган защиты {comp_name}'
                
                component, created = Component.objects.get_or_create(
                    setting_designation=comp_name,
                    defaults={
                        'name': comp_name,
                        'description': description,
                        'is_active': True,
                    }
                )
                if created:
                    created_components += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'    ✓ Создан компонент: {comp_name}')
                    )
                else:
                    # Обновляем описание, если оно изменилось
                    if component.description != description:
                        component.description = description
                        component.save()
                        self.stdout.write(
                            self.style.WARNING(f'    ↻ Обновлен компонент: {comp_name}')
                        )

            total_created_components += created_components
            self.stdout.write(
                self.style.SUCCESS(
                    f"  Создано компонентов: {created_components}, всего в БД: {Component.objects.count()}\n"
                )
            )

            # Обрабатываем каждую модель устройства
            for model_name in models_to_process:
                self.stdout.write(f"  Обработка модели: {model_name}")
                
                # Получаем компоненты для этой модели
                model_components = manufacturer_models.get(model_name, {})
                component_names = list(model_components.keys())
                
                if not component_names:
                    self.stdout.write(
                        self.style.WARNING(f"    Нет компонентов для модели '{model_name}'")
                    )
                    continue

                # Получаем или создаем устройство защиты в БД
                device = None
                
                # Сначала пытаемся найти по точному совпадению
                try:
                    device = ProtectionDevice.objects.get(device_model=model_name)
                except ProtectionDevice.DoesNotExist:
                    # Пытаемся найти по частичному совпадению (например, "ШЭ 2607 081" в "ШЭ 2607 081/ШЭ 2710 58х")
                    # Ищем устройства, где название модели содержит ключевые слова из model_name
                    model_keywords = model_name.split()
                    if model_keywords:
                        # Ищем устройства, которые содержат первое ключевое слово
                        matching_devices = ProtectionDevice.objects.filter(
                            device_model__icontains=model_keywords[0]
                        )
                        
                        # Если есть производитель, фильтруем по нему
                        if manufacturer_name:
                            # Пытаемся найти производителя в БД
                            manufacturer_obj = None
                            # Ищем производителя по точному или частичному совпадению
                            for mfr_name in Manufacturer.objects.all():
                                if manufacturer_name.upper() in mfr_name.name.upper() or mfr_name.name.upper() in manufacturer_name.upper():
                                    manufacturer_obj = mfr_name
                                    break
                            
                            if manufacturer_obj:
                                matching_devices = matching_devices.filter(manufacturer_fk=manufacturer_obj)
                        
                        if matching_devices.exists():
                            device = matching_devices.first()
                            self.stdout.write(
                                self.style.WARNING(
                                    f"    Устройство '{model_name}' не найдено, используется '{device.device_model}'"
                                )
                            )
                
                # Если устройство все еще не найдено, создаем его
                if device is None:
                    # Получаем или создаем производителя
                    manufacturer_obj = None
                    if manufacturer_name:
                        for mfr_name in Manufacturer.objects.all():
                            if manufacturer_name.upper() in mfr_name.name.upper() or mfr_name.name.upper() in manufacturer_name.upper():
                                manufacturer_obj = mfr_name
                                break
                        
                        if manufacturer_obj is None:
                            # Создаем производителя, если его нет
                            manufacturer_obj, created = Manufacturer.objects.get_or_create(
                                name=manufacturer_name
                            )
                            if created:
                                self.stdout.write(
                                    self.style.SUCCESS(f"    ✓ Создан производитель: {manufacturer_name}")
                                )
                    
                    # Создаем устройство защиты
                    # Используем короткое название модели (первую часть до "/")
                    short_model_name = model_name.split('/')[0].strip()
                    device, created = ProtectionDevice.objects.get_or_create(
                        device_model=short_model_name,
                        defaults={
                            'manufacturer_fk': manufacturer_obj,
                        }
                    )
                    if created:
                        self.stdout.write(
                            self.style.SUCCESS(f"    ✓ Создано устройство защиты: {short_model_name}")
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f"    - Устройство уже существует: {short_model_name}")
                        )

                # Получаем компоненты из БД
                components_to_add = Component.objects.filter(setting_designation__in=component_names)
                
                # Добавляем компоненты к устройству
                existing_count = device.components.count()
                device.components.add(*components_to_add)
                added_count = device.components.count() - existing_count

                if added_count > 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"    ✓ Добавлено компонентов: {added_count}, всего: {device.components.count()}"
                        )
                    )
                    total_processed_devices += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"    - Все компоненты уже добавлены ({device.components.count()} шт.)"
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n{"="*60}'
                f'\n✓ Заполнение завершено!'
                f'\n  Создано компонентов: {total_created_components}'
                f'\n  Обработано устройств: {total_processed_devices}'
                f'\n{"="*60}'
            )
        )
