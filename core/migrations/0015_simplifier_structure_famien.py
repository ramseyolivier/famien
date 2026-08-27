"""
Simplification de la structure pour FAMIEN :
- Suppression du modèle Commune
- Suppression du champ magasin_rattachement sur Site
- Suppression du champ commune sur Site et Utilisateur
- Conversion de tous les types de site en SITE
- Conversion des profils obsolètes (COMMERCIAL→CHEF_EQUIPE, autres→DG)
"""

from django.db import migrations, models


def migrer_types_sites(apps, schema_editor):
    Site = apps.get_model("core", "Site")
    Site.objects.all().update(type="SITE")


def migrer_profils(apps, schema_editor):
    Utilisateur = apps.get_model("core", "Utilisateur")
    Utilisateur.objects.filter(profil="COMMERCIAL").update(profil="CHEF_EQUIPE")
    Utilisateur.objects.filter(profil__in=["MANAGER", "SUPERVISEUR", "GEST_MAGASIN"]).update(profil="DG")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_numero_local"),
    ]

    operations = [
        # 1. Migration des données avant de toucher aux colonnes
        migrations.RunPython(migrer_types_sites, migrations.RunPython.noop),
        migrations.RunPython(migrer_profils, migrations.RunPython.noop),

        # 2. Supprimer les contraintes qui référencent les anciens champs
        migrations.RemoveConstraint(
            model_name="site",
            name="seule_une_ecole_a_un_magasin_de_rattachement",
        ),
        migrations.RemoveConstraint(
            model_name="site",
            name="site_nom_unique_par_type",
        ),

        # 3. Supprimer les champs obsolètes sur Site
        migrations.RemoveField(model_name="site", name="magasin_rattachement"),
        migrations.RemoveField(model_name="site", name="commune"),

        # 4. Rendre nom unique sur Site (remplace l'ancienne contrainte composite)
        migrations.AlterField(
            model_name="site",
            name="nom",
            field=models.CharField(max_length=150, unique=True),
        ),

        # 5. Supprimer le champ commune sur Utilisateur
        migrations.RemoveField(model_name="utilisateur", name="commune"),

        # 6. Supprimer le modèle Commune
        migrations.DeleteModel(name="Commune"),
    ]
