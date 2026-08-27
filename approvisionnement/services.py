"""
Services métier de l'approvisionnement (M16 et M17).

Flux école (M16) :
1. soumettre_commande_ecole        — chef soumet (BROUILLON → SOUMISE)
2. valider_commande_ecole          — gestionnaire magasin valide (SOUMISE → VALIDEE, crée StockReserve)
3. rejeter_commande_ecole          — gestionnaire magasin rejette (SOUMISE → REJETEE)
4. livrer_commande_ecole           — gestionnaire livre (VALIDEE → LIVREE, ajuste StockReserve)
5. refuser_livraison_ecole         — gestionnaire refuse (VALIDEE → REJETEE, libère StockReserve)
6. receptionner_commande_ecole     — chef réceptionne (LIVREE → RECUE, débit magasin + crédit école)
7. sauvegarder_livraison_directe_ecole_brouillon — gestionnaire crée LDE (BROUILLON)
8. valider_livraison_directe_ecole — gestionnaire valide LDE (BROUILLON → LIVREE, crée StockReserve)

Règles de verrouillage (CLAUDE.md) :
- receptionner_commande_ecole : SoldeStock magasin d'abord, école ensuite, code ASC.
"""

import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone as tz

from core.models import Notification, Profil, TypeNotification, Utilisateur
from core.services import creer_notification
from stock.models import SoldeStock, TypeMouvement
from stock.services import enregistrer_mouvement

from .models import (
    CommandeEcole,
    CommandeEcoleLigne,
    CommandeMagasin,
    CommandeMagasinLigne,
    StatutCommandeEcole,
    StatutCommandeMagasin,
    StockReserve,
    StockReserveDepot,
)


def stock_disponible(magasin, produit):
    """
    Stock disponible réel du magasin pour un produit donné.

    Soustrait les réservations (StockReserve) pour éviter de promettre le même
    article à deux écoles. Inclut les commandes VALIDEE et LIVREE.
    """
    try:
        solde = SoldeStock.objects.get(site=magasin, produit=produit)
        quantite_en_stock = solde.quantite
    except SoldeStock.DoesNotExist:
        quantite_en_stock = 0

    reserves = (
        StockReserve.objects.filter(magasin=magasin, produit=produit)
        .aggregate(total=Sum("quantite"))["total"]
        or 0
    )
    return max(0, quantite_en_stock - reserves)


@transaction.atomic
def soumettre_commande_ecole(commande, *, par):
    """Chef d'équipe soumet la demande (BROUILLON → SOUMISE). Section 16.2."""
    if commande.statut != StatutCommandeEcole.BROUILLON:
        raise ValidationError("Seule une commande en brouillon peut être soumise.")
    if not commande.lignes.exists():
        raise ValidationError("La commande ne contient aucune ligne.")
    commande.statut = StatutCommandeEcole.SOUMISE
    commande.soumise_le = tz.now()
    commande.soumise_par = par
    commande.save(update_fields=["statut", "soumise_le", "soumise_par"])
    lien = f"/approvisionnement/ecole/commande/{commande.pk}/"
    titre = f"Commande site #{commande.numero} à valider — {commande.ecole.nom}"
    message = f"{par.get_full_name() or par.username} a soumis une commande. En attente de votre validation."
    for dg in Utilisateur.objects.filter(is_active=True, profil=Profil.DG):
        creer_notification(dg, type=TypeNotification.DEMANDE_SOUMISE, titre=titre, message=message, lien=lien)
    return commande


@transaction.atomic
def valider_commande_ecole(commande, *, par):
    """
    Gestionnaire de magasin valide la commande (SOUMISE → VALIDEE).
    Crée les StockReserve pour la quantité complète demandée, même si le stock
    est insuffisant : le déficit apparaît dans le tableau de bord et sera résolu
    par un approvisionnement depuis le dépôt. Pas de contrôle bloquant ici —
    même logique que pour les commandes magasin (section M17).
    Section 16.3 du cahier des charges.
    """
    if commande.statut != StatutCommandeEcole.SOUMISE:
        raise ValidationError("Seule une commande soumise peut être validée.")

    lignes = list(commande.lignes.select_related("produit").order_by("produit__code"))

    commande.statut = StatutCommandeEcole.VALIDEE
    commande.validee_le = tz.now()
    commande.validee_par = par
    commande.save(update_fields=["statut", "validee_le", "validee_par"])
    # Modèle FAMIEN plat : pas de magasin intermédiaire, pas de StockReserve à créer ici.
    lien_notif = f"/approvisionnement/ecole/commande/{commande.pk}/"
    # Purge les notifications de soumission envoyées aux DG (ils ont déjà traité la demande)
    Notification.objects.filter(
        destinataire__in=Utilisateur.objects.filter(is_active=True, profil=Profil.DG),
        lien=lien_notif, lue=False, type=TypeNotification.DEMANDE_SOUMISE,
    ).delete()
    creer_notification(
        commande.cree_par,
        type=TypeNotification.DEMANDE_VALIDEE,
        titre=f"Commande #{commande.numero} validée",
        message=f"{par.get_full_name() or par.username} a validé votre commande #{commande.numero}. La livraison est en cours de préparation.",
        lien=lien_notif,
    )
    return commande


