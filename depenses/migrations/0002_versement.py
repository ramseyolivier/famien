from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("depenses", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Versement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("montant", models.DecimalField(decimal_places=2, max_digits=14, validators=[django.core.validators.MinValueValidator(1)])),
                ("date", models.DateField()),
                ("mode", models.CharField(choices=[("ESPECES", "Espèces"), ("MOBILE_MONEY", "Mobile money")], max_length=15)),
                ("reference", models.CharField(blank=True, help_text="Numéro de transaction mobile money ou référence.", max_length=200)),
                ("note", models.TextField(blank=True)),
                ("statut", models.CharField(choices=[("EN_ATTENTE", "En attente"), ("CONFIRME", "Confirmé"), ("REJETE", "Rejeté")], default="EN_ATTENTE", max_length=12)),
                ("cree_le", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("traite_le", models.DateTimeField(blank=True, null=True)),
                ("motif_rejet", models.CharField(blank=True, max_length=500)),
                ("verseur", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versements_effectues", to=settings.AUTH_USER_MODEL)),
                ("destinataire", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versements_recus", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "versement", "ordering": ["-cree_le"]},
        ),
    ]
