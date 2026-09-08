"""
Vues d'approvisionnement (M16 et M17).

Flux école (M16) :
- CHEF_EQUIPE : crée/soumet les commandes ; réceptionne les livraisons.
- GEST_MAGASIN : valide/rejette les commandes soumises ; livre ; peut refuser.
- COMMERCIAL : lecture seule.
- DG/MANAGER/SUPERVISEUR : supervision en lecture seule.

Cloisonnement strict : chaque vue filtre sur le site de l'utilisateur connecté.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from achats.models import Reception, ReceptionLigne
from achats.services import valider_reception as valider_reception_directe
from catalogue.models import Fournisseur, Produit
from core.models import Profil, Site
from stock.models import SoldeStock

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


def _nb_articles_deficit():
    """Nombre de produits avec déficit (demande VALIDEE > stock dispo).

    Dans FAMIEN, pas de dépôt central : on compare les demandes au stock global des sites.
    """
    from collections import defaultdict
    from django.db.models import Sum
    from stock.models import SoldeStock
    soldes = {s.produit_id: s.quantite for s in SoldeStock.objects.all()}
    demandes = defaultdict(int)
    for l in CommandeMagasinLigne.objects.filter(commande__statut=StatutCommandeMagasin.VALIDEE).values("produit_id", "quantite", "quantite_deja_recue"):
        demandes[l["produit_id"]] += max(0, l["quantite"] - (l["quantite_deja_recue"] or 0))
    return sum(
        1 for pid, qte in demandes.items()
        if max(0, qte - soldes.get(pid, 0)) > 0
    )


def _nb_articles_deficit_ecole(user):
    """Nombre d'articles en déficit sur les sites de l'utilisateur (VALIDEE > stock dispo)."""
    from collections import defaultdict
    sites = user.sites_autorises().filter(actif=True)
    if not sites.exists():
        return 0
    soldes = {
        (s.site_id, s.produit_id): s.quantite
        for s in SoldeStock.objects.filter(site__in=sites)
    }
    demandes = defaultdict(int)
    for l in CommandeEcoleLigne.objects.filter(
        commande__statut=StatutCommandeEcole.VALIDEE,
        commande__ecole__in=sites,
    ).values("produit_id", "quantite_demandee", "quantite_deja_recue", "commande__ecole_id"):
        key = (l["commande__ecole_id"], l["produit_id"])
        demandes[key] += max(0, l["quantite_demandee"] - (l["quantite_deja_recue"] or 0))
    return sum(
        1 for (site_id, pid), qte in demandes.items()
        if max(0, qte - soldes.get((site_id, pid), 0)) > 0
    )


@login_required
def hub_approvisionnement(request):
    from django.shortcuts import render as _render
    u = request.user

    _AUTORISES = {Profil.DG, Profil.CHEF_EQUIPE}
    if u.profil not in _AUTORISES and not u.is_superuser:
        return redirect("accueil")

    from achats.models import CommandeFournisseur, StatutCommande
    from approvisionnement.models import (
        CommandeEcole, CommandeMagasin,
        StatutCommandeEcole, StatutCommandeMagasin,
        StockReserve, StockReserveDepot,
    )

    ctx = {
        "nb_commandes": 0,
        "nb_commandes_ecole_a_valider": 0,
        "nb_livraisons_ecole_a_preparer": 0,
        "nb_receptions_ecole_a_faire": 0,
        "nb_produits_reserves_magasin": 0,
        "nb_commandes_magasin_a_valider": 0,
        "nb_livraisons_magasin_a_preparer": 0,
        "nb_livraisons_magasin_a_recevoir": 0,
        "nb_produits_reserves_depot": 0,
        "nb_articles_deficit_ecole": 0,
    }

    if u.profil == Profil.DG or u.is_superuser:
        from ventes.views import _sites_perimetre
        sites = _sites_perimetre(u)
        ctx.update({
            "nb_commandes": CommandeFournisseur.objects.filter(
                site_destination__in=sites,
                statut__in=[StatutCommande.SOUMIS, StatutCommande.VALIDE_N1],
            ).count(),
            "nb_commandes_ecole_a_valider": CommandeEcole.objects.filter(statut=StatutCommandeEcole.SOUMISE).count(),
            "nb_produits_reserves_magasin": StockReserve.objects.values("produit_id").distinct().count(),
            "nb_commandes_magasin_a_valider": CommandeMagasin.objects.filter(statut=StatutCommandeMagasin.SOUMISE).count(),
            "nb_livraisons_magasin_a_preparer": CommandeMagasin.objects.filter(
                statut=StatutCommandeMagasin.VALIDEE, validee_par__isnull=False
            ).count(),
            "nb_livraisons_magasin_a_recevoir": CommandeMagasin.objects.filter(
                statut=StatutCommandeMagasin.LIVREE,
            ).count(),
            "nb_produits_reserves_depot": StockReserveDepot.objects.values("produit_id").distinct().count(),
            "nb_articles_deficit": _nb_articles_deficit(),
        })

    elif u.profil == Profil.CHEF_EQUIPE and u.site:
        ecole = u.site
        if ecole.est_ecole:
            ctx.update({
                "nb_receptions_ecole_a_faire": CommandeEcole.objects.filter(
                    ecole=ecole,
                    statut=StatutCommandeEcole.LIVREE,
                ).count(),
            })

    return _render(request, "approvisionnement/hub.html", ctx)
from .services import (
    livraison_directe_magasin as _livraison_directe_service,
    livrer_commande_ecole,
    livrer_commande_magasin,
    receptionner_commande_ecole,
    receptionner_commande_magasin,
    refuser_livraison_ecole,
    refuser_livraison_magasin,
    rejeter_commande_ecole,
    rejeter_commande_magasin,
    sauvegarder_livraison_directe_brouillon,
    sauvegarder_livraison_directe_ecole_brouillon,
    soumettre_commande_ecole,
    soumettre_commande_magasin,
    stock_disponible,
    valider_commande_ecole,
    valider_commande_magasin,
    valider_livraison_directe,
    valider_livraison_directe_ecole,
)


_SUPERVISION = {Profil.DG}


# ─── Utilitaires ─────────────────────────────────────────────────────────────


def _exiger_chef(request):
    """Retourne True si l'utilisateur est chef d'équipe, False sinon (avec message)."""
    if request.user.profil != Profil.CHEF_EQUIPE:
        messages.error(request, "Accès réservé aux chefs d'équipe.")
        return False
    return True


def _exiger_gestionnaire(request):
    """Retourne True si l'utilisateur est DG (gestionnaire central dans FAMIEN)."""
    if request.user.profil != Profil.DG and not request.user.is_superuser:
        messages.error(request, "Accès réservé au DG.")
        return False
    return True


def _magasin_du_chef(request):
    """Retourne le site de l'utilisateur (dans FAMIEN, pas de magasin intermédiaire)."""
    return request.user.site


# ─── Chef d'équipe : commandes ───────────────────────────────────────────────


@login_required
def commandes_liste(request):
    """Liste des commandes de l'école. Chef d'équipe : toutes actions. Caissière : lecture seule.
    DG / MANAGER / SUPERVISEUR : supervision en lecture seule avec filtres."""
    u = request.user

    filtre_commande = request.GET.get("commande") or ""
    filtre_statut = request.GET.get("statut") or ""
    filtre_debut = request.GET.get("debut") or ""
    filtre_fin = request.GET.get("fin") or ""

    if u.profil in _SUPERVISION or u.is_superuser:
        filtre_site = request.GET.get("site") or ""

        sites_qs = Site.objects.filter(actif=True).order_by("nom")

        qs = CommandeEcole.objects.exclude(observations__startswith="[LDE]").select_related("ecole", "cree_par").order_by("-cree_le")
        if filtre_site:
            qs = qs.filter(ecole_id=filtre_site)
        if filtre_statut == "ATTENTE":
            qs = qs.filter(statut__in=[StatutCommandeEcole.BROUILLON, StatutCommandeEcole.SOUMISE])
        elif filtre_statut == "EN_COURS":
            qs = qs.filter(statut__in=[StatutCommandeEcole.VALIDEE, StatutCommandeEcole.LIVREE])
        elif filtre_statut == "TERMINE":
            qs = qs.filter(statut__in=[StatutCommandeEcole.RECUE, StatutCommandeEcole.REJETEE])
        if filtre_commande.isdigit():
            qs = qs.filter(pk=filtre_commande)
        if filtre_debut:
            qs = qs.filter(cree_le__date__gte=filtre_debut)
        if filtre_fin:
            qs = qs.filter(cree_le__date__lte=filtre_fin)

        commandes_filtre = (
            CommandeEcole.objects.exclude(observations__startswith="[LDE]").select_related("ecole").order_by("-cree_le")
        )

        return render(request, "approvisionnement/commandes_liste.html", {
            "commandes": qs[:200],
            "commandes_filtre": commandes_filtre,
            "ecoles": sites_qs,
            "filtre_ecole": filtre_site,
            "filtre_commande": filtre_commande,
            "filtre_statut": filtre_statut,
            "filtre_debut": filtre_debut,
            "filtre_fin": filtre_fin,
            "supervision": True,
        })

    if u.profil != Profil.CHEF_EQUIPE:
        messages.error(request, "Accès non autorisé.")
        return redirect("accueil")

    ecole = u.site
    if ecole is None or not ecole.est_ecole:
        messages.error(request, "Votre compte n'est rattaché à aucun site.")
        return redirect("accueil")

    qs = (
        CommandeEcole.objects.filter(ecole=ecole)
        .exclude(observations__startswith="[LDE]")
        .select_related("ecole", "cree_par").order_by("-cree_le")
    )
    commandes_filtre = qs
    if filtre_statut == "ATTENTE":
        qs = qs.filter(statut__in=[StatutCommandeEcole.BROUILLON, StatutCommandeEcole.SOUMISE])
    elif filtre_statut == "EN_COURS":
        qs = qs.filter(statut__in=[StatutCommandeEcole.VALIDEE, StatutCommandeEcole.LIVREE])
    elif filtre_statut == "TERMINE":
        qs = qs.filter(statut__in=[StatutCommandeEcole.RECUE, StatutCommandeEcole.REJETEE])
    if filtre_commande.isdigit():
        qs = qs.filter(pk=filtre_commande)
    if filtre_debut:
        qs = qs.filter(cree_le__date__gte=filtre_debut)
    if filtre_fin:
        qs = qs.filter(cree_le__date__lte=filtre_fin)
    return render(request, "approvisionnement/commandes_liste.html", {
        "commandes": qs[:100],
        "commandes_filtre": commandes_filtre,
        "ecole": ecole,
        "filtre_commande": filtre_commande,
        "filtre_statut": filtre_statut,
        "filtre_debut": filtre_debut,
        "filtre_fin": filtre_fin,
    })