@transaction.atomic
def rejeter_commande_ecole(commande, *, par, motif):
    """Gestionnaire de magasin rejette une commande soumise (SOUMISE → REJETEE). Section 16.3."""
    if commande.statut != StatutCommandeEcole.SOUMISE:
        raise ValidationError("Seule une commande soumise peut être rejetée.")
    if not motif or len(motif.strip()) < 10:
        raise ValidationError("Le motif de rejet doit faire au moins 10 caractères.")
    commande.statut = StatutCommandeEcole.REJETEE
    commande.motif_rejet = motif.strip()
    commande.rejete_le = tz.now()
    commande.rejete_par = par
    commande.save(update_fields=["statut", "motif_rejet", "rejete_le", "rejete_par"])
    lien_notif = f"/approvisionnement/ecole/commande/{commande.pk}/"
    # Purge les notifications de soumission envoyées aux DG
    Notification.objects.filter(
        destinataire__in=Utilisateur.objects.filter(is_active=True, profil=Profil.DG),
        lien=lien_notif, lue=False, type=TypeNotification.DEMANDE_SOUMISE,
    ).delete()
    _purger_notifs_obsoletes(commande.cree_par, lien_notif, [TypeNotification.DEMANDE_VALIDEE])
    creer_notification(
        commande.cree_par,
        type=TypeNotification.DEMANDE_REJETEE,
        titre=f"Commande #{commande.numero} rejetée",
        message=f"{par.get_full_name() or par.username} a rejeté votre commande #{commande.numero}. Motif : {motif.strip()}",
        lien=lien_notif,
    )
    return commande


@transaction.atomic
def livrer_commande_ecole(commande, lignes_livrees: dict, *, par, clore=False):
    """
    Gestionnaire livre depuis le magasin (VALIDEE → LIVREE).

    `lignes_livrees` : {produit_id: quantite_livree}

    Aucun mouvement de stock à ce stade — le magasin sera débité à la réception.
    Ajuste les StockReserve aux quantités réellement expédiées.

    Section 16.4 du cahier des charges.
    """
    if commande.statut != StatutCommandeEcole.VALIDEE:
        raise ValidationError("Seule une commande validée peut être livrée.")
    lignes = list(commande.lignes.select_related("produit").order_by("produit__code"))

    qty_total_restant = 0
    for ligne in lignes:
        restant = max(0, ligne.quantite_demandee - (ligne.quantite_deja_recue or 0))
        qty = min(max(0, int(lignes_livrees.get(ligne.produit_id, 0) or 0)), restant)
        ligne.quantite_livree = qty
        ligne.quantite_deja_livree = (ligne.quantite_deja_livree or 0) + qty
        qty_total_restant += max(0, restant - qty)
        ligne.save(update_fields=["quantite_livree", "quantite_deja_livree"])
        # Modèle FAMIEN plat : pas de magasin intermédiaire, pas de StockReserve à ajuster.

    commande.statut = StatutCommandeEcole.LIVREE
    commande.livree_le = tz.now()
    commande.livree_par = par
    commande.livraison_close = clore
    commande.save(update_fields=["statut", "livree_le", "livree_par", "livraison_close"])

    lien = f"/approvisionnement/ecole/commande/{commande.pk}/"
    est_partielle = qty_total_restant > 0 and not clore
    auteur = par.get_full_name() or par.username
    if est_partielle:
        titre = f"Livraison partielle #{commande.numero} — {commande.ecole.nom}"
        message = (
            f"{auteur} a expédié une partie de la commande #{commande.numero}. "
            f"Il reste {qty_total_restant} unité(s) à envoyer."
        )
    else:
        titre = f"Livraison #{commande.numero} prête — {commande.ecole.nom}"
        message = f"{auteur} a préparé et expédié la commande #{commande.numero}."

    if _est_lde(commande):
        # LDE : cree_par est le gestionnaire, pas le chef — notifier les chefs de l'école
        for chef in Utilisateur.objects.filter(
            is_active=True, profil=Profil.CHEF_EQUIPE, site=commande.ecole
        ).exclude(pk=par.pk):
            _purger_notifs_obsoletes(chef, lien, [TypeNotification.LIVRAISON_CONFIRMEE])
            creer_notification(chef, type=TypeNotification.LIVRAISON_PRETE, titre=titre, message=message, lien=lien)
    elif commande.cree_par:
        _purger_notifs_obsoletes(
            commande.cree_par, lien,
            [TypeNotification.DEMANDE_VALIDEE, TypeNotification.LIVRAISON_CONFIRMEE],
        )
        if commande.cree_par != par:
            creer_notification(
                commande.cree_par,
                type=TypeNotification.LIVRAISON_PRETE,
                titre=titre,
                message=message,
                lien=lien,
            )
    return commande


@transaction.atomic
def refuser_livraison_ecole(commande, *, par, motif):
    """
    Gestionnaire refuse d'envoyer une commande validée (VALIDEE → REJETEE).
    Libère les StockReserve créées à la validation.
    """
    if commande.statut != StatutCommandeEcole.VALIDEE:
        raise ValidationError("Seule une commande validée peut être refusée.")
    if not motif or len(motif.strip()) < 10:
        raise ValidationError("Le motif de refus doit faire au moins 10 caractères.")
    commande.statut = StatutCommandeEcole.REJETEE
    commande.motif_rejet = motif.strip()
    commande.rejete_le = tz.now()
    commande.rejete_par = par
    commande.save(update_fields=["statut", "motif_rejet", "rejete_le", "rejete_par"])
    StockReserve.objects.filter(commande=commande).delete()
    if commande.cree_par:
        creer_notification(
            commande.cree_par,
            type=TypeNotification.LIVRAISON_REFUSEE,
            titre=f"Livraison refusée — commande #{commande.pk}",
            message=f"La livraison de votre commande #{commande.pk} a été refusée. Motif : {motif.strip()}",
            lien=f"/approvisionnement/ecole/commande/{commande.pk}/",
        )
    return commande


