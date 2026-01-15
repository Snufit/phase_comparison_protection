from decimal import Decimal

from django.db import models
from django.db.models import Q


class LineType(models.Model):
    """Модель типа ЛЭП."""

    type_code = models.CharField(
        verbose_name="Наименование типа ЛЭП", max_length=100, unique=True
    )

    class Meta:
        """Мета-данные модели LineType."""

        verbose_name = "Тип ЛЭП"
        verbose_name_plural = "Типы ЛЭП"

    def __str__(self):
        """
        :return: Наименование типа ЛЭП.
        """
        return self.type_code


class MethodologyDocument(models.Model):
    """Модель документа методики расчета."""

    name_file = models.CharField(
        verbose_name="URL документа с методикой", max_length=255, unique=True
    )
    created_at = models.DateTimeField(
        verbose_name="Дата и время добавления", auto_now_add=True
    )
    updated_at = models.DateTimeField(
        verbose_name="Дата и время последнего обновления", auto_now=True
    )

    class Meta:
        """Мета-данные модели MethodologyDocument."""

        verbose_name = "Документ методики"
        verbose_name_plural = "Документы методик"

    def __str__(self):
        """
        :return: Название файла документа методики.
        """
        return self.name_file

    def get_filename(self):
        """
        :return: Только имя файла без пути.
        """
        import os

        return os.path.basename(self.name_file)


class Manufacturer(models.Model):
    """Модель производителя устройства РЗА."""

    name = models.CharField(
        verbose_name="Название производителя", max_length=150, unique=True
    )

    class Meta:
        """Мета-данные модели Manufacturer."""

        verbose_name = "Производитель"
        verbose_name_plural = "Производители"

    def __str__(self):
        """
        :return: Название производителя.
        """
        return self.name


class CoefficientType(models.Model):
    """Модель типа коэффициента защиты."""

    code = models.CharField(
        verbose_name="Код типа коэффициента", max_length=50, unique=True
    )
    name = models.CharField(
        verbose_name="Название типа коэффициента", max_length=150, unique=True
    )
    description = models.TextField(
        verbose_name="Описание коэффициента", blank=True, null=True
    )

    class Meta:
        """Мета-данные модели CoefficientType."""

        verbose_name = "Тип коэффициента"
        verbose_name_plural = "Типы коэффициентов"

    def __str__(self):
        """
        :return: Название типа коэффициента.
        """
        return self.name


class CurrentTransformer(models.Model):
    """Модель трансформатора тока (ТТ)."""

    model_ct_pf_name = models.CharField(
        verbose_name="Наименование модели ТТ в PowerFactory",
        max_length=50,
        unique=True,
        help_text="Наименование модели ТТ в PowerFactory (например, 'ТТ 630/1')",
    )
    primary_current = models.IntegerField(
        verbose_name="Первичный ток, А",
        help_text="Первичный ток трансформатора тока (например, 630)",
    )
    secondary_current = models.IntegerField(
        verbose_name="Вторичный ток, А",
        help_text="Вторичный ток трансформатора тока (например, 1)",
    )
    ratio = models.FloatField(
        verbose_name="Коэффициент трансформации ТТ",
        help_text="Вычисляется автоматически как primary_current / secondary_current",
        editable=False,  # Нельзя редактировать вручную
    )

    class Meta:
        """Мета-данные модели CurrentTransformer."""

        verbose_name = "Трансформатор тока"
        verbose_name_plural = "Трансформаторы тока"

    def __str__(self):
        return f"{self.model_ct_pf_name}"

    def calculate_ratio(self) -> float:
        """
        Вычисляет коэффициент трансформации ТТ.

        Returns:
            float: Коэффициент трансформации (primary_current / secondary_current)
        """
        if self.secondary_current and self.secondary_current != 0:
            return self.primary_current / self.secondary_current
        return 1000

    def save(self, *args, **kwargs):
        """Переопределяем save для автоматического расчета ratio."""
        self.ratio = self.calculate_ratio()
        super().save(*args, **kwargs)


