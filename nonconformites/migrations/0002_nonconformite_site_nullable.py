from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("nonconformites", "0001_initial"),
        ("core", "0010_notification_groupe"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nonconformite",
            name="site",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="non_conformites",
                to="core.site",
            ),
        ),
    ]