@transaction.atomic
def receptionner_commande_ecole(commande, lignes_recues: dict, motifs_ecart: dict, *, par):
    """
    Chef d'équipe réceptionne (LIVREE → RECUE).

    `lignes_recues`  : {produit_id: quantite_recue}
    `motifs_ecart`   : {produit_id: motif} — obligatoire si quantite_recue ≠ quantite_livree

    Mouvement SORTIE_LIVRAISON_ECOLE sur le magasin + ENTREE_LIVRAISON_ECOLE
    sur l'école. Supprime les StockReserve.

    Ordre de verrouillage : magasin d'abord, école ensuite, produit.code ASC.
    Section 16.5 du cahier des charges.
    """
    if commande.statut != StatutCommandeEcole.LIVREE:
        raise ValidationError("Seule une commande livrée peut être réceptionnée.")

    ecole = commande.ecole
    lignes = list(commande.lignes.select_related("produit").order_by("produit__code"))
    produit_ids = [l.produit_id for l in lignes]

    # Verrou sur les soldes de l'école — produit.code ASC (modèle FAMIEN plat : pas de magasin intermédiaire)
    list(SoldeStock.objects.select_for_update().filter(site=ecole, produit_id__in=produit_ids).order_by("produit__code"))

    ref = f"REC-ECO-{commande.pk}"
    erreurs = []

    for ligne in lignes:
        qty_recue = int(lignes_recues.get(ligne.produit_id, 0) or 0)
        if qty_recue < 0:
            erreurs.append(f"{ligne.produit.code} : quantité reçue négative.")

    if erreurs:
        raise ValidationError("Erreur dans les quantités reçues :\n" + "\n".join(erreurs))

    for ligne in lignes:
        qty_livree = ligne.quantite_livree or 0
        qty_recue = max(0, min(int(lignes_recues.get(ligne.produit_id, 0) or 0), qty_livree))
        ligne.quantite_recue = qty_recue
        ligne.motif_ecart = motifs_ecart.get(ligne.produit_id, "").strip()
        ligne.quantite_deja_recue = (ligne.quantite_deja_recue or 0) + qty_recue

        if qty_recue > 0:
            # Modèle FAMIEN plat : pas de débit magasin intermédiaire — seul le crédit école est enregistré.
            enregistrer_mouvement(
                site=ecole,
                produit=ligne.produit,
                type=TypeMouvement.ENTREE_LIVRAISON_ECOLE,
                quantite=qty_recue,
                auteur=par,
                reference_document=ref,
                commentaire=f"Réception commande #{commande.pk}",
            )

        if ligne.quantite_deja_recue >= ligne.quantite_demandee:
            ligne.save(update_fields=["quantite_recue", "motif_ecart", "quantite_deja_recue"])
        else:
            ligne.quantite_livree = None
            ligne.quantite_recue = None
            ligne.save(update_fields=["quantite_livree", "quantite_recue", "motif_ecart", "quantite_deja_recue"])

    StockReserve.objects.filter(commande=commande).delete()

    toutes_recues = all((l.quantite_deja_recue or 0) >= l.quantite_demandee for l in lignes)
    auteur = par.get_full_name() or par.username
    lien = f"/approvisionnement/ecole/commande/{commande.pk}/"

    est_lde = _est_lde(commande)

    def _purger_chefs(types):
        if est_lde:
            for chef in Utilisateur.objects.filter(is_active=True, profil=Profil.CHEF_EQUIPE, site=commande.ecole):
                _purger_notifs_obsoletes(chef, lien, types)
        elif commande.cree_par:
            _purger_notifs_obsoletes(commande.cree_par, lien, types)

    if toutes_recues or commande.livraison_close:
        commande.statut = StatutCommandeEcole.RECUE
        commande.recue_le = tz.now()
        commande.recue_par = par
        commande.save(update_fields=["statut", "recue_le", "recue_par"])
        _purger_chefs([TypeNotification.LIVRAISON_PRETE])
        if commande.livraison_close and not toutes_recues:
            reliquat = sum(max(0, l.quantite_demandee - (l.quantite_deja_recue or 0)) for l in lignes)
            _notifier_gestionnaires_ecole(
                commande,
                type=TypeNotification.LIVRAISON_CONFIRMEE,
                titre=f"CM#{commande.numero} clôturée partiellement — {commande.ecole.nom}",
                message=(
                    f"{auteur} a réceptionné la dernière livraison de la commande #{commande.numero}. "
                    f"La commande est clôturée ({reliquat} unité(s) non livrée(s))."
                ),
            )
    else:
        # Réception partielle : repasse en VALIDEE pour une nouvelle livraison
        commande.statut = StatutCommandeEcole.VALIDEE
        commande.livree_le = None
        commande.livree_par = None
        commande.save(update_fields=["statut", "livree_le", "livree_par"])
        reliquat = sum(max(0, l.quantite_demandee - (l.quantite_deja_recue or 0)) for l in lignes)
        _purger_chefs([TypeNotification.LIVRAISON_PRETE])
        if est_lde:
            # LDE : informer les chefs que leur réception est enregistrée
            _notifier_chefs_ecole(
                commande,
                type=TypeNotification.LIVRAISON_CONFIRMEE,
                titre=f"Réception partielle CM#{commande.numero} enregistrée — {commande.ecole.nom}",
                message=(
                    f"Votre réception partielle de la commande #{commande.numero} est enregistrée. "
                    f"Le magasin va expédier le reliquat ({reliquat} unité(s))."
                ),
                exclure_pk=par.pk,
            )
        elif commande.cree_par and commande.cree_par != par:
            creer_notification(
                commande.cree_par,
                type=TypeNotification.LIVRAISON_CONFIRMEE,
                titre=f"Réception partielle CM#{commande.numero} enregistrée — {commande.ecole.nom}",
                message=(
                    f"Votre réception partielle de la commande #{commande.numero} est enregistrée. "
                    f"Le magasin va expédier le reliquat ({reliquat} unité(s))."
                ),
                lien=lien,
            )
        _notifier_gestionnaires_ecole(
            commande,
            type=TypeNotification.LIVRAISON_CONFIRMEE,
            titre=f"Réception partielle CM#{commande.numero} — {commande.ecole.nom}",
            message=(
                f"{auteur} a réceptionné partiellement la commande #{commande.numero}. "
                f"Il reste {reliquat} unité(s) à expédier."
            ),
        )

    return commande