class VoltageTransformer(models.Model):
    """Модель трансформатора напряжения (ТН)."""

    # Типы соединения обмоток ТН
    CONNECTION_DELTA = "delta"
    CONNECTION_STAR = "star"
    CONNECTION_CHOICES = [
        (CONNECTION_DELTA, "Разомкнутый треугольник (∆)"),
        (CONNECTION_STAR, "Звезда (Y)"),
    ]

    # Типы ТН
    TYPE_IDEAL = "ideal"
    TYPE_STANDARD = "standard"
    TYPE_CAPACITIVE = "capacitive"
    TYPE_CHOICES = [
        (TYPE_IDEAL, "Идеальный трансформатор напряжения"),
        (TYPE_STANDARD, "Трансформатор напряжения"),
        (TYPE_CAPACITIVE, "Емкостной трансформатор напряжения"),
    ]

    model_vt_pf_name = models.CharField(
        verbose_name="Наименование модели ТН в PowerFactory",
        max_length=50,
        unique=True,
        help_text="Наименование модели ТН в PowerFactory (например, 'ТН 220000/100')",
    )
    primary_voltage = models.IntegerField(
        verbose_name="Первичное напряжение, кВ",
        help_text="Первичное номинальное напряжение ТН в кВ (например, 220)",
    )
    connection_type = models.CharField(
        verbose_name="Тип соединения обмоток",
        max_length=20,
        choices=CONNECTION_CHOICES,
        default=CONNECTION_DELTA,
        help_text="Тип соединения вторичных обмоток ТН",
    )
    type = models.CharField(
        verbose_name="Тип ТН",
        max_length=50,
        choices=TYPE_CHOICES,
        default=TYPE_IDEAL,
        help_text="Тип трансформатора напряжения",
    )
    ratio = models.FloatField(
        verbose_name="Коэффициент трансформации ТН",
        help_text="Вычисляется автоматически на основе primary_voltage и connection_type. При использовании с ЛЭП используется calculate_ratio(line_voltage_kv).",
        editable=False,  # Нельзя редактировать вручную
    )

    class Meta:
        """Мета-данные модели VoltageTransformer."""

        verbose_name = "Трансформатор напряжения"
        verbose_name_plural = "Трансформаторы напряжения"

    def __str__(self):
        return f"{self.model_vt_pf_name}"

    def calculate_ratio(self, line_voltage_kv=None) -> float:
        """
        Вычисляет коэффициент трансформации ТН.

        Args:
            line_voltage_kv: Напряжение ЛЭП в кВ (может быть Decimal или float).
                           Если не указано, используется primary_voltage.

        Returns:
            float: Коэффициент трансформации ТН
        """
        import math

        # Используем напряжение ЛЭП, если указано, иначе primary_voltage ТН
        # Конвертируем Decimal в float для вычислений
        if line_voltage_kv is not None:
            u_nom = float(line_voltage_kv)
        else:
            u_nom = self.primary_voltage
        sqrt3 = math.sqrt(3)

        if self.connection_type == self.CONNECTION_DELTA:
            # Разомкнутый треугольник: n_ТН∆ = (Uном/√3)/100
            return (u_nom / sqrt3) / 100
        elif self.connection_type == self.CONNECTION_STAR:
            # Звезда: n_ТНY = Uном/100
            return u_nom / 100
        else:
            # По умолчанию используем разомкнутый треугольник
            return (u_nom / sqrt3) / 100

    def save(self, *args, **kwargs):
        """Переопределяем save для автоматического расчета ratio на основе primary_voltage."""
        # Вычисляем базовый коэффициент на основе primary_voltage
        # При использовании с конкретной ЛЭП будет использоваться calculate_ratio(line_voltage_kv)
        self.ratio = self.calculate_ratio()  # Без параметра использует primary_voltage
        super().save(*args, **kwargs)


