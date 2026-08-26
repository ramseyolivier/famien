"""
Migration : remplacement de Categorie (TextChoices) par CategorieProduit (modèle).

Les trois catégories existantes sont créées automatiquement. Chaque produit
est mis à jour pour pointer vers la bonne CategorieProduit via son ancien code.
"""

import django.db.models.deletion
from django.db import migrations, models

CATEGORIES_INITIALES = [
    ("CAHIER", "Cahier"),
    ("PETIT_MATERIEL", "Petit matériel"),
    ("LIVRE", "Livre au programme"),
]


def creer_categories(apps, schema_editor):
    CategorieProduit = apps.get_model("catalogue", "CategorieProduit")
    Produit = apps.get_model("catalogue", "Produit")

    for code, nom in CATEGORIES_INITIALES:
        cat = CategorieProduit.objects.create(nom=nom)
        Produit.objects.filter(ancienne_categorie=code).update(categorie=cat)


class Migration(migrations.Migration):

    dependencies = [
        ("catalogue", "0001_initial"),
    ]

    operations = [
        # Créer le nouveau modèle
        migrations.CreateModel(
            name="CategorieProduit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nom", models.CharField(max_length=100, unique=True)),
            ],
            options={
                "verbose_name": "catégorie",
                "ordering": ["nom"],
            },
        ),
        # Renommer l'ancien champ pour libérer le nom "categorie"
        migrations.RenameField(
            model_name="produit",
            old_name="categorie",
            new_name="ancienne_categorie",
        ),
        # Ajouter la nouvelle FK nullable
        migrations.AddField(
            model_name="produit",
            name="categorie",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="produits",
                to="catalogue.categorieproduit",
            ),
        ),
        # Migrer les données
        migrations.RunPython(creer_categories, reverse_code=migrations.RunPython.noop),
        # Supprimer l'ancien champ
        migrations.RemoveField(model_name="produit", name="ancienne_categorie"),
    ]
