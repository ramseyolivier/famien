"""
Migration : nouveau workflow école (M16 v2).

Ajoute les champs de traçabilité (soumise_le/par, validee_le/par, rejete_le/par/motif)
et motif_ecart sur les lignes.

La migration de données auto-clôture les commandes déjà à l'état LIVREE :
- crédite le stock école (ENTREE_LIVRAISON_ECOLE) pour les quantités livrées
- marque quantite_recue = quantite_livree
- supprime les StockReserve correspondantes
- passe le statut en RECUE
Le stock magasin avait déjà été débité dans l'ancien flux : pas de double débit.
"""

import django.db.models.deletion
from django.db import migrations, models


def migrer_livrees_en_recues(apps, schema_editor):
    CommandeEcole = apps.get_model("approvisionnement", "CommandeEcole")
    CommandeEcoleLigne = apps.get_model("approvisionnement", "CommandeEcoleLigne")
    StockReserve = apps.get_model("approvisionnement", "StockReserve")
    SoldeStock = apps.get_model("stock", "SoldeStock")
    MouvementStock = apps.get_model("stock", "MouvementStock")

    livrees = list(
        CommandeEcole.objects.filter(statut="LIVREE").select_related("ecole")
    )

    for commande in livrees:
        ecole = commande.ecole
        lignes = list(
            CommandeEcoleLigne.objects.filter(commande=commande).select_related("produit")
        )
        ref = f"REC-ECO-MIGRATION-{commande.pk}"

        for ligne in lignes:
            qty = ligne.quantite_livree or 0
            ligne.quantite_recue = qty
            ligne.save(update_fields=["quantite_recue"])

            if qty > 0:
                solde, _ = SoldeStock.objects.get_or_create(
                    site=ecole,
                    produit=ligne.produit,
                    defaults={
                        "quantite": 0,
                        "stock_minimum": 0,
                        "stock_securite": 0,
                        "stock_maximum": 0,
                    },
                )
                SoldeStock.objects.filter(pk=solde.pk).update(
                    quantite=solde.quantite + qty
                )
                MouvementStock.objects.create(
                    site=ecole,
                    produit=ligne.produit,
                    type="ENTREE_LIVRAISON_ECOLE",
                    quantite=qty,
                    reference_document=ref,
                    commentaire=f"Migration — réception auto commande #{commande.pk}",
                )

        StockReserve.objects.filter(commande=commande).delete()

        from django.utils import timezone
        commande.statut = "RECUE"
        commande.recue_le = commande.livree_le or timezone.now()
        commande.recue_par = commande.livree_par
        commande.save(update_fields=["statut", "recue_le", "recue_par"])


class Migration(migrations.Migration):

    dependencies = [
        ("approvisionnement", "0004_motif_ecart_ligne_magasin"),
        ("core", "0001_initial"),
        ("stock", "0004_solde_stock_minimum"),
    ]

    operations = [
        # Nouveaux statuts — AlterField met à jour les choix dans la schema state
        migrations.AlterField(
            model_name="commandeecole",
            name="statut",
            field=models.CharField(
                choices=[
                    ("BROUILLON", "Brouillon"),
                    ("SOUMISE", "Soumise"),
                    ("VALIDEE", "Validée"),
                    ("LIVREE", "Livrée — en attente de réception"),
                    ("RECUE", "Reçue"),
                    ("REJETEE", "Rejetée"),
                    ("ANNULEE", "Annulée"),
                ],
                default="BROUILLON",
                max_length=10,
            ),
        ),
        # Traçabilité soumission
        migrations.AddField(
            model_name="commandeecole",
            name="soumise_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="commandeecole",
            name="soumise_par",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="commandes_ecole_soumises",
                to="core.utilisateur",
            ),
        ),
        # Traçabilité validation superviseur
        migrations.AddField(
            model_name="commandeecole",
            name="validee_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="commandeecole",
            name="validee_par",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="commandes_ecole_validees",
                to="core.utilisateur",
            ),
        ),
        # Traçabilité rejet
        migrations.AddField(
            model_name="commandeecole",
            name="motif_rejet",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="commandeecole",
            name="rejete_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="commandeecole",
            name="rejete_par",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="commandes_ecole_rejetees",
                to="core.utilisateur",
            ),
        ),
        # Motif d'écart sur les lignes
        migrations.AddField(
            model_name="commandeecoleligne",
            name="motif_ecart",
            field=models.CharField(blank=True, max_length=300),
        ),
        # Migration données : LIVREE → RECUE (ancien flux)
        migrations.RunPython(migrer_livrees_en_recues, migrations.RunPython.noop),
    ]
