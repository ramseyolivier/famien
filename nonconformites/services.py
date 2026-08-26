from django.core.exceptions import ValidationError
from django.db import models as dj_models
from django.db import transaction
from django.utils import timezone

from core.models import Profil, TypeNotification, Utilisateur
from core.services import creer_notification

from .models import ActionCorrective, NonConformite, StatutNonConformite


def _destinataires(auteur):
    p = auteur.profil
    commune_id = auteur.site.commune_id if auteur.site_id else None

    if p == Profil.COMMERCIAL and commune_id:
        return Utilisateur.objects.filter(
            dj_models.Q(profil=Profil.CHEF_EQUIPE, site=auteur.site)
            | dj_models.Q(profil=Profil.SUPERVISEUR, commune_id=commune_id)
            | dj_models.Q(profil__in=[Profil.MANAGER, Profil.DG])
        ).exclude(pk=auteur.pk)

    if p == Profil.CHEF_EQUIPE and commune_id:
        return Utilisateur.objects.filter(
            dj_models.Q(profil=Profil.SUPERVISEUR, commune_id=commune_id)
            | dj_models.Q(profil__in=[Profil.MANAGER, Profil.DG])
        ).exclude(pk=auteur.pk)

    if p == Profil.GEST_MAGASIN and commune_id:
        return Utilisateur.objects.filter(
            dj_models.Q(profil=Profil.SUPERVISEUR, commune_id=commune_id)
            | dj_models.Q(profil__in=[Profil.MANAGER, Profil.DG])
        ).exclude(pk=auteur.pk)

    if p == Profil.SUPERVISEUR:
        return Utilisateur.objects.filter(
            profil__in=[Profil.MANAGER, Profil.DG]
        ).exclude(pk=auteur.pk)

    if p in {Profil.MANAGER, Profil.DG}:
        return Utilisateur.objects.filter(
            profil__in=[Profil.MANAGER, Profil.DG]
        ).exclude(pk=auteur.pk)

    return Utilisateur.objects.none()


@transaction.atomic
def creer_nc(*, auteur, type_nc, titre, description, reference="", image=None):
    nc = NonConformite.objects.create(
        site=auteur.site if auteur.site_id else None,
        type=type_nc,
        titre=titre,
        description=description,
        reference_document=reference,
        image=image,
        cree_par=auteur,
    )
    lien = f"/nonconformites/{nc.pk}/"
    nom_auteur = auteur.get_full_name() or auteur.username
    for dest in _destinataires(auteur):
        creer_notification(
            dest,
            type=TypeNotification.NON_CONFORMITE,
            titre=f"Non-conformité signalée — {titre}",
            message=f"Déclarée par {nom_auteur}",
            lien=lien,
        )
    return nc


@transaction.atomic
def ajouter_action(nc, *, par, description):
    if not nc.est_ouverte:
        raise ValidationError("Impossible d'ajouter une action à une NC clôturée ou annulée.")
    action = ActionCorrective.objects.create(
        non_conformite=nc, description=description, cree_par=par
    )
    if nc.statut == StatutNonConformite.OUVERTE:
        nc.statut = StatutNonConformite.EN_COURS
        nc.save(update_fields=["statut"])
    return action


@transaction.atomic
def cloturer_nc(nc, *, par):
    if not nc.est_ouverte:
        raise ValidationError("Cette non-conformité est déjà clôturée ou annulée.")
    nc.statut = StatutNonConformite.CLOTUREE
    nc.cloture_le = timezone.now()
    nc.cloture_par = par
    nc.save(update_fields=["statut", "cloture_le", "cloture_par"])
    return nc


@transaction.atomic
def annuler_nc(nc, *, par):
    if nc.statut == StatutNonConformite.CLOTUREE:
        raise ValidationError("Une non-conformité clôturée ne peut pas être annulée.")
    nc.statut = StatutNonConformite.ANNULEE
    nc.save(update_fields=["statut"])
    return nc
