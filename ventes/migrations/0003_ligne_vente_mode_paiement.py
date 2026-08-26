from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventes", "0002_cloturecaisse"),
    ]

    operations = [
        migrations.AddField(
            model_name="lignevente",
            name="mode_paiement",
            field=models.CharField(
                choices=[
                    ("ESPECES", "Espèces"),
                    ("MOBILE_MONEY", "Mobile money"),
                    ("AUTRE", "Autre"),
                ],
                default="ESPECES",
                max_length=20,
                help_text="Mode de paiement choisi pour cette ligne spécifiquement.",
            ),
        ),
    ]
