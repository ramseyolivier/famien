from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from catalogue.models import Fournisseur, Produit, ProduitFournisseur
from core.models import Profil, Site

from .models import (
    CommandeFournisseur,
    CommandeFournisseurLigne,
    Reception,
    ReceptionLigne,
    StatutCommande,
    StatutReception,
)
from .services import (
    cloturer_commande,
    rejeter_commande,
    soumettre_commande,
    valider_commande,
    valider_commande_n1,
    valider_reception,
)


@login_required
def hub_operations(request):
    from depenses.models import Depense, StatutDepense
    from nonconformites.models import NonConformite, StatutNonConformite
    from approvisionnement.models import CommandeEcole, StatutCommandeEcole

    user = request.user
    sites = user.sites_autorises()

    nb_a_livrer = 0
    nb_a_recevoir = 0
    if user.profil == Profil.CHEF_EQUIPE and user.site_id:
        nb_a_recevoir = CommandeEcole.objects.filter(
            ecole=user.site,
            statut=StatutCommandeEcole.LIVREE,
        ).count()

    return render(request, "achats/hub_operations.html", {
        "nb_commandes": CommandeFournisseur.objects.filter(
            site_destination__in=sites,
            statut__in=[StatutCommande.SOUMIS, StatutCommande.VALIDE_N1],
        ).count(),
        "nb_depenses": Depense.objects.filter(site__in=sites, statut=StatutDepense.SOUMIS).count(),
        "nb_nc": NonConformite.objects.filter(
            site__in=sites,
            statut__in=[StatutNonConformite.OUVERTE, StatutNonConformite.EN_COURS]
        ).count(),
        "nb_a_livrer": nb_a_livrer,
        "nb_a_recevoir": nb_a_recevoir,
    })


# ─── Commandes fournisseurs ───────────────────────────────────────────────────

def _peut_acceder_achats_fournisseur(user):
    """Seul le DG accède aux commandes et réceptions fournisseurs."""
    return user.profil == Profil.DG or user.is_superuser


@login_required
def commandes_liste(request):
    if not _peut_acceder_achats_fournisseur(request.user):
        messages.error(request, "Accès réservé au Manager et au DG.")
        return redirect("hub_approvisionnement")
    u = request.user
    sites = u.sites_autorises()
    qs = (
        CommandeFournisseur.objects
        .filter(site_destination__in=sites)
        .filter(Q(statut=StatutCommande.BROUILLON, cree_par=u) | ~Q(statut=StatutCommande.BROUILLON))
        .select_related("fournisseur", "site_destination", "cree_par")
        .order_by("-cree_le")
    )

    filtre_commande = request.GET.get("commande", "")
    filtre_statut = request.GET.get("statut", "")
    filtre_debut = request.GET.get("debut", "")
    filtre_fin = request.GET.get("fin", "")

    commandes_filtre = (
        CommandeFournisseur.objects
        .filter(site_destination__in=sites)
        .filter(Q(statut=StatutCommande.BROUILLON, cree_par=u) | ~Q(statut=StatutCommande.BROUILLON))
        .select_related("fournisseur")
        .order_by("-pk")
    )

    if filtre_commande.isdigit():
        qs = qs.filter(pk=filtre_commande)
    if filtre_statut:
        qs = qs.filter(statut=filtre_statut)
    if filtre_debut:
        qs = qs.filter(cree_le__date__gte=filtre_debut)
    if filtre_fin:
        qs = qs.filter(cree_le__date__lte=filtre_fin)

    return render(request, "achats/commandes_liste.html", {
        "commandes": qs[:100],
        "commandes_filtre": commandes_filtre,
        "filtre_commande": filtre_commande,
        "filtre_statut": filtre_statut,
        "filtre_debut": filtre_debut,
        "filtre_fin": filtre_fin,
    })