class Line(models.Model):
    """
    Модель линии электропередач (ЛЭП).

    ЛЭП напряжением 110 кВ и выше с двусторонним питанием.
    Поддерживает одиночные, параллельные линии и линии с ответвлениями.
    """

    dispatch_name = models.CharField(
        verbose_name="Диспетчерское наименование", max_length=100
    )
    pf_name = models.CharField(
        verbose_name="Наименование в PowerFactory",
        max_length=100,
        blank=True,
        null=True,
    )
    project_name = models.CharField(
        verbose_name="Имя проекта PowerFactory",
        max_length=200,
        blank=True,
        null=True,
        help_text="Имя проекта PowerFactory, из которого импортирована линия",
    )
    index_pf = models.IntegerField(
        verbose_name="Индекс линии в PowerFactory",
        null=True,
        blank=True,
        help_text="Индекс линии в списке всех линий PowerFactory (ElmBranch)",
    )
    line_type = models.ForeignKey(
        LineType,
        on_delete=models.PROTECT,
        related_name="lines",
        verbose_name="Тип ЛЭП",
        null=True,  # Временно для миграции
        blank=True,
    )
    current_capacity = models.FloatField(verbose_name="ДДТН, А", default=2000)
    length = models.DecimalField(
        verbose_name="Длина ЛЭП, км",
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),  # Значение по умолчанию для существующих записей
    )
    # Связи с трансформаторами
    ct = models.ForeignKey(
        CurrentTransformer,
        on_delete=models.PROTECT,
        related_name="lines",
        verbose_name="Трансформатор тока",
        null=True,  # Временно для миграции
        blank=True,
    )
    vt = models.ForeignKey(
        VoltageTransformer,
        on_delete=models.PROTECT,
        related_name="lines",
        verbose_name="Трансформатор напряжения",
        null=True,  # Временно для миграции
        blank=True,
    )
    # Напряжение ЛЭП (получается из PowerFactory)
    voltage_level = models.DecimalField(
        verbose_name="Номинальное напряжение ЛЭП, кВ",
        max_digits=7,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Номинальное напряжение ЛЭП, получаемое из PowerFactory",
    )
    # Сопротивления ЛЭП (получаются из PowerFactory)
    r1 = models.DecimalField(
        verbose_name="Сопротивление прямой последовательности, Ом",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Активное сопротивление прямой последовательности, получаемое из PowerFactory",
    )
    r0 = models.DecimalField(
        verbose_name="Сопротивление нулевой последовательности, Ом",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Активное сопротивление нулевой последовательности, получаемое из PowerFactory",
    )
    x1 = models.DecimalField(
        verbose_name="Реактивное сопротивление прямой последовательности, Ом",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Реактивное сопротивление прямой последовательности, получаемое из PowerFactory",
    )
    x0 = models.DecimalField(
        verbose_name="Реактивное сопротивление нулевой последовательности, Ом",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Реактивное сопротивление нулевой последовательности, получаемое из PowerFactory",
    )
    # Полные сопротивления (вычисляются как sqrt(R² + X²))
    z1 = models.DecimalField(
        verbose_name="Полное сопротивление прямой последовательности, Ом",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Модуль полного сопротивления прямой последовательности (Z1 = sqrt(R1² + X1²))",
    )
    z0 = models.DecimalField(
        verbose_name="Полное сопротивление нулевой последовательности, Ом",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Модуль полного сопротивления нулевой последовательности (Z0 = sqrt(R0² + X0²))",
    )
    branch_count = models.IntegerField(
        verbose_name="Количество ответвлений", null=True, blank=True, default=0
    )
    is_offset_applied = models.BooleanField(
        verbose_name="Применение смещения в защищаемую зону", default=False
    )
    zero_sequence_voltage = models.FloatField(
        verbose_name="Составляющая напряжения нулевой последовательности",
        null=True,
        blank=True,
    )
    offset_coefficient = models.FloatField(
        verbose_name="Коэффициент смещения для ЛЭП", null=True, blank=True
    )

    @property
    def length_formatted(self) -> str:
        """Возвращает длину с форматированием до 2 знаков после запятой."""
        if self.length is not None:
            return f"{self.length:.2f}"
        return "0.00"

    @property
    def voltage_level_formatted(self) -> str:
        """Возвращает напряжение с форматированием до 2 знаков после запятой."""
        if self.voltage_level is not None:
            return f"{self.voltage_level:.2f}"
        return "0.00"

    class Meta:
        """Мета-данные модели Line."""

        verbose_name = "ЛЭП"
        verbose_name_plural = "ЛЭП"
        unique_together = [("pf_name", "project_name")]

    def update_voltage_from_pf(self, app) -> None:
        """
        Получает напряжение и длину ЛЭП из PowerFactory и сохраняет в БД.

        Метод сам получает объект ЛЭП из PowerFactory по self.pf_name.

        Args:
            app: COM-объект PowerFactory
        """
        if not self.pf_name:
            print(f"Для ЛЭП {self.dispatch_name} не указано pf_name")
            return

        try:
            # Получаем объект ЛЭП из PowerFactory по имени
            pf_lines = app.GetCalcRelevantObjects("*.ElmBranch")
            pf_line = None
            for line in pf_lines:
                if line.GetAttribute("loc_name") == self.pf_name:
                    pf_line = line
                    break

            if not pf_line:
                print(f"ЛЭП '{self.pf_name}' не найдена в PowerFactory")
                return

            # Получаем напряжение из терминалов ЛЭП
            line_terminals = pf_line.GetConnectedElements()
            if line_terminals:
                voltage_level = line_terminals[0].GetUnom()
                if voltage_level is not None:
                    self.voltage_level = Decimal(str(round(voltage_level, 2)))

            # Получаем длину линии из атрибута length
            try:
                length = pf_line.GetAttribute("length")
                if length is not None:
                    self.length = Decimal(
                        str(round(length, 2))
                    )  # Округляем до 2 знаков после запятой
            except Exception as e:
                print(f"Не удалось получить длину для ЛЭП {self.dispatch_name}: {e}")

            self.save()
        except Exception as e:
            # Логируем ошибку, но не прерываем выполнение
            print(
                f"Ошибка при получении данных из PowerFactory для ЛЭП {self.dispatch_name}: {e}"
            )

    def update_branches_from_pf(self, app) -> None:
        """
        Определяет подстанции ответвлений и создает/обновляет записи LineBranch.

        Логика определения:
        - Получает все подстанции на концах ЛЭП (_get_line_end_substations)
        - Получает основные подстанции (_get_main_substations_with_voltage)
        - Подстанции ответвлений = все подстанции - основные подстанции

        Args:
            app: COM-объект PowerFactory
        """
        if not self.pf_name:
            print(f"Для ЛЭП {self.dispatch_name} не указано pf_name")
            return

        try:
            from calculation.services.powerfactory_locator import (
                _get_line_end_substations,
                _get_main_substations_with_voltage,
            )

            # Получаем объект ЛЭП из PowerFactory по имени
            pf_lines = app.GetCalcRelevantObjects("*.ElmBranch")
            pf_line = None
            for line in pf_lines:
                if line.GetAttribute("loc_name") == self.pf_name:
                    pf_line = line
                    break

            if not pf_line:
                print(f"ЛЭП '{self.pf_name}' не найдена в PowerFactory")
                return

            # Получаем все подстанции на концах ЛЭП
            all_substations = _get_line_end_substations(pf_line, app)
            # Получаем основные подстанции
            main_substations = _get_main_substations_with_voltage(pf_line, app)

            # Создаем множества для сравнения (по имени и напряжению)
            main_substations_set = {
                (sub["name"], sub["voltage_kv"]) for sub in main_substations
            }
            all_substations_set = {
                (sub["name"], sub["voltage_kv"]) for sub in all_substations
            }

            # Подстанции ответвлений = все подстанции - основные подстанции
            branch_substations_keys = all_substations_set - main_substations_set

            # Создаем или обновляем записи LineBranch для каждой подстанции ответвления
            for sub in all_substations:
                key = (sub["name"], sub["voltage_kv"])
                if key in branch_substations_keys:
                    substation_name = sub["name"]

                    # Находим или создаем подстанцию в БД
                    substation, _ = Substation.objects.get_or_create(
                        pf_name=substation_name
                    )

                    # Создаем или обновляем ответвление
                    line_branch, created = LineBranch.objects.get_or_create(
                        line=self,
                        substation=substation,
                        defaults={
                            "pf_name_substation": substation_name,
                            "is_active": True,
                        },
                    )

                    # Обновляем имя подстанции, если оно изменилось
                    if line_branch.pf_name_substation != substation_name:
                        line_branch.pf_name_substation = substation_name
                        line_branch.save()

                    if created:
                        print(
                            f"Создано ответвление для ЛЭП {self.dispatch_name}: {substation_name}"
                        )
                    else:
                        print(
                            f"Обновлено ответвление для ЛЭП {self.dispatch_name}: {substation_name}"
                        )

        except Exception as e:
            print(
                f"Ошибка при определении ответвлений для ЛЭП {self.dispatch_name}: {e}"
            )

    def __str__(self):
        """
        :return: Диспетчерское наименование ЛЭП.
        """

        return self.dispatch_name


