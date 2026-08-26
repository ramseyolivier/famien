"""
Étape 3/3 — Suppression du modèle Zone (DDL pure, sans DML).

Les données ont été migrées en 0004. On peut maintenant supprimer les colonnes
zone_id de Site et Utilisateur, puis supprimer la table Zone.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_migrer_zones_data"),
    ]

    operations = [
        migrations.RemoveField(model_name="site", name="zone"),
        migrations.RemoveField(model_name="utilisateur", name="zone"),
        migrations.DeleteModel(name="Zone"),
    ]
