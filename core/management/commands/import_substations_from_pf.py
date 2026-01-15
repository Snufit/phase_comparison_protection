from django.core.management import BaseCommand

from core.models import Substation
from calculation.services.powerfactory_manager import PowerFactoryManager


class Command(BaseCommand):
    """
    Команда для импорта всех подстанций из PowerFactory в базу данных.
    """

    help = "Импортирует все подстанции (ElmSubstat) из PowerFactory в базу данных"

    def add_arguments(self, parser):
        parser.add_argument(
            "--update",
            action="store_true",
            help="Обновить существующие записи",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Пропустить существующие записи",
        )
        parser.add_argument(
            "--project",
            type=str,
            help="Имя проекта PowerFactory для активации",
        )

    def handle(self, *args, **options):
        self.stdout.write("Подключение к PowerFactory...")

        try:
            pf_manager = PowerFactoryManager()
            if options["project"]:
                pf_manager.PROJECT_NAME = options["project"]

            app = pf_manager.get_application()
            self.stdout.write(self.style.SUCCESS("Подключение к PowerFactory успешно"))

            # Получаем все подстанции из PowerFactory
            self.stdout.write("Получение подстанций из PowerFactory...")
            pf_substations = app.GetCalcRelevantObjects("*.ElmSubstat")

            if not pf_substations:
                self.stdout.write(
                    self.style.WARNING("Подстанции не найдены в PowerFactory")
                )
                return

            self.stdout.write(
                self.style.SUCCESS(
                    f"Найдено подстанций в PowerFactory: {len(pf_substations)}"
                )
            )

            # Статистика
            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0

            # Импортируем каждую подстанцию
            self.stdout.write("\nИмпорт подстанций...")
            self.stdout.write("=" * 80)

            for index, pf_substation in enumerate(pf_substations):
                try:
                    # Получаем имя подстанции из PowerFactory
                    pf_name = pf_substation.GetAttribute("loc_name")
                    if not pf_name:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] Пропущена подстанция без имени (loc_name)"
                            )
                        )
                        skipped_count += 1
                        continue

                    # Проверяем, существует ли подстанция в БД
                    existing_substation = None
                    try:
                        existing_substation = Substation.objects.get(pf_name=pf_name)
                    except Substation.DoesNotExist:
                        pass
                    except Substation.MultipleObjectsReturned:
                        # Если найдено несколько записей, берем первую
                        existing_substation = Substation.objects.filter(
                            pf_name=pf_name
                        ).first()
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] {pf_name}: найдено несколько записей, обновляется первая"
                            )
                        )

                    if existing_substation:
                        # Обновляем существующую запись
                        if options["skip_existing"]:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"[{index}] {pf_name}: пропущена (уже существует)"
                                )
                            )
                            skipped_count += 1
                            continue

                        # Обновление не требуется, так как у нас только pf_name
                        # Но можно добавить логику обновления других полей в будущем
                        updated_count += 1
                        if updated_count % 50 == 0:
                            self.stdout.write(
                                f"Обновлено {updated_count} подстанций...",
                                ending="\r",
                            )
                    else:
                        # Создаем новую запись
                        Substation.objects.create(pf_name=pf_name)

                        self.stdout.write(
                            self.style.SUCCESS(f"[{index}] {pf_name}: создана")
                        )
                        created_count += 1

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"[{index}] Ошибка при импорте подстанции: {e}"
                        )
                    )
                    error_count += 1
                    continue

            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Импорт завершен!\n"
                    f"Создано: {created_count}\n"
                    f"Обновлено: {updated_count}\n"
                    f"Пропущено: {skipped_count}\n"
                    f"Ошибок: {error_count}"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Ошибка при импорте: {str(e)}"))
            raise