class LineBranch(models.Model):
    """Модель ответвления ЛЭП."""

    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="branches",
        verbose_name="Основная ЛЭП",
    )
    pf_name_line = models.CharField(
        verbose_name="Имя ЛЭП в PowerFactory",
        max_length=100,
        null=True,
        blank=True,
        help_text="Имя линии из PowerFactory (копия line.pf_name для удобства поиска)",
    )
    substation = models.ForeignKey(
        "Substation",
        on_delete=models.CASCADE,
        related_name="line_branches",
        verbose_name="Подстанция",
        null=True,  # Сделать опциональным
        blank=True,  # Сделать опциональным
    )
    pf_name_substation = models.CharField(
        verbose_name="Подстанция ответвления",
        max_length=100,
        null=True,
        blank=True,
        default="",
        help_text="Имя подстанции ответвления из PowerFactory",
    )
    is_active = models.BooleanField(verbose_name="Активно ли ответвление", default=True)
    protection_recommendation = models.TextField(
        verbose_name="Рекомендация по установке доп. комплекта защиты на ответвлении",
        null=True,
        blank=True,
        default="Нет необходимости",
    )

    class Meta:
        """Мета-данные модели LineBranch."""

        verbose_name = "Ответвление ЛЭП"
        verbose_name_plural = "Ответвления ЛЭП"

    def __str__(self):
        """
        :return: Имя подстанции ответвления.
        """
        # Используем наименование подстанции из PowerFactory, если есть связь
        if self.substation:
            return str(self.substation)
        # Иначе используем имя из PowerFactory
        return self.pf_name_substation or "Ответвление без подстанции"


