from .models import Notification, TypeNotification


def creer_notification(destinataire, *, type, titre, message="", lien="", groupe=""):
    """Crée une notification pour un utilisateur. Ne lève jamais d'exception."""
    try:
        Notification.objects.create(
            destinataire=destinataire,
            type=type,
            titre=titre,
            message=message,
            lien=lien,
            groupe=groupe,
        )
    except Exception:
        pass


def notifier_chefs_equipe(ecole, *, type, titre, message="", lien=""):
    """Envoie une notification à tous les CHEF_EQUIPE dont le périmètre couvre cette école."""
    from core.models import Profil, Utilisateur
    for u in Utilisateur.objects.filter(is_active=True, profil=Profil.CHEF_EQUIPE):
        if u.peut_acceder_au_site(ecole):
            creer_notification(u, type=type, titre=titre, message=message, lien=lien)


def notifier_managers(sites_concernes, *, type, titre, message="", lien=""):
    """Envoie une notification à tous les DG/MANAGER/SUPERVISEUR du périmètre."""
    from core.models import Profil, Utilisateur
    destinataires = Utilisateur.objects.filter(
        is_active=True,
        profil__in=[Profil.DG, Profil.MANAGER, Profil.SUPERVISEUR],
    )
    for u in destinataires:
        if u.acces_national or u.sites_autorises().filter(pk__in=sites_concernes).exists():
            creer_notification(u, type=type, titre=titre, message=message, lien=lien)