# ─── Approvisionnement magasin ────────────────────────────────────────────────


@transaction.atomic
def _notifier_dg_manager_partage(commande, *, type, titre, message=""):
    """Notifie les DG actifs avec un groupe partagé — le premier à lire efface chez l'autre."""
    lien = f"/approvisionnement/magasin/{commande.pk}/"
    dest = list(Utilisateur.objects.filter(is_active=True, profil=Profil.DG))
    groupe = str(uuid.uuid4()) if len(dest) > 1 else ""
    for u in dest:
        creer_notification(u, type=type, titre=titre, message=message, lien=lien, groupe=groupe)


def _purger_notifs_obsoletes(destinataire, lien, types_obsoletes):
    """Supprime les notifications non-lues devenues obsolètes pour un même lien."""
    Notification.objects.filter(
        destinataire=destinataire,
        lien=lien,
        lue=False,
        type__in=types_obsoletes,
    ).delete()


def _notifier_superviseurs_magasin(commande, *, type, titre, message=""):
    """Notifie les DG actifs (rôle superviseur dans le modèle FAMIEN plat)."""
    lien = f"/approvisionnement/magasin/{commande.pk}/"
    for dg in Utilisateur.objects.filter(is_active=True, profil=Profil.DG):
        creer_notification(dg, type=type, titre=titre, message=message, lien=lien)


def _notifier_gestionnaires_ecole(commande, *, type, titre, message=""):
    """Notifie les DG actifs (modèle FAMIEN plat — pas de gestionnaire magasin intermédiaire)."""
    lien = f"/approvisionnement/ecole/commande/{commande.pk}/"
    for u in Utilisateur.objects.filter(is_active=True, profil=Profil.DG):
        creer_notification(u, type=type, titre=titre, message=message, lien=lien)


def _notifier_chefs_ecole(commande, *, type, titre, message="", exclure_pk=None):
    """Notifie les CHEF_EQUIPE rattachés à l'école de la commande."""
    lien = f"/approvisionnement/ecole/commande/{commande.pk}/"
    qs = Utilisateur.objects.filter(is_active=True, profil=Profil.CHEF_EQUIPE, site=commande.ecole)
    if exclure_pk:
        qs = qs.exclude(pk=exclure_pk)
    for chef in qs:
        creer_notification(chef, type=type, titre=titre, message=message, lien=lien)


def _est_lde(commande):
    """Vrai si la commande est une livraison directe école (observations commence par [LDE])."""
    return bool(commande.observations and commande.observations.startswith("[LDE]"))


def soumettre_commande_magasin(commande, *, par):
    """
    GEST_MAGASIN soumet une commande brouillon vers le dépôt (DG/Manager).
    Section M17 du cahier des charges.
    """
    if commande.statut != StatutCommandeMagasin.BROUILLON:
        raise ValidationError("Seule une commande en brouillon peut être soumise.")
    if not commande.lignes.exists():
        raise ValidationError("La commande ne contient aucune ligne.")
    commande.statut = StatutCommandeMagasin.SOUMISE
    commande.soumise_le = tz.now()
    commande.soumise_par = par
    commande.save(update_fields=["statut", "soumise_le", "soumise_par"])
    _notifier_dg_manager_partage(
        commande,
        type=TypeNotification.DEMANDE_SOUMISE,
        titre=f"Approbation attendue — Commande #{commande.numero} ({commande.magasin.nom})",
        message=f"{par.get_full_name() or par.username} a soumis une commande magasin.",
    )
    return commande


@transaction.atomic
def valider_commande_magasin(commande, *, par):
    """
    DG/MANAGER valide la commande (SOUMISE → VALIDEE).

    Aucune réservation de stock n'est créée ici : le magasin peut commander
    quelle que soit la disponibilité du dépôt. Le contrôle de stock et la
    réservation interviennent à la livraison (livrer_commande_magasin).
    Section M17 du cahier des charges.
    """
    if commande.statut != StatutCommandeMagasin.SOUMISE:
        raise ValidationError("Seule une commande soumise peut être validée.")

    commande.statut = StatutCommandeMagasin.VALIDEE
    commande.validee_le = tz.now()
    commande.validee_par = par
    commande.save(update_fields=["statut", "validee_le", "validee_par"])
    creer_notification(
        commande.cree_par,
        type=TypeNotification.DEMANDE_VALIDEE,
        titre=f"Commande #{commande.numero} validée",
        message=f"Votre commande pour {commande.magasin.nom} a été validée par {par.get_full_name() or par.username}. La livraison est en cours de préparation.",
        lien=f"/approvisionnement/magasin/{commande.pk}/",
    )
    return commande


