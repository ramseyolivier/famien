from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import localdate, now as tz_now

from core.models import Profil, TypeNotification

from .models import CategorieDepense, Depense, StatutDepense
from .services import confirmer_depense, rejeter_depense, soumettre_depense, valider_depense, _notifier_dg_manager


def _peut_acceder_depense(user, dep):
    """Dépense sans site (niveau superviseur) : accessible par son créateur et Manager/DG."""
    if dep.site_id is None:
        return (dep.cree_par_id == user.pk
                or user.profil in {Profil.DG, Profil.DG}
                or user.is_superuser)
    return user.sites_autorises().filter(pk=dep.site_id).exists()


@login_required
def depenses_liste(request):
    from django.db.models import Q as _Q
    u = request.user
    sites = u.sites_autorises()
    qs = (
        Depense.objects
        .filter(_Q(site__in=sites) | _Q(site__isnull=True, cree_par=u))
        .select_related("site", "categorie", "cree_par")
        .order_by("-cree_le")[:100]
    )
    return render(request, "depenses/liste.html", {"depenses": qs})


@login_required
def depense_formulaire(request):
    u = request.user
    if u.profil not in {Profil.CHEF_EQUIPE, Profil.DG} and not u.is_superuser:
        messages.error(request, "Seuls les chefs d'équipe et le DG peuvent saisir une dépense.")
        return redirect("depenses_liste")
    sites = request.user.sites_autorises()
    categorie_defaut, _ = CategorieDepense.objects.get_or_create(nom="Générale")

    est_superviseur = False

    if request.method == "POST":
        raw_site = request.POST.get("site", "")
        site_id = None if (not raw_site or raw_site == "__sup__") else raw_site
        categorie_id = request.POST.get("categorie") or categorie_defaut.pk
        montant = request.POST.get("montant", "0")
        motif = request.POST.get("motif", "").strip()
        date_depense = request.POST.get("date_depense") or localdate().isoformat()
        piece = request.POST.get("piece_justificative", "")

        # Un superviseur peut créer une dépense sans site (dépense à son propre niveau).
        site_valide = (site_id is None and est_superviseur) or (site_id and sites.filter(pk=site_id).exists())
        if not site_valide:
            messages.error(request, "Site non autorisé.")
        elif not motif:
            messages.error(request, "Le motif est obligatoire.")
        else:
            try:
                auto_valide = u.profil in {Profil.DG, Profil.DG} or u.is_superuser
                dep = Depense.objects.create(
                    site_id=site_id,
                    categorie_id=categorie_id,
                    montant=montant,
                    motif=motif,
                    date_depense=date_depense,
                    piece_justificative=piece,
                    cree_par=u,
                    statut=StatutDepense.VALIDE if auto_valide else StatutDepense.SOUMIS,
                    valide_par=u if auto_valide else None,
                    valide_le=tz_now() if auto_valide else None,
                )
                if auto_valide:
                    messages.success(request, "Dépense validée — confirmez le montant réellement dépensé.")
                else:
                    _notifier_dg_manager(
                        dep,
                        type=TypeNotification.DEPENSE_SOUMISE,
                        titre=f"Dépense à valider — {float(dep.montant):,.0f} F",
                        message=f"{u.get_full_name() or u.username} · {dep.motif}",
                    )
                    messages.success(request, "Dépense soumise — en attente de validation.")
                return redirect("depense_detail", pk=dep.pk)
            except Exception as e:
                messages.error(request, str(e))

    sites_list = list(sites)
    site_unique = sites_list[0] if len(sites_list) == 1 else None
    libelle_superviseur = u.get_full_name() or u.username
    return render(request, "depenses/formulaire.html", {
        "sites": sites_list,
        "site_unique": site_unique,
        "est_superviseur": est_superviseur,
        "libelle_superviseur": libelle_superviseur,
        "categorie_defaut": categorie_defaut,
    })


@login_required
def depense_modifier(request, pk):
    u = request.user
    if u.profil not in {Profil.DG, Profil.DG} and not u.is_superuser:
        messages.error(request, "Seuls les DG/Managers peuvent modifier une dépense.")
        return redirect("depense_detail", pk=pk)
    sites = u.sites_autorises()
    dep = get_object_or_404(Depense.objects.select_related("site", "categorie"), pk=pk, statut=StatutDepense.SOUMIS)
    if not sites.filter(pk=dep.site_id).exists():
        messages.error(request, "Accès refusé.")
        return redirect("depenses_liste")
    categorie_defaut, _ = CategorieDepense.objects.get_or_create(nom="Générale")
    categories = CategorieDepense.objects.all()

    if request.method == "POST":
        site_id = request.POST.get("site")
        categorie_id = request.POST.get("categorie") or categorie_defaut.pk
        montant = request.POST.get("montant", "0")
        motif = request.POST.get("motif", "").strip()
        date_depense = request.POST.get("date_depense") or dep.date_depense.isoformat()
        piece = request.POST.get("piece_justificative", "")

        if not sites.filter(pk=site_id).exists():
            messages.error(request, "Site non autorisé.")
        elif not motif:
            messages.error(request, "Le motif est obligatoire.")
        else:
            try:
                dep.site_id = site_id
                dep.categorie_id = categorie_id
                dep.montant = montant
                dep.motif = motif
                dep.date_depense = date_depense
                dep.piece_justificative = piece
                dep.save(update_fields=["site_id", "categorie_id", "montant", "motif", "date_depense", "piece_justificative"])
                messages.success(request, "Dépense modifiée.")
                return redirect("depense_detail", pk=dep.pk)
            except Exception as e:
                messages.error(request, str(e))

    sites_list = list(sites)
    site_unique = sites_list[0] if len(sites_list) == 1 else None
    return render(request, "depenses/formulaire.html", {
        "depense": dep,
        "montant_initial": int(dep.montant),
        "sites": sites_list,
        "site_unique": site_unique,
        "categorie_defaut": categorie_defaut,
        "categories": categories,
        "mode_edition": True,
    })


