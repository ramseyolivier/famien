"""
Étape 2/3 — Migration des données Zone → Commune.

Copie le nom de chaque Zone vers une Commune homonyme, puis met à jour
les FK de Site et Utilisateur. Séparé de la DDL (0005) pour ne pas mélanger
DML et ALTER TABLE dans la même transaction PostgreSQL.
"""

from django.db import migrations


def migrer_zone_vers_commune(apps, schema_editor):
    Zone = apps.get_model("core", "Zone")
    Commune = apps.get_model("core", "Commune")
    Site = apps.get_model("core", "Site")
    Utilisateur = apps.get_model("core", "Utilisateur")

    for zone in Zone.objects.all():
        commune, _ = Commune.objects.get_or_create(nom=zone.nom)
        Site.objects.filter(zone_id=zone.pk, commune__isnull=True).update(commune=commune)

    for u in Utilisateur.objects.filter(zone__isnull=False):
        commune, _ = Commune.objects.get_or_create(nom=u.zone.nom)
        u.commune_id = commune.pk
        u.save(update_fields=["commune_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_zone_vers_commune"),
    ]

    operations = [
        migrations.RunPython(migrer_zone_vers_commune, reverse_code=migrations.RunPython.noop),
    ]