@transaction.atomic
def rejeter_commande_magasin(commande, *, par, motif):
    """
    SUPERVISEUR rejette une commande soumise (avant validation, donc pas de réservation à libérer).
    Section M17 du cahier des charges.
    """
    if commande.statut != StatutCommandeMagasin.SOUMISE:
        raise ValidationError("Seule une commande soumise peut être rejetée.")
    if not motif or len(motif.strip()) < 10:
        raise ValidationError("Le motif de rejet doit faire au moins 10 caractères.")
    commande.statut = StatutCommandeMagasin.REJETEE
    commande.motif_rejet = motif.strip()
    commande.rejete_le = tz.now()
    commande.rejete_par = par
    commande.save(update_fields=["statut", "motif_rejet", "rejete_le", "rejete_par"])
    creer_notification(
        commande.cree_par,
        type=TypeNotification.DEMANDE_REJETEE,
        titre=f"Commande #{commande.numero} rejetée",
        message=f"Votre commande pour {commande.magasin.nom} a été rejetée par {par.get_full_name() or par.username}. Motif : {motif.strip()}",
        lien=f"/approvisionnement/magasin/{commande.pk}/",
    )
    return commande


def refuser_livraison_magasin(commande, *, par, motif):
    """
    DG/MANAGER refuse d'envoyer une commande validée (VALIDEE → REJETEE).
    Si des lignes ont déjà été partiellement réceptionnées, la notification
    indique que le reliquat est rejeté (réception partielle conservée).
    """
    if commande.statut != StatutCommandeMagasin.VALIDEE:
        raise ValidationError("Seule une commande validée peut être refusée.")
    if not motif or len(motif.strip()) < 10:
        raise ValidationError("Le motif de refus doit faire au moins 10 caractères.")

    est_rejet_partiel = commande.lignes.filter(quantite_deja_recue__gt=0).exists()

    commande.statut = StatutCommandeMagasin.REJETEE
    commande.motif_rejet = motif.strip()
    commande.rejete_le = tz.now()
    commande.rejete_par = par
    commande.save(update_fields=["statut", "motif_rejet", "rejete_le", "rejete_par"])
    StockReserveDepot.objects.filter(commande=commande).delete()
    lien = f"/approvisionnement/magasin/{commande.pk}/"

    if est_rejet_partiel:
        titre = f"Commande #{commande.numero} partiellement rejetée — {commande.magasin.nom}"
        message = (
            f"{par.get_full_name() or par.username} a rejeté le reliquat de la commande #{commande.numero}. "
            f"La partie déjà réceptionnée est conservée. Motif : {motif.strip()}"
        )
    else:
        titre = f"Livraison #{commande.numero} refusée — {commande.magasin.nom}"
        message = f"{par.get_full_name() or par.username} a refusé d'expédier la commande #{commande.numero}. Motif : {motif.strip()}"

    if commande.cree_par:
        _purger_notifs_obsoletes(commande.cree_par, lien, [TypeNotification.DEMANDE_VALIDEE])
        creer_notification(
            commande.cree_par,
            type=TypeNotification.LIVRAISON_REFUSEE,
            titre=titre,
            message=message,
            lien=lien,
        )
    _notifier_superviseurs_magasin(
        commande,
        type=TypeNotification.LIVRAISON_REFUSEE,
        titre=titre,
        message=message,
    )
    return commande