@login_required
def commande_formulaire(request):
    u = request.user
    if not _peut_acceder_achats_fournisseur(u):
        messages.error(request, "Accès réservé au Manager et au DG.")
        return redirect("hub_approvisionnement")
    sites = u.sites_autorises()
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by("raison_sociale")
    produits = Produit.objects.filter(actif=True).order_by("code")

    # Le DG choisit le site destination de la commande fournisseur.
    site_fixe = u.site if u.site_id else sites.first()
    if not site_fixe:
        messages.error(request, "Aucun site disponible pour votre compte.")
        return redirect("hub_approvisionnement")

    if request.method == "POST":
        fourn_id = request.POST.get("fournisseur")
        site_id = str(site_fixe.pk)
        observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")

        if not site_id or not sites.filter(pk=site_id).exists():
            messages.error(request, "Site non autorisé.")
        elif not fourn_id:
            messages.error(request, "Veuillez sélectionner un fournisseur.")
        else:
            qtés: dict[int, int] = {}
            for pid, q in zip(produit_ids, quantites):
                try:
                    pid_int, q_int = int(pid), int(q)
                    if q_int > 0 and pid_int:
                        qtés[pid_int] = qtés.get(pid_int, 0) + q_int
                except (ValueError, TypeError):
                    pass
            if not qtés:
                messages.error(request, "Ajoutez au moins une ligne.")
            else:
                with transaction.atomic():
                    cf = CommandeFournisseur.objects.create(
                        fournisseur_id=fourn_id,
                        site_destination_id=site_id,
                        observations=observations,
                        cree_par=u,
                    )
                    CommandeFournisseurLigne.objects.bulk_create([
                        CommandeFournisseurLigne(commande=cf, produit_id=pid, quantite=q)
                        for pid, q in qtés.items()
                    ])
                messages.success(request, "Commande créée.")
                return redirect("commande_detail", pk=cf.pk)

    prefill_lignes = []
    for key, val in request.GET.items():
        if key.startswith("p_"):
            try:
                pk = int(key[2:])
                qty = int(val)
                if pk > 0 and qty > 0:
                    prefill_lignes.append({"pk": pk, "quantite": qty})
            except (ValueError, TypeError):
                pass

    return render(request, "achats/commande_formulaire.html", {
        "fournisseurs": fournisseurs,
        "sites": sites,
        "produits_data": [
            {"pk": p.pk, "code": p.code, "designation": p.designation}
            for p in produits
        ],
        "site_fixe": site_fixe,
        "prefill_lignes": prefill_lignes,
    })


@login_required
def commande_detail(request, pk):
    u = request.user
    if not _peut_acceder_achats_fournisseur(u):
        messages.error(request, "Accès réservé au Manager et au DG.")
        return redirect("hub_approvisionnement")
    cf = get_object_or_404(
        CommandeFournisseur.objects.select_related(
            "fournisseur", "site_destination", "cree_par",
            "soumis_par", "valide_par", "modifie_par"
        ),
        pk=pk,
    )
    sites = u.sites_autorises()
    if not sites.filter(pk=cf.site_destination_id).exists():
        messages.error(request, "Accès refusé.")
        return redirect("commandes_liste")
    if cf.statut == StatutCommande.BROUILLON and cf.cree_par_id != u.pk:
        messages.error(request, "Cette commande est en brouillon et n'est pas la vôtre.")
        return redirect("commandes_liste")
    lignes = cf.lignes.select_related("produit")
    receptions = cf.receptions.select_related("cree_par")
    # Commandes fournisseurs : workflow DG/MANAGER uniquement, pas de superviseur.
    peut_valider_n1 = False
    peut_valider = cf.statut == StatutCommande.SOUMIS and (u.profil == Profil.DG or u.is_superuser)
    peut_rejeter = (u.profil == Profil.DG or u.is_superuser) and cf.statut == StatutCommande.SOUMIS
    if cf.statut == StatutCommande.BROUILLON:
        peut_modifier = u.profil == Profil.DG or u.is_superuser
    elif cf.statut == StatutCommande.SOUMIS:
        peut_modifier = u.profil == Profil.DG or u.is_superuser
    else:
        peut_modifier = False
    est_dg = u.profil == Profil.DG or u.is_superuser
    a_reception_validee = receptions.filter(statut=StatutReception.VALIDE).exists()
    est_dg_ou_manager = u.profil == Profil.DG or u.is_superuser
    peut_cloturer = est_dg_ou_manager and cf.statut == StatutCommande.VALIDE and a_reception_validee
    peut_modifier_reception = _peut_gerer_reception(u)
    return render(request, "achats/commande_detail.html", {
        "commande": cf,
        "lignes": lignes,
        "receptions": receptions,
        "peut_valider_n1": peut_valider_n1,
        "peut_valider": peut_valider,
        "peut_rejeter": peut_rejeter,
        "peut_modifier": peut_modifier,
        "peut_cloturer": peut_cloturer,
        "peut_modifier_reception": peut_modifier_reception,
        "StatutCommande": StatutCommande,
    })