class Substation(models.Model):
    """Модель подстанции."""

    pf_name = models.CharField(
        verbose_name="Наименование в PowerFactory",
        max_length=100,
        null=True,
        blank=True,
        default="",
        help_text="Имя подстанции из PowerFactory",
    )
    project_name = models.CharField(
        verbose_name="Имя проекта PowerFactory",
        max_length=200,
        blank=True,
        null=True,
        help_text="Имя проекта PowerFactory, из которого импортирована подстанция",
    )

    class Meta:
        """Мета-данные модели Substation."""

        verbose_name = "Подстанция"
        verbose_name_plural = "Подстанции"
        unique_together = [("pf_name", "project_name")]

    def __str__(self):
        """
        :return: Наименование подстанции в PowerFactory.
        """
        return self.pf_name or f"Подстанция #{self.id}"


class Component(models.Model):
    """Модель органа защиты для реализации функции ДФЗ."""

    name = models.CharField(
        verbose_name="Название органа",
        max_length=100,
        unique=True,
        blank=True,  # Временно разрешаем пустое значение для миграции
        null=True,  # Временно разрешаем NULL для миграции
        help_text="Будет заполнено автоматически на основе setting_designation",
    )
    description = models.TextField(
        verbose_name="Описание работы органа",
        blank=True,  # Временно разрешаем пустое значение для миграции
        default="",  # Значение по умолчанию для существующих записей
    )
    setting_designation = models.CharField(
        verbose_name="Обозначение органа ДФЗ", max_length=100, unique=True
    )
    is_active = models.BooleanField(
        verbose_name="Статус активации органа", default=True
    )

    class Meta:
        """Мета-данные модели Component."""

        verbose_name = "Орган ДФЗ"
        verbose_name_plural = "Органы ДФЗ"

    def __str__(self):
        """
        :return: Обозначение параметра настройки органа.
        """

        return self.setting_designation


