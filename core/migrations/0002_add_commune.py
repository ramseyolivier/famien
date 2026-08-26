import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Commune",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nom", models.CharField(max_length=100, unique=True)),
            ],
            options={
                "verbose_name": "commune",
                "ordering": ["nom"],
            },
        ),
        migrations.AddField(
            model_name="site",
            name="commune",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sites",
                to="core.commune",
            ),
        ),
    ]