@login_required
def commande_modifier(request, pk):
    u = request.user
    if not _peut_acceder_achats_fournisseur(u):
        messages.error(request, "Accès réservé au Manager et au DG.")
        return redirect("hub_approvisionnement")
    sites = u.sites_autorises()
    cf = get_object_or_404(
        CommandeFournisseur,
        pk=pk,
        statut__in=[StatutCommande.BROUILLON, StatutCommande.SOUMIS],
    )
    if not sites.filter(pk=cf.site_destination_id).exists():
        messages.error(request, "Accès refusé.")
        return redirect("commandes_liste")
    # Seul le DG peut modifier une commande déjà soumise.
    if cf.statut == StatutCommande.SOUMIS and u.profil != Profil.DG and not u.is_superuser:
        messages.error(request, "Seul le DG peut modifier une commande déjà soumise.")
        return redirect("commande_detail", pk=pk)

    fournisseurs = Fournisseur.objects.filter(actif=True).order_by("raison_sociale")
    produits = Produit.objects.filter(actif=True).order_by("code")

    if request.method == "POST":
        fourn_id = request.POST.get("fournisseur")
        observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        quantites = request.POST.getlist("quantite")

        if not fourn_id:
            messages.error(request, "Veuillez sélectionner un fournisseur.")
        else:
            qtés: dict[int, int] = {}
            for pid, q in zip(produit_ids, quantites):
                try:
                    pid_int, q_int = int(pid), int(q)
                    if q_int > 0 and pid_int:
                        qtés[pid_int] = qtés.get(pid_int, 0) + q_int
                except (ValueError, TypeError):
                    pass
            if not qtés:
                messages.error(request, "Ajoutez au moins une ligne.")
            else:
                with transaction.atomic():
                    cf.lignes.all().delete()
                    CommandeFournisseurLigne.objects.bulk_create([
                        CommandeFournisseurLigne(commande=cf, produit_id=pid, quantite=q)
                        for pid, q in qtés.items()
                    ])
                    cf.fournisseur_id = fourn_id
                    cf.observations = observations
                    update_fields = ["fournisseur", "observations"]
                    if cf.statut == StatutCommande.SOUMIS:
                        # DG modifie une commande soumise : elle reste soumise, on trace.
                        cf.modifie_par = u
                        cf.modifie_le = timezone.now()
                        update_fields += ["modifie_par", "modifie_le"]
                        messages.info(request, "Modification enregistrée — la commande reste soumise.")
                    cf.save(update_fields=update_fields)
                messages.success(request, "Commande mise à jour.")
                return redirect("commande_detail", pk=cf.pk)

    lignes_initiales = [
        {"produit_id": l.produit_id, "quantite": l.quantite}
        for l in cf.lignes.select_related("produit").order_by("produit__code")
    ]
    return render(request, "achats/commande_modifier.html", {
        "commande": cf,
        "fournisseurs": fournisseurs,
        "produits_data": [
            {"pk": p.pk, "code": p.code, "designation": p.designation}
            for p in produits
        ],
        "lignes_initiales": lignes_initiales,
    })


@login_required
def commande_supprimer(request, pk):
    u = request.user
    if not _peut_acceder_achats_fournisseur(u):
        messages.error(request, "Accès réservé au Manager et au DG.")
        return redirect("hub_approvisionnement")
    sites = u.sites_autorises()
    cf = get_object_or_404(CommandeFournisseur, pk=pk, statut=StatutCommande.BROUILLON)
    if not sites.filter(pk=cf.site_destination_id).exists():
        messages.error(request, "Accès refusé.")
        return redirect("commandes_liste")
    if request.method == "POST":
        cf.delete()
        messages.success(request, "Commande supprimée.")
        return redirect("commandes_liste")
    return redirect("commande_detail", pk=pk)