@transaction.atomic
def livrer_commande_magasin(commande, lignes_livrees: dict, *, par, clore=False):
    """
    DG ou Manager prépare et envoie depuis le dépôt (VALIDEE → LIVREE).

    `lignes_livrees` : {produit_id: quantite_livree}

    C'est ici que le stock est contrôlé et réservé : la livraison est
    plafonnée par le stock physique disponible au dépôt (solde moins les
    réservations des autres livraisons en transit). Le select_for_update
    garantit qu'aucune livraison concurrente ne dépasse le stock disponible.
    Le dépôt sera définitivement débité lors de la réception.

    Section M17 du cahier des charges.
    """
    if commande.statut != StatutCommandeMagasin.VALIDEE:
        raise ValidationError("Seule une commande validée peut être livrée.")

    from core.models import Site

    depot = Site.objects.filter(actif=True).first()
    if not depot:
        raise ValidationError("Aucun site actif trouvé.")

    lignes = list(commande.lignes.select_related("produit").order_by("produit__code"))
    produit_ids = [l.produit_id for l in lignes]

    # Verrou dépôt — ordre produit.code ASC (CLAUDE.md : ordre de verrouillage constant)
    soldes = {
        s.produit_id: s.quantite
        for s in SoldeStock.objects.select_for_update()
        .filter(site=depot, produit_id__in=produit_ids)
        .order_by("produit__code")
    }

    # Réservations des autres livraisons en transit (livraisons directes, etc.)
    reserves_autres = {
        r["produit_id"]: r["total"]
        for r in StockReserveDepot.objects
        .filter(produit_id__in=produit_ids)
        .exclude(commande=commande)
        .values("produit_id")
        .annotate(total=Sum("quantite"))
    }

    # Supprimer les éventuelles réservations de cette commande créées avant
    # la migration vers ce flux (commandes validées sous l'ancien code)
    StockReserveDepot.objects.filter(commande=commande).delete()

    manques = []
    lignes_expediees = []
    qty_total_restant = 0
    for ligne in lignes:
        # Plafonne à ce qu'il reste à livrer (quantite − déjà réceptionnée)
        restant = max(0, ligne.quantite - (ligne.quantite_deja_recue or 0))
        qty = min(max(0, int(lignes_livrees.get(ligne.produit_id, 0) or 0)), restant)
        ligne.quantite_livree = qty
        ligne.quantite_deja_livree = (ligne.quantite_deja_livree or 0) + qty
        if qty > 0:
            dispo = max(0, soldes.get(ligne.produit_id, 0) - reserves_autres.get(ligne.produit_id, 0))
            if qty > dispo:
                manques.append(
                    f"{ligne.produit.code} — {ligne.produit.designation} : "
                    f"{qty} à livrer, seulement {dispo} disponible au dépôt"
                )
            else:
                lignes_expediees.append(ligne)
        qty_total_restant += max(0, restant - qty)

    if manques:
        raise ValidationError(
            "Stock dépôt insuffisant : " + " | ".join(manques)
        )

    for ligne in lignes:
        ligne.save(update_fields=["quantite_livree", "quantite_deja_livree"])

    # Réservations créées pour bloquer le stock jusqu'à la réception
    StockReserveDepot.objects.bulk_create([
        StockReserveDepot(commande=commande, produit=l.produit, quantite=l.quantite_livree)
        for l in lignes_expediees
    ])

    commande.statut = StatutCommandeMagasin.LIVREE
    commande.livree_le = tz.now()
    commande.livree_par = par
    commande.livraison_close = clore
    commande.save(update_fields=["statut", "livree_le", "livree_par", "livraison_close"])

    est_partielle = qty_total_restant > 0 and not clore
    lien = f"/approvisionnement/magasin/{commande.pk}/"
    if est_partielle:
        titre = f"Livraison partielle #{commande.numero} — {commande.magasin.nom}"
        message = (
            f"{par.get_full_name() or par.username} a expédié une partie de la commande #{commande.numero}. "
            f"Il reste {qty_total_restant} unité(s) à envoyer."
        )
    else:
        titre = f"Livraison #{commande.numero} confirmée — {commande.magasin.nom}"
        message = f"{par.get_full_name() or par.username} a préparé et expédié la commande #{commande.numero}."
    if commande.cree_par:
        _purger_notifs_obsoletes(commande.cree_par, lien, [TypeNotification.DEMANDE_VALIDEE])
        creer_notification(
            commande.cree_par,
            type=TypeNotification.LIVRAISON_CONFIRMEE,
            titre=titre,
            message=message,
            lien=lien,
        )
    _notifier_superviseurs_magasin(
        commande,
        type=TypeNotification.LIVRAISON_CONFIRMEE,
        titre=titre,
        message=message,
    )
    return commande


@transaction.atomic
def receptionner_commande_magasin(commande, lignes_recues: dict, motifs_ecart: dict, *, par):
    """
    GEST_MAGASIN confirme la réception au magasin (LIVREE → RECUE).

    `lignes_recues`  : {produit_id: quantite_recue}
    `motifs_ecart`   : {produit_id: motif} — obligatoire si quantite_recue ≠ quantite_livree

    Mouvement ENTREE_APPRO_MAGASIN vers le magasin, SORTIE_APPRO_MAGASIN depuis le dépôt.
    Ordre de verrouillage : magasin SoldeStock par produit.code ASC.

    Section M17 du cahier des charges.
    """
    if commande.statut != StatutCommandeMagasin.LIVREE:
        raise ValidationError("Seule une commande livrée peut être réceptionnée.")

    from core.models import Site

    depot = Site.objects.filter(actif=True).first()
    if not depot:
        raise ValidationError("Aucun site actif trouvé.")

    magasin = commande.magasin
    lignes = list(commande.lignes.select_related("produit").order_by("produit__code"))
    produit_ids = [l.produit_id for l in lignes]

    # Verrou dépôt d'abord, magasin ensuite — produit.code ASC dans chaque groupe
    list(SoldeStock.objects.select_for_update().filter(site=depot, produit_id__in=produit_ids).order_by("produit__code"))
    list(SoldeStock.objects.select_for_update().filter(site=magasin, produit_id__in=produit_ids).order_by("produit__code"))

    ref = f"REC-MAG-{commande.pk}-{tz.now().strftime('%Y%m%d%H%M%S')}"

    for ligne in lignes:
        qty_livree = ligne.quantite_livree or 0
        qty = max(0, min(int(lignes_recues.get(ligne.produit_id, 0) or 0), qty_livree))
        ligne.quantite_recue = qty
        ligne.motif_ecart = motifs_ecart.get(ligne.produit_id, "").strip()
        ligne.quantite_deja_recue = (ligne.quantite_deja_recue or 0) + qty
        if qty > 0:
            enregistrer_mouvement(
                site=depot,
                produit=ligne.produit,
                type=TypeMouvement.SORTIE_APPRO_MAGASIN,
                quantite=-qty,
                auteur=par,
                reference_document=ref,
                commentaire=f"Réception magasin {magasin.nom}",
            )
            enregistrer_mouvement(
                site=magasin,
                produit=ligne.produit,
                type=TypeMouvement.ENTREE_APPRO_MAGASIN,
                quantite=qty,
                auteur=par,
                reference_document=ref,
                commentaire="Réception depuis dépôt",
            )
        # Prépare les champs à sauvegarder
        if ligne.quantite_deja_recue >= ligne.quantite:
            ligne.save(update_fields=["quantite_recue", "motif_ecart", "quantite_deja_recue"])
        else:
            # Réinitialise la tournée courante pour permettre un nouvel envoi
            ligne.quantite_livree = None
            ligne.quantite_recue = None
            ligne.save(update_fields=["quantite_livree", "quantite_recue", "motif_ecart", "quantite_deja_recue"])

    StockReserveDepot.objects.filter(commande=commande).delete()

    toutes_recues = all((l.quantite_deja_recue or 0) >= l.quantite for l in lignes)
    # Les livraisons directes (validee_par non renseigné) se clôturent toujours à la réception
    est_livraison_directe = commande.validee_par_id is None

    if toutes_recues or commande.livraison_close or est_livraison_directe:
        commande.statut = StatutCommandeMagasin.RECUE
        commande.recue_le = tz.now()
        commande.recue_par = par
        commande.save(update_fields=["statut", "recue_le", "recue_par"])
        if commande.livraison_close and not toutes_recues:
            reliquat = sum(max(0, l.quantite - (l.quantite_deja_recue or 0)) for l in lignes)
            _notifier_dg_manager_partage(
                commande,
                type=TypeNotification.LIVRAISON_CONFIRMEE,
                titre=f"Commande CM#{commande.numero} clôturée partiellement — {commande.magasin.nom}",
                message=(
                    f"{par.get_full_name() or par.username} a réceptionné la dernière livraison de la commande #{commande.numero}. "
                    f"La commande est clôturée ({reliquat} unité(s) non livrée(s))."
                ),
            )
    else:
        # Livraison partielle : repasse en VALIDEE, le dépôt doit envoyer le reliquat
        commande.statut = StatutCommandeMagasin.VALIDEE
        commande.livree_le = None
        commande.livree_par = None
        commande.save(update_fields=["statut", "livree_le", "livree_par"])
        reliquat = sum(max(0, l.quantite - (l.quantite_deja_recue or 0)) for l in lignes)
        _notifier_dg_manager_partage(
            commande,
            type=TypeNotification.LIVRAISON_CONFIRMEE,
            titre=f"Réception partielle CM#{commande.numero} — {commande.magasin.nom}",
            message=(
                f"{par.get_full_name() or par.username} a réceptionné partiellement la commande #{commande.numero}. "
                f"Il reste {reliquat} unité(s) à expédier."
            ),
        )
    return commande


