"""Services du workflow d'achat."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from stock.models import TypeMouvement
from stock.services import enregistrer_mouvement


@transaction.atomic
def soumettre_commande(commande, *, par):
    from .models import StatutCommande
    from core.models import Profil, TypeNotification
    from core.services import creer_notification
    from core.models import Utilisateur

    if commande.statut != StatutCommande.BROUILLON:
        raise ValidationError("Seul un brouillon peut être soumis.")
    if not commande.lignes.exists():
        raise ValidationError("La commande doit contenir au moins une ligne.")
    commande.statut = StatutCommande.SOUMIS
    commande.soumis_le = timezone.now()
    commande.soumis_par = par
    commande.save(update_fields=["statut", "soumis_le", "soumis_par"])

    # Notifier le DG uniquement si c'est un profil inférieur au Manager qui soumet.
    # Si le Manager soumet, il a déjà l'autorité de valider — le DG n'a pas à être alerté.
    if par.profil != Profil.MANAGER:
        dgs = Utilisateur.objects.filter(profil=Profil.DG, is_active=True).exclude(pk=par.pk)
        soumis_par_nom = par.get_full_name() or par.username
        for dg in dgs:
            creer_notification(
                dg,
                type=TypeNotification.DEMANDE_SOUMISE,
                titre=f"Commande fournisseur à valider — {commande.fournisseur.raison_sociale}",
                message=f"La commande #{commande.pk} soumise par {soumis_par_nom} attend votre validation.",
                lien=f"/approvisionnement/fournisseurs/commandes/{commande.pk}/",
            )

    return commande


@transaction.atomic
def valider_commande_n1(commande, *, par):
    from .models import StatutCommande
    if commande.statut != StatutCommande.SOUMIS:
        raise ValidationError("La commande doit être soumise pour être validée au niveau 1.")
    commande.statut = StatutCommande.VALIDE_N1
    commande.valide_n1_le = timezone.now()
    commande.valide_n1_par = par
    commande.save(update_fields=["statut", "valide_n1_le", "valide_n1_par"])
    return commande


@transaction.atomic
def valider_commande(commande, *, par):
    from .models import StatutCommande
    from core.models import TypeNotification
    from core.services import creer_notification

    if commande.statut not in {StatutCommande.SOUMIS, StatutCommande.VALIDE_N1}:
        raise ValidationError("La commande doit être soumise ou validée N1 avant validation finale.")
    commande.statut = StatutCommande.VALIDE
    commande.valide_le = timezone.now()
    commande.valide_par = par
    commande.save(update_fields=["statut", "valide_le", "valide_par"])

    if commande.soumis_par_id and commande.soumis_par_id != par.pk:
        creer_notification(
            commande.soumis_par,
            type=TypeNotification.DEMANDE_VALIDEE,
            titre=f"Commande #{commande.pk} validée — {commande.fournisseur.raison_sociale}",
            message=f"Votre commande a été validée par {par.get_full_name() or par.username}.",
            lien=f"/approvisionnement/fournisseurs/commandes/{commande.pk}/",
        )

    return commande


@transaction.atomic
def rejeter_commande(commande, *, par, motif):
    from .models import StatutCommande
    from core.models import TypeNotification
    from core.services import creer_notification

    if commande.statut not in {StatutCommande.SOUMIS, StatutCommande.VALIDE_N1}:
        raise ValidationError("Seule une commande soumise ou validée N1 peut être rejetée.")
    if not motif or len(motif) < 10:
        raise ValidationError("Le motif de rejet doit faire au moins 10 caractères.")
    commande.statut = StatutCommande.REJETE
    commande.motif_rejet = motif
    commande.save(update_fields=["statut", "motif_rejet"])

    if commande.soumis_par_id and commande.soumis_par_id != par.pk:
        creer_notification(
            commande.soumis_par,
            type=TypeNotification.DEMANDE_REJETEE,
            titre=f"Commande #{commande.pk} rejetée — {commande.fournisseur.raison_sociale}",
            message=f"Votre commande a été rejetée. Motif : {motif}",
            lien=f"/approvisionnement/fournisseurs/commandes/{commande.pk}/",
        )

    return commande


@transaction.atomic
def valider_reception(reception, *, par):
    from .models import StatutReception
    if reception.statut != StatutReception.BROUILLON:
        raise ValidationError("Seule une réception en brouillon peut être validée.")
    if not reception.lignes.exists():
        raise ValidationError("La réception doit contenir au moins une ligne.")
    ref = f"REC-{reception.pk}"
    site = reception.site_effectif
    fourn_label = str(reception.fournisseur_effectif) if reception.fournisseur_effectif else "fournisseur inconnu"
    for ligne in reception.lignes.select_related("produit").order_by("produit__code"):
        if ligne.quantite_recue > 0:
            enregistrer_mouvement(
                site=site,
                produit=ligne.produit,
                type=TypeMouvement.ENTREE_ACHAT,
                quantite=ligne.quantite_recue,
                auteur=par,
                reference_document=ref,
                commentaire=f"Réception {fourn_label}",
            )
    # Réception directe (sans commande) : clôture immédiate — pas de validation partielle possible.
    statut_final = StatutReception.CLOTURE if not reception.commande_id else StatutReception.VALIDE
    reception.statut = statut_final
    reception.valide_le = timezone.now()
    reception.valide_par = par
    reception.save(update_fields=["statut", "valide_le", "valide_par"])
    return reception


@transaction.atomic
def cloturer_commande(commande, *, par):
    from .models import StatutCommande
    if commande.statut not in {StatutCommande.VALIDE, StatutCommande.CLOTURE}:
        raise ValidationError("Seule une commande validée peut être clôturée.")
    commande.statut = StatutCommande.CLOTURE
    commande.save(update_fields=["statut"])
    return commande
