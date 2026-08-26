"""
Migration de Kit.niveau → Kit.classe (ClasseEcole).
Les kits existants obtiennent automatiquement une ClasseEcole dont le libellé
est l'ancien intitulé du niveau (ex : "6ème", "3ème"…).
"""

from django.db import migrations, models
import django.db.models.deletion


# Mapping niveau code → libellé (copie de Niveau.choices pour la migration)
_NIVEAU_LABELS = {
    "6E": "6ème", "5E": "5ème", "4E": "4ème", "3E": "3ème",
    "2NDA": "2nde A", "2NDC": "2nde C",
    "1REA": "1ère A", "1REC": "1ère C", "1RED": "1ère D",
    "TLEA": "Terminale A", "TLEC": "Terminale C", "TLED": "Terminale D",
}


def creer_classes_depuis_niveaux(apps, schema_editor):
    """Crée une ClasseEcole par couple (ecole, niveau) existant et rattache les kits."""
    Kit = apps.get_model("kits", "Kit")
    ClasseEcole = apps.get_model("kits", "ClasseEcole")

    classes_cache = {}
    for kit in Kit.objects.select_related("ecole").all():
        key = (kit.ecole_id, kit.niveau)
        if key not in classes_cache:
            libelle = _NIVEAU_LABELS.get(kit.niveau, kit.niveau)
            classe, _ = ClasseEcole.objects.get_or_create(
                ecole_id=kit.ecole_id,
                libelle=libelle,
                defaults={"niveau": kit.niveau},
            )
            classes_cache[key] = classe
        Kit.objects.filter(pk=kit.pk).update(classe=classes_cache[key])


class Migration(migrations.Migration):

    dependencies = [
        ("kits", "0001_initial"),
    ]

    operations = [
        # 1. Créer ClasseEcole
        migrations.CreateModel(
            name="ClasseEcole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("niveau", models.CharField(
                    choices=[
                        ("6E", "6ème"), ("5E", "5ème"), ("4E", "4ème"), ("3E", "3ème"),
                        ("2NDA", "2nde A"), ("2NDC", "2nde C"),
                        ("1REA", "1ère A"), ("1REC", "1ère C"), ("1RED", "1ère D"),
                        ("TLEA", "Terminale A"), ("TLEC", "Terminale C"), ("TLED", "Terminale D"),
                    ],
                    max_length=6,
                )),
                ("libelle", models.CharField(
                    help_text="Intitulé exact de la classe (ex : 3ème A, 4ème Allemand, 3ème B…)",
                    max_length=100,
                )),
                ("ecole", models.ForeignKey(
                    limit_choices_to={"type": "ECOLE"},
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="classes",
                    to="core.site",
                )),
            ],
            options={
                "verbose_name": "classe",
                "verbose_name_plural": "classes",
                "ordering": ["ecole__nom", "niveau", "libelle"],
            },
        ),
        migrations.AddConstraint(
            model_name="classeecole",
            constraint=models.UniqueConstraint(
                fields=["ecole", "libelle"],
                name="une_classe_par_ecole_et_libelle",
            ),
        ),

        # 2. Ajouter Kit.classe (nullable d'abord pour la migration de données)
        migrations.AddField(
            model_name="kit",
            name="classe",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="kits",
                to="kits.classeecole",
            ),
        ),

        # 3. Migration de données : créer les ClasseEcole et les rattacher aux kits
        migrations.RunPython(creer_classes_depuis_niveaux, migrations.RunPython.noop),

        # 4. Rendre Kit.classe obligatoire
        migrations.AlterField(
            model_name="kit",
            name="classe",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="kits",
                to="kits.classeecole",
            ),
        ),

        # 5. Supprimer les anciennes contraintes qui référencent niveau
        migrations.RemoveConstraint(model_name="kit", name="une_version_par_ecole_et_niveau"),
        migrations.RemoveConstraint(model_name="kit", name="un_seul_kit_actif_par_ecole_et_niveau"),

        # 6. Supprimer Kit.niveau
        migrations.RemoveField(model_name="kit", name="niveau"),

        # 7. Ajouter les nouvelles contraintes basées sur classe
        migrations.AddConstraint(
            model_name="kit",
            constraint=models.UniqueConstraint(
                fields=["classe", "version"],
                name="une_version_par_classe",
            ),
        ),
        migrations.AddConstraint(
            model_name="kit",
            constraint=models.UniqueConstraint(
                fields=["classe"],
                condition=models.Q(actif=True),
                name="un_seul_kit_actif_par_classe",
            ),
        ),

        # 8. Mettre à jour le tri
        migrations.AlterModelOptions(
            name="kit",
            options={
                "ordering": ["ecole__nom", "classe__libelle", "-version"],
                "verbose_name": "kit scolaire",
            },
        ),
    ]