@login_required
def commande_soumettre(request, pk):
    u = request.user
    if not _peut_acceder_achats_fournisseur(u):
        messages.error(request, "Accès réservé au Manager et au DG.")
        return redirect("hub_approvisionnement")
    sites = u.sites_autorises()
    cf = get_object_or_404(CommandeFournisseur, pk=pk, statut=StatutCommande.BROUILLON)
    if not sites.filter(pk=cf.site_destination_id).exists():
        messages.error(request, "Accès refusé.")
        return redirect("commandes_liste")
    if request.method == "POST":
        try:
            soumettre_commande(cf, par=request.user)
            messages.success(request, "Commande soumise.")
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect("commande_detail", pk=pk)


@login_required
def commande_valider_n1(request, pk):
    # Désactivé pour les commandes fournisseurs — le superviseur n'intervient pas.
    messages.error(request, "Cette action n'est pas disponible.")
    return redirect("commande_detail", pk=pk)


@login_required
def commande_valider(request, pk):
    u = request.user
    if u.profil != Profil.DG and not u.is_superuser:
        messages.error(request, "Seuls le DG et le Manager peuvent valider une commande fournisseur.")
        return redirect("commande_detail", pk=pk)
    cf = get_object_or_404(CommandeFournisseur, pk=pk, statut=StatutCommande.SOUMIS)
    if request.method == "POST":
        try:
            valider_commande(cf, par=u)
            messages.success(request, "Commande validée.")
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect("commande_detail", pk=pk)


@login_required
def commande_rejeter(request, pk):
    u = request.user
    if u.profil != Profil.DG and not u.is_superuser:
        messages.error(request, "Seuls le DG et le Manager peuvent rejeter une commande fournisseur.")
        return redirect("commande_detail", pk=pk)
    cf = get_object_or_404(CommandeFournisseur, pk=pk)
    if request.method == "POST":
        motif = request.POST.get("motif", "")
        try:
            rejeter_commande(cf, par=u, motif=motif)
            messages.success(request, "Commande rejetée.")
            return redirect("commandes_liste")
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect("commande_detail", pk=pk)


@login_required
def commande_cloturer(request, pk):
    u = request.user
    if u.profil != Profil.DG and not u.is_superuser:
        messages.error(request, "Seuls le DG et le Manager peuvent clôturer une commande.")
        return redirect("commande_detail", pk=pk)
    cf = get_object_or_404(CommandeFournisseur, pk=pk)
    if request.method == "POST":
        try:
            cloturer_commande(cf, par=u)
            messages.success(request, "Commande clôturée — aucune nouvelle réception possible.")
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect("commande_detail", pk=pk)


# ─── Réceptions ──────────────────────────────────────────────────────────────

def _peut_gerer_reception(user):
    return user.profil == Profil.DG or user.is_superuser


@login_required
def reception_detail(request, pk):
    if not _peut_acceder_achats_fournisseur(request.user):
        messages.error(request, "Accès réservé au Manager et au DG.")
        return redirect("hub_approvisionnement")
    rec = get_object_or_404(
        Reception.objects.select_related(
            "commande__fournisseur", "commande__site_destination",
            "fournisseur", "site_destination", "cree_par", "valide_par"
        ),
        pk=pk,
    )
    lignes = list(rec.lignes.select_related("produit").order_by("produit__code"))
    total_attendu = sum(l.quantite_attendue for l in lignes)
    total_recu = sum(l.quantite_recue for l in lignes)
    total_montant = sum(l.montant for l in lignes)
    return render(request, "achats/reception_detail.html", {
        "reception": rec,
        "lignes": lignes,
        "total_attendu": total_attendu,
        "total_recu": total_recu,
        "ecart_total": total_recu - total_attendu,
        "total_montant": total_montant,
        "peut_gerer": _peut_gerer_reception(request.user),
    })


