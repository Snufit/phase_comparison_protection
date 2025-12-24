from django.core.management import BaseCommand

from core.models import Line, ProtectionHalfSet
from calculation.services.topology_analysis_service import TopologyAnalysisService
from calculation.services.powerfactory_manager import PowerFactoryManager


class Command(BaseCommand):
    """
    Команда для анализа топологии для всех линий с полукомплектами защиты.
    
    Находит все линии, которые имеют полукомплекты защиты,
    и для каждого полукомплекта получает топологию из PowerFactory
    и сохраняет в БД (HalfSetTopology).
    
    Запуск:
        python manage.py analyze_topology_for_all_lines
        python manage.py analyze_topology_for_all_lines --line-id 123
        python manage.py analyze_topology_for_all_lines --half-set-id 456
        python manage.py analyze_topology_for_all_lines --force-refresh
        python manage.py analyze_topology_for_all_lines --only-missing
    """

    help = "Анализирует топологию для всех линий с полукомплектами защиты"

    def add_arguments(self, parser):
        parser.add_argument(
            "--line-id",
            type=int,
            help="Обработать только конкретную линию по ID",
        )
        parser.add_argument(
            "--half-set-id",
            type=int,
            help="Обработать только конкретный полукомплект защиты по ID",
        )
        parser.add_argument(
            "--force-refresh",
            action="store_true",
            help="Принудительно обновить топологию из PowerFactory (даже если есть в БД)",
        )
        parser.add_argument(
            "--only-missing",
            action="store_true",
            help="Обработать только полукомплекты без топологии в БД",
        )
        parser.add_argument(
            "--project",
            type=str,
            help="Имя проекта PowerFactory для активации",
        )

    def handle(self, *args, **options):
        self.stdout.write("Поиск полукомплектов защиты...")

        # Определяем, какие полукомплекты обрабатывать
        if options.get("half_set_id"):
            # Если указан конкретный ID полукомплекта
            try:
                half_sets = [ProtectionHalfSet.objects.get(id=options["half_set_id"])]
            except ProtectionHalfSet.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(
                        f"Полукомплект защиты с ID {options['half_set_id']} не найден"
                    )
                )
                return
        elif options.get("line_id"):
            # Если указан конкретный ID линии
            try:
                line = Line.objects.get(id=options["line_id"])
                half_sets = line.protection_half_sets.all()
                if not half_sets.exists():
                    self.stdout.write(
                        self.style.WARNING(
                            f"Линия с ID {options['line_id']} не имеет полукомплектов защиты"
                        )
                    )
                    return
            except Line.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Линия с ID {options['line_id']} не найдена")
                )
                return
        else:
            # Находим все полукомплекты защиты
            half_sets = ProtectionHalfSet.objects.all().select_related(
                "line", "substation", "protection_device"
            )

        # Фильтруем только те, у которых нет топологии (если указан флаг)
        if options.get("only_missing"):
            from core.models import HalfSetTopology
            existing_topology_half_set_ids = set(
                HalfSetTopology.objects.values_list("protection_half_set_id", flat=True)
            )
            half_sets = [hs for hs in half_sets if hs.id not in existing_topology_half_set_ids]

        if not half_sets:
            self.stdout.write(
                self.style.WARNING("Не найдено полукомплектов защиты для обработки")
            )
            return

        total_half_sets = len(half_sets) if isinstance(half_sets, list) else half_sets.count()
        self.stdout.write(
            self.style.SUCCESS(f"Найдено полукомплектов защиты: {total_half_sets}")
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
        processed_half_sets = 0
        created_topologies = 0
        updated_topologies = 0
        skipped_topologies = 0
        error_count = 0

        self.stdout.write("\nОбработка полукомплектов защиты...")
        self.stdout.write("=" * 80)

        # Преобразуем QuerySet в список для единообразной обработки
        if not isinstance(half_sets, list):
            half_sets = list(half_sets)

        for half_set in half_sets:
            try:
                # Проверяем, есть ли уже топология в БД
                from core.models import HalfSetTopology

                topology_exists = HalfSetTopology.objects.filter(
                    protection_half_set=half_set
                ).exists()

                if topology_exists and not options.get("force_refresh"):
                    skipped_topologies += 1
                    self.stdout.write(
                        f"  - Полукомплект {half_set} (ЛЭП: {half_set.line.dispatch_name}, "
                        f"ПС: {half_set.substation}): топология уже существует, пропущен"
                    )
                    continue

                # Проверяем наличие необходимых данных
                if not half_set.line.pf_name:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠ Полукомплект {half_set}: ЛЭП не имеет pf_name, пропущен"
                        )
                    )
                    continue

                if not half_set.substation.pf_name:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠ Полукомплект {half_set}: ПС не имеет pf_name, пропущен"
                        )
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
                            f"  ✓ Полукомплект {half_set} (ЛЭП: {half_set.line.dispatch_name}, "
                            f"ПС: {half_set.substation}): топология обновлена "
                            f"({len(topology)} элементов)"
                        )
                    )
                else:
                    created_topologies += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ Полукомплект {half_set} (ЛЭП: {half_set.line.dispatch_name}, "
                            f"ПС: {half_set.substation}): топология создана "
                            f"({len(topology)} элементов)"
                        )
                    )

                processed_half_sets += 1

                # Прогресс каждые 50 полукомплектов
                if processed_half_sets % 50 == 0:
                    self.stdout.write(
                        f"\nОбработано {processed_half_sets}/{total_half_sets} полукомплектов...",
                        ending="\r",
                    )

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ Ошибка при обработке полукомплекта {half_set}: {e}"
                    )
                )
                import traceback
                self.stdout.write(self.style.ERROR(traceback.format_exc()))
                continue

        # Итоговая статистика
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("Обработка завершена!"))
        self.stdout.write(f"  Обработано полукомплектов: {processed_half_sets}")
        self.stdout.write(f"  Создано топологий: {created_topologies}")
        self.stdout.write(f"  Обновлено топологий: {updated_topologies}")
        self.stdout.write(f"  Пропущено топологий: {skipped_topologies}")
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"  Ошибок: {error_count}"))

