from django.db import models


class Line(models.Model):
    """
    Модель линии электропередач (ЛЭП).

    ЛЭП напряжением 110 кВ и выше с двусторонним питанием без ответвлений.
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
    current_capacity = models.FloatField(verbose_name="ДДТН, А", default=2000)
    length = models.FloatField(
        verbose_name="Длина ЛЭП, км", blank=True, null=True
    )
    voltage_transformer_ratio = models.FloatField(
        verbose_name='Коэффициент трансформации ТН',
        default=5000,
        blank=True,
        null=True
    )

    class Meta:
        """Мета-данные модели Line."""

        verbose_name = "ЛЭП"
        verbose_name_plural = "ЛЭП"

    def __str__(self):
        """
        :return: Диспетчерское наименование ЛЭП.
        """

        return self.dispatch_name


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

    description = models.TextField(
        verbose_name="Описание работы органа", blank=True, null=True
    )
    setting_designation = models.CharField(
        verbose_name="Обозначение параметра настройки", max_length=100, unique=True
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


class ProtectionDevice(models.Model):
    """Модель устройства РЗА с функцией ДФЗ."""

    device_model = models.CharField(
        verbose_name="Модель устройства", max_length=100, unique=True
    )
    manufacturer = models.CharField(verbose_name="Производитель", max_length=100)
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