def _sauvegarder_lignes_reception(rec, produit_ids, qtes_attendues, qtes_recues, justifications):
    """Supprime les lignes existantes et recrée depuis les données POST.
    Le prix unitaire est lu depuis ProduitFournisseur (catalogue), pas saisi manuellement."""
    fournisseur = rec.commande.fournisseur if rec.commande_id else None
    pid_ints = [int(p) for p in produit_ids if p]
    offres = {}
    if fournisseur and pid_ints:
        offres = {
            o.produit_id: o.prix_achat
            for o in ProduitFournisseur.objects.filter(fournisseur=fournisseur, produit_id__in=pid_ints)
        }

    rec.lignes.all().delete()
    n = len(produit_ids)
    justifs_pad = justifications + [""] * n
    for pid, qa, qr, justif in zip(produit_ids, qtes_attendues, qtes_recues, justifs_pad):
        try:
            pid_int = int(pid)
            ReceptionLigne.objects.create(
                reception=rec,
                produit_id=pid_int,
                quantite_attendue=int(qa),
                quantite_recue=max(0, int(qr)),
                prix_unitaire=offres.get(pid_int, 0),
                conforme=True,
                justification_ecart=justif.strip(),
            )
        except (ValueError, TypeError):
            pass


@login_required
def receptions_liste(request):
    if not _peut_acceder_achats_fournisseur(request.user):
        messages.error(request, "Accès réservé au Manager et au DG.")
        return redirect("hub_approvisionnement")

    filtre_reception = request.GET.get("reception", "")
    filtre_statut = request.GET.get("statut", "")
    filtre_debut = request.GET.get("debut", "")
    filtre_fin = request.GET.get("fin", "")

    sites = request.user.sites_autorises()
    qs = (
        Reception.objects
        .select_related("commande__fournisseur", "commande__site_destination",
                        "fournisseur", "site_destination", "cree_par", "valide_par")
        .order_by("-cree_le")
    )

    if filtre_reception.isdigit():
        qs = qs.filter(pk=filtre_reception)
    if filtre_statut:
        qs = qs.filter(statut=filtre_statut)
    if filtre_debut:
        qs = qs.filter(cree_le__date__gte=filtre_debut)
    if filtre_fin:
        qs = qs.filter(cree_le__date__lte=filtre_fin)

    qs = list(qs[:100])

    commandes_avec_valide = set(
        Reception.objects
        .filter(statut=StatutReception.VALIDE, commande__isnull=False)
        .values_list("commande_id", flat=True)
    )

    # Calcul des références en Python (une seule requête, pas de N+1)
    from collections import defaultdict
    recs_pour_filtre = list(
        Reception.objects.only("pk", "commande_id").order_by("pk")
    )
    _compteur = defaultdict(int)
    receptions_filtre = []
    for r in recs_pour_filtre:
        if r.commande_id:
            _compteur[r.commande_id] += 1
            ref = f"{r.pk}RC#{_compteur[r.commande_id]} — CF#{r.commande_id}"
        else:
            ref = f"{r.pk}RX"
        receptions_filtre.append({"pk": r.pk, "ref": ref})

    return render(request, "achats/receptions_liste.html", {
        "receptions": qs,
        "commandes_avec_valide": commandes_avec_valide,
        "peut_gerer": _peut_gerer_reception(request.user),
        "est_dg": request.user.profil == Profil.DG or request.user.is_superuser,
        "receptions_filtre": receptions_filtre,
        "filtre_reception": filtre_reception,
        "filtre_statut": filtre_statut,
        "filtre_debut": filtre_debut,
        "filtre_fin": filtre_fin,
    })


