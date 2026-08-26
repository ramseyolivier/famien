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
        CommandeMagasin,
        StatutCommandeEcole,
        StatutCommandeMagasin,
    )
    from core.models import TypeSite
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

    ACTIFS_ECOLE = [
        StatutCommandeEcole.SOUMISE,
        StatutCommandeEcole.VALIDEE,
        StatutCommandeEcole.LIVREE,
    ]
    ACTIFS_MAGASIN = [
        StatutCommandeMagasin.SOUMISE,
        StatutCommandeMagasin.VALIDEE,
        StatutCommandeMagasin.LIVREE,
    ]

    if site.type == TypeSite.ECOLE:
        nb_cmd = CommandeEcole.objects.filter(ecole=site, statut__in=ACTIFS_ECOLE).count()
        if nb_cmd:
            blocages.append({
                "message": f"{nb_cmd} commande(s) école en cours",
                "url_name": "commandes_ecole_liste",
                "label": "Voir les commandes",
            })

    elif site.type == TypeSite.MAGASIN:
        nb_cmd_mag = CommandeMagasin.objects.filter(magasin=site, statut__in=ACTIFS_MAGASIN).count()
        if nb_cmd_mag:
            blocages.append({
                "message": f"{nb_cmd_mag} commande(s) magasin en cours",
                "url_name": "commandes_magasin_liste",
                "label": "Voir les commandes",
            })
        nb_livr = CommandeEcole.objects.filter(
            ecole__magasin_rattachement=site, statut__in=ACTIFS_ECOLE
        ).count()
        if nb_livr:
            blocages.append({
                "message": f"{nb_livr} commande(s) école en cours",
                "url_name": "commandes_ecole_liste",
                "label": "Voir les commandes",
            })

    elif site.type == TypeSite.DEPOT:
        nb_cmd = CommandeMagasin.objects.filter(statut__in=ACTIFS_MAGASIN).count()
        if nb_cmd:
            blocages.append({
                "message": f"{nb_cmd} commande(s) magasin en cours",
                "url_name": "commandes_magasin_liste",
                "label": "Voir les commandes",
            })
        from achats.models import CommandeFournisseur, StatutCommande
        ACTIFS_FOURN = [StatutCommande.SOUMIS, StatutCommande.VALIDE_N1, StatutCommande.VALIDE]
        nb_fourn = CommandeFournisseur.objects.filter(
            site_destination=site, statut__in=ACTIFS_FOURN
        ).count()
        if nb_fourn:
            blocages.append({
                "message": f"{nb_fourn} commande(s) fournisseur en cours",
                "url_name": "commandes_liste",
                "label": "Voir les commandes fournisseur",
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