@transaction.atomic
def sauvegarder_livraison_directe_brouillon(magasin, produit_quantites: dict, observations: str, *, par, commande_existante=None):
    """Sauvegarde une livraison directe en BROUILLON (sans toucher au stock)."""
    from catalogue.models import Produit

    lignes_valides = {}
    for pid, qty in produit_quantites.items():
        try:
            q = int(qty)
            if q > 0:
                lignes_valides[int(pid)] = q
        except (ValueError, TypeError):
            pass

    if not lignes_valides:
        raise ValidationError("Ajoutez au moins une ligne avec une quantité > 0.")

    obs = "[LD] " + observations.strip() if observations.strip() else "[LD]"

    if commande_existante:
        commande = commande_existante
        commande.magasin = magasin
        commande.observations = obs
        commande.save(update_fields=["magasin", "observations"])
        commande.lignes.all().delete()
    else:
        commande = CommandeMagasin.objects.create(
            magasin=magasin,
            statut=StatutCommandeMagasin.BROUILLON,
            observations=obs,
            cree_par=par,
        )

    produits_par_id = {
        p.pk: p
        for p in Produit.objects.filter(pk__in=lignes_valides.keys()).order_by("code")
    }
    for produit in sorted(produits_par_id.values(), key=lambda p: p.code):
        CommandeMagasinLigne.objects.create(
            commande=commande,
            produit=produit,
            quantite=lignes_valides[produit.pk],
        )
    return commande


@transaction.atomic
def valider_livraison_directe(commande, *, par):
    """Valide une livraison directe BROUILLON → LIVREE. Vérifie stock dépôt et crée StockReserveDepot."""
    from core.models import Site

    if commande.statut != StatutCommandeMagasin.BROUILLON:
        raise ValidationError("Seule une livraison directe en brouillon peut être validée.")

    depot = Site.objects.filter(actif=True).first()
    if not depot:
        raise ValidationError("Aucun site actif trouvé.")

    lignes = list(commande.lignes.select_related("produit").order_by("produit__code"))
    produit_ids = [l.produit_id for l in lignes]

    soldes = {
        s.produit_id: s.quantite
        for s in SoldeStock.objects.select_for_update()
        .filter(site=depot, produit_id__in=produit_ids)
        .order_by("produit__code")
    }
    reserves = dict(
        StockReserveDepot.objects.filter(produit_id__in=produit_ids)
        .exclude(commande=commande)
        .values("produit_id")
        .annotate(total=Sum("quantite"))
        .values_list("produit_id", "total")
    )

    manques = []
    for ligne in lignes:
        dispo = max(0, soldes.get(ligne.produit_id, 0) - reserves.get(ligne.produit_id, 0))
        if dispo < ligne.quantite:
            manques.append(
                f"{ligne.produit.code} — {ligne.produit.designation} : "
                f"demandé {ligne.quantite}, disponible {dispo}"
            )
    if manques:
        raise ValidationError("Stock insuffisant au dépôt : " + " | ".join(manques))

    commande.statut = StatutCommandeMagasin.LIVREE
    commande.livree_le = tz.now()
    commande.livree_par = par
    commande.save(update_fields=["statut", "livree_le", "livree_par"])

    for ligne in lignes:
        CommandeMagasinLigne.objects.filter(pk=ligne.pk).update(quantite_livree=ligne.quantite)
        StockReserveDepot.objects.create(
            commande=commande,
            produit=ligne.produit,
            quantite=ligne.quantite,
        )

    lien = f"/approvisionnement/magasin/{commande.pk}/reception/"
    titre = f"Livraison directe #{commande.numero} à réceptionner — {commande.magasin.nom}"
    message = f"{par.get_full_name() or par.username} vous a envoyé une livraison directe pour {commande.magasin.nom}. Merci de confirmer la réception."
    for chef in Utilisateur.objects.filter(is_active=True, profil=Profil.CHEF_EQUIPE).exclude(pk=par.pk):
        if chef.sites_autorises().filter(pk=commande.magasin_id).exists():
            creer_notification(chef, type=TypeNotification.LIVRAISON_PRETE, titre=titre, message=message, lien=lien)

    return commande


