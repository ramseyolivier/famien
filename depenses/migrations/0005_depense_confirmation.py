# Generated manually 2026-08-15 — ajout statut CONFIRME et champs de confirmation

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('depenses', '0004_depense_site_nullable'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Élargissement du max_length pour accueillir "CONFIRME" (7 chars vs "BROUILLON" 9 — déjà bon)
        migrations.AlterField(
            model_name='depense',
            name='statut',
            field=models.CharField(
                choices=[
                    ('BROUILLON', 'Brouillon'),
                    ('SOUMIS', 'Soumis'),
                    ('VALIDE', 'Validé'),
                    ('CONFIRME', 'Confirmé'),
                    ('REJETE', 'Rejeté'),
                ],
                default='BROUILLON',
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='depense',
            name='montant_confirme',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='depense',
            name='confirme_par',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='depenses_confirmees',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='depense',
            name='confirme_le',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
