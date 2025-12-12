from django.contrib.auth.models import User  # type: ignore
from django.db import models  # type: ignore
from django.db.models.signals import pre_save  # type: ignore
from django.dispatch import receiver  # type: ignore

from core.models import Component, Line, ProtectionHalfSet


class CalculationMeta(models.Model):
    """Модель мета-данных расчета."""

    line = models.ForeignKey(
        Line,
        on_delete=models.CASCADE,
        related_name="calculations",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,  # Временно nullable для миграции
    )
    calculation_number = models.PositiveIntegerField(
        verbose_name="Номер расчета", null=True, blank=True
    )
    calculation_date = models.DateTimeField(
        verbose_name="Дата расчета", auto_now_add=True
    )

    class Meta:
        """Мета-данные модели CalculationMeta."""

        verbose_name = "Мета-данные расчета"
        verbose_name_plural = "Мета-данные расчетов"

    def __str__(self):
        """
        :return: Номер расчета.
        """

        return f"Расчет параметров настройки ДФЗ {self.line} от {self.calculation_date}"


class SettingsCalculation(models.Model):
    """Модель протокола расчета параметра настройки органа."""

    calculation_meta = models.ForeignKey(
        CalculationMeta, on_delete=models.CASCADE, related_name="settings_calculations"
    )
    protection_half_set = models.ForeignKey(
        ProtectionHalfSet,
        on_delete=models.CASCADE,
        related_name="settings_calculations",
    )
    component = models.ForeignKey(
        Component, on_delete=models.CASCADE, related_name="settings_calculations"
    )
    calculation_factors = models.JSONField(blank=True, null=True)
    result_value = models.FloatField(
        verbose_name="Результат расчета",
        null=True,  # Временно nullable для обратной совместимости
        blank=True,
    )
    primary_value = models.FloatField(
        verbose_name="Значение уставки в первичных величинах",
        null=True,  # Временно nullable для миграции
        blank=True,
    )
    secondary_value = models.FloatField(
        verbose_name="Значение уставки во вторичных величинах",
        null=True,  # Временно nullable для миграции
        blank=True,
    )

    class Meta:
        """Мета-данные модели CalculationData."""

        verbose_name = "Протокол расчета"
        verbose_name_plural = "Протоколы расчетов"


class FaultCalculation(models.Model):
    """Модель протокола расчета токов КЗ."""

    calculation_meta = models.ForeignKey(
        CalculationMeta, on_delete=models.CASCADE, blank=True, null=True
    )
    protection_half_set = models.ForeignKey(
        ProtectionHalfSet, on_delete=models.CASCADE, related_name="fault_calculations"
    )
    fault_type = models.CharField(verbose_name="Вид КЗ", max_length=255)
    fault_location = models.CharField(verbose_name="Узел КЗ", max_length=255)
    network_topology = models.CharField(verbose_name="Схема сети", max_length=255)
    fault_values = models.JSONField()

    class Meta:
        """Мета-данные модели FaultCalculation."""

        verbose_name = "Расчет токов КЗ"
        verbose_name_plural = "Протоколы расчетов токов КЗ"


class SensitivityAnalysis(models.Model):
    """Модель анализа чувствительности."""

    STATUS_CHOICES = [
        ("Нечувствительна", "Нечувствительна"),
        ("Низкая чувствительность", "Низкая чувствительность"),
        ("Чувствительность", "Чувствительность"),
    ]

    settings_calculation = models.ForeignKey(
        SettingsCalculation,
        on_delete=models.CASCADE,
        related_name="sensitivity_analysis",
    )
    fault_calculation = models.ForeignKey(
        FaultCalculation, on_delete=models.CASCADE, related_name="sensitivity_analysis"
    )
    sensitivity_rate = models.FloatField(verbose_name="Коэффициент чувствительности")
    status = models.CharField(
        verbose_name="Статус",
        max_length=255,
        choices=STATUS_CHOICES,
        default="Нечувствительна",
    )

    def save(self, *args, **kwargs):
        if self.sensitivity_rate <= 1:
            self.status = "Нечувствительна"
        elif 1 < self.sensitivity_rate < 2:
            self.status = "Низкая чувствительность"
        else:
            self.status = "Чувствительна"
        super().save(*args, **kwargs)

    class Meta:
        """Мета-данные модели SensitivityAnalysis."""

        verbose_name = "Анализ чувствительности"
        verbose_name_plural = "Анализ чувствительности"


@receiver(pre_save, sender=CalculationMeta)
def generate_calculation_number(sender, instance, **kwargs):
    """Генерация номера расчета перед сохранением."""

    if not instance.calculation_number:
        last_calculation = (
            CalculationMeta.objects.all().order_by("calculation_number").last()
        )
        if last_calculation:
            instance.calculation_number = last_calculation.calculation_number + 1
        else:
            instance.calculation_number = 1