@login_required
def commande_formulaire(request):
    """Création d'une nouvelle commande école."""
    if not _exiger_chef(request):
        return redirect("accueil")

    ecole = request.user.site
    if ecole is None:
        messages.error(request, "Votre compte n'est rattaché à aucun site.")
        return redirect("accueil")

    produits = Produit.objects.filter(actif=True).order_by("code")
    _, stock_ecole_json, stock_max_ecole_json = _get_stock_ecole_context(ecole, ecole)
    stock_magasin_json = stock_ecole_json

    observations_init = ""
    lignes_soumises_json = "[]"

    if request.method == "POST":
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")
        observations_init = request.POST.get("observations", "")

        lignes = []
        for pid, q in zip(produit_ids, quantites):
            try:
                q_int = int(q)
                if q_int > 0 and pid:
                    lignes.append((int(pid), q_int))
            except (ValueError, TypeError):
                pass

        lignes_soumises_json = json.dumps([{"pid": pid, "qty": q} for pid, q in lignes])

        if not lignes:
            messages.error(request, "Ajoutez au moins une ligne.")
        else:
            erreurs = _valider_seuils_ecole(ecole, lignes)
            if erreurs:
                for e in erreurs:
                    messages.error(request, e)
            else:
                try:
                    with transaction.atomic():
                        commande = CommandeEcole.objects.create(
                            ecole=ecole,
                            observations=observations_init,
                            cree_par=request.user,
                        )
                        CommandeEcoleLigne.objects.bulk_create([
                            CommandeEcoleLigne(
                                commande=commande,
                                produit_id=pid,
                                quantite_demandee=q,
                            )
                            for pid, q in lignes
                        ])
                    messages.success(request, "Commande créée en brouillon.")
                    return redirect("commande_ecole_detail", pk=commande.pk)
                except Exception as e:
                    messages.error(request, str(e))

    return render(request, "approvisionnement/commande_formulaire.html", {
        "ecole": ecole,
        "produits": produits,
        "stock_magasin_json": stock_magasin_json,
        "stock_ecole_json": stock_ecole_json,
        "stock_max_ecole_json": stock_max_ecole_json,
        "lignes_existantes_json": lignes_soumises_json,
        "observations_init": observations_init,
        "erreur_magasin": False,
    })


@login_required
def commande_detail(request, pk):
    """Détail d'une commande école, accessible selon le profil."""
    u = request.user

    qs = CommandeEcole.objects.select_related(
        "ecole",
        "cree_par", "soumise_par", "validee_par",
        "livree_par", "recue_par", "rejete_par",
    )

    if False:  # Profil.GEST_MAGASIN supprimé — garde-fou inatteignable
        commande = get_object_or_404(qs, pk=pk)
    elif u.profil in _SUPERVISION or u.is_superuser:
        commande = get_object_or_404(qs, pk=pk)
    else:
        ecole = u.site
        if ecole is None:
            messages.error(request, "Votre compte n'est rattaché à aucun site.")
            return redirect("accueil")
        commande = get_object_or_404(qs, pk=pk, ecole=ecole)

    lignes = commande.lignes.select_related("produit").order_by("produit__code")

    from django.db.models import F as _F, Q as _Q
    has_livraison = lignes.filter(quantite_deja_livree__gt=0).exists()
    has_partial = lignes.filter(quantite_deja_livree__gt=0, quantite_deja_livree__lt=_F("quantite_demandee")).exists()
    toutes_recues = not lignes.filter(
        _Q(quantite_deja_recue__isnull=True) | _Q(quantite_deja_recue__lt=_F("quantite_demandee"))
    ).exists()
    show_livraison = has_livraison or commande.statut in (
        StatutCommandeEcole.LIVREE, StatutCommandeEcole.RECUE
    )

    peut_modifier = (
        commande.statut == StatutCommandeEcole.BROUILLON
        and u.profil == Profil.CHEF_EQUIPE
    )
    peut_soumettre = (
        commande.statut == StatutCommandeEcole.BROUILLON
        and u.profil == Profil.CHEF_EQUIPE
    )
    peut_supprimer = (
        commande.statut == StatutCommandeEcole.BROUILLON
        and u.profil == Profil.CHEF_EQUIPE
    )
    peut_valider = (
        commande.statut == StatutCommandeEcole.SOUMISE
        and u.profil == Profil.DG
    )
    peut_rejeter = (
        commande.statut == StatutCommandeEcole.SOUMISE
        and u.profil == Profil.DG
    )
    peut_livrer = (
        commande.statut == StatutCommandeEcole.VALIDEE
        and u.profil == Profil.DG
    )
    peut_refuser_livraison = (
        commande.statut == StatutCommandeEcole.VALIDEE
        and u.profil == Profil.DG
    )
    peut_receptionner = (
        commande.statut == StatutCommandeEcole.LIVREE
        and u.profil == Profil.CHEF_EQUIPE
    )

    return render(request, "approvisionnement/commande_detail.html", {
        "commande": commande,
        "lignes": lignes,
        "has_partial": has_partial,
        "has_livraison": has_livraison,
        "toutes_recues": toutes_recues,
        "show_livraison": show_livraison,
        "peut_modifier": peut_modifier,
        "peut_soumettre": peut_soumettre,
        "peut_supprimer": peut_supprimer,
        "peut_valider": peut_valider,
        "peut_rejeter": peut_rejeter,
        "peut_livrer": peut_livrer,
        "peut_refuser_livraison": peut_refuser_livraison,
        "peut_receptionner": peut_receptionner,
    })


@login_required
def commande_modifier(request, pk):
    """Modification d'une commande brouillon ou soumise (repasse en brouillon si soumise)."""
    if not _exiger_chef(request):
        return redirect("accueil")

    ecole = request.user.site
    commande = get_object_or_404(
        CommandeEcole,
        pk=pk,
        ecole=ecole,
        statut__in=[StatutCommandeEcole.BROUILLON, StatutCommandeEcole.SOUMISE],
    )

    produits = Produit.objects.filter(actif=True).order_by("code")
    _, stock_ecole_json, stock_max_ecole_json = _get_stock_ecole_context(ecole, ecole)
    stock_magasin_json = stock_ecole_json
    lignes_existantes_json = json.dumps([
        {"pid": l.produit_id, "qty": l.quantite_demandee}
        for l in commande.lignes.order_by("produit__code")
    ])

    if request.method == "POST":
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")
        observations = request.POST.get("observations", "")

        lignes = []
        for pid, q in zip(produit_ids, quantites):
            try:
                q_int = int(q)
                if q_int > 0 and pid:
                    lignes.append((int(pid), q_int))
            except (ValueError, TypeError):
                pass

        if not lignes:
            messages.error(request, "Ajoutez au moins une ligne.")
        else:
            erreurs = _valider_seuils_ecole(ecole, lignes)
            if erreurs:
                messages.error(request, "Dépassement du seuil maximal : " + " — ".join(erreurs))
            else:
                try:
                    with transaction.atomic():
                        commande.observations = observations
                        # Si la commande était soumise, la repasser en brouillon
                        if commande.statut == StatutCommandeEcole.SOUMISE:
                            commande.statut = StatutCommandeEcole.BROUILLON
                        commande.save(update_fields=["observations", "statut"])
                        commande.lignes.all().delete()
                        CommandeEcoleLigne.objects.bulk_create([
                            CommandeEcoleLigne(
                                commande=commande,
                                produit_id=pid,
                                quantite_demandee=q,
                            )
                            for pid, q in lignes
                        ])
                    messages.success(request, "Commande mise à jour.")
                    return redirect("commande_ecole_detail", pk=commande.pk)
                except Exception as e:
                    messages.error(request, str(e))

    return render(request, "approvisionnement/commande_formulaire.html", {
        "ecole": ecole,
        "produits": produits,
        "stock_magasin_json": stock_magasin_json,
        "stock_ecole_json": stock_ecole_json,
        "stock_max_ecole_json": stock_max_ecole_json,
        "lignes_existantes_json": lignes_existantes_json,
        "commande": commande,
        "erreur_magasin": False,
    })


@login_required
def commande_supprimer(request, pk):
    """Suppression d'une commande brouillon (POST only)."""
    if not _exiger_chef(request):
        return redirect("accueil")

    ecole = request.user.site
    commande = get_object_or_404(
        CommandeEcole,
        pk=pk,
        ecole=ecole,
        statut=StatutCommandeEcole.BROUILLON,
    )
    if request.method == "POST":
        commande.delete()
        messages.success(request, "Commande supprimée.")
    return redirect("commandes_ecole_liste")


