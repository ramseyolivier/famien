"""Service de transfert de stock. Toute écriture de stock passe par stock.services."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import Notification, Profil, TypeNotification, Utilisateur
from stock.models import TypeMouvement
from stock.services import enregistrer_mouvement

from .models import TypeTransfert


def _utilisateurs_du_site(site):
    return Utilisateur.objects.filter(is_active=True, site=site, profil=Profil.CHEF_EQUIPE)


def _dgs():
    return Utilisateur.objects.filter(is_active=True, profil=Profil.DG)


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
    Pour DON/SURPLUS : pas de site destination, notification aux DG.
    """
    from .models import StatutTransfert

    if transfert.statut != StatutTransfert.EN_ATTENTE:
        raise ValidationError("Ce transfert a déjà été traité.")
    if not transfert.lignes.exists():
        raise ValidationError("Un transfert doit contenir au moins une ligne.")

    if transfert.type_transfert == TypeTransfert.DON:
        type_mv = TypeMouvement.SORTIE_DON
        commentaire = "Don"
    elif transfert.type_transfert == TypeTransfert.SURPLUS:
        type_mv = TypeMouvement.SORTIE_SURPLUS
        commentaire = "Surplus retiré"
    else:
        type_mv = TypeMouvement.SORTIE_TRANSFERT
        commentaire = f"Vers {transfert.site_destination.nom}"

    ref = f"TRF-{transfert.pk}"
    for ligne in transfert.lignes.select_related("produit").order_by("produit__code"):
        enregistrer_mouvement(
            site=transfert.site_origine,
            produit=ligne.produit,
            type=type_mv,
            quantite=-ligne.quantite,
            auteur=par,
            reference_document=ref,
            commentaire=commentaire,
        )

    lien = f"/transferts/{transfert.pk}/"
    groupe = f"trf-{transfert.pk}"

    if transfert.type_transfert == TypeTransfert.NORMAL:
        _notifier(
            _utilisateurs_du_site(transfert.site_destination),
            TypeNotification.TRANSFERT_RECU,
            titre=f"Transfert reçu de {transfert.site_origine.nom}",
            message=f"{transfert.lignes.count()} article(s) en attente de votre confirmation.",
            lien=lien, groupe=groupe,
        )
    else:
        label = "Don" if transfert.type_transfert == TypeTransfert.DON else "Surplus"
        _notifier(
            _dgs().exclude(pk=par.pk),
            TypeNotification.TRANSFERT_RECU,
            titre=f"Transfert {label} à valider — {transfert.site_origine.nom}",
            message=f"{transfert.lignes.count()} article(s) en attente de votre validation.",
            lien=lien, groupe=groupe,
        )

    return transfert


@transaction.atomic
def accepter_transfert(transfert, *, par):
    """
    Pour les transferts NORMAUX : crédite le stock du destinataire.
    Pour DON/SURPLUS : pas de crédit (le stock a déjà quitté l'origine, il disparaît).
    """
    from .models import StatutTransfert

    if transfert.statut != StatutTransfert.EN_ATTENTE:
        raise ValidationError("Seul un transfert en attente peut être accepté.")

    if transfert.type_transfert == TypeTransfert.NORMAL:
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

    lien_detail  = f"/transferts/{transfert.pk}/"
    groupe_trf   = f"trf-{transfert.pk}"

    if transfert.type_transfert == TypeTransfert.NORMAL:
        _notifier(
            _utilisateurs_du_site(transfert.site_origine).exclude(pk=par.pk),
            TypeNotification.TRANSFERT_ACCEPTE,
            titre=f"Transfert accepté par {transfert.site_destination.nom}",
            message=f"Le transfert TRF-{transfert.pk} a été accepté.",
            lien=lien_detail, groupe=groupe_trf,
        )
    else:
        label = transfert.get_type_transfert_display()
        destinataires = Utilisateur.objects.filter(pk=transfert.cree_par_id).exclude(pk=par.pk)
        _notifier(
            destinataires,
            TypeNotification.TRANSFERT_ACCEPTE,
            titre=f"Transfert {label} validé",
            message=f"Le transfert TRF-{transfert.pk} ({label}) a été validé par le DG.",
            lien=lien_detail, groupe=groupe_trf,
        )

    return transfert


@transaction.atomic
def rejeter_transfert(transfert, *, par):
    """Recrédite le stock de l'émetteur et marque REJETE."""
    from .models import StatutTransfert

    if transfert.statut != StatutTransfert.EN_ATTENTE:
        raise ValidationError("Seul un transfert en attente peut être rejeté.")

    # Pour DON/SURPLUS, on utilise le même type que le débit initial avec quantité positive
    # afin que le net (SORTIE_DON ou SORTIE_SURPLUS) tombe à 0 dans le rapport journalier.
    # Pour NORMAL, ENTREE_TRANSFERT annule SORTIE_TRANSFERT (transfert = ENTREE + SORTIE = 0).
    if transfert.type_transfert == TypeTransfert.DON:
        type_mv_retour = TypeMouvement.SORTIE_DON
    elif transfert.type_transfert == TypeTransfert.SURPLUS:
        type_mv_retour = TypeMouvement.SORTIE_SURPLUS
    else:
        type_mv_retour = TypeMouvement.ENTREE_TRANSFERT

    ref = f"TRF-{transfert.pk}"
    for ligne in transfert.lignes.select_related("produit").order_by("produit__code"):
        enregistrer_mouvement(
            site=transfert.site_origine,
            produit=ligne.produit,
            type=type_mv_retour,
            quantite=ligne.quantite,
            auteur=par,
            reference_document=ref,
            commentaire="Retour — rejeté",
        )

    transfert.statut = StatutTransfert.REJETE
    transfert.traite_le = timezone.now()
    transfert.traite_par = par
    transfert.save(update_fields=["statut", "traite_le", "traite_par"])

    label       = transfert.get_type_transfert_display()
    lien_detail = f"/transferts/{transfert.pk}/"
    groupe_trf  = f"trf-{transfert.pk}"

    if transfert.type_transfert == TypeTransfert.NORMAL:
        destinataires = _utilisateurs_du_site(transfert.site_origine).exclude(pk=par.pk)
    else:
        destinataires = Utilisateur.objects.filter(pk=transfert.cree_par_id).exclude(pk=par.pk)

    _notifier(
        destinataires,
        TypeNotification.TRANSFERT_REJETE,
        titre=f"Transfert {label} rejeté",
        message=f"Le transfert TRF-{transfert.pk} a été rejeté. Votre stock a été recrédité.",
        lien=lien_detail,
        groupe=groupe_trf,
    )
    return transfert


def destinations_possibles(user):
    from core.models import Site
    if not user.site_id:
        if user.acces_national:
            return Site.objects.filter(actif=True)
        return Site.objects.none()
    return Site.objects.filter(actif=True).exclude(pk=user.site_id)
