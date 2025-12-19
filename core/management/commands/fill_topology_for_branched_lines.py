from django.core.management import BaseCommand

from core.models import Line, LineBranch, ProtectionHalfSet
from calculation.services.topology_analysis_service import TopologyAnalysisService
from calculation.services.powerfactory_manager import PowerFactoryManager


class Command(BaseCommand):
    """
    Команда для заполнения HalfSetTopology для всех линий с ответвлениями.
    
    Находит все линии, которые имеют ответвления (через LineBranch),
    и для каждого полукомплекта защиты этих линий получает топологию
    из PowerFactory и сохраняет в БД.
    
    Запуск:
        python manage.py fill_topology_for_branched_lines
        python manage.py fill_topology_for_branched_lines --line-id 123
        python manage.py fill_topology_for_branched_lines --force-refresh
    """

    help = "Заполняет HalfSetTopology для всех линий с ответвлениями"

    def add_arguments(self, parser):
        parser.add_argument(
            "--line-id",
            type=int,
            help="Обработать только конкретную линию по ID",
        )
        parser.add_argument(
            "--force-refresh",
            action="store_true",
            help="Принудительно обновить топологию из PowerFactory (даже если есть в БД)",
        )
        parser.add_argument(
            "--project",
            type=str,
            help="Имя проекта PowerFactory для активации",
        )

    def handle(self, *args, **options):
        self.stdout.write("Поиск линий с ответвлениями...")

        # Находим все уникальные линии, которые имеют ответвления
        if options.get("line_id"):
            # Если указан конкретный ID линии
            try:
                line = Line.objects.get(id=options["line_id"])
                if not LineBranch.objects.filter(line=line).exists():
                    self.stdout.write(
                        self.style.WARNING(
                            f"Линия с ID {options['line_id']} не имеет ответвлений"
                        )
                    )
                    return
                lines_with_branches = [line]
            except Line.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Линия с ID {options['line_id']} не найдена")
                )
                return
        else:
            # Находим все линии с ответвлениями
            lines_with_branches = Line.objects.filter(
                branches__isnull=False
            ).distinct()

        if not lines_with_branches.exists():
            self.stdout.write(
                self.style.WARNING("Не найдено линий с ответвлениями")
            )
            return

        total_lines = lines_with_branches.count()
        self.stdout.write(
            self.style.SUCCESS(f"Найдено линий с ответвлениями: {total_lines}")
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
        processed_half_sets = 0
        created_topologies = 0
        updated_topologies = 0
        skipped_topologies = 0
        error_count = 0

        self.stdout.write("\nОбработка линий...")
        self.stdout.write("=" * 80)

        for line in lines_with_branches:
            try:
                # Получаем все полукомплекты защиты для этой линии
                protection_half_sets = line.protection_half_sets.all()

                if not protection_half_sets.exists():
                    self.stdout.write(
                        self.style.WARNING(
                            f"ЛЭП '{line.dispatch_name}' (ID: {line.id}) не имеет полукомплектов защиты, пропущена"
                        )
                    )
                    continue

                self.stdout.write(
                    f"\nЛЭП: {line.dispatch_name} (ID: {line.id}, pf_name: {line.pf_name})"
                )
                self.stdout.write(
                    f"  Полукомплектов защиты: {protection_half_sets.count()}"
                )

                # Обрабатываем каждый полукомплект
                for half_set in protection_half_sets:
                    try:
                        # Проверяем, есть ли уже топология в БД
                        from core.models import HalfSetTopology

                        topology_exists = HalfSetTopology.objects.filter(
                            protection_half_set=half_set
                        ).exists()

                        if topology_exists and not options.get("force_refresh"):
                            skipped_topologies += 1
                            self.stdout.write(
                                f"    - Полукомплект {half_set.substation}: "
                                f"топология уже существует, пропущен"
                            )
                            continue

                        # Получаем топологию через сервис
                        topology_service = TopologyAnalysisService(half_set)
                        topology = topology_service.get_half_set_topology(
                            app=app, force_refresh=options.get("force_refresh", False)
                        )

                        if topology_exists:
                            updated_topologies += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"    ✓ Полукомплект {half_set.substation}: "
                                    f"топология обновлена ({len(topology)} элементов)"
                                )
                            )
                        else:
                            created_topologies += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"    ✓ Полукомплект {half_set.substation}: "
                                    f"топология создана ({len(topology)} элементов)"
                                )
                            )

                        processed_half_sets += 1

                    except Exception as e:
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f"    ✗ Ошибка при обработке полукомплекта "
                                f"{half_set.substation}: {e}"
                            )
                        )
                        import traceback
                        self.stdout.write(self.style.ERROR(traceback.format_exc()))

                processed_lines += 1

                # Прогресс каждые 10 линий
                if processed_lines % 10 == 0:
                    self.stdout.write(
                        f"\nОбработано {processed_lines}/{total_lines} линий...",
                        ending="\r",
                    )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Ошибка при обработке ЛЭП '{line.dispatch_name}': {e}"
                    )
                )
                continue

        # Итоговая статистика
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("Обработка завершена!"))
        self.stdout.write(f"  Обработано линий: {processed_lines}")
        self.stdout.write(f"  Обработано полукомплектов: {processed_half_sets}")
        self.stdout.write(f"  Создано топологий: {created_topologies}")
        self.stdout.write(f"  Обновлено топологий: {updated_topologies}")
        self.stdout.write(f"  Пропущено топологий: {skipped_topologies}")
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"  Ошибок: {error_count}"))

