from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calculation", "0012_alter_sensitivityanalysis_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="sensitivityanalysis",
            name="details",
            field=models.JSONField(
                blank=True,
                help_text="Дополнительные вычисленные величины для интерпретации результата (например, 3U0_эфф для РННП).",
                null=True,
                verbose_name="Детали расчета",
            ),
        ),
    ]