@login_required
def depense_detail(request, pk):
    dep = get_object_or_404(
        Depense.objects.select_related("site", "categorie", "cree_par", "valide_par", "confirme_par"),
        pk=pk,
    )
    if not _peut_acceder_depense(request.user, dep):
        messages.error(request, "Accès refusé.")
        return redirect("depenses_liste")
    peut_valider = request.user.profil in {Profil.DG, Profil.DG} or request.user.is_superuser
    return render(request, "depenses/detail.html", {
        "depense": dep,
        "peut_valider": peut_valider,
    })


@login_required
def depense_soumettre(request, pk):
    dep = get_object_or_404(Depense, pk=pk, statut=StatutDepense.BROUILLON)
    if not _peut_acceder_depense(request.user, dep):
        messages.error(request, "Accès refusé.")
        return redirect("depenses_liste")
    if request.method == "POST":
        try:
            soumettre_depense(dep, par=request.user)
            messages.success(request, "Dépense soumise — en attente de validation DG/Manager.")
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect("depense_detail", pk=pk)


@login_required
def depense_valider(request, pk):
    u = request.user
    if u.profil not in {Profil.DG, Profil.DG} and not u.is_superuser:
        messages.error(request, "Seuls les DG/Managers peuvent valider une dépense.")
        return redirect("depense_detail", pk=pk)
    dep = get_object_or_404(Depense, pk=pk, statut=StatutDepense.SOUMIS)
    if request.method == "POST":
        try:
            valider_depense(dep, par=u)
            messages.success(request, "Dépense validée.")
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect("depense_detail", pk=pk)


@login_required
def depense_rejeter(request, pk):
    u = request.user
    if u.profil not in {Profil.DG, Profil.DG} and not u.is_superuser:
        messages.error(request, "Seuls les DG/Managers peuvent rejeter une dépense.")
        return redirect("depense_detail", pk=pk)
    dep = get_object_or_404(Depense, pk=pk, statut=StatutDepense.SOUMIS)
    if request.method == "POST":
        motif = request.POST.get("motif", "")
        try:
            rejeter_depense(dep, par=u, motif=motif)
            messages.success(request, "Dépense rejetée.")
            return redirect("depenses_liste")
        except ValidationError as e:
            messages.error(request, str(e))
    return redirect("depense_detail", pk=pk)


@login_required
def depense_confirmer(request, pk):
    """Confirmation du montant réellement dépensé par le créateur (étape 3 du workflow — section 20).

    Seul le créateur original ou un Manager/DG peut confirmer une dépense VALIDE.
    Le montant confirmé doit être ≤ au montant autorisé.
    """
    u = request.user
    dep = get_object_or_404(
        Depense.objects.select_related("site", "categorie", "cree_par", "valide_par"),
        pk=pk,
        statut=StatutDepense.VALIDE,
    )
    if not _peut_acceder_depense(u, dep):
        messages.error(request, "Accès refusé.")
        return redirect("depenses_liste")

    peut_confirmer = (dep.cree_par_id == u.pk
                      or u.profil in {Profil.DG, Profil.DG}
                      or u.is_superuser)
    if not peut_confirmer:
        messages.error(request, "Seul le créateur ou un Manager/DG peut confirmer cette dépense.")
        return redirect("depense_detail", pk=pk)

    if request.method == "POST":
        raw = request.POST.get("montant_reel", "").strip().replace(" ", "").replace(",", ".")
        try:
            montant_reel = Decimal(raw)
        except (InvalidOperation, ValueError):
            messages.error(request, "Montant invalide.")
            return render(request, "depenses/confirmer.html", {"depense": dep})
        try:
            confirmer_depense(dep, par=u, montant_reel=montant_reel)
            messages.success(request, f"Dépense confirmée — {montant_reel:,.0f} F CFA réellement dépensés.")
        except ValidationError as e:
            messages.error(request, str(e))
            return render(request, "depenses/confirmer.html", {"depense": dep})
        return redirect("depense_detail", pk=pk)

    return render(request, "depenses/confirmer.html", {"depense": dep})


@login_required
def depense_supprimer(request, pk):
    u = request.user
    if u.profil not in {Profil.DG, Profil.DG} and not u.is_superuser:
        messages.error(request, "Accès refusé.")
        return redirect("depense_detail", pk=pk)
    dep = get_object_or_404(Depense, pk=pk)
    if not _peut_acceder_depense(u, dep):
        messages.error(request, "Accès refusé.")
        return redirect("depenses_liste")
    if request.method == "POST":
        dep.delete()
        messages.success(request, "Dépense supprimée.")
        return redirect("finances_entrees_sorties")
    return redirect("depense_detail", pk=pk)
