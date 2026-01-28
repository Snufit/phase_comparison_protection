# Generated manually
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_add_project_name_to_models'),
    ]

    operations = [
        migrations.AlterField(
            model_name='line',
            name='dispatch_name',
            field=models.CharField(max_length=300, verbose_name='Диспетчерское наименование'),
        ),
    ]