@transaction.atomic
def livraison_directe_magasin(magasin, produit_quantites: dict, *, par):
    """
    DG ou Manager envoie directement des articles du dépôt vers un magasin,
    sans commande préalable.

    `produit_quantites` : {produit_id: quantite}

    Crée une CommandeMagasin en statut LIVREE avec réservation du stock dépôt.
    Le stock sera débité lors de la réception par le gestionnaire (RECUE).

    Section M17 du cahier des charges.
    """
    from catalogue.models import Produit
    from core.models import Site

    lignes_valides = {pid: qty for pid, qty in produit_quantites.items() if int(qty) > 0}
    if not lignes_valides:
        raise ValidationError("Au moins une quantité doit être supérieure à 0.")

    depot = Site.objects.filter(actif=True).first()
    if not depot:
        raise ValidationError("Aucun site actif trouvé.")

    produit_ids = list(lignes_valides.keys())

    commande = CommandeMagasin.objects.create(
        magasin=magasin,
        statut=StatutCommandeMagasin.LIVREE,
        observations="Livraison directe",
        cree_par=par,
        livree_par=par,
        livree_le=tz.now(),
    )

    produits_par_id = {
        p.pk: p
        for p in Produit.objects.filter(pk__in=produit_ids).order_by("code")
    }

    for produit in sorted(produits_par_id.values(), key=lambda p: p.code):
        qty = int(lignes_valides[produit.pk])
        CommandeMagasinLigne.objects.create(
            commande=commande,
            produit=produit,
            quantite=qty,
            quantite_livree=qty,
        )
        StockReserveDepot.objects.create(
            commande=commande,
            produit=produit,
            quantite=qty,
        )

    return commande


@transaction.atomic
def sauvegarder_livraison_directe_ecole_brouillon(ecole, produit_quantites: dict, observations: str, *, par, commande_existante=None):
    """Sauvegarde une livraison directe école en BROUILLON (GEST_MAGASIN → école, sans commande)."""
    from catalogue.models import Produit

    lignes_valides = {}
    for pid, qty in produit_quantites.items():
        try:
            q = int(qty)
            if q > 0:
                lignes_valides[int(pid)] = q
        except (ValueError, TypeError):
            pass

    if not lignes_valides:
        raise ValidationError("Ajoutez au moins une ligne avec une quantité > 0.")

    obs = "[LDE] " + observations.strip() if observations.strip() else "[LDE]"

    if commande_existante:
        commande = commande_existante
        commande.ecole = ecole
        commande.observations = obs
        commande.save(update_fields=["ecole", "observations"])
        commande.lignes.all().delete()
    else:
        commande = CommandeEcole.objects.create(
            ecole=ecole,
            statut=StatutCommandeEcole.BROUILLON,
            observations=obs,
            cree_par=par,
        )

    produits_par_id = {
        p.pk: p
        for p in Produit.objects.filter(pk__in=lignes_valides.keys()).order_by("code")
    }
    for produit in sorted(produits_par_id.values(), key=lambda p: p.code):
        CommandeEcoleLigne.objects.create(
            commande=commande,
            produit=produit,
            quantite_demandee=lignes_valides[produit.pk],
        )
    return commande


@transaction.atomic
def valider_livraison_directe_ecole(commande, *, par):
    """Valide une livraison directe école BROUILLON → LIVREE. Vérifie stock magasin et crée StockReserve."""
    if commande.statut != StatutCommandeEcole.BROUILLON:
        raise ValidationError("Seule une livraison directe en brouillon peut être validée.")

    # Modèle FAMIEN plat : pas de magasin intermédiaire, pas de contrôle de stock ni de StockReserve.
    lignes = list(commande.lignes.select_related("produit").order_by("produit__code"))

    commande.statut = StatutCommandeEcole.LIVREE
    commande.livree_le = tz.now()
    commande.livree_par = par
    commande.save(update_fields=["statut", "livree_le", "livree_par"])

    for ligne in lignes:
        CommandeEcoleLigne.objects.filter(pk=ligne.pk).update(quantite_livree=ligne.quantite_demandee)

    lien = f"/approvisionnement/ecole/commande/{commande.pk}/"
    titre = f"Livraison directe #{commande.numero} à réceptionner — {commande.ecole.nom}"
    message = f"{par.get_full_name() or par.username} vous a envoyé une livraison directe. Merci de confirmer la réception."
    for chef in Utilisateur.objects.filter(is_active=True, profil=Profil.CHEF_EQUIPE):
        if chef.site_id == commande.ecole_id:
            creer_notification(chef, type=TypeNotification.LIVRAISON_PRETE, titre=titre, message=message, lien=lien)

    return commande