@login_required
def reception_formulaire(request, commande_pk):
    u = request.user
    if not _peut_gerer_reception(u):
        messages.error(request, "Seuls le Manager et le DG peuvent saisir une réception.")
        return redirect("commande_detail", pk=commande_pk)
    cf = get_object_or_404(CommandeFournisseur, pk=commande_pk, statut=StatutCommande.VALIDE)
    lignes_commande = cf.lignes.select_related("produit")

    if request.method == "POST":
        action = request.POST.get("action", "brouillon")
        observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        qtes_attendues = request.POST.getlist("quantite_attendue")
        qtes_recues = request.POST.getlist("quantite_recue")
        justifications = request.POST.getlist("justification_ecart")

        with transaction.atomic():
            rec = Reception.objects.create(commande=cf, observations=observations, cree_par=u)
            _sauvegarder_lignes_reception(rec, produit_ids, qtes_attendues, qtes_recues, justifications)
            if action == "valider":
                valider_reception(rec, par=u)
                messages.success(request, "Réception validée — stock du dépôt mis à jour.")
                return redirect("receptions_liste")
            else:
                messages.success(request, "Réception enregistrée en brouillon.")
                return redirect("reception_detail", pk=rec.pk)

    lignes = [
        {"produit": l.produit, "quantite_commandee": l.quantite,
         "quantite_recue": l.quantite, "justification": ""}
        for l in lignes_commande
    ]
    return render(request, "achats/reception_formulaire.html", {
        "commande": cf,
        "lignes": lignes,
    })


@login_required
def reception_modifier(request, pk):
    u = request.user
    if not _peut_gerer_reception(u):
        messages.error(request, "Seuls le Manager et le DG peuvent modifier une réception.")
        return redirect("receptions_liste")
    rec = get_object_or_404(
        Reception.objects.select_related(
            "commande__fournisseur", "commande__site_destination",
            "site_destination", "fournisseur",
        ),
        pk=pk, statut=StatutReception.BROUILLON,
    )

    # ── Réception directe (sans commande) ──────────────────────────────────
    if not rec.commande_id:
        if request.method == "POST":
            action = request.POST.get("action", "brouillon")
            rec.fournisseur_id = request.POST.get("fournisseur") or None
            rec.observations = request.POST.get("observations", "")
            produit_ids = request.POST.getlist("produit_id")
            qtes_recues = request.POST.getlist("quantite_recue")

            with transaction.atomic():
                rec.save(update_fields=["fournisseur", "observations"])
                _sauvegarder_lignes_libre(rec, produit_ids, qtes_recues)
                messages.success(request, "Brouillon mis à jour.")
            return redirect("reception_detail", pk=rec.pk)

        fournisseurs = Fournisseur.objects.filter(actif=True).order_by("raison_sociale")
        produits = Produit.objects.filter(actif=True).order_by("code")
        lignes_existantes = [
            {"pk": l.produit_id, "qte": l.quantite_recue}
            for l in rec.lignes.select_related("produit").order_by("produit__code")
        ]
        return render(request, "achats/reception_libre.html", {
            "reception": rec,
            "site_fixe": rec.site_destination,
            "fournisseurs": fournisseurs,
            "produits_data": [{"pk": p.pk, "code": p.code, "designation": p.designation} for p in produits],
            "lignes_existantes": lignes_existantes,
        })

    # ── Réception liée à une commande ──────────────────────────────────────
    if request.method == "POST":
        action = request.POST.get("action", "brouillon")
        rec.observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        qtes_attendues = request.POST.getlist("quantite_attendue")
        qtes_recues = request.POST.getlist("quantite_recue")
        justifications = request.POST.getlist("justification_ecart")

        with transaction.atomic():
            rec.save(update_fields=["observations"])
            _sauvegarder_lignes_reception(rec, produit_ids, qtes_attendues, qtes_recues, justifications)
            if action == "valider":
                valider_reception(rec, par=u)
                messages.success(request, "Réception validée — stock du dépôt mis à jour.")
            else:
                messages.success(request, "Brouillon mis à jour.")
        return redirect("reception_detail", pk=rec.pk)

    existantes = {l.produit_id: l for l in rec.lignes.select_related("produit").all()}
    lignes = [
        {"produit": l.produit,
         "quantite_commandee": l.quantite,
         "quantite_recue": existantes[l.produit_id].quantite_recue if l.produit_id in existantes else l.quantite,
         "justification": existantes[l.produit_id].justification_ecart if l.produit_id in existantes else ""}
        for l in rec.commande.lignes.select_related("produit").all()
    ]
    return render(request, "achats/reception_formulaire.html", {
        "commande": rec.commande,
        "lignes": lignes,
        "reception": rec,
    })


