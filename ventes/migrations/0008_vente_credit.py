from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("ventes", "0007_montant_recu"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="vente",
            name="a_credit",
            field=models.BooleanField(default=False, help_text="Le stock est sorti mais le client n'a pas encore payé."),
        ),
        migrations.AddField(
            model_name="vente",
            name="client_nom",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="vente",
            name="client_prenom",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.CreateModel(
            name="PaiementCredit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("montant", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
                ("date", models.DateField()),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("cree_le", models.DateTimeField(auto_now_add=True)),
                ("auteur", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="paiements_credit_saisis", to=settings.AUTH_USER_MODEL)),
                ("vente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="paiements_credit", to="ventes.vente")),
            ],
            options={"verbose_name": "paiement crédit", "ordering": ["date", "cree_le"]},
        ),
    ]
