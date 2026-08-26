"""
Étape 1/3 — Ajout de la FK commune sur Utilisateur.

Séparé de la migration de données (0004) et de la suppression de Zone (0005)
pour éviter l'erreur PostgreSQL « pending trigger events » qui survient quand
on mélange UPDATE et ALTER TABLE sur la même table dans la même transaction.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_add_commune"),
    ]

    operations = [
        migrations.AddField(
            model_name="utilisateur",
            name="commune",
            field=models.ForeignKey(
                blank=True,
                help_text="Commune de supervision (superviseur de zone).",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="utilisateurs",
                to="core.commune",
            ),
        ),
    ]
