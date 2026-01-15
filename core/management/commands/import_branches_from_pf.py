from django.core.management import BaseCommand

from core.models import Line, LineBranch, Substation
from calculation.services.powerfactory_manager import PowerFactoryManager
from calculation.services.powerfactory_locator import (
    _get_line_end_substations,
    _get_main_substations_with_voltage,
    get_pf_line,
)


class Command(BaseCommand):
    """
    Команда для заполнения подстанций в существующих записях LineBranch.

    Логика работы:
    1. Находит все LineBranch без подстанций (substation is None)
    2. Для каждой линии определяет подстанции ответвлений через PowerFactory
    3. Заполняет substation и pf_name_substation в существующих LineBranch
    4. Если подстанций ответвлений больше чем LineBranch, создает недостающие записи
    """

    help = "Заполняет подстанции в существующих записях LineBranch из PowerFactory"

    def add_arguments(self, parser):
        parser.add_argument(
            "--line-id",
            type=int,
            help="ID конкретной ЛЭП для обработки (если не указано, обрабатываются все ЛЭП)",
        )
        parser.add_argument(
            "--project",
            type=str,
            help="Имя проекта PowerFactory для активации",
        )
        parser.add_argument(
            "--update-only",
            action="store_true",
            help="Обновлять только существующие ответвления",
        )

    def handle(self, *args, **options):
        self.stdout.write("Подключение к PowerFactory...")

        try:
            pf_manager = PowerFactoryManager()
            if options["project"]:
                pf_manager.PROJECT_NAME = options["project"]

            app = pf_manager.get_application()
            self.stdout.write(self.style.SUCCESS("Подключение к PowerFactory успешно"))

            # Находим все LineBranch без подстанций (где substation is None)
            line_branches = LineBranch.objects.filter(substation__isnull=True)

            if not line_branches.exists():
                self.stdout.write(
                    self.style.WARNING(
                        "Не найдено LineBranch без подстанций для заполнения"
                    )
                )
                return

            # Обрабатываем каждую уникальную линию
            unique_lines = Line.objects.filter(
                branches__substation__isnull=True
            ).distinct()

            total_lines = unique_lines.count()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Найдено линий с LineBranch без подстанций: {total_lines}"
                )
            )

            # Статистика
            processed_count = 0
            filled_count = 0
            error_count = 0

            self.stdout.write("\nОбработка ответвлений...")
            self.stdout.write("=" * 80)

            for line in unique_lines:
                try:
                    if not line.pf_name:
                        self.stdout.write(
                            self.style.WARNING(
                                f"ЛЭП '{line.dispatch_name}' не имеет pf_name, пропущена"
                            )
                        )
                        continue

                    # Получаем объект ЛЭП из PowerFactory
                    pf_line = get_pf_line(app, line.pf_name)
                    if not pf_line:
                        self.stdout.write(
                            self.style.WARNING(
                                f"ЛЭП '{line.pf_name}' не найдена в PowerFactory"
                            )
                        )
                        continue

                    # Определяем подстанции ответвлений
                    all_substations = _get_line_end_substations(pf_line, app)
                    main_substations = _get_main_substations_with_voltage(pf_line, app)

                    main_substations_set = {
                        (sub["name"], sub["voltage_kv"]) for sub in main_substations
                    }
                    all_substations_set = {
                        (sub["name"], sub["voltage_kv"]) for sub in all_substations
                    }

                    branch_substations_keys = all_substations_set - main_substations_set

                    # Получаем все LineBranch для этой линии без подстанций
                    line_branches_for_line = LineBranch.objects.filter(
                        line=line, substation__isnull=True
                    )

                    # Заполняем подстанции для каждого LineBranch
                    branch_substations_list = [
                        sub
                        for sub in all_substations
                        if (sub["name"], sub["voltage_kv"]) in branch_substations_keys
                    ]

                    # Если подстанций ответвлений больше чем LineBranch, создаем недостающие
                    if len(branch_substations_list) > line_branches_for_line.count():
                        for _ in range(
                            len(branch_substations_list)
                            - line_branches_for_line.count()
                        ):
                            LineBranch.objects.create(
                                line=line,
                                pf_name_line=line.pf_name,
                                substation=None,
                                is_active=True,
                            )
                        line_branches_for_line = LineBranch.objects.filter(
                            line=line, substation__isnull=True
                        )

                    # Заполняем подстанции
                    for i, line_branch in enumerate(line_branches_for_line):
                        if i < len(branch_substations_list):
                            substation_data = branch_substations_list[i]
                            substation_name = substation_data["name"]

                            # Находим или создаем подстанцию
                            substation, _ = Substation.objects.get_or_create(
                                pf_name=substation_name
                            )

                            # Обновляем LineBranch
                            line_branch.substation = substation
                            line_branch.pf_name_substation = substation_name
                            line_branch.save()

                            filled_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Заполнена ПС для LineBranch (ЛЭП: {line.dispatch_name}, ПС: {substation_name})"
                                )
                            )

                    processed_count += 1

                    if processed_count % 50 == 0:
                        self.stdout.write(
                            f"Обработано {processed_count}/{total_lines} линий...",
                            ending="\r",
                        )

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Ошибка при обработке ЛЭП '{line.dispatch_name}': {e}"
                        )
                    )
                    error_count += 1
                    continue

            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Обработка завершена!\n"
                    f"Обработано линий: {processed_count}\n"
                    f"Заполнено подстанций: {filled_count}\n"
                    f"Ошибок: {error_count}"
                )
            )

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Ошибка при импорте: {str(e)}"))
            raise
