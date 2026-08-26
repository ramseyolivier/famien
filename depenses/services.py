from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone


def _notifier_dg_manager(depense, *, type, titre, message=""):
    """Notifie les DG/Managers ayant accès à la dépense, sauf le créateur lui-même."""
    from core.models import Utilisateur, Profil, TypeNotification
    from core.services import creer_notification
    lien = f"/depenses/{depense.pk}/"
    for u in Utilisateur.objects.filter(profil__in=[Profil.DG, Profil.MANAGER], is_active=True):
        if u.pk == depense.cree_par_id:
            continue
        if u.acces_national or depense.site is None or depense.site in u.sites_autorises():
            creer_notification(u, type=type, titre=titre, message=message, lien=lien)


def _notifier_createur(depense, *, type, titre, message=""):
    from core.services import creer_notification
    lien = f"/depenses/{depense.pk}/"
    creer_notification(depense.cree_par, type=type, titre=titre, message=message, lien=lien)


@transaction.atomic
def soumettre_depense(depense, *, par):
    from .models import StatutDepense
    from core.models import TypeNotification
    if depense.statut != StatutDepense.BROUILLON:
        raise ValidationError("Seul un brouillon peut être soumis.")
    depense.statut = StatutDepense.SOUMIS
    depense.save(update_fields=["statut"])
    _notifier_dg_manager(
        depense,
        type=TypeNotification.DEPENSE_SOUMISE,
        titre=f"Dépense à valider — {float(depense.montant):,.0f} F",
        message=f"{par.get_full_name() or par.username} · {depense.motif}",
    )
    return depense


@transaction.atomic
def valider_depense(depense, *, par):
    from .models import StatutDepense
    from core.models import TypeNotification
    if depense.statut != StatutDepense.SOUMIS:
        raise ValidationError("La dépense doit être soumise pour être validée.")
    depense.statut = StatutDepense.VALIDE
    depense.valide_le = timezone.now()
    depense.valide_par = par
    depense.save(update_fields=["statut", "valide_le", "valide_par"])
    _notifier_createur(
        depense,
        type=TypeNotification.DEPENSE_VALIDEE,
        titre=f"Dépense validée — {float(depense.montant):,.0f} F",
        message=depense.motif,
    )
    return depense


@transaction.atomic
def confirmer_depense(depense, *, par, montant_reel):
    """Confirmation par le créateur après dépense effective (section 20 — étape 3 du workflow).

    VALIDE signifie que le Manager/DG a autorisé la dépense mais l'argent n'est pas encore
    sorti. CONFIRME signifie que la dépense a réellement eu lieu pour montant_reel.
    C'est uniquement à ce stade que le solde est impacté dans les calculs financiers.
    """
    from decimal import Decimal
    from .models import StatutDepense
    from core.models import TypeNotification
    if depense.statut != StatutDepense.VALIDE:
        raise ValidationError("Seule une dépense validée peut être confirmée.")
    if montant_reel < Decimal("0"):
        raise ValidationError("Le montant réellement dépensé ne peut pas être négatif.")
    if montant_reel > depense.montant:
        raise ValidationError(
            f"Le montant réellement dépensé ({montant_reel:,.0f} F) ne peut pas dépasser "
            f"le montant autorisé ({depense.montant:,.0f} F)."
        )
    depense.statut = StatutDepense.CONFIRME
    depense.montant_confirme = montant_reel
    depense.confirme_par = par
    depense.confirme_le = timezone.now()
    depense.save(update_fields=["statut", "montant_confirme", "confirme_par", "confirme_le"])
    _notifier_dg_manager(
        depense,
        type=TypeNotification.DEPENSE_VALIDEE,
        titre=f"Dépense confirmée — {float(montant_reel):,.0f} F / {float(depense.montant):,.0f} F autorisés",
        message=f"{par.get_full_name() or par.username} · {depense.motif}",
    )
    return depense


@transaction.atomic
def rejeter_depense(depense, *, par, motif):
    from .models import StatutDepense
    from core.models import TypeNotification
    if depense.statut != StatutDepense.SOUMIS:
        raise ValidationError("Seule une dépense soumise peut être rejetée.")
    if not motif or len(motif) < 10:
        raise ValidationError("Le motif doit faire au moins 10 caractères (RG-M00-009).")
    depense.statut = StatutDepense.REJETE
    depense.motif_rejet = motif
    depense.save(update_fields=["statut", "motif_rejet"])
    _notifier_createur(
        depense,
        type=TypeNotification.DEPENSE_REJETEE,
        titre=f"Dépense rejetée — {float(depense.montant):,.0f} F",
        message=motif,
    )
    return depense