@login_required
def reception_valider(request, pk):
    u = request.user
    if not _peut_gerer_reception(u):
        messages.error(request, "Seuls le Manager et le DG peuvent valider une réception.")
        return redirect("receptions_liste")
    rec = get_object_or_404(Reception, pk=pk, statut=StatutReception.BROUILLON)
    if request.method == "POST":
        try:
            valider_reception(rec, par=u)
            messages.success(request, "Réception validée — stock du dépôt mis à jour.")
        except ValidationError as e:
            messages.error(request, str(e))
    if rec.commande_id:
        return redirect("commande_detail", pk=rec.commande_id)
    return redirect("receptions_liste")


@login_required
def reception_supprimer(request, pk):
    u = request.user
    if not _peut_gerer_reception(u):
        messages.error(request, "Seuls le Manager et le DG peuvent supprimer une réception.")
        return redirect("receptions_liste")
    rec = get_object_or_404(Reception, pk=pk, statut=StatutReception.BROUILLON)
    if request.method == "POST":
        rec.delete()
        messages.success(request, "Réception supprimée.")
        return redirect("receptions_liste")
    return redirect("reception_detail", pk=pk)


def _site_depot_pour_reception_libre(user):
    """Retourne le site de réception directe : site de l'utilisateur ou premier site actif."""
    if user.site_id:
        return user.site
    return Site.objects.filter(actif=True).first()


def _sauvegarder_lignes_libre(rec, produit_ids, qtes_recues):
    """Supprime et recrée les lignes d'une réception directe (attendu = reçu, toujours conforme).
    Plusieurs lignes du même produit sont agrégées. Prix lu depuis ProduitFournisseur, sinon 0."""
    from collections import defaultdict
    # Agréger les quantités par produit (le formulaire peut avoir plusieurs lignes du même produit)
    qtés: dict[int, int] = defaultdict(int)
    for pid, qr in zip(produit_ids, qtes_recues):
        try:
            pid_int, q = int(pid), max(0, int(qr))
            if q > 0:
                qtés[pid_int] += q
        except (ValueError, TypeError):
            pass

    fournisseur = rec.fournisseur
    offres = {}
    if fournisseur and qtés:
        offres = {
            o.produit_id: o.prix_achat
            for o in ProduitFournisseur.objects.filter(fournisseur=fournisseur, produit_id__in=qtés)
        }
    couts = {p.pk: p.cout_achat for p in Produit.objects.filter(pk__in=qtés)}
    rec.lignes.all().delete()
    for pid_int, q in qtés.items():
        prix = offres.get(pid_int) or couts.get(pid_int, 0)
        ReceptionLigne.objects.create(
            reception=rec,
            produit_id=pid_int,
            quantite_attendue=q,
            quantite_recue=q,
            prix_unitaire=prix,
            conforme=True,
        )


@login_required
def reception_libre_formulaire(request):
    u = request.user
    if not _peut_gerer_reception(u):
        messages.error(request, "Seuls le Manager et le DG peuvent saisir une réception directe.")
        return redirect("receptions_liste")

    site_fixe = _site_depot_pour_reception_libre(u)
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by("raison_sociale")
    produits = Produit.objects.filter(actif=True).order_by("code")

    if request.method == "POST":
        fourn_id = request.POST.get("fournisseur") or None
        observations = request.POST.get("observations", "")
        produit_ids = request.POST.getlist("produit_id")
        qtes_recues = request.POST.getlist("quantite_recue")
        action = request.POST.get("action", "brouillon")

        # Valider les lignes avant d'ouvrir la transaction
        lignes_valides = []
        for pid, qr in zip(produit_ids, qtes_recues):
            try:
                q = max(0, int(qr))
                if q > 0:
                    lignes_valides.append(int(pid))
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
                _sauvegarder_lignes_libre(rec, produit_ids, qtes_recues)
                messages.success(request, "Réception directe enregistrée en brouillon.")
            return redirect("reception_detail", pk=rec.pk)

    return render(request, "achats/reception_libre.html", {
        "site_fixe": site_fixe,
        "fournisseurs": fournisseurs,
        "produits_data": [{"pk": p.pk, "code": p.code, "designation": p.designation} for p in produits],
        "lignes_existantes": [],
    })