class ProtectionComponentCoefficient(models.Model):
    """Модель коэффициента органа защиты."""

    component = models.ForeignKey(
        Component,
        on_delete=models.CASCADE,
        related_name="coefficients",
        verbose_name="Орган ДФЗ",
    )
    coefficient_type = models.ForeignKey(
        CoefficientType,
        on_delete=models.CASCADE,
        related_name="component_coefficients",
        verbose_name="Тип коэффициента",
    )
    default_value = models.FloatField(verbose_name="Значение по умолчанию")
    min_value = models.FloatField(
        verbose_name="Минимальное значение", null=True, blank=True
    )
    max_value = models.FloatField(
        verbose_name="Максимальное значение", null=True, blank=True
    )

    class Meta:
        """Мета-данные модели ProtectionComponentCoefficient."""

        verbose_name = "Коэффициент органа защиты"
        verbose_name_plural = "Коэффициенты органов защиты"
        unique_together = (
            ("component", "coefficient_type"),
        )  # Предотвращает дублирование

    def __str__(self):
        """
        :return: Название коэффициента для органа.
        """
        return f"{self.component.setting_designation} - {self.coefficient_type.name}"


class ProtectionDevice(models.Model):
    """Модель устройства РЗА с функцией ДФЗ."""

    device_model = models.CharField(
        verbose_name="Модель устройства", max_length=100, unique=True
    )
    manufacturer_fk = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="protection_devices",
        verbose_name="Производитель",
        null=True,  # Временно nullable для миграции
        blank=True,
    )
    methodology = models.ForeignKey(
        MethodologyDocument,
        on_delete=models.SET_NULL,
        related_name="protection_devices",
        verbose_name="Методика расчета для устройства",
        null=True,
        blank=True,
        help_text="Основная методика расчета для данной модели устройства",
    )
    components = models.ManyToManyField(
        Component, verbose_name="Органы ДФЗ", related_name="protection_devices"
    )

    class Meta:
        """Мета-данные модели ProtectionDevice."""

        verbose_name = "Устройство РЗА"
        verbose_name_plural = "Устройства РЗА"

    def __str__(self):
        """
        :return: Модель устройства РЗА
        """

        return self.device_model

    def get_methodology_by_voltage(self, voltage_level):
        """
        Возвращает методику расчета в зависимости от напряжения ЛЭП.
        Ищет методику по напряжению среди всех доступных методик.

        Args:
            voltage_level: Напряжение ЛЭП в кВ (Decimal или float)

        Returns:
            MethodologyDocument или None
        """
        if voltage_level is None:
            return self.methodology

        # Преобразуем в float для сравнения
        voltage = float(voltage_level)

        # Получаем название производителя для уточнения поиска
        manufacturer_name = None
        if self.manufacturer_fk:
            manufacturer_name = self.manufacturer_fk.name

        # Если напряжение >= 330 кВ, ищем методику для 330 и выше
        if voltage >= 330:
            # Ищем методику с "330" в имени файла
            # Если есть производитель, ищем среди методик с его названием в пути
            if manufacturer_name:
                methodology_330 = MethodologyDocument.objects.filter(
                    Q(name_file__icontains="330")
                    & Q(name_file__icontains=manufacturer_name)
                ).first()
                if methodology_330:
                    return methodology_330

            # Если не найдено с производителем, ищем любую методику для 330
            methodology_330 = MethodologyDocument.objects.filter(
                name_file__icontains="330"
            ).first()
            if methodology_330:
                return methodology_330

        # Если напряжение < 330 кВ, ищем методику для 110-220
        elif voltage >= 110:
            # Ищем методику с "110-220" в имени файла
            # Если есть производитель, ищем среди методик с его названием в пути
            if manufacturer_name:
                methodology_110_220 = MethodologyDocument.objects.filter(
                    Q(name_file__icontains="110-220")
                    & Q(name_file__icontains=manufacturer_name)
                ).first()
                if methodology_110_220:
                    return methodology_110_220

            # Если не найдено с производителем, ищем любую методику для 110-220
            methodology_110_220 = MethodologyDocument.objects.filter(
                name_file__icontains="110-220"
            ).first()
            if methodology_110_220:
                return methodology_110_220

        # Если не найдено, возвращаем основную методику
        return self.methodology


