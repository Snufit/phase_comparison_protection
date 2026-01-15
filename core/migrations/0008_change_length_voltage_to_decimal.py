# Generated manually to convert FloatField to DecimalField

from decimal import Decimal

from django.db import migrations, models


def convert_float_to_decimal(apps, schema_editor):
    """Конвертирует float значения в Decimal с округлением до 2 знаков."""
    Line = apps.get_model("core", "Line")
    for line in Line.objects.all():
        if line.length is not None:
            line.length = Decimal(str(round(float(line.length), 2)))
        if line.voltage_level is not None:
            line.voltage_level = Decimal(str(round(float(line.voltage_level), 2)))
        line.save(update_fields=["length", "voltage_level"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0007_line_index_pf"),
    ]

    operations = [
        # Сначала конвертируем данные
        migrations.RunPython(convert_float_to_decimal, migrations.RunPython.noop),
        # Затем изменяем тип полей
        migrations.AlterField(
            model_name="line",
            name="length",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
                verbose_name="Длина ЛЭП, км",
            ),
        ),
        migrations.AlterField(
            model_name="line",
            name="voltage_level",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=7,
                verbose_name="Номинальное напряжение ЛЭП, кВ",
                help_text="Номинальное напряжение ЛЭП, получаемое из PowerFactory",
            ),
        ),
    ]
