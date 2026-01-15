from django.core.management import BaseCommand

from core.models import Line, ProtectionHalfSet, ProtectionDevice, Substation
from calculation.services.powerfactory_manager import PowerFactoryManager
from calculation.services.powerfactory_locator import (
    get_pf_line,
    _get_main_substations_with_voltage,
)


class Command(BaseCommand):
    """
    Команда для автоматического создания полукомплектов защиты для всех линий.

    Для каждой линии:
    1. Определяет основные подстанции на концах линии из PowerFactory
    2. Создает ProtectionHalfSet для каждой пары (линия + подстанция)
    3. Использует устройство РЗА "ШЭ 2607 081" по умолчанию

    Запуск:
        python manage.py create_protection_half_sets_for_all_lines
        python manage.py create_protection_half_sets_for_all_lines --line-id 123
        python manage.py create_protection_half_sets_for_all_lines --device-model "ТОР 300 ДФЗ 54X"
        python manage.py create_protection_half_sets_for_all_lines --only-missing
    """

    help = "Создает полукомплекты защиты для всех линий"

    def add_arguments(self, parser):
        parser.add_argument(
            "--line-id",
            type=int,
            help="Обработать только конкретную линию по ID",
        )
        parser.add_argument(
            "--device-model",
            type=str,
            default="ШЭ 2607 081",
            help="Модель устройства РЗА для использования (по умолчанию: ШЭ 2607 081)",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Создавать полукомплекты только для линий, у которых их еще нет",
        )
        parser.add_argument(
            "--project",
            type=str,
            help="Имя проекта PowerFactory для активации",
        )

    def handle(self, *args, **options):
        self.stdout.write("Поиск линий...")

        # Получаем устройство РЗА
        try:
            protection_device = ProtectionDevice.objects.get(
                device_model=options["device_model"]
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Используется устройство РЗА: {protection_device.device_model}"
                )
            )
        except ProtectionDevice.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"Устройство РЗА '{options['device_model']}' не найдено в БД. "
                    f"Доступные устройства: {', '.join(ProtectionDevice.objects.values_list('device_model', flat=True))}"
                )
            )
            return

        # Находим линии для обработки
        if options.get("line_id"):
            # Если указан конкретный ID линии
            try:
                line = Line.objects.get(id=options["line_id"])
                if not line.pf_name:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Линия с ID {options['line_id']} не имеет pf_name, пропущена"
                        )
                    )
                    return
                lines_to_process = [line]
            except Line.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Линия с ID {options['line_id']} не найдена")
                )
                return
        else:
            # Находим все линии с pf_name
            lines_to_process = Line.objects.filter(pf_name__isnull=False).exclude(
                pf_name=""
            )

        # Фильтруем только те линии, у которых нет полукомплектов (если указан флаг)
        if options.get("only_missing"):
            lines_with_half_sets = set(
                ProtectionHalfSet.objects.values_list("line_id", flat=True).distinct()
            )
            lines_to_process = [
                line for line in lines_to_process if line.id not in lines_with_half_sets
            ]

        if not lines_to_process:
            self.stdout.write(self.style.WARNING("Не найдено линий для обработки"))
            return

        # Преобразуем QuerySet в список для единообразной обработки
        if not isinstance(lines_to_process, list):
            lines_to_process = list(lines_to_process)

        total_lines = len(lines_to_process)
        self.stdout.write(
            self.style.SUCCESS(f"Найдено линий для обработки: {total_lines}")
        )

        # Подключаемся к PowerFactory
        self.stdout.write("\nПодключение к PowerFactory...")
        try:
            pf_manager = PowerFactoryManager()
            if options.get("project"):
                pf_manager.PROJECT_NAME = options["project"]
            app = pf_manager.get_application()
            self.stdout.write(self.style.SUCCESS("Подключение к PowerFactory успешно"))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Ошибка подключения к PowerFactory: {e}")
            )
            return

        # Статистика
        processed_lines = 0
        created_half_sets = 0
        skipped_half_sets = 0
        skipped_lines = 0
        error_count = 0

        self.stdout.write("\nОбработка линий...")
        self.stdout.write("=" * 80)

        for line in lines_to_process:
            try:
                if not line.pf_name:
                    self.stdout.write(
                        self.style.WARNING(
                            f"ЛЭП '{line.dispatch_name}' (ID: {line.id}) не имеет pf_name, пропущена"
                        )
                    )
                    skipped_lines += 1
                    continue

                self.stdout.write(
                    f"\nЛЭП: {line.dispatch_name} (ID: {line.id}, pf_name: {line.pf_name})"
                )

                # Получаем линию из PowerFactory
                try:
                    pf_line = get_pf_line(app, line.pf_name)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"  ✗ Не удалось найти линию в PowerFactory: {e}"
                        )
                    )
                    error_count += 1
                    skipped_lines += 1
                    continue

                # Определяем основные подстанции на концах линии
                try:
                    main_substations = _get_main_substations_with_voltage(pf_line, app)
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"  ✗ Ошибка при определении подстанций: {e}")
                    )
                    error_count += 1
                    skipped_lines += 1
                    continue

                if len(main_substations) < 2:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠ Найдено подстанций: {len(main_substations)} (ожидается 2), пропущена"
                        )
                    )
                    skipped_lines += 1
                    continue

                self.stdout.write(
                    f"  Найдено подстанций на концах: {len(main_substations)}"
                )

                # Создаем полукомплекты для каждой подстанции
                for sub_info in main_substations:
                    substation_name = sub_info["name"]

                    try:
                        # Находим или создаем подстанцию в БД
                        substation, created = Substation.objects.get_or_create(
                            pf_name=substation_name,
                        )

                        if created:
                            self.stdout.write(
                                f"    + Создана подстанция: {substation_name}"
                            )

                        # Проверяем, существует ли уже полукомплект
                        half_set_exists = ProtectionHalfSet.objects.filter(
                            line=line, substation=substation
                        ).exists()

                        if half_set_exists:
                            skipped_half_sets += 1
                            self.stdout.write(
                                f"    - Полукомплект для ПС '{substation_name}' уже существует, пропущен"
                            )
                            continue

                        # Создаем полукомплект защиты
                        half_set = ProtectionHalfSet.objects.create(
                            line=line,
                            substation=substation,
                            protection_device=protection_device,
                        )

                        created_half_sets += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"    ✓ Создан полукомплект для ПС '{substation_name}'"
                            )
                        )

                    except Exception as e:
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f"    ✗ Ошибка при создании полукомплекта для ПС '{substation_name}': {e}"
                            )
                        )
                        import traceback

                        self.stdout.write(self.style.ERROR(traceback.format_exc()))
                        continue

                processed_lines += 1

                # Прогресс каждые 10 линий
                if processed_lines % 10 == 0:
                    self.stdout.write(
                        f"\nОбработано {processed_lines}/{total_lines} линий...",
                        ending="\r",
                    )

            except Exception as e:
                error_count += 1
                skipped_lines += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Ошибка при обработке ЛЭП '{line.dispatch_name}': {e}"
                    )
                )
                import traceback

                self.stdout.write(self.style.ERROR(traceback.format_exc()))
                continue

        # Итоговая статистика
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("Обработка завершена!"))
        self.stdout.write(f"  Обработано линий: {processed_lines}")
        self.stdout.write(f"  Пропущено линий: {skipped_lines}")
        self.stdout.write(f"  Создано полукомплектов: {created_half_sets}")
        self.stdout.write(f"  Пропущено полукомплектов: {skipped_half_sets}")
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"  Ошибок: {error_count}"))
