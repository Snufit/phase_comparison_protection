from django.db import models


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

    methodology_url = models.CharField(
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
        :return: URL документа методики.
        """
        return self.methodology_url


class Manufacturer(models.Model):
    """Модель производителя устройства РЗА."""

    name = models.CharField(
        verbose_name="Название производителя", max_length=150, unique=True
    )
    methodology = models.ForeignKey(
        MethodologyDocument,
        on_delete=models.SET_NULL,  # Если методика удаляется, то у производителя не проставляется методика
        related_name="manufacturers",
        null=True,
        blank=True,
        verbose_name="Методика производителя",
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
        return (
            f"{self.model_ct_pf_name} ({self.primary_current}/{self.secondary_current})"
        )

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
        connection_display = dict(self.CONNECTION_CHOICES).get(self.connection_type, "")
        type_display = dict(self.TYPE_CHOICES).get(self.type, "")
        return f"{self.model_vt_pf_name} ({self.primary_voltage} кВ, {connection_display}, {type_display})"

    def calculate_ratio(self, line_voltage_kv: float = None) -> float:
        """
        Вычисляет коэффициент трансформации ТН.

        Args:
            line_voltage_kv: Напряжение ЛЭП в кВ. Если не указано, используется primary_voltage.

        Returns:
            float: Коэффициент трансформации ТН
        """
        import math

        # Используем напряжение ЛЭП, если указано, иначе primary_voltage ТН
        u_nom = line_voltage_kv if line_voltage_kv is not None else self.primary_voltage
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
        verbose_name="Диспетчерское наименование", max_length=100, unique=True
    )
    pf_name = models.CharField(
        verbose_name="Наименование в PowerFactory",
        max_length=100,
        blank=True,
        null=True,
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
    length = models.FloatField(
        verbose_name="Длина ЛЭП, км",
        default=0.0,  # Значение по умолчанию для существующих записей
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
    voltage_level = models.FloatField(
        verbose_name="Номинальное напряжение ЛЭП, кВ",
        default=220.0,
        help_text="Номинальное напряжение ЛЭП, получаемое из PowerFactory",
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

    class Meta:
        """Мета-данные модели Line."""

        verbose_name = "ЛЭП"
        verbose_name_plural = "ЛЭП"

    def update_voltage_from_pf(self, app) -> None:
        """
        Получает напряжение ЛЭП из PowerFactory и сохраняет в БД.

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
                self.voltage_level = voltage_level
                self.save()
        except Exception as e:
            # Логируем ошибку, но не прерываем выполнение
            print(
                f"Ошибка при получении напряжения из PowerFactory для ЛЭП {self.dispatch_name}: {e}"
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
    substation = models.ForeignKey(
        "Substation",
        on_delete=models.CASCADE,
        related_name="line_branches",
        verbose_name="Подстанция",
    )
    dispatch_name = models.CharField(
        verbose_name="Диспетчерское наименование ответвления",
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )
    pf_name = models.CharField(
        verbose_name="Наименование в PowerFactory", max_length=100, unique=True
    )
    length = models.FloatField(verbose_name="Длина ответвления, км")
    is_active = models.BooleanField(verbose_name="Активно ли ответвление", default=True)
    protection_recommendation = models.TextField(
        verbose_name="Рекомендация по установке доп. комплекта защиты на ответвлении",
        null=True,
        blank=True,
    )

    class Meta:
        """Мета-данные модели LineBranch."""

        verbose_name = "Ответвление ЛЭП"
        verbose_name_plural = "Ответвления ЛЭП"

    def __str__(self):
        """
        :return: Диспетчерское наименование ответвления или pf_name.
        """
        return self.dispatch_name or self.pf_name


class Substation(models.Model):
    """Модель подстанции."""

    dispatch_name = models.CharField(
        verbose_name="Диспетчерское наименование", max_length=100, unique=True
    )
    pf_name = models.CharField(
        verbose_name="Наименование в PowerFactory",
        max_length=100,
        blank=True,
        null=True,
    )

    class Meta:
        """Мета-данные модели Substation."""

        verbose_name = "Подстанция"
        verbose_name_plural = "Подстанции"

    def __str__(self):
        """
        :return: Диспетчерское наименование подстанции.
        """

        return self.dispatch_name


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
    manufacturer = models.CharField(
        verbose_name="Производитель (старое поле)",
        max_length=100,
        blank=True,
        null=True,
    )
    manufacturer_fk = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="protection_devices",
        verbose_name="Производитель",
        null=True,  # Временно nullable для миграции
        blank=True,
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
        :return: Диспетчерское наименование полукомплекта ДФЗ.
        """

        return self.substation.dispatch_name