class ProtectionHalfSet(models.Model):
    """Модель полукомплекта ДФЗ."""

    line = models.ForeignKey(
        Line, on_delete=models.CASCADE, related_name="protection_half_sets"
    )
    substation = models.ForeignKey(
        Substation, on_delete=models.CASCADE, related_name="protection_half_sets"
    )
    protection_device = models.ForeignKey(
        ProtectionDevice, on_delete=models.CASCADE, related_name="protection_half_sets"
    )

    class Meta:
        """Мета-данные модели ProtectionHalfSet."""

        unique_together = (("line", "substation"),)
        verbose_name = "Полукомплект ДФЗ"
        verbose_name_plural = "Полукомплекты ДФЗ"

    def __str__(self):
        """
        :return: Наименование подстанции полукомплекта ДФЗ.
        """
        return str(self.substation) if self.substation else f"Полукомплект #{self.id}"


class HalfSetTopology(models.Model):
    """Модель для хранения топологии полукомплекта защиты."""

    protection_half_set = models.OneToOneField(
        ProtectionHalfSet,
        on_delete=models.CASCADE,
        related_name="topology",
        verbose_name="Полукомплект защиты",
    )

    # JSON поле для хранения топологии
    topology_data = models.JSONField(
        verbose_name="Данные топологии",
        help_text="Список элементов топологии (ЛЭП и АТ) в формате JSON",
    )

    # Метаданные для контроля актуальности
    voltage_level = models.DecimalField(
        verbose_name="Класс напряжения, кВ",
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )

    last_updated = models.DateTimeField(
        verbose_name="Дата последнего обновления",
        auto_now=True,
    )

    # Хэш для быстрой проверки изменений
    topology_hash = models.CharField(
        max_length=64,
        verbose_name="Хэш топологии",
        help_text="MD5 хэш для быстрой проверки изменений",
        null=True,
        blank=True,
    )

    class Meta:
        """Мета-данные модели HalfSetTopology."""

        verbose_name = "Топология полукомплекта"
        verbose_name_plural = "Топологии полукомплектов"

    def __str__(self):
        return f"Топология {self.protection_half_set}"
