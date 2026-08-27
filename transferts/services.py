"""Service de transfert de stock. Toute écriture de stock passe par stock.services."""
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from core.models import Notification, Profil, TypeNotification, Utilisateur
from stock.models import TypeMouvement
from stock.services import enregistrer_mouvement


def _utilisateurs_du_site(site):
    """Retourne les utilisateurs actifs à notifier pour un site donné."""
    return Utilisateur.objects.filter(is_active=True, site=site, profil=Profil.CHEF_EQUIPE)


def _notifier(utilisateurs, type_notif, titre, message, lien, groupe):
    Notification.objects.bulk_create([
        Notification(
            destinataire=u, type=type_notif,
            titre=titre, message=message, lien=lien, groupe=groupe,
        )
        for u in utilisateurs
    ])


@transaction.atomic
def envoyer_transfert(transfert, *, par):
    """
    Débite le stock de l'émetteur et place le transfert EN_ATTENTE.
    La notification part vers les utilisateurs du site destination.
    """
    from .models import StatutTransfert

    if transfert.statut != StatutTransfert.EN_ATTENTE:
        raise ValidationError("Ce transfert a déjà été traité.")
    if not transfert.lignes.exists():
        raise ValidationError("Un transfert doit contenir au moins une ligne.")

    ref = f"TRF-{transfert.pk}"
    for ligne in transfert.lignes.select_related("produit").order_by("produit__code"):
        enregistrer_mouvement(
            site=transfert.site_origine,
            produit=ligne.produit,
            type=TypeMouvement.SORTIE_TRANSFERT,
            quantite=-ligne.quantite,
            auteur=par,
            reference_document=ref,
            commentaire=f"Vers {transfert.site_destination.nom}",
        )

    lien = f"/transferts/{transfert.pk}/"
    groupe = f"trf-{transfert.pk}"
    destinataires = _utilisateurs_du_site(transfert.site_destination)
    _notifier(
        destinataires,
        TypeNotification.TRANSFERT_RECU,
        titre=f"Transfert reçu de {transfert.site_origine.nom}",
        message=f"{transfert.lignes.count()} article(s) en attente de votre confirmation.",
        lien=lien,
        groupe=groupe,
    )
    return transfert


@transaction.atomic
def accepter_transfert(transfert, *, par):
    """Crédite le stock du destinataire et marque ACCEPTE."""
    from .models import StatutTransfert

    if transfert.statut != StatutTransfert.EN_ATTENTE:
        raise ValidationError("Seul un transfert en attente peut être accepté.")

    ref = f"TRF-{transfert.pk}"
    for ligne in transfert.lignes.select_related("produit").order_by("produit__code"):
        enregistrer_mouvement(
            site=transfert.site_destination,
            produit=ligne.produit,
            type=TypeMouvement.ENTREE_TRANSFERT,
            quantite=ligne.quantite,
            auteur=par,
            reference_document=ref,
            commentaire=f"Depuis {transfert.site_origine.nom}",
        )

    transfert.statut = StatutTransfert.ACCEPTE
    transfert.traite_le = timezone.now()
    transfert.traite_par = par
    transfert.save(update_fields=["statut", "traite_le", "traite_par"])

    expediteurs = _utilisateurs_du_site(transfert.site_origine)
    _notifier(
        expediteurs,
        TypeNotification.TRANSFERT_ACCEPTE,
        titre=f"Transfert accepté par {transfert.site_destination.nom}",
        message=f"Le transfert TRF-{transfert.pk} a été accepté.",
        lien=f"/transferts/{transfert.pk}/",
        groupe=f"trf-{transfert.pk}",
    )
    return transfert


@transaction.atomic
def rejeter_transfert(transfert, *, par):
    """Recrédite le stock de l'émetteur et marque REJETE."""
    from .models import StatutTransfert

    if transfert.statut != StatutTransfert.EN_ATTENTE:
        raise ValidationError("Seul un transfert en attente peut être rejeté.")

    ref = f"TRF-{transfert.pk}"
    for ligne in transfert.lignes.select_related("produit").order_by("produit__code"):
        enregistrer_mouvement(
            site=transfert.site_origine,
            produit=ligne.produit,
            type=TypeMouvement.ENTREE_TRANSFERT,
            quantite=ligne.quantite,
            auteur=par,
            reference_document=ref,
            commentaire=f"Retour rejet par {transfert.site_destination.nom}",
        )

    transfert.statut = StatutTransfert.REJETE
    transfert.traite_le = timezone.now()
    transfert.traite_par = par
    transfert.save(update_fields=["statut", "traite_le", "traite_par"])

    expediteurs = _utilisateurs_du_site(transfert.site_origine)
    _notifier(
        expediteurs,
        TypeNotification.TRANSFERT_REJETE,
        titre=f"Transfert rejeté par {transfert.site_destination.nom}",
        message=f"Le transfert TRF-{transfert.pk} a été rejeté. Votre stock a été recrédité.",
        lien=f"/transferts/{transfert.pk}/",
        groupe=f"trf-{transfert.pk}",
    )
    return transfert


def destinations_possibles(user):
    """
    Sites vers lesquels cet utilisateur peut envoyer un transfert.
    En FAMIEN tous les sites sont du même type — tout site peut transférer vers tout autre site autorisé.
    """
    from core.models import Site

    if not user.site_id:
        if user.acces_national:
            return Site.objects.filter(actif=True)
        return Site.objects.none()

    return Site.objects.filter(actif=True).exclude(pk=user.site_id)
