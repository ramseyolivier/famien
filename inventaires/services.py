"""Service de validation et de contrôle des inventaires."""
from django.core.exceptions import ValidationError
from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from stock.models import TypeMouvement
from stock.services import enregistrer_mouvement


def verifier_blocages_inventaire(site):
    """
    Retourne une liste de dicts {"message", "url_name", "label"} pour chaque flux
    bloquant le démarrage d'un inventaire sur ce site (section 7.2 du CDC).
    """
    from approvisionnement.models import (
        CommandeEcole,
        StatutCommandeEcole,
    )
    from transferts.models import StatutTransfert, Transfert

    blocages = []

    nb_transferts = Transfert.objects.filter(
        statut=StatutTransfert.EN_ATTENTE
    ).filter(
        django_models.Q(site_origine=site) | django_models.Q(site_destination=site)
    ).count()
    if nb_transferts:
        blocages.append({
            "message": f"{nb_transferts} transfert(s) en attente",
            "url_name": "transferts_liste",
            "label": "Voir les transferts",
        })

    ACTIFS = [
        StatutCommandeEcole.SOUMISE,
        StatutCommandeEcole.VALIDEE,
        StatutCommandeEcole.LIVREE,
    ]

    nb_cmd = CommandeEcole.objects.filter(ecole=site, statut__in=ACTIFS).count()
    if nb_cmd:
        blocages.append({
            "message": f"{nb_cmd} commande(s) en cours",
            "url_name": "commandes_ecole_liste",
            "label": "Voir les commandes",
        })

    return blocages


@transaction.atomic
def valider_inventaire(inventaire, *, par):
    from .models import StatutInventaire

    if inventaire.statut != StatutInventaire.EN_COURS:
        raise ValidationError("Seul un inventaire en cours peut être validé.")
    if not inventaire.lignes.exists():
        raise ValidationError("L'inventaire ne contient aucune ligne.")
    ref = f"INV-{inventaire.pk}"
    for ligne in inventaire.lignes.select_related("produit").order_by("produit__code"):
        ecart = ligne.ecart
        if ecart != 0:
            enregistrer_mouvement(
                site=inventaire.site,
                produit=ligne.produit,
                type=TypeMouvement.AJUSTEMENT,
                quantite=ecart,
                auteur=par,
                reference_document=ref,
                commentaire=f"Inventaire validé : écart {ecart:+d}",
                autoriser_negatif=True,
            )
    inventaire.statut = StatutInventaire.VALIDE
    inventaire.valide_le = timezone.now()
    inventaire.valide_par = par
    inventaire.save(update_fields=["statut", "valide_le", "valide_par"])
    return inventaire
