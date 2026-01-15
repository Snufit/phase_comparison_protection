from decimal import Decimal
import math

from django.core.management import BaseCommand

from core.models import Line, LineType, LineBranch
from calculation.services.powerfactory_locator import get_line_type, _has_branches
from calculation.services.powerfactory_manager import PowerFactoryManager


class Command(BaseCommand):
    """
    Команда для импорта всех линий из PowerFactory в базу данных.

    Запуск:
        python manage.py import_lines_from_pf
    """

    help = "Импортирует все линии (ElmBranch) из PowerFactory в базу данных"

    def add_arguments(self, parser):
        """Добавляет аргументы командной строки."""
        parser.add_argument(
            "--update",
            action="store_true",
            help="Обновить существующие записи, если они найдены по pf_name",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Пропустить существующие записи (по умолчанию обновляются)",
        )
        parser.add_argument(
            "--project",
            type=str,
            help="Имя проекта PowerFactory для активации (по умолчанию используется из настроек)",
        )

    def handle(self, *args, **options):
        """Метод импорта линий из PowerFactory."""
        try:
            # Подключаемся к PowerFactory
            self.stdout.write("Подключение к PowerFactory...")
            pf_manager = PowerFactoryManager()

            # Если указано имя проекта через параметр, используем его
            if options.get("project"):
                pf_manager.PROJECT_NAME = options["project"]
                self.stdout.write(
                    self.style.WARNING(
                        f"Используется проект: {pf_manager.PROJECT_NAME}"
                    )
                )

            app = pf_manager.get_application()
            self.stdout.write(self.style.SUCCESS("Подключение к PowerFactory успешно"))

            # Получаем все линии из PowerFactory
            self.stdout.write("Получение линий из PowerFactory...")
            pf_lines = app.GetCalcRelevantObjects("*.ElmBranch") or []

            if not pf_lines:
                self.stdout.write(self.style.WARNING("Линии не найдены в PowerFactory"))
                return

            self.stdout.write(
                self.style.SUCCESS(f"Найдено линий в PowerFactory: {len(pf_lines)}")
            )

            # Статистика
            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0

            # Импортируем каждую линию
            self.stdout.write("\nИмпорт линий...")
            self.stdout.write("=" * 80)

            for index, pf_line in enumerate(pf_lines):
                try:
                    # Получаем имя линии из PowerFactory
                    pf_name = pf_line.GetAttribute("loc_name")
                    if not pf_name:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] Пропущена линия без имени (loc_name)"
                            )
                        )
                        skipped_count += 1
                        continue

                    # Получаем напряжение из терминалов
                    voltage_level = None
                    try:
                        line_terminals = pf_line.GetConnectedElements()
                        if line_terminals:
                            voltage_raw = line_terminals[0].GetUnom()
                            if voltage_raw is not None:
                                voltage_level = Decimal(str(round(voltage_raw, 2)))
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] {pf_name}: не удалось получить напряжение ({e})"
                            )
                        )

                    # Получаем длину линии из атрибута length
                    length = None
                    try:
                        length_raw = pf_line.GetAttribute("length")
                        if length_raw is not None:
                            length = Decimal(
                                str(round(length_raw, 2))
                            )  # Округляем до 2 знаков после запятой
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] {pf_name}: не удалось получить длину ({e})"
                            )
                        )

                    # Получаем сопротивление прямой последовательности R1
                    r1 = None
                    try:
                        r1_raw = pf_line.GetAttribute("R1")
                        if r1_raw is not None:
                            r1 = Decimal(
                                str(round(r1_raw, 2))
                            )  # Округляем до 2 знаков после запятой
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] {pf_name}: не удалось получить R1 ({e})"
                            )
                        )

                    # Получаем сопротивление нулевой последовательности R0
                    r0 = None
                    try:
                        r0_raw = pf_line.GetAttribute("R0")
                        if r0_raw is not None:
                            r0 = Decimal(
                                str(round(r0_raw, 2))
                            )  # Округляем до 2 знаков после запятой
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] {pf_name}: не удалось получить R0 ({e})"
                            )
                        )

                    # Получаем реактивное сопротивление прямой последовательности X1
                    x1 = None
                    try:
                        x1_raw = pf_line.GetAttribute("X1")
                        if x1_raw is not None:
                            x1 = Decimal(
                                str(round(x1_raw, 2))
                            )  # Округляем до 2 знаков после запятой
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] {pf_name}: не удалось получить X1 ({e})"
                            )
                        )

                    # Получаем реактивное сопротивление нулевой последовательности X0
                    x0 = None
                    try:
                        x0_raw = pf_line.GetAttribute("X0")
                        if x0_raw is not None:
                            x0 = Decimal(
                                str(round(x0_raw, 2))
                            )  # Округляем до 2 знаков после запятой
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] {pf_name}: не удалось получить X0 ({e})"
                            )
                        )

                    # Вычисляем полное сопротивление прямой последовательности Z1 = sqrt(R1² + X1²)
                    z1 = None
                    if r1 is not None and x1 is not None:
                        try:
                            z1_value = math.sqrt(float(r1) ** 2 + float(x1) ** 2)
                            z1 = Decimal(str(round(z1_value, 2)))
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"[{index}] {pf_name}: не удалось вычислить Z1 ({e})"
                                )
                            )

                    # Вычисляем полное сопротивление нулевой последовательности Z0 = sqrt(R0² + X0²)
                    z0 = None
                    if r0 is not None and x0 is not None:
                        try:
                            z0_value = math.sqrt(float(r0) ** 2 + float(x0) ** 2)
                            z0 = Decimal(str(round(z0_value, 2)))
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"[{index}] {pf_name}: не удалось вычислить Z0 ({e})"
                                )
                            )

                    # Определяем тип ЛЭП
                    line_type_str = None
                    try:
                        line_type_str = get_line_type(app, pf_line)
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(
                                f"[{index}] {pf_name}: не удалось определить тип ЛЭП ({e})"
                            )
                        )

                    # Находим или создаем объект LineType
                    line_type_obj = None
                    if line_type_str:
                        line_type_obj, _ = LineType.objects.get_or_create(
                            type_code=line_type_str
                        )

                    # Проверяем, есть ли у линии ответвления
                    has_branches = False
                    branch_substations = []
                    if line_type_str and (
                        "ответвлением" in line_type_str
                        or "ответвлениями" in line_type_str
                    ):
                        # Линия имеет ответвления - определяем количество и подстанции
                        try:
                            branch_substations = _has_branches(
                                app,
                                pf_line,
                                return_branch_substations=True,
                                check_substations=True,
                            )
                            has_branches = len(branch_substations) > 0
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"[{index}] {pf_name}: не удалось определить подстанции ответвлений ({e})"
                                )
                            )

                    # Проверяем, существует ли линия в БД
                    existing_line = None
                    if pf_name:
                        try:
                            existing_line = Line.objects.get(pf_name=pf_name)
                        except Line.DoesNotExist:
                            pass
                        except Line.MultipleObjectsReturned:
                            # Если найдено несколько записей, берем первую
                            existing_line = Line.objects.filter(pf_name=pf_name).first()
                            self.stdout.write(
                                self.style.WARNING(
                                    f"[{index}] {pf_name}: найдено несколько записей, обновляется первая"
                                )
                            )

                    if existing_line:
                        # Обновляем существующую запись
                        if options["skip_existing"]:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"[{index}] {pf_name}: пропущена (уже существует)"
                                )
                            )
                            skipped_count += 1
                            continue

                        existing_line.index_pf = index
                        if voltage_level is not None:
                            existing_line.voltage_level = voltage_level
                        if length is not None:
                            existing_line.length = length
                        if r1 is not None:
                            existing_line.r1 = r1
                        if r0 is not None:
                            existing_line.r0 = r0
                        if x1 is not None:
                            existing_line.x1 = x1
                        if x0 is not None:
                            existing_line.x0 = x0
                        if z1 is not None:
                            existing_line.z1 = z1
                        if z0 is not None:
                            existing_line.z0 = z0
                        if line_type_obj is not None:
                            existing_line.line_type = line_type_obj
                        existing_line.save()

                        # Создаем или обновляем LineBranch для линий с ответвлениями
                        if has_branches:
                            existing_branches = LineBranch.objects.filter(
                                line=existing_line
                            )
                            existing_branch_count = existing_branches.count()

                            # Обновляем pf_name_line в существующих LineBranch
                            existing_branches.update(pf_name_line=pf_name)

                            # Если записей LineBranch нет или их меньше чем подстанций ответвлений
                            if existing_branch_count < len(branch_substations):
                                # Создаем недостающие записи LineBranch
                                for i in range(
                                    len(branch_substations) - existing_branch_count
                                ):
                                    LineBranch.objects.create(
                                        line=existing_line,
                                        pf_name_line=pf_name,
                                        substation=None,  # Пока без подстанции
                                        is_active=True,
                                    )
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"[{index}] {pf_name}: создано {len(branch_substations) - existing_branch_count} записей LineBranch"
                                    )
                                )

                        length_str = (
                            f", длина: {length:.2f} км" if length is not None else ""
                        )
                        voltage_str = f"{voltage_level or Decimal('0.00'):.2f}"
                        type_str = f", тип: {line_type_str}" if line_type_str else ""
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[{index}] {pf_name}: обновлена (напряжение: {voltage_str} кВ{length_str}{type_str})"
                            )
                        )
                        updated_count += 1
                    else:
                        # Создаем новую запись
                        # Используем pf_name как dispatch_name, если нет другого значения
                        dispatch_name = pf_name

                        line = Line.objects.create(
                            dispatch_name=dispatch_name,
                            pf_name=pf_name,
                            index_pf=index,
                            voltage_level=voltage_level
                            or Decimal("0.00"),  # По умолчанию 0.00 кВ
                            length=length or Decimal("0.00"),  # По умолчанию 0.00 км
                            r1=r1,  # Сопротивление прямой последовательности
                            r0=r0,  # Сопротивление нулевой последовательности
                            x1=x1,  # Реактивное сопротивление прямой последовательности
                            x0=x0,  # Реактивное сопротивление нулевой последовательности
                            z1=z1,  # Полное сопротивление прямой последовательности
                            z0=z0,  # Полное сопротивление нулевой последовательности
                            line_type=line_type_obj,  # Тип ЛЭП
                        )

                        # Создаем LineBranch для линий с ответвлениями
                        if has_branches:
                            for _ in range(len(branch_substations)):
                                LineBranch.objects.create(
                                    line=line,
                                    pf_name_line=pf_name,
                                    substation=None,  # Пока без подстанции
                                    is_active=True,
                                )
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"[{index}] {pf_name}: создано {len(branch_substations)} записей LineBranch"
                                )
                            )

                        length_str = (
                            f", длина: {length:.2f} км" if length is not None else ""
                        )
                        voltage_str = f"{voltage_level or Decimal('0.00'):.2f}"
                        type_str = f", тип: {line_type_str}" if line_type_str else ""
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[{index}] {pf_name}: создана (напряжение: {voltage_str} кВ{length_str}{type_str})"
                            )
                        )
                        created_count += 1

                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(f"[{index}] Ошибка при обработке линии: {e}")
                    )
                    import traceback

                    self.stdout.write(self.style.ERROR(traceback.format_exc()))

            # Выводим статистику
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(self.style.SUCCESS("Импорт завершен"))
            self.stdout.write(f"Создано: {created_count}")
            self.stdout.write(f"Обновлено: {updated_count}")
            self.stdout.write(f"Пропущено: {skipped_count}")
            if error_count > 0:
                self.stdout.write(self.style.ERROR(f"Ошибок: {error_count}"))

        except ModuleNotFoundError as e:
            self.stdout.write(
                self.style.ERROR(
                    f"PowerFactory недоступен: {e}\n"
                    "Убедитесь, что PowerFactory запущен и проект открыт."
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Ошибка при импорте: {str(e)}"))
            import traceback

            self.stdout.write(self.style.ERROR(traceback.format_exc()))