@login_required
def commande_soumettre(request, pk):
    """Soumet la commande au gestionnaire du magasin."""
    if not _exiger_chef(request):
        return redirect("accueil")

    ecole = request.user.site
    commande = get_object_or_404(
        CommandeEcole,
        pk=pk,
        ecole=ecole,
        statut=StatutCommandeEcole.BROUILLON,
    )
    if request.method == "POST":
        try:
            soumettre_commande_ecole(commande, par=request.user)
            messages.success(request, "Commande soumise au gestionnaire.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("commande_ecole_detail", pk=pk)


@login_required
def commande_ecole_valider(request, pk):
    """DG valide la commande (SOUMISE → VALIDEE, crée StockReserve)."""
    u = request.user
    if u.profil != Profil.DG and not u.is_superuser:
        messages.error(request, "Accès réservé au DG.")
        return redirect("accueil")

    commande = get_object_or_404(
        CommandeEcole.objects.select_related("ecole"),
        pk=pk,
        statut=StatutCommandeEcole.SOUMISE,
    )
    if request.method == "POST":
        try:
            valider_commande_ecole(commande, par=u)
            messages.success(request, "Commande validée — réservation de stock créée.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("commande_ecole_detail", pk=pk)


@login_required
def commande_ecole_rejeter(request, pk):
    """DG rejette une commande soumise avec motif obligatoire."""
    u = request.user
    if u.profil != Profil.DG and not u.is_superuser:
        messages.error(request, "Accès réservé au DG.")
        return redirect("accueil")

    commande = get_object_or_404(
        CommandeEcole,
        pk=pk,
        statut=StatutCommandeEcole.SOUMISE,
    )
    if request.method == "POST":
        motif = request.POST.get("motif", "").strip()
        try:
            rejeter_commande_ecole(commande, par=u, motif=motif)
            messages.success(request, "Commande rejetée.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("commande_ecole_detail", pk=pk)


@login_required
def receptions_liste(request):
    """Liste des commandes livrées / partiellement reçues pour le périmètre de l'utilisateur.
    DG / MANAGER / SUPERVISEUR : supervision en lecture seule avec filtres."""
    from django.db.models import Exists, OuterRef
    from django.db.models.functions import Greatest

    u = request.user

    def _base_qs(extra_filter=None):
        _partielle = CommandeEcoleLigne.objects.filter(
            commande=OuterRef("pk"), quantite_deja_recue__gt=0
        )
        qs = (
            CommandeEcole.objects
            .annotate(
                has_partial=Exists(_partielle),
                derniere_maj=Greatest("recue_le", "rejete_le", "livree_le", "validee_le"),
            )
            .filter(
                Q(statut__in=[StatutCommandeEcole.LIVREE, StatutCommandeEcole.RECUE])
                | Q(statut=StatutCommandeEcole.VALIDEE, has_partial=True, validee_par__isnull=False)
                | Q(statut=StatutCommandeEcole.REJETEE, has_partial=True, validee_par__isnull=False)
            )
            .select_related("ecole", "cree_par", "livree_par")
        )
        if extra_filter:
            qs = qs.filter(**extra_filter)
        return qs.order_by("-derniere_maj")

    def _apply_statut(qs, filtre_statut):
        if filtre_statut == "EN_COURS":
            return qs.filter(statut__in=[StatutCommandeEcole.LIVREE, StatutCommandeEcole.VALIDEE])
        if filtre_statut == "TERMINE":
            return qs.filter(statut__in=[StatutCommandeEcole.RECUE, StatutCommandeEcole.REJETEE])
        if filtre_statut:
            return qs.filter(statut=filtre_statut)
        return qs

    if u.profil in _SUPERVISION or u.is_superuser:
        ecole_id = request.GET.get("ecole") or ""
        filtre_reception = request.GET.get("reception") or ""
        filtre_statut = request.GET.get("statut") or ""
        debut = request.GET.get("debut") or ""
        fin = request.GET.get("fin") or ""

        sites_qs = Site.objects.filter(actif=True).order_by("nom")

        qs = _base_qs()
        receptions_filtre = qs
        if filtre_reception.isdigit():
            qs = qs.filter(pk=filtre_reception)
        if ecole_id:
            qs = qs.filter(ecole_id=ecole_id)
        qs = _apply_statut(qs, filtre_statut)
        if debut:
            qs = qs.filter(derniere_maj__date__gte=debut)
        if fin:
            qs = qs.filter(derniere_maj__date__lte=fin)

        return render(request, "approvisionnement/receptions_liste.html", {
            "commandes": qs[:200],
            "receptions_filtre": receptions_filtre,
            "ecoles": sites_qs,
            "filtre_ecole": ecole_id,
            "filtre_reception": filtre_reception,
            "filtre_statut": filtre_statut,
            "filtre_debut": debut,
            "filtre_fin": fin,
            "supervision": True,
        })

    if not _exiger_chef(request):
        return redirect("accueil")

    ecole = u.site
    if ecole is None:
        messages.error(request, "Votre compte n'est rattaché à aucun site.")
        return redirect("accueil")

    filtre_reception = request.GET.get("reception") or ""
    filtre_statut = request.GET.get("statut") or ""
    filtre_debut = request.GET.get("debut") or ""
    filtre_fin = request.GET.get("fin") or ""
    qs = _base_qs({"ecole": ecole})
    receptions_filtre = qs
    if filtre_reception.isdigit():
        qs = qs.filter(pk=filtre_reception)
    qs = _apply_statut(qs, filtre_statut)
    if filtre_debut:
        qs = qs.filter(derniere_maj__date__gte=filtre_debut)
    if filtre_fin:
        qs = qs.filter(derniere_maj__date__lte=filtre_fin)
    return render(request, "approvisionnement/receptions_liste.html", {
        "commandes": qs[:200],
        "receptions_filtre": receptions_filtre,
        "filtre_reception": filtre_reception,
        "filtre_statut": filtre_statut,
        "filtre_debut": filtre_debut,
        "filtre_fin": filtre_fin,
    })


@login_required
def reception_valider(request, pk):
    """Formulaire de réception d'une commande livrée."""
    if not _exiger_chef(request):
        return redirect("accueil")

    ecole = request.user.site
    commande = get_object_or_404(
        CommandeEcole.objects.select_related("ecole"),
        pk=pk,
        ecole=ecole,
        statut=StatutCommandeEcole.LIVREE,
    )
    lignes = commande.lignes.select_related("produit").filter(quantite_livree__gt=0).order_by("produit__code")

    if request.method == "POST":
        lignes_recues = {}
        motifs_ecart = {}
        for ligne in lignes:
            val = request.POST.get(f"quantite_recue_{ligne.produit_id}", "0")
            try:
                lignes_recues[ligne.produit_id] = int(val)
            except (ValueError, TypeError):
                lignes_recues[ligne.produit_id] = 0
            motifs_ecart[ligne.produit_id] = request.POST.get(f"motif_ecart_{ligne.produit_id}", "")

        try:
            receptionner_commande_ecole(commande, lignes_recues, motifs_ecart, par=request.user)
            if commande.statut == StatutCommandeEcole.RECUE:
                messages.success(request, "Réception confirmée — stock du site mis à jour.")
            else:
                messages.success(request, "Réception partielle enregistrée — le magasin sera notifié pour le reliquat.")
            return redirect("commande_ecole_detail", pk=pk)
        except ValidationError as e:
            messages.error(request, str(e.message))

    return render(request, "approvisionnement/reception_valider.html", {
        "commande": commande,
        "lignes": lignes,
    })


# ─── Gestionnaire de magasin : livraisons ────────────────────────────────────


@login_required
def livraisons_liste(request):
    """Liste des commandes soumises au magasin.
    DG / MANAGER / SUPERVISEUR : supervision en lecture seule avec filtres."""
    u = request.user

    # DG voit toutes les livraisons ; CHEF_EQUIPE voit celles de son site
    ecole_id = request.GET.get("ecole") or ""
    debut = request.GET.get("debut") or ""
    fin = request.GET.get("fin") or ""

    sites_qs = Site.objects.filter(actif=True).order_by("nom")

    _lde = Q(observations__startswith="[LDE]")
    qs_base = (
        Q(statut__in=[StatutCommandeEcole.VALIDEE, StatutCommandeEcole.LIVREE])
        | (_lde & Q(statut=StatutCommandeEcole.BROUILLON))
    )

    qs = (
        CommandeEcole.objects.filter(qs_base)
        .select_related("ecole", "cree_par", "validee_par")
        .order_by("-cree_le")
    )

    if u.profil == Profil.CHEF_EQUIPE and u.site:
        qs = qs.filter(ecole=u.site)

    if ecole_id:
        qs = qs.filter(ecole_id=ecole_id)
    if debut:
        qs = qs.filter(cree_le__date__gte=debut)
    if fin:
        qs = qs.filter(cree_le__date__lte=fin)

    return render(request, "approvisionnement/livraisons_liste.html", {
        "commandes": qs[:200],
        "ecoles": sites_qs,
        "filtre_ecole": ecole_id,
        "filtre_debut": debut,
        "filtre_fin": fin,
        "supervision": u.profil == Profil.DG or u.is_superuser,
    })


@login_required
def livraison_traiter(request, pk):
    """DG prépare la livraison depuis le site source vers le site destinataire (VALIDEE → LIVREE)."""
    if not _exiger_gestionnaire(request):
        return redirect("accueil")

    commande = get_object_or_404(
        CommandeEcole.objects.select_related("ecole"),
        pk=pk,
        statut=StatutCommandeEcole.VALIDEE,
    )
    magasin = commande.ecole  # Dans FAMIEN, le DG livre directement au site
    lignes = list(commande.lignes.select_related("produit").order_by("produit__code"))
    produit_ids = [l.produit_id for l in lignes]

    # Stock disponible = stock total − réservations des AUTRES commandes
    # (la réservation courante appartient à cette commande ; on l'inclut dans le disponible)
    soldes = {
        s.produit_id: s.quantite
        for s in SoldeStock.objects.filter(site=magasin, produit_id__in=produit_ids)
    }
    reserves_autres = {
        r["produit_id"]: r["total"]
        for r in StockReserve.objects
        .filter(produit_id__in=produit_ids, magasin=magasin)
        .exclude(commande=commande)
        .values("produit_id")
        .annotate(total=Sum("quantite"))
    }
    lignes_avec_dispo = []
    for l in lignes:
        quantite_restante = max(0, l.quantite_demandee - (l.quantite_deja_recue or 0))
        dispo = max(0, soldes.get(l.produit_id, 0) - reserves_autres.get(l.produit_id, 0))
        lignes_avec_dispo.append({
            "ligne": l,
            "dispo": dispo,
            "quantite_restante": quantite_restante,
            "max_livrable": min(dispo, quantite_restante),
        })
    lignes_avec_dispo = [item for item in lignes_avec_dispo if item["quantite_restante"] > 0]

    if request.method == "POST":
        lignes_livrees = {}
        for item in lignes_avec_dispo:
            l = item["ligne"]
            val = request.POST.get(f"quantite_livree_{l.produit_id}", "0")
            try:
                lignes_livrees[l.produit_id] = int(val)
            except (ValueError, TypeError):
                lignes_livrees[l.produit_id] = 0

        try:
            clore = request.POST.get("clore_livraison") == "1"
            livrer_commande_ecole(commande, lignes_livrees, par=request.user, clore=clore)
            if clore:
                messages.success(request, "Livraison confirmée et clôturée — aucun reliquat ne sera expédié.")
            else:
                messages.success(request, "Livraison confirmée — stock toujours réservé au magasin. En attente de réception par le chef d'équipe.")
            return redirect("livraisons_liste")
        except ValidationError as e:
            messages.error(request, str(e.message))

    return render(request, "approvisionnement/livraison_traiter.html", {
        "commande": commande,
        "lignes_avec_dispo": lignes_avec_dispo,
        "magasin": magasin,
    })


@login_required
def commande_ecole_refuser_livraison(request, pk):
    """DG refuse d'envoyer une commande validée (VALIDEE → REJETEE)."""
    if not _exiger_gestionnaire(request):
        return redirect("accueil")

    commande = get_object_or_404(
        CommandeEcole,
        pk=pk,
        statut=StatutCommandeEcole.VALIDEE,
    )
    if request.method == "POST":
        motif = request.POST.get("motif", "").strip()
        try:
            refuser_livraison_ecole(commande, par=request.user, motif=motif)
            messages.success(request, "Livraison refusée — réservation libérée.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("commande_ecole_detail", pk=pk)


@login_required
def stock_reserve(request):
    """Consultation des réservations, groupées par (produit, site). DG voit tout, CHEF_EQUIPE son site."""
    u = request.user
    peut_tout_voir = u.profil == Profil.DG or u.is_superuser
    est_dg_manager = peut_tout_voir

    if not peut_tout_voir and u.profil != Profil.CHEF_EQUIPE:
        messages.error(request, "Accès non autorisé.")
        return redirect("accueil")

    filtre_produit = request.GET.get("produit") or ""
    filtre_site    = request.GET.get("site") or ""

    if peut_tout_voir:
        sites_autorises = u.sites_autorises().filter(actif=True)
        if filtre_site:
            sites_autorises = sites_autorises.filter(pk=filtre_site)

        sites_filtre = u.sites_autorises().filter(actif=True).order_by("nom")

        reserves_qs = (
            StockReserve.objects.filter(magasin__in=sites_autorises)
            .select_related("ecole", "produit", "commande", "magasin")
            .order_by("magasin__nom", "produit__code", "ecole__nom")
        )
        soldes = {
            (s.produit_id, s.site_id): s.quantite
            for s in SoldeStock.objects.filter(site__in=sites_autorises)
        }
        produits_filtre = (
            StockReserve.objects.filter(magasin__in=sites_autorises)
            .select_related("produit").order_by("produit__code")
            .values("produit_id", "produit__code", "produit__designation").distinct()
        )
        magasin = None
    else:
        magasin = u.site
        sites_filtre = None
        if magasin is None:
            messages.error(request, "Votre compte n'est rattaché à aucun site.")
            return redirect("accueil")
        reserves_qs = (
            StockReserve.objects.filter(magasin=magasin)
            .select_related("ecole", "produit", "commande")
            .order_by("produit__code", "ecole__nom")
        )
        soldes = {
            (s.produit_id, s.site_id): s.quantite
            for s in SoldeStock.objects.filter(site=magasin)
        }
        produits_filtre = (
            StockReserve.objects.filter(magasin=magasin)
            .select_related("produit").order_by("produit__code")
            .values("produit_id", "produit__code", "produit__designation").distinct()
        )

    if filtre_produit.isdigit():
        reserves_qs = reserves_qs.filter(produit_id=filtre_produit)

    groupes = {}
    for r in reserves_qs:
        pid = r.produit_id
        mid = r.magasin_id if peut_tout_voir else (magasin.pk if magasin else 0)
        key = (pid, mid)
        if key not in groupes:
            groupes[key] = {
                "produit":      r.produit,
                "magasin":      r.magasin if peut_tout_voir else magasin,
                "stock_total":  soldes.get((pid, mid), 0),
                "reserve_total": 0,
                "lignes":       [],
            }
        groupes[key]["reserve_total"] += r.quantite
        groupes[key]["lignes"].append(r)

    for g in groupes.values():
        g["disponible"] = max(0, g["stock_total"] - g["reserve_total"])

    return render(request, "approvisionnement/stock_reserve.html", {
        "groupes":         groupes.values(),
        "produits_filtre": produits_filtre,
        "filtre_produit":  filtre_produit,
        "filtre_site":     filtre_site,
        "sites_filtre":    sites_filtre,
        "magasin":         magasin,
        "peut_tout_voir":  peut_tout_voir,
        "est_dg_manager":  est_dg_manager,
        "est_superviseur": False,
    })


# ─── Approvisionnement magasin (M17) ─────────────────────────────────────────


def _peut_voir_appro_magasin(user):
    """Vrai pour DG et superuser (dans FAMIEN, le DG gère l'approvisionnement central)."""
    return user.is_superuser or user.profil == Profil.DG


def _est_superviseur(user):
    """Dans FAMIEN, pas de superviseur — seul le DG supervise."""
    return user.is_superuser


def _est_dg_manager(user):
    return user.profil == Profil.DG or user.is_superuser


def _peut_valider_livraison_directe(user, commande):
    if _est_dg_manager(user):
        return True
    return user.profil == Profil.CHEF_EQUIPE and user.site_id == commande.magasin_id


def _est_gestionnaire(user):
    """Dans FAMIEN, le DG joue le rôle de gestionnaire central."""
    return user.profil == Profil.DG or user.is_superuser


@login_required
def commandes_magasin_liste(request):
    """Liste des commandes magasin, filtrée selon le profil de l'utilisateur."""
    u = request.user
    if not _peut_voir_appro_magasin(u):
        messages.error(request, "Accès non autorisé.")
        return redirect("accueil")

    filtre_commande = request.GET.get("commande") or ""
    filtre_magasin = request.GET.get("magasin") or ""
    filtre_statut = request.GET.get("statut") or ""
    debut = request.GET.get("debut") or ""
    fin = request.GET.get("fin") or ""

    qs = (
        CommandeMagasin.objects
        .exclude(observations__startswith="[LD]")
        .select_related("magasin", "cree_par")
        .order_by("-cree_le")
    )

    # Cloisonnement par profil
    if _est_gestionnaire(u) and u.site:
        qs = qs.filter(magasin=u.site)
    elif _est_superviseur(u):
        qs = qs.filter(magasin__in=u.sites_autorises())

    sites_filtre = u.sites_autorises() if _est_superviseur(u) else (
        Site.objects.filter(pk=u.site_id) if _est_gestionnaire(u) and u.site else Site.objects.all()
    )
    commandes_filtre = (
        CommandeMagasin.objects
        .exclude(observations__startswith="[LD]")
        .filter(magasin__in=sites_filtre)
        .select_related("magasin").only("pk", "magasin__nom").order_by("-cree_le")
    )

    afficher_filtre_magasin = _est_dg_manager(u) or (_est_superviseur(u) and not _est_gestionnaire(u))
    magasins = (
        Site.objects.filter(actif=True).order_by("nom")
        if afficher_filtre_magasin else None
    )

    if filtre_commande.isdigit():
        qs = qs.filter(pk=filtre_commande)
    if filtre_magasin:
        qs = qs.filter(magasin_id=filtre_magasin)
    if filtre_statut == "ATTENTE":
        qs = qs.filter(statut__in=[StatutCommandeMagasin.BROUILLON, StatutCommandeMagasin.SOUMISE])
    elif filtre_statut == "EN_COURS":
        qs = qs.filter(statut__in=[StatutCommandeMagasin.VALIDEE, StatutCommandeMagasin.LIVREE])
    elif filtre_statut == "TERMINE":
        qs = qs.filter(statut__in=[StatutCommandeMagasin.RECUE, StatutCommandeMagasin.REJETEE])
    if debut:
        qs = qs.filter(cree_le__date__gte=debut)
    if fin:
        qs = qs.filter(cree_le__date__lte=fin)

    return render(request, "approvisionnement/commandes_magasin_liste.html", {
        "commandes": qs[:200],
        "commandes_filtre": commandes_filtre,
        "magasins": magasins,
        "afficher_filtre_magasin": afficher_filtre_magasin,
        "peut_creer": _est_gestionnaire(u),
        "filtre_commande": filtre_commande,
        "filtre_magasin": filtre_magasin,
        "filtre_statut": filtre_statut,
        "filtre_debut": debut,
        "filtre_fin": fin,
    })


def _get_stock_depot_context():
    """Dans FAMIEN, il n'y a pas de dépôt central distinct — retourne toujours vide.

    L'ancien concept dépôt LEPAD n'existe pas dans FAMIEN ; les stocks sont portés
    directement par chaque site. Cette fonction est conservée pour éviter de modifier
    tous les formulaires qui l'appellent.
    """
    return None, "{}", "—"


def _get_stock_magasin_context(magasin):
    """Retourne stock actuel, stock_maximum et réservé écoles par produit pour un magasin."""
    if magasin is None:
        return "{}", "{}", "{}"
    soldes = list(SoldeStock.objects.filter(site=magasin).values("produit_id", "quantite", "stock_maximum"))
    reserves = {
        r["produit_id"]: r["total"]
        for r in StockReserve.objects.filter(magasin=magasin)
        .values("produit_id").annotate(total=Sum("quantite"))
    }
    stock_magasin_json = json.dumps({str(s["produit_id"]): s["quantite"] for s in soldes})
    stock_max_json = json.dumps({str(s["produit_id"]): s["stock_maximum"] for s in soldes})
    stock_reserve_json = json.dumps({str(pid): total for pid, total in reserves.items()})
    return stock_magasin_json, stock_max_json, stock_reserve_json


def _get_stock_ecole_context(ecole, magasin):
    """Retourne (stock_magasin_json, stock_ecole_json, stock_max_ecole_json) pour le formulaire école."""
    reserves_magasin = {
        r["produit_id"]: r["total"]
        for r in StockReserve.objects.filter(magasin=magasin)
        .values("produit_id")
        .annotate(total=Sum("quantite"))
    }
    stock_magasin = {
        str(s.produit_id): max(0, s.quantite - reserves_magasin.get(s.produit_id, 0))
        for s in SoldeStock.objects.filter(site=magasin)
    }
    soldes_ecole = list(SoldeStock.objects.filter(site=ecole).values("produit_id", "quantite", "stock_maximum"))
    stock_ecole = {str(s["produit_id"]): s["quantite"] for s in soldes_ecole}
    stock_max_ecole = {str(s["produit_id"]): s["stock_maximum"] for s in soldes_ecole}
    return json.dumps(stock_magasin), json.dumps(stock_ecole), json.dumps(stock_max_ecole)


def _valider_seuils_magasin(magasin, lignes):
    """Vérifie que chaque quantité ne dépasse pas le seuil maximal du magasin.

    Le stock dépôt n'est plus un facteur bloquant à la commande — seule la
    capacité d'accueil du magasin (stock_maximum) est contrôlée côté serveur.
    """
    pids = [pid for pid, _ in lignes]
    soldes = {
        s["produit_id"]: s
        for s in SoldeStock.objects.filter(site=magasin, produit_id__in=pids).values("produit_id", "quantite", "stock_maximum")
    }
    erreurs = []
    for pid, q in lignes:
        s = soldes.get(pid, {})
        max_stock = s.get("stock_maximum", 0)
        if max_stock > 0:
            propose = max(0, max_stock - s.get("quantite", 0))
            if q > propose:
                prod = Produit.objects.only("code").get(pk=pid)
                erreurs.append(f"{prod.code} : {q} demandé, {propose} disponible (seuil maximal du magasin)")
    return erreurs


def _valider_seuils_ecole(ecole, lignes):
    """Vérifie que chaque quantité ne dépasse pas le seuil maximal de l'école."""
    pids = [pid for pid, _ in lignes]
    soldes = {
        s["produit_id"]: s
        for s in SoldeStock.objects.filter(site=ecole, produit_id__in=pids).values("produit_id", "quantite", "stock_maximum")
    }
    erreurs = []
    for pid, q in lignes:
        s = soldes.get(pid, {})
        max_stock = s.get("stock_maximum", 0)
        if max_stock > 0:
            propose = max(0, max_stock - s.get("quantite", 0))
            if q > propose:
                prod = Produit.objects.only("code").get(pk=pid)
                erreurs.append(f"{prod.code} : {q} demandé, {propose} proposé (seuil maximal du site)")
    return erreurs


@login_required
def commande_magasin_formulaire(request):
    """Création d'une nouvelle commande magasin. Réservé au GEST_MAGASIN."""
    u = request.user
    if not _est_gestionnaire(u):
        messages.error(request, "Accès réservé aux gestionnaires de magasin.")
        return redirect("commandes_magasin_liste")

    magasin = u.site
    if magasin is None:
        messages.error(request, "Votre compte n'est rattaché à aucun magasin.")
        return redirect("commandes_magasin_liste")

    produits = Produit.objects.filter(actif=True).order_by("code")
    _depot, stock_depot_json, depot_nom = _get_stock_depot_context()
    stock_magasin_json, stock_max_json, stock_reserve_json = _get_stock_magasin_context(magasin)

    observations_init = ""
    lignes_soumises_json = "[]"

    # Pré-remplissage depuis les déficits consolidés école (?p_<pk>=<qty>)
    if request.method == "GET":
        prefill = []
        for key, val in request.GET.items():
            if key.startswith("p_"):
                try:
                    pid = int(key[2:])
                    qty = int(val)
                    if pid > 0 and qty > 0:
                        prefill.append({"pid": pid, "qty": qty})
                except (ValueError, TypeError):
                    pass
        if prefill:
            lignes_soumises_json = json.dumps(prefill)

    if request.method == "POST":
        observations_init = request.POST.get("observations", "").strip()
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")

        lignes = []
        for pid, q in zip(produit_ids, quantites):
            try:
                q_int = int(q)
                if q_int > 0 and pid:
                    lignes.append((int(pid), q_int))
            except (ValueError, TypeError):
                pass

        lignes_soumises_json = json.dumps([{"pid": pid, "qty": q} for pid, q in lignes])

        if not lignes:
            messages.error(request, "Ajoutez au moins une ligne.")
        else:
            erreurs = _valider_seuils_magasin(magasin, lignes)
            if erreurs:
                for e in erreurs:
                    messages.error(request, e)
            else:
                try:
                    with transaction.atomic():
                        commande = CommandeMagasin.objects.create(
                            magasin=magasin,
                            observations=observations_init,
                            cree_par=u,
                        )
                        CommandeMagasinLigne.objects.bulk_create([
                            CommandeMagasinLigne(
                                commande=commande,
                                produit_id=pid,
                                quantite=q,
                            )
                            for pid, q in lignes
                        ])
                    messages.success(request, "Commande créée en brouillon.")
                    return redirect("commande_magasin_detail", pk=commande.pk)
                except Exception as e:
                    messages.error(request, str(e))

    prefill_from_deficit = bool(
        request.method == "GET" and any(k.startswith("p_") for k in request.GET)
    )

    return render(request, "approvisionnement/commande_magasin_formulaire.html", {
        "magasin": magasin,
        "produits": produits,
        "stock_depot_json": stock_depot_json,
        "stock_magasin_json": stock_magasin_json,
        "stock_max_json": stock_max_json,
        "stock_reserve_json": stock_reserve_json,
        "depot_nom": depot_nom,
        "lignes_existantes_json": lignes_soumises_json,
        "observations_init": observations_init,
        "prefill_from_deficit": prefill_from_deficit,
    })


@login_required
def commande_magasin_detail(request, pk):
    """Détail d'une commande magasin avec boutons d'action selon rôle et statut."""
    u = request.user
    if not _peut_voir_appro_magasin(u):
        messages.error(request, "Accès non autorisé.")
        return redirect("accueil")

    qs = CommandeMagasin.objects.select_related(
        "magasin", "cree_par",
        "soumise_par", "validee_par", "livree_par", "recue_par", "rejete_par",
    )
    # Cloisonnement par profil
    if _est_gestionnaire(u) and u.site:
        commande = get_object_or_404(qs, pk=pk, magasin=u.site)
    elif _est_superviseur(u):
        commande = get_object_or_404(qs, pk=pk, magasin__in=u.sites_autorises())
    else:
        commande = get_object_or_404(qs, pk=pk)

    # Une livraison directe en brouillon n'est pas visible par le gestionnaire
    if (commande.observations or "").startswith("[LD]") and commande.statut == StatutCommandeMagasin.BROUILLON and _est_gestionnaire(u):
        messages.error(request, "Cette livraison n'est pas encore disponible.")
        return redirect("commandes_magasin_liste")

    lignes = commande.lignes.select_related("produit").order_by("produit__code")

    peut_soumettre = (
        commande.statut == StatutCommandeMagasin.BROUILLON
        and _est_gestionnaire(u)
    )
    peut_modifier = (
        commande.statut == StatutCommandeMagasin.BROUILLON
        and _est_gestionnaire(u)
    )
    peut_valider = (
        commande.statut == StatutCommandeMagasin.SOUMISE
        and _est_dg_manager(u)
    )
    peut_rejeter = (
        commande.statut == StatutCommandeMagasin.SOUMISE
        and _est_dg_manager(u)
    )
    peut_livrer = (
        commande.statut == StatutCommandeMagasin.VALIDEE
        and _est_dg_manager(u)
    )
    peut_receptionner = (
        commande.statut == StatutCommandeMagasin.LIVREE
        and _est_gestionnaire(u)
    )

    peut_supprimer = (
        commande.statut == StatutCommandeMagasin.BROUILLON
        and _est_gestionnaire(u)
    )

    from django.db.models import F as _F
    has_partial = lignes.filter(quantite_deja_recue__gt=0).exists()
    has_livraison = lignes.filter(quantite_deja_livree__gt=0).exists()
    toutes_recues = not lignes.filter(quantite_deja_recue__lt=_F("quantite")).exists()
    show_livraison = has_partial or commande.statut in (
        StatutCommandeMagasin.LIVREE, StatutCommandeMagasin.RECUE
    )

    return render(request, "approvisionnement/commande_magasin_detail.html", {
        "commande": commande,
        "lignes": lignes,
        "has_partial": has_partial,
        "has_livraison": has_livraison,
        "toutes_recues": toutes_recues,
        "show_livraison": show_livraison,
        "peut_soumettre": peut_soumettre,
        "peut_modifier": peut_modifier,
        "peut_supprimer": peut_supprimer,
        "peut_valider": peut_valider,
        "peut_rejeter": peut_rejeter,
        "peut_livrer": peut_livrer,
        "peut_receptionner": peut_receptionner,
    })


@login_required
def commande_magasin_supprimer(request, pk):
    """Suppression d'une commande magasin en brouillon. Réservé au GEST_MAGASIN."""
    u = request.user
    if not _est_gestionnaire(u):
        messages.error(request, "Accès réservé aux gestionnaires de magasin.")
        return redirect("accueil")
    commande = get_object_or_404(
        CommandeMagasin, pk=pk, magasin=u.site, statut=StatutCommandeMagasin.BROUILLON
    )
    if request.method == "POST":
        commande.delete()
        messages.success(request, "Commande supprimée.")
        return redirect("commandes_magasin_liste")
    return redirect("commande_magasin_detail", pk=pk)


@login_required
def commande_magasin_modifier(request, pk):
    """Modification d'une commande magasin en brouillon. Réservé au GEST_MAGASIN."""
    u = request.user
    if not _est_gestionnaire(u):
        messages.error(request, "Accès réservé aux gestionnaires de magasin.")
        return redirect("accueil")

    if u.site:
        commande = get_object_or_404(
            CommandeMagasin,
            pk=pk,
            magasin=u.site,
            statut=StatutCommandeMagasin.BROUILLON,
        )
    else:
        commande = get_object_or_404(
            CommandeMagasin,
            pk=pk,
            statut=StatutCommandeMagasin.BROUILLON,
        )

    produits = Produit.objects.filter(actif=True).order_by("code")
    _depot, stock_depot_json, depot_nom = _get_stock_depot_context()
    stock_magasin_json, stock_max_json, stock_reserve_json = _get_stock_magasin_context(commande.magasin)
    lignes_existantes_json = json.dumps([
        {"pid": str(l.produit_id), "qty": l.quantite}
        for l in commande.lignes.order_by("produit__code")
    ])

    if request.method == "POST":
        observations = request.POST.get("observations", "").strip()
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")

        lignes = []
        for pid, q in zip(produit_ids, quantites):
            try:
                q_int = int(q)
                if q_int > 0 and pid:
                    lignes.append((int(pid), q_int))
            except (ValueError, TypeError):
                pass

        if not lignes:
            messages.error(request, "Ajoutez au moins une ligne.")
        else:
            erreurs = _valider_seuils_magasin(commande.magasin, lignes)
            if erreurs:
                messages.error(request, "Dépassement du seuil maximal : " + " — ".join(erreurs))
            else:
                try:
                    with transaction.atomic():
                        commande.observations = observations
                        commande.save(update_fields=["observations"])
                        commande.lignes.all().delete()
                        CommandeMagasinLigne.objects.bulk_create([
                            CommandeMagasinLigne(
                                commande=commande,
                                produit_id=pid,
                                quantite=q,
                            )
                            for pid, q in lignes
                        ])
                    messages.success(request, "Commande mise à jour.")
                    return redirect("commande_magasin_detail", pk=commande.pk)
                except Exception as e:
                    messages.error(request, str(e))

    return render(request, "approvisionnement/commande_magasin_formulaire.html", {
        "magasin": commande.magasin,
        "produits": produits,
        "commande": commande,
        "stock_depot_json": stock_depot_json,
        "stock_magasin_json": stock_magasin_json,
        "stock_max_json": stock_max_json,
        "stock_reserve_json": stock_reserve_json,
        "depot_nom": depot_nom,
        "lignes_existantes_json": lignes_existantes_json,
    })


@login_required
def commande_magasin_soumettre(request, pk):
    """GEST_MAGASIN soumet la commande au superviseur."""
    u = request.user
    if not _est_gestionnaire(u):
        messages.error(request, "Accès réservé aux gestionnaires de magasin.")
        return redirect("accueil")

    qs_filter = {"pk": pk, "statut": StatutCommandeMagasin.BROUILLON}
    if u.site:
        qs_filter["magasin"] = u.site
    commande = get_object_or_404(CommandeMagasin, **qs_filter)

    if request.method == "POST":
        try:
            soumettre_commande_magasin(commande, par=u)
            messages.success(request, "Commande soumise au dépôt principal.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("commande_magasin_detail", pk=pk)


@login_required
def commande_magasin_valider(request, pk):
    """DG/MANAGER valide la commande (SOUMISE → VALIDEE)."""
    u = request.user
    if not _est_dg_manager(u):
        messages.error(request, "Accès réservé au DG et au manager.")
        return redirect("accueil")

    commande = get_object_or_404(
        CommandeMagasin, pk=pk, statut=StatutCommandeMagasin.SOUMISE,
    )
    if request.method == "POST":
        try:
            valider_commande_magasin(commande, par=u)
            messages.success(request, "Commande validée.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("commande_magasin_detail", pk=pk)


@login_required
def commande_magasin_rejeter(request, pk):
    """DG/MANAGER rejette une commande soumise avec motif obligatoire."""
    u = request.user
    if not _est_dg_manager(u):
        messages.error(request, "Accès réservé au DG et au manager.")
        return redirect("accueil")

    commande = get_object_or_404(
        CommandeMagasin, pk=pk, statut=StatutCommandeMagasin.SOUMISE,
    )
    if request.method == "POST":
        motif = request.POST.get("motif", "").strip()
        try:
            rejeter_commande_magasin(commande, par=u, motif=motif)
            messages.success(request, "Commande rejetée.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("commande_magasin_detail", pk=pk)


@login_required
def livraisons_magasin_liste(request):
    return redirect("livraisons_liste")


def _livraisons_magasin_liste_ancien(request):
    """Conservé pour référence — remplacé par le flux école."""
    u = request.user
    est_dg = _est_dg_manager(u)
    est_chef = u.profil == Profil.CHEF_EQUIPE

    if not (est_dg or _est_superviseur(u) or est_chef):
        messages.error(request, "Accès non autorisé.")
        return redirect("accueil")

    magasin_id = request.GET.get("magasin") or ""
    filtre_statut = request.GET.get("statut") or ""
    debut = request.GET.get("debut") or ""
    fin = request.GET.get("fin") or ""

    _reguliere_validee = Q(statut=StatutCommandeMagasin.VALIDEE) & ~Q(observations__startswith="[LD]")
    _reguliere_livree  = Q(statut=StatutCommandeMagasin.LIVREE, validee_par__isnull=False)
    _ld_brouillon      = Q(observations__startswith="[LD]", statut=StatutCommandeMagasin.BROUILLON)

    if est_chef and not est_dg:
        # Le chef d'équipe ne voit que les livraisons directes en attente pour son site
        qs_base = _ld_brouillon
        if u.site_id:
            qs_base = _ld_brouillon & Q(magasin_id=u.site_id)
    else:
        qs_base = _reguliere_validee | _reguliere_livree | _ld_brouillon
        if filtre_statut == "VALIDEE":
            qs_base = _reguliere_validee
        elif filtre_statut == "LIVREE":
            qs_base = _reguliere_livree
        elif filtre_statut == "BROUILLON":
            qs_base = _ld_brouillon

    commandes = (
        CommandeMagasin.objects
        .filter(qs_base)
        .select_related("magasin", "cree_par", "validee_par")
        .order_by("-cree_le")
    )
    magasins = Site.objects.filter(actif=True).order_by("nom")

    if est_dg or _est_superviseur(u):
        if magasin_id:
            commandes = commandes.filter(magasin_id=magasin_id)
    if debut:
        commandes = commandes.filter(cree_le__date__gte=debut)
    if fin:
        commandes = commandes.filter(cree_le__date__lte=fin)

    return render(request, "approvisionnement/livraisons_magasin_liste.html", {
        "commandes": commandes[:200],
        "est_dg_manager": est_dg,
        "peut_livrer": est_dg,
        "magasins": magasins,
        "filtre_magasin": magasin_id,
        "filtre_statut": filtre_statut,
        "filtre_debut": debut,
        "filtre_fin": fin,
    })


@login_required
def stock_reserve_depot(request):
    """DG/MANAGER — stock dépôt réservé par produit pour les commandes magasin validées."""
    u = request.user
    if not _est_dg_manager(u):
        messages.error(request, "Accès réservé au DG et au manager.")
        return redirect("accueil")

    filtre_produit = request.GET.get("produit") or ""

    depot = None  # Pas de dépôt central dans FAMIEN
    soldes = {}

    reserves = (
        StockReserveDepot.objects
        .select_related("produit", "commande__magasin", "commande__validee_par")
        .order_by("produit__code", "commande__magasin__nom")
    )
    if filtre_produit.isdigit():
        reserves = reserves.filter(produit_id=filtre_produit)

    # Liste des produits ayant des réservations (pour le dropdown)
    produits_filtre = (
        StockReserveDepot.objects
        .select_related("produit")
        .order_by("produit__code")
        .values("produit_id", "produit__code", "produit__designation")
        .distinct()
    )

    groupes = {}
    for r in reserves:
        pid = r.produit_id
        if pid not in groupes:
            groupes[pid] = {
                "produit": r.produit,
                "stock_total": soldes.get(pid, 0),
                "reserve_total": 0,
                "lignes": [],
            }
        groupes[pid]["reserve_total"] += r.quantite
        groupes[pid]["lignes"].append(r)

    for g in groupes.values():
        g["disponible"] = max(0, g["stock_total"] - g["reserve_total"])

    return render(request, "approvisionnement/stock_reserve_depot.html", {
        "groupes": groupes.values(),
        "produits_filtre": produits_filtre,
        "filtre_produit": filtre_produit,
        "depot": depot,
    })


@login_required
def commande_magasin_livraison(request, pk):
    """DG/MANAGER prépare la livraison depuis le dépôt (VALIDEE → LIVREE)."""
    u = request.user
    if not _est_dg_manager(u):
        messages.error(request, "Accès réservé au DG et au manager.")
        return redirect("accueil")

    commande = get_object_or_404(
        CommandeMagasin.objects.select_related("magasin"),
        pk=pk,
        statut=StatutCommandeMagasin.VALIDEE,
    )
    lignes = list(commande.lignes.select_related("produit").order_by("produit__code"))
    produit_ids = [l.produit_id for l in lignes]

    # Dans FAMIEN, pas de dépôt central distinct — le stock est porté par le magasin destination
    soldes_bruts = {
        s.produit_id: s.quantite
        for s in SoldeStock.objects.filter(site=commande.magasin, produit_id__in=produit_ids)
    }
    reserves_autres = {}

    for l in lignes:
        l.stock_total = soldes_bruts.get(l.produit_id, 0)
        l.stock_reserve = reserves_autres.get(l.produit_id, 0)
        l.stock_dispo = max(0, l.stock_total - l.stock_reserve)
        l.quantite_restante = max(0, l.quantite - (l.quantite_deja_recue or 0))
        l.max_livrable = min(l.stock_dispo, l.quantite_restante)

    lignes = [l for l in lignes if l.quantite_restante > 0]

    if request.method == "POST":
        lignes_livrees = {}
        for ligne in lignes:
            val = request.POST.get(f"quantite_livree_{ligne.produit_id}", "0")
            try:
                lignes_livrees[ligne.produit_id] = int(val)
            except (ValueError, TypeError):
                lignes_livrees[ligne.produit_id] = 0

        # Pré-vérification UX — le service refait le contrôle de façon atomique
        erreurs = []
        for ligne in lignes:
            qty = lignes_livrees.get(ligne.produit_id, 0)
            if qty > ligne.stock_dispo:
                erreurs.append(
                    f"{ligne.produit.code} : {qty} demandé, seulement {ligne.stock_dispo} disponible au dépôt."
                )
        if erreurs:
            for e in erreurs:
                messages.error(request, e)
        else:
            try:
                clore = request.POST.get("clore_livraison") == "1"
                livrer_commande_magasin(commande, lignes_livrees, par=u, clore=clore)
                if clore:
                    messages.success(request, "Livraison confirmée et clôturée — aucun reliquat ne sera expédié.")
                else:
                    messages.success(request, "Livraison confirmée. En attente de réception par le gestionnaire.")
                return redirect("livraisons_magasin_liste")
            except ValidationError as e:
                messages.error(request, str(e.message))

    return render(request, "approvisionnement/commande_magasin_livraison.html", {
        "commande": commande,
        "lignes": lignes,
    })


@login_required
def commande_magasin_refuser_livraison(request, pk):
    """DG/MANAGER refuse d'expédier une commande validée (VALIDEE → REJETEE)."""
    u = request.user
    if not _est_dg_manager(u):
        messages.error(request, "Accès réservé au DG et au manager.")
        return redirect("accueil")

    commande = get_object_or_404(
        CommandeMagasin,
        pk=pk,
        statut=StatutCommandeMagasin.VALIDEE,
    )
    if request.method == "POST":
        motif = request.POST.get("motif", "").strip()
        try:
            refuser_livraison_magasin(commande, par=u, motif=motif)
            messages.success(request, "Livraison refusée — réservation libérée.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("commande_magasin_detail", pk=pk)


@login_required
def receptions_magasin_liste(request):
    """Liste des commandes livrées et reçues pour le périmètre de l'utilisateur."""
    u = request.user
    est_chef = u.profil == Profil.CHEF_EQUIPE
    if not (_peut_voir_appro_magasin(u) or est_chef):
        messages.error(request, "Accès non autorisé.")
        return redirect("accueil")

    magasin_id = request.GET.get("magasin") or ""
    filtre_reception = request.GET.get("reception") or ""
    filtre_statut = request.GET.get("statut") or ""
    debut = request.GET.get("debut") or ""
    fin = request.GET.get("fin") or ""

    from django.db.models import Exists, OuterRef
    from django.db.models.functions import Greatest
    _ligne_partielle = CommandeMagasinLigne.objects.filter(
        commande=OuterRef("pk"), quantite_deja_recue__gt=0
    )
    # Inclut LIVREE, RECUE, VALIDEE+partiel et REJETEE+partiel
    qs_base = (
        CommandeMagasin.objects
        .annotate(
            has_partial=Exists(_ligne_partielle),
            # Sur PostgreSQL, GREATEST ignore les NULLs
            derniere_maj=Greatest("recue_le", "rejete_le", "livree_le", "validee_le"),
        )
        .filter(
            Q(statut__in=[StatutCommandeMagasin.LIVREE, StatutCommandeMagasin.RECUE])
            | Q(statut=StatutCommandeMagasin.VALIDEE,  has_partial=True, validee_par__isnull=False)
            | Q(statut=StatutCommandeMagasin.REJETEE,  has_partial=True, validee_par__isnull=False)
        )
        .select_related("magasin", "cree_par", "livree_par")
    )

    if est_chef and not _est_dg_manager(u):
        qs_base = qs_base.filter(magasin=u.site)
    elif _est_gestionnaire(u) and u.site:
        qs_base = qs_base.filter(magasin=u.site)
    elif _est_superviseur(u) and not _est_dg_manager(u):
        qs_base = qs_base.filter(magasin__in=u.sites_autorises())

    # Dropdown de réceptions pour le filtre
    receptions_filtre = qs_base.order_by("-derniere_maj")

    qs = qs_base.order_by("-derniere_maj")

    if magasin_id:
        qs = qs.filter(magasin_id=magasin_id)
    if filtre_reception:
        qs = qs.filter(pk=filtre_reception)
    if filtre_statut == "EN_COURS":
        qs = qs.filter(statut__in=[StatutCommandeMagasin.LIVREE, StatutCommandeMagasin.VALIDEE])
    elif filtre_statut == "TERMINE":
        qs = qs.filter(statut__in=[StatutCommandeMagasin.RECUE, StatutCommandeMagasin.REJETEE])
    elif filtre_statut:
        qs = qs.filter(statut=filtre_statut)
    if debut:
        qs = qs.filter(derniere_maj__date__gte=debut)
    if fin:
        qs = qs.filter(derniere_maj__date__lte=fin)

    magasins_qs = Site.objects.filter(actif=True).order_by("nom")

    return render(request, "approvisionnement/receptions_magasin_liste.html", {
        "receptions": qs[:200],
        "receptions_filtre": receptions_filtre[:300],
        "est_gestionnaire": _est_gestionnaire(u),
        "magasins": magasins_qs,
        "filtre_magasin": magasin_id,
        "filtre_reception": filtre_reception,
        "filtre_statut": filtre_statut,
        "filtre_debut": debut,
        "filtre_fin": fin,
    })


@login_required
def commande_magasin_reception(request, pk):
    """GEST_MAGASIN ou CHEF_EQUIPE confirme la réception physique au magasin (LIVREE → RECUE)."""
    u = request.user
    if not (_est_gestionnaire(u) or u.profil == Profil.CHEF_EQUIPE):
        messages.error(request, "Accès non autorisé.")
        return redirect("accueil")

    qs_filter = {"pk": pk}
    if u.site:
        qs_filter["magasin"] = u.site
    commande = get_object_or_404(
        CommandeMagasin.objects.select_related("magasin"),
        **qs_filter,
    )
    if commande.statut != StatutCommandeMagasin.LIVREE:
        messages.error(request, "Cette livraison n'est plus disponible à la réception.")
        return redirect("receptions_magasin_liste")

    lignes = list(
        commande.lignes.select_related("produit")
        .filter(quantite_livree__gt=0)
        .order_by("produit__code")
    )

    if request.method == "POST":
        lignes_recues = {}
        motifs_ecart = {}
        for ligne in lignes:
            val = request.POST.get(f"quantite_recue_{ligne.produit_id}", "0")
            try:
                lignes_recues[ligne.produit_id] = int(val)
            except (ValueError, TypeError):
                lignes_recues[ligne.produit_id] = 0
            motifs_ecart[ligne.produit_id] = request.POST.get(f"motif_ecart_{ligne.produit_id}", "")

        try:
            receptionner_commande_magasin(commande, lignes_recues, motifs_ecart, par=u)
            if commande.statut == StatutCommandeMagasin.RECUE:
                messages.success(request, "Réception confirmée — stock magasin mis à jour.")
                return redirect("receptions_magasin_liste")
            else:
                messages.success(request, "Réception partielle enregistrée — le dépôt sera notifié pour le reliquat.")
                return redirect("commande_magasin_detail", pk=pk)
        except ValidationError as e:
            messages.error(request, str(e.message))

    return render(request, "approvisionnement/commande_magasin_reception.html", {
        "commande": commande,
        "lignes": lignes,
    })


@login_required
def livraison_directe_magasin(request):
    return redirect("livraison_directe_ecole")

    magasins = Site.objects.filter(actif=True).order_by("nom")
    produits = Produit.objects.filter(actif=True).order_by("code")
    _depot, stock_depot_json, depot_nom = _get_stock_depot_context()

    if request.method == "POST":
        magasin_id = request.POST.get("magasin")
        observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")

        try:
            magasin = Site.objects.get(pk=magasin_id, actif=True)
        except Site.DoesNotExist:
            messages.error(request, "Magasin invalide.")
            return render(request, "approvisionnement/livraison_directe_magasin.html", {
                "magasins": magasins, "produits": produits,
                "stock_depot_json": stock_depot_json, "depot_nom": depot_nom,
            })

        produit_quantites = {}
        for pid, q in zip(produit_ids, quantites):
            try:
                q_int = int(q)
                if q_int > 0 and pid:
                    produit_quantites[int(pid)] = q_int
            except (ValueError, TypeError):
                pass

        try:
            commande = sauvegarder_livraison_directe_brouillon(
                magasin, produit_quantites, observations, par=u
            )
            messages.success(request, "Livraison directe enregistrée.")
            return redirect("livraison_directe_detail", pk=commande.pk)
        except ValidationError as e:
            messages.error(request, str(e.message))

    return render(request, "approvisionnement/livraison_directe_magasin.html", {
        "magasins": magasins,
        "produits": produits,
        "stock_depot_json": stock_depot_json,
        "depot_nom": depot_nom,
    })


@login_required
def livraison_directe_detail(request, pk):
    u = request.user
    est_dg = _est_dg_manager(u)
    est_chef = u.profil == Profil.CHEF_EQUIPE

    if not (est_dg or est_chef):
        messages.error(request, "Accès non autorisé.")
        return redirect("accueil")

    qs = CommandeMagasin.objects.select_related("magasin", "cree_par", "livree_par", "recue_par")
    commande = get_object_or_404(qs, pk=pk, observations__startswith="[LD]")

    if est_chef and not est_dg:
        if not u.site_id or commande.magasin_id != u.site_id:
            messages.error(request, "Accès non autorisé.")
            return redirect("accueil")

    peut_valider = _peut_valider_livraison_directe(u, commande) and commande.statut == StatutCommandeMagasin.BROUILLON
    lignes = commande.lignes.select_related("produit").order_by("produit__code")
    obs = commande.observations[4:].strip() if commande.observations.startswith("[LD] ") else commande.observations[4:]
    return render(request, "approvisionnement/livraison_directe_detail.html", {
        "commande": commande,
        "lignes": lignes,
        "observations": obs,
        "est_dg_manager": est_dg,
        "peut_valider": peut_valider,
        "peut_modifier": est_dg and commande.statut == StatutCommandeMagasin.BROUILLON,
        "peut_supprimer": est_dg and commande.statut == StatutCommandeMagasin.BROUILLON,
    })


@login_required
def livraison_directe_valider(request, pk):
    u = request.user
    commande = get_object_or_404(CommandeMagasin, pk=pk, observations__startswith="[LD]")
    if not _peut_valider_livraison_directe(u, commande):
        messages.error(request, "Accès réservé.")
        return redirect("livraisons_magasin_liste")
    if request.method == "POST":
        try:
            valider_livraison_directe(commande, par=u)
            messages.success(request, "Livraison directe validée — stock réservé au dépôt.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("livraison_directe_detail", pk=pk)


@login_required
def livraison_directe_modifier(request, pk):
    u = request.user
    if not _est_dg_manager(u):
        messages.error(request, "Accès réservé.")
        return redirect("livraisons_magasin_liste")
    commande = get_object_or_404(
        CommandeMagasin, pk=pk,
        statut=StatutCommandeMagasin.BROUILLON, observations__startswith="[LD]",
    )
    magasins = Site.objects.filter(actif=True).order_by("nom")
    produits = Produit.objects.filter(actif=True).order_by("code")
    _depot, stock_depot_json, depot_nom = _get_stock_depot_context()

    if request.method == "POST":
        magasin_id = request.POST.get("magasin")
        observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")
        try:
            magasin = Site.objects.get(pk=magasin_id, actif=True)
        except Site.DoesNotExist:
            messages.error(request, "Site invalide.")
        else:
            produit_quantites = {}
            for pid, q in zip(produit_ids, quantites):
                try:
                    q_int = int(q)
                    if q_int > 0 and pid:
                        produit_quantites[int(pid)] = q_int
                except (ValueError, TypeError):
                    pass
            try:
                sauvegarder_livraison_directe_brouillon(
                    magasin, produit_quantites, observations, par=u, commande_existante=commande
                )
                messages.success(request, "Livraison directe mise à jour.")
                return redirect("livraison_directe_detail", pk=pk)
            except ValidationError as e:
                messages.error(request, str(e.message))

    obs = commande.observations[4:].strip() if commande.observations.startswith("[LD] ") else commande.observations[4:]
    lignes_init = json.dumps([{"pid": l.produit_id, "qty": l.quantite}
                               for l in commande.lignes.order_by("produit__code")])
    return render(request, "approvisionnement/livraison_directe_magasin.html", {
        "magasins": magasins, "produits": produits,
        "stock_depot_json": stock_depot_json, "depot_nom": depot_nom,
        "commande": commande,
        "magasin_selectionne": commande.magasin_id,
        "observations_init": obs,
        "lignes_init_json": lignes_init,
    })


@login_required
def livraison_directe_supprimer(request, pk):
    u = request.user
    if not _est_dg_manager(u):
        messages.error(request, "Accès réservé.")
        return redirect("livraisons_magasin_liste")
    commande = get_object_or_404(
        CommandeMagasin, pk=pk,
        statut=StatutCommandeMagasin.BROUILLON, observations__startswith="[LD]",
    )
    if request.method == "POST":
        commande.delete()
        messages.success(request, "Livraison directe supprimée.")
    return redirect("livraisons_magasin_liste")


@login_required
def livraison_directe_ecole(request):
    """DG envoie directement des articles vers un site sans commande préalable."""
    u = request.user
    if not _est_gestionnaire(u):
        messages.error(request, "Accès réservé au DG.")
        return redirect("livraisons_liste")

    # Dans FAMIEN le DG livre directement depuis le stock central vers un site
    magasin = u.site  # site source (peut être None pour le DG, il voit tout)

    ecoles = Site.objects.filter(actif=True).order_by("nom")
    produits = Produit.objects.filter(actif=True).order_by("code")
    _stock_raw_json, _, _stock_res_json = _get_stock_magasin_context(magasin)
    _stock_raw = json.loads(_stock_raw_json)
    _stock_res = json.loads(_stock_res_json)
    stock_magasin_json = json.dumps({pid: max(0, qty - _stock_res.get(pid, 0)) for pid, qty in _stock_raw.items()})

    if request.method == "POST":
        ecole_id = request.POST.get("ecole")
        observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")

        try:
            ecole = Site.objects.get(pk=ecole_id, actif=True)
        except Site.DoesNotExist:
            messages.error(request, "Site invalide.")
            return render(request, "approvisionnement/livraison_directe_ecole.html", {
                "ecoles": ecoles, "produits": produits,
                "stock_magasin_json": stock_magasin_json, "magasin": magasin,
            })

        produit_quantites = {}
        for pid, q in zip(produit_ids, quantites):
            try:
                q_int = int(q)
                if q_int > 0 and pid:
                    produit_quantites[int(pid)] = q_int
            except (ValueError, TypeError):
                pass

        try:
            commande = sauvegarder_livraison_directe_ecole_brouillon(
                ecole, produit_quantites, observations, par=u
            )
            messages.success(request, "Livraison directe enregistrée.")
            return redirect("livraison_directe_ecole_detail", pk=commande.pk)
        except ValidationError as e:
            messages.error(request, str(e.message))

    return render(request, "approvisionnement/livraison_directe_ecole.html", {
        "ecoles": ecoles,
        "produits": produits,
        "stock_magasin_json": stock_magasin_json,
        "magasin": magasin,
    })


@login_required
def livraison_directe_ecole_detail(request, pk):
    """Détail d'une livraison directe école."""
    u = request.user
    est_gest = _est_gestionnaire(u)
    est_chef = u.profil == Profil.CHEF_EQUIPE
    est_dg = _est_dg_manager(u)
    est_sup = _est_superviseur(u) and not est_dg

    if not (est_gest or est_chef or est_dg or est_sup):
        messages.error(request, "Accès non autorisé.")
        return redirect("accueil")

    qs = CommandeEcole.objects.select_related(
        "ecole", "cree_par", "livree_par", "recue_par"
    )
    commande = get_object_or_404(qs, pk=pk, observations__startswith="[LDE]")

    if est_chef:
        if commande.statut not in (StatutCommandeEcole.LIVREE, StatutCommandeEcole.RECUE):
            messages.error(request, "Cette livraison directe n'est pas encore disponible.")
            return redirect("receptions_ecole_liste")
        if u.site_id != commande.ecole_id:
            messages.error(request, "Accès non autorisé.")
            return redirect("receptions_ecole_liste")
    # Dans FAMIEN, le DG gère toutes les livraisons directes — pas de restriction par site source

    lignes = commande.lignes.select_related("produit").order_by("produit__code")
    obs = commande.observations[5:].strip() if commande.observations.startswith("[LDE] ") else commande.observations[5:]

    return render(request, "approvisionnement/livraison_directe_ecole_detail.html", {
        "commande": commande,
        "lignes": lignes,
        "observations": obs,
        "est_gestionnaire": est_gest,
        "peut_valider": est_gest and commande.statut == StatutCommandeEcole.BROUILLON,
        "peut_modifier": est_gest and commande.statut == StatutCommandeEcole.BROUILLON,
        "peut_supprimer": est_gest and commande.statut == StatutCommandeEcole.BROUILLON,
        "peut_receptionner": est_chef and commande.statut == StatutCommandeEcole.LIVREE,
    })


@login_required
def livraison_directe_ecole_valider(request, pk):
    """GEST_MAGASIN valide une livraison directe école (BROUILLON → LIVREE)."""
    u = request.user
    if not _est_gestionnaire(u):
        messages.error(request, "Accès réservé.")
        return redirect("livraisons_liste")
    commande = get_object_or_404(
        CommandeEcole,
        pk=pk,
        observations__startswith="[LDE]",
    )
    if request.method == "POST":
        try:
            valider_livraison_directe_ecole(commande, par=u)
            messages.success(request, "Livraison directe validée — stock réservé au magasin.")
        except ValidationError as e:
            messages.error(request, str(e.message))
    return redirect("livraison_directe_ecole_detail", pk=pk)


@login_required
def livraison_directe_ecole_modifier(request, pk):
    """GEST_MAGASIN modifie une livraison directe école en brouillon."""
    u = request.user
    if not _est_gestionnaire(u):
        messages.error(request, "Accès réservé.")
        return redirect("livraisons_liste")
    commande = get_object_or_404(
        CommandeEcole,
        pk=pk,
        statut=StatutCommandeEcole.BROUILLON,
        observations__startswith="[LDE]",
    )
    magasin = u.site
    ecoles = Site.objects.filter(actif=True).order_by("nom")
    produits = Produit.objects.filter(actif=True).order_by("code")
    _stock_raw_json, _, _stock_res_json = _get_stock_magasin_context(magasin)
    _stock_raw = json.loads(_stock_raw_json)
    _stock_res = json.loads(_stock_res_json)
    stock_magasin_json = json.dumps({pid: max(0, qty - _stock_res.get(pid, 0)) for pid, qty in _stock_raw.items()})

    if request.method == "POST":
        ecole_id = request.POST.get("ecole")
        observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")
        try:
            ecole = Site.objects.get(pk=ecole_id, actif=True)
        except Site.DoesNotExist:
            messages.error(request, "Site invalide.")
        else:
            produit_quantites = {}
            for pid, q in zip(produit_ids, quantites):
                try:
                    q_int = int(q)
                    if q_int > 0 and pid:
                        produit_quantites[int(pid)] = q_int
                except (ValueError, TypeError):
                    pass
            try:
                sauvegarder_livraison_directe_ecole_brouillon(
                    ecole, produit_quantites, observations, par=u, commande_existante=commande
                )
                messages.success(request, "Livraison directe mise à jour.")
                return redirect("livraison_directe_ecole_detail", pk=pk)
            except ValidationError as e:
                messages.error(request, str(e.message))

    obs = commande.observations[5:].strip() if commande.observations.startswith("[LDE] ") else commande.observations[5:]
    lignes_init = json.dumps([{"pid": l.produit_id, "qty": l.quantite_demandee}
                               for l in commande.lignes.order_by("produit__code")])
    return render(request, "approvisionnement/livraison_directe_ecole.html", {
        "ecoles": ecoles, "produits": produits,
        "stock_magasin_json": stock_magasin_json, "magasin": magasin,
        "commande": commande,
        "ecole_selectionnee": commande.ecole_id,
        "observations_init": obs,
        "lignes_init_json": lignes_init,
    })


@login_required
def livraison_directe_ecole_supprimer(request, pk):
    """GEST_MAGASIN supprime une livraison directe école en brouillon."""
    u = request.user
    if not _est_gestionnaire(u):
        messages.error(request, "Accès réservé.")
        return redirect("livraisons_liste")
    commande = get_object_or_404(
        CommandeEcole,
        pk=pk,
        statut=StatutCommandeEcole.BROUILLON,
        observations__startswith="[LDE]",
    )
    if request.method == "POST":
        commande.delete()
        messages.success(request, "Livraison directe supprimée.")
    return redirect("livraisons_liste")


@login_required
def reception_directe_magasin(request):
    """GEST_MAGASIN saisit une réception directe sur son magasin (sans commande préalable)."""
    u = request.user
    if not _est_gestionnaire(u):
        messages.error(request, "Accès réservé aux gestionnaires de magasin.")
        return redirect("receptions_magasin_liste")

    site_fixe = u.site if u.site_id else None
    if not site_fixe and not u.is_superuser:
        messages.error(request, "Votre compte n'est associé à aucun site.")
        return redirect("receptions_magasin_liste")

    fournisseurs = Fournisseur.objects.filter(actif=True).order_by("raison_sociale")
    produits = Produit.objects.filter(actif=True).order_by("code")

    if request.method == "POST":
        fourn_id = request.POST.get("fournisseur") or None
        observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        qtes_recues = request.POST.getlist("quantite_recue")
        prix_list = request.POST.getlist("prix_unitaire")
        action = request.POST.get("action", "brouillon")
        prix_pad = list(prix_list) + ["0"] * len(produit_ids)

        lignes_valides = []
        for pid, qr, prix in zip(produit_ids, qtes_recues, prix_pad):
            try:
                q = max(0, int(qr))
                p = float(prix) if prix else 0
                if q > 0:
                    lignes_valides.append((int(pid), q, p))
            except (ValueError, TypeError):
                pass

        if not lignes_valides:
            messages.error(request, "Ajoutez au moins une ligne avec une quantité reçue > 0.")
        else:
            with transaction.atomic():
                rec = Reception.objects.create(
                    commande=None,
                    site_destination=site_fixe,
                    fournisseur_id=fourn_id,
                    observations=observations,
                    cree_par=u,
                )
                for pid, q, p in lignes_valides:
                    ReceptionLigne.objects.create(
                        reception=rec,
                        produit_id=pid,
                        quantite_attendue=q,
                        quantite_recue=q,
                        prix_unitaire=p,
                        conforme=True,
                    )
                if action == "valider":
                    valider_reception_directe(rec, par=u)
                    messages.success(request, "Réception directe validée — stock magasin mis à jour.")
                else:
                    messages.success(request, "Réception directe enregistrée en brouillon.")
            return redirect("receptions_magasin_liste")

    return render(request, "approvisionnement/reception_directe_magasin.html", {
        "site_fixe": site_fixe,
        "fournisseurs": fournisseurs,
        "produits": produits,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Pilotage commandes magasin (M17 — vue de décision DG/Manager)
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def pilotage_commandes_depot(request):
    """
    Tableau de bord de décision d'achat : toutes les commandes magasin en cours,
    regroupées par article. Permet d'identifier les déficits à commander au
    fournisseur. Accès réservé au DG et au Manager.
    """
    u = request.user
    if not _est_dg_manager(u):
        messages.error(request, "Accès réservé au DG et au manager.")
        return redirect("hub_approvisionnement")

    filtre_produit = request.GET.get("produit", "").strip()
    filtre_magasin = request.GET.get("magasin", "").strip()

    # Seules les commandes VALIDEE (approuvées mais pas encore expédiées)
    qs = CommandeMagasinLigne.objects.filter(
        commande__statut=StatutCommandeMagasin.VALIDEE
    ).select_related("produit", "commande__magasin")

    if filtre_produit:
        qs = qs.filter(produit_id=filtre_produit)
    if filtre_magasin:
        qs = qs.filter(commande__magasin_id=filtre_magasin)

    # Dans FAMIEN, pas de dépôt central — les réservations sont par site (StockReserveDepot inutilisé)
    soldes_depot = {}
    reserves_transit = {}

    from collections import defaultdict
    produits_data = defaultdict(lambda: {"produit": None, "total_demande": 0})
    for ligne in qs:
        pid = ligne.produit_id
        if produits_data[pid]["produit"] is None:
            produits_data[pid]["produit"] = ligne.produit
        # Demande nette : commandé moins déjà réceptionné au magasin (cumul inter-tournées)
        produits_data[pid]["total_demande"] += max(0, ligne.quantite - (ligne.quantite_deja_recue or 0))

    articles = []
    for pid, data in produits_data.items():
        stock_dispo = max(0, soldes_depot.get(pid, 0) - reserves_transit.get(pid, 0))
        deficit = max(0, data["total_demande"] - stock_dispo)
        if deficit == 0:
            continue  # stock suffisant — article masqué
        articles.append({
            "produit": data["produit"],
            "total_demande": data["total_demande"],
            "stock_dispo": stock_dispo,
            "deficit": deficit,
        })

    articles.sort(key=lambda a: a["produit"].code if a["produit"] else "")

    magasins = Site.objects.filter(actif=True).order_by("nom")
    produits_filtre = Produit.objects.filter(actif=True).order_by("code")

    return render(request, "approvisionnement/pilotage_commandes_depot.html", {
        "articles": articles,
        "produits_filtre": produits_filtre,
        "magasins": magasins,
        "filtres": {
            "produit": filtre_produit,
            "magasin": filtre_magasin,
        },
    })


@login_required
def pilotage_export(request):
    """Export CSV du tableau de pilotage, mêmes filtres que la vue principale."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    u = request.user
    if not _est_dg_manager(u):
        messages.error(request, "Accès réservé au DG et au manager.")
        return redirect("hub_approvisionnement")

    filtre_produit = request.GET.get("produit", "").strip()
    filtre_magasin = request.GET.get("magasin", "").strip()

    qs = CommandeMagasinLigne.objects.filter(
        commande__statut=StatutCommandeMagasin.VALIDEE
    ).select_related("produit", "produit__categorie")

    if filtre_produit:
        qs = qs.filter(produit_id=filtre_produit)
    if filtre_magasin:
        qs = qs.filter(commande__magasin_id=filtre_magasin)

    # Dans FAMIEN, pas de dépôt central
    soldes_depot = {}
    reserves_transit = {}

    from collections import defaultdict
    produits_data = defaultdict(lambda: {"produit": None, "total_demande": 0})
    for ligne in qs:
        pid = ligne.produit_id
        if produits_data[pid]["produit"] is None:
            produits_data[pid]["produit"] = ligne.produit
        produits_data[pid]["total_demande"] += max(0, ligne.quantite - (ligne.quantite_deja_recue or 0))

    rows = []
    for pid, data in produits_data.items():
        stock_dispo = max(0, soldes_depot.get(pid, 0) - reserves_transit.get(pid, 0))
        deficit = max(0, data["total_demande"] - stock_dispo)
        if deficit == 0:
            continue
        p = data["produit"]
        rows.append([
            p.code if p else "",
            p.designation if p else "",
            str(p.categorie) if p and p.categorie else "",
            data["total_demande"],
            stock_dispo,
            deficit,
        ])
    rows.sort(key=lambda r: r[0])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pilotage commandes"

    entetes = ["Code", "Désignation", "Catégorie", "Total commandé", "Stock disponible", "Déficit fournisseur"]
    ws.append(entetes)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1A6FC4")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    rouge_fill = PatternFill("solid", fgColor="FEE2E2")
    for row in rows:
        ws.append(row)
        # Mettre en rouge les lignes en déficit (toutes ici)
        for cell in ws[ws.max_row]:
            cell.fill = rouge_fill
        ws.cell(ws.max_row, 6).font = Font(bold=True, color="B91C1C")

    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 36
    ws.column_dimensions["C"].width = 20
    for col in ["D", "E", "F"]:
        ws.column_dimensions[col].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="pilotage_commandes_depot.xlsx"'
    return response


@login_required
def pilotage_commandes_ecole(request):
    """
    Déficits consolidés côté magasin : commandes école SOUMISES vs stock magasin disponible.
    Aide le gestionnaire à décider quels articles commander au dépôt (M16/M17).
    """
    u = request.user
    if not _peut_voir_appro_magasin(u):
        messages.error(request, "Accès refusé.")
        return redirect("hub_approvisionnement")

    from collections import defaultdict

    sites = u.sites_autorises()
    # Dans FAMIEN, tous les sites sont équivalents — pas de distinction magasin/école
    tous_sites = sites.filter(actif=True)

    filtre_produit = request.GET.get("produit", "").strip()
    filtre_ecole   = request.GET.get("ecole", "").strip()
    filtre_magasin = request.GET.get("magasin", "").strip()

    qs = CommandeEcoleLigne.objects.filter(
        commande__statut=StatutCommandeEcole.VALIDEE,
    ).select_related("produit", "commande__ecole")

    if filtre_produit:
        qs = qs.filter(produit_id=filtre_produit)
    if filtre_ecole:
        qs = qs.filter(commande__ecole_id=filtre_ecole)

    soldes = {
        (s.site_id, s.produit_id): s.quantite
        for s in SoldeStock.objects.filter(site__in=tous_sites)
    }
    reserves_transit = {}  # Pas de StockReserve par magasin_rattachement dans FAMIEN

    data = defaultdict(lambda: {"produit": None, "site": None, "total_demande": 0})
    for ligne in qs:
        site = ligne.commande.ecole
        key = (site.pk, ligne.produit_id)
        data[key]["produit"] = ligne.produit
        data[key]["site"] = site
        data[key]["total_demande"] += max(0, ligne.quantite_demandee - (ligne.quantite_deja_recue or 0))

    articles = []
    for (site_id, pid), d in data.items():
        stock_dispo = max(0, soldes.get((site_id, pid), 0) - reserves_transit.get((site_id, pid), 0))
        deficit = max(0, d["total_demande"] - stock_dispo)
        if deficit == 0:
            continue
        articles.append({
            "produit": d["produit"],
            "magasin": d["site"],  # conserve la clé "magasin" pour compatibilité template
            "total_demande": d["total_demande"],
            "stock_dispo": stock_dispo,
            "deficit": deficit,
        })

    articles.sort(key=lambda a: (a["magasin"].nom, a["produit"].code))

    ecoles_qs = Site.objects.filter(actif=True).order_by("nom")
    produits_filtre = Produit.objects.filter(actif=True).order_by("code")
    show_magasin_col = tous_sites.count() > 1

    return render(request, "approvisionnement/pilotage_commandes_ecole.html", {
        "articles": articles,
        "produits_filtre": produits_filtre,
        "ecoles": ecoles_qs,
        "magasins": tous_sites.order_by("nom"),
        "show_magasin_col": show_magasin_col,
        "filtres": {
            "produit": filtre_produit,
            "ecole": filtre_ecole,
            "magasin": filtre_magasin,
        },
    })


@login_required
def pilotage_ecole_export(request):
    """Export Excel du tableau déficits consolidés école, mêmes filtres que la vue principale."""
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse
    from collections import defaultdict

    u = request.user
    if not _peut_voir_appro_magasin(u):
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden()

    sites = u.sites_autorises()
    tous_sites = sites.filter(actif=True)

    filtre_produit = request.GET.get("produit", "").strip()
    filtre_ecole   = request.GET.get("ecole", "").strip()
    filtre_magasin = request.GET.get("magasin", "").strip()

    qs = CommandeEcoleLigne.objects.filter(
        commande__statut=StatutCommandeEcole.VALIDEE,
    ).select_related("produit", "commande__ecole")

    if filtre_produit:
        qs = qs.filter(produit_id=filtre_produit)
    if filtre_ecole:
        qs = qs.filter(commande__ecole_id=filtre_ecole)

    soldes = {
        (s.site_id, s.produit_id): s.quantite
        for s in SoldeStock.objects.filter(site__in=tous_sites)
    }
    reserves_transit = {}  # Pas de StockReserve par magasin_rattachement dans FAMIEN

    data = defaultdict(lambda: {"produit": None, "magasin": None, "total_demande": 0})
    for ligne in qs:
        site = ligne.commande.ecole
        key = (site.pk, ligne.produit_id)
        data[key]["produit"] = ligne.produit
        data[key]["magasin"] = site
        data[key]["total_demande"] += max(0, ligne.quantite_demandee - (ligne.quantite_deja_recue or 0))

    rows = []
    for (site_id, pid), d in data.items():
        stock_dispo = max(0, soldes.get((site_id, pid), 0) - reserves_transit.get((site_id, pid), 0))
        deficit = max(0, d["total_demande"] - stock_dispo)
        if deficit == 0:
            continue
        rows.append({
            "produit": d["produit"],
            "magasin": d["magasin"],
            "total_demande": d["total_demande"],
            "stock_dispo": stock_dispo,
            "deficit": deficit,
        })
    rows.sort(key=lambda a: (a["magasin"].nom, a["produit"].code))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Déficits site"

    entetes = ["Magasin", "Code", "Désignation", "Catégorie", "À livrer", "Stock disponible", "Déficit dépôt"]
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1A6FC4")
    ws.append(entetes)
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    rouge_fill = PatternFill("solid", fgColor="FEE2E2")
    for r in rows:
        p = r["produit"]
        ws.append([
            r["magasin"].nom,
            p.code if p else "",
            p.designation if p else "",
            str(p.categorie) if p and p.categorie else "",
            r["total_demande"],
            r["stock_dispo"],
            r["deficit"],
        ])
        for cell in ws[ws.max_row]:
            cell.fill = rouge_fill
        ws.cell(ws.max_row, 7).font = Font(bold=True, color="B91C1C")

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 36
    ws.column_dimensions["D"].width = 20
    for col in ["E", "F", "G"]:
        ws.column_dimensions[col].width = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(buf, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="deficits_ecole.xlsx"'
    return response
