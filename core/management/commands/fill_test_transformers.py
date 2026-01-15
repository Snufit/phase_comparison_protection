from django.core.management import BaseCommand

from core.models import Line, VoltageTransformer


class Command(BaseCommand):
    """
    Команда для назначения трансформаторов напряжения (ТН) линиям в зависимости от напряжения.
    Трансформаторы должны быть предварительно созданы в БД.

    Логика назначения:
    - Для линий 110 кВ: ищет ТН с primary_voltage = 110
    - Для линий 220 кВ: ищет ТН с primary_voltage = 220
    - Для линий 500 кВ: ищет ТН с primary_voltage = 500
    """

    help = "Назначает трансформаторы напряжения (ТН) линиям в зависимости от напряжения"

    def add_arguments(self, parser):
        parser.add_argument(
            "--voltage",
            type=int,
            help="Обработать только линии с указанным напряжением (110, 220, 500)",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Пропустить линии, у которых уже назначен трансформатор напряжения (ТН)",
        )

    def handle(self, *args, **options):
        self.stdout.write("Поиск трансформаторов напряжения (ТН) в БД...")

        # Словарь для сопоставления напряжения и трансформаторов напряжения
        transformer_map = {}

        for voltage in [110, 220, 500]:
            # Ищем ТН по primary_voltage
            vt = VoltageTransformer.objects.filter(primary_voltage=voltage).first()

            if vt:
                transformer_map[voltage] = vt
                self.stdout.write(
                    self.style.SUCCESS(f"Найден ТН для {voltage} кВ: {vt}")
                )
            else:
                self.stdout.write(self.style.WARNING(f"Для {voltage} кВ не найден ТН"))

        if not transformer_map:
            self.stdout.write(
                self.style.ERROR(
                    "Не найдено ни одного трансформатора напряжения. "
                    "Убедитесь, что трансформаторы созданы в БД."
                )
            )
            return

        self.stdout.write("\nНазначение трансформаторов напряжения линиям...")

        updated_count = 0
        skipped_count = 0
        error_count = 0

        # Получаем линии для обработки
        lines = Line.objects.all()
        if options.get("voltage"):
            # Фильтруем по напряжению, если указано
            voltage_filter = options["voltage"]
            lines = lines.filter(voltage_level=voltage_filter)

        for line in lines:
            try:
                # Пропускаем линии с уже назначенным трансформатором напряжения
                if options.get("skip_existing") and line.vt:
                    skipped_count += 1
                    continue

                # Определяем напряжение линии
                voltage_level = (
                    float(line.voltage_level) if line.voltage_level else None
                )

                if voltage_level is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"ЛЭП '{line.dispatch_name}' не имеет напряжения, пропущена"
                        )
                    )
                    skipped_count += 1
                    continue

                # Округляем до ближайшего стандартного напряжения
                if voltage_level < 150:
                    voltage_key = 110
                elif voltage_level < 350:
                    voltage_key = 220
                else:
                    voltage_key = 500

                # Получаем соответствующий трансформатор напряжения
                if voltage_key in transformer_map:
                    vt = transformer_map[voltage_key]
                    line.vt = vt
                    line.save()

                    updated_count += 1
                    if updated_count % 50 == 0:
                        self.stdout.write(
                            f"Обновлено {updated_count} линий...",
                            ending="\r",
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"ЛЭП '{line.dispatch_name}' имеет нестандартное напряжение {voltage_level} кВ "
                            f"(не найден ТН для {voltage_key} кВ)"
                        )
                    )
                    skipped_count += 1

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Ошибка при обработке ЛЭП '{line.dispatch_name}': {e}"
                    )
                )
                error_count += 1

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(
            self.style.SUCCESS(
                f"Назначение завершено!\n"
                f"Обновлено: {updated_count}\n"
                f"Пропущено: {skipped_count}\n"
                f"Ошибок: {error_count}"
            )
        )
