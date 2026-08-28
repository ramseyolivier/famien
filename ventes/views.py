"""Écrans opérationnels : vente, file de livraison, reçu, tableau de bord."""

import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from datetime import date as date_cls

from django.core.paginator import Paginator
from collections import Counter

from django.db.models import Case, Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogue.models import CategorieProduit, Produit, PrixEcole
from core.models import Profil, Site, Utilisateur
from kits.models import Kit, Niveau
from stock.models import SoldeStock
from stock.services import references_sous_seuil

from .models import ClotureCaisse, ModePaiement, StatutVente, Vente
from core.models import TypeNotification
from core.services import creer_notification, notifier_chefs_equipe

from .services import (
    VenteDejaEnregistree,
    annuler_avoir,
    annuler_vente,
    completer_livraison,
    enregistrer_vente,
    marquer_livree,
)


def _kits_disponibles(ecole, stock_depuis=None):
    """
    Kits actifs de l'école, avec le nombre d'exemplaires réellement constructibles.
    stock_depuis : site dont on lit le stock (défaut = l'école elle-même ;
    passer le magasin pour le GEST_MAGASIN qui consulte son propre stock).
    """
    site_stock = stock_depuis if stock_depuis is not None else ecole
    soldes = {s.produit_id: s.quantite for s in SoldeStock.objects.filter(site=site_stock)}
    resultat = []
    _ordre = {"6E": 1, "5E": 2, "4E": 3, "3E": 4, "2NDA": 5, "2NDC": 6, "1REA": 7, "1REC": 8, "1RED": 9, "TLEA": 10, "TLEC": 11, "TLED": 12}
    for kit in Kit.objects.filter(ecole=ecole, actif=True).select_related("classe").prefetch_related("lignes__produit"):
        lignes = list(kit.lignes.all())
        constructibles = min(
            (soldes.get(l.produit_id, 0) // l.quantite for l in lignes), default=0
        )
        resultat.append(
            {
                "kit": kit,
                "constructibles": max(constructibles, 0),
                "manquants": [l.produit.designation for l in lignes if soldes.get(l.produit_id, 0) < l.quantite],
            }
        )
    resultat.sort(key=lambda e: (_ordre.get(e["kit"].classe.niveau, 99), e["kit"].classe.libelle))
    return resultat


@login_required
def accueil(request):
    u = request.user
    if u.is_superuser:
        return redirect("/admin/")
    if u.peut_vendre():
        return redirect("vente")
    if u.acces_national:
        return redirect("admin_accueil")
    if not u.peut_voir_ventes():
        return redirect("hub_stock")
    return redirect("hub_ventes")


@login_required
def vente(request):
    u = request.user
    if not u.peut_vendre():
        messages.error(request, "Votre compte n'est pas autorisé à effectuer des ventes.")
        return redirect("hub_ventes")

    ecole = u.site
    if request.method == "POST":
        return _enregistrer(request, ecole)

    soldes_dict = {s.produit_id: s.quantite for s in SoldeStock.objects.filter(site=ecole)}
    kits_disponibles = _kits_disponibles(ecole)
    produits_detail = [
        {"produit": p, "stock": soldes_dict.get(p.pk, 0)}
        for p in Produit.objects.filter(actif=True).select_related("categorie").order_by("code")
    ]
    prix_ecoles_map = {
        pe.produit_id: pe.prix_detail
        for pe in PrixEcole.objects.filter(ecole=ecole)
    }
    # Sérialisation JSON des données JS — évite les séparateurs de milliers fr-fr
    # qui rendent les littéraux numériques invalides en JavaScript.
    js_data = {
        "kits": [
            {
                "id": str(e["kit"].pk),
                "libelle": f"Kit {e['kit'].classe.libelle}",
                "prix": int(e["kit"].prix_vente),
                "max": e["constructibles"],
                "lignes": [
                    {"produit_id": str(l.produit_id), "quantite": l.quantite}
                    for l in e["kit"].lignes.all()
                ],
            }
            for e in kits_disponibles
        ],
        "articles": [
            {
                "id": str(p["produit"].pk),
                "libelle": p['produit'].designation,
                "prix": int(prix_ecoles_map.get(p["produit"].pk, p["produit"].prix_detail)),
                "stock": p["stock"],
            }
            for p in produits_detail
        ],
        "taux": float(ecole.remise_convention or 0),
    }
    contexte = {
        "ecole": ecole,
        "kits": kits_disponibles,
        "produits_detail": produits_detail,
        "js_data": js_data,
        "modes_paiement": ModePaiement.choices,
        "ventes_du_jour": (
            Vente.objects.filter(ecole=ecole, vendeuse=u, horodatage__date=timezone.localdate())
            .prefetch_related("lignes__kit", "lignes__produit")[:20]
        ),
        "total_du_jour": Vente.objects.filter(
            ecole=ecole, vendeuse=u, horodatage__date=timezone.localdate()
        ).exclude(statut=StatutVente.ANNULEE).aggregate(t=Sum("montant_total"))["t"] or 0,
    }
    return render(request, "ventes/vente.html", contexte)


# ─── Proforma ────────────────────────────────────────────────────────────────

@login_required
def proforma_formulaire(request):
    u = request.user
    ecole = u.site
    prix_ecoles_map = {
        pe.produit_id: pe.prix_detail
        for pe in PrixEcole.objects.filter(ecole=ecole)
    }
    articles_js = [
        {
            "id": str(p.pk),
            "libelle": p.designation,
            "designation": p.designation,
            "prix": int(prix_ecoles_map.get(p.pk, p.prix_detail)),
        }
        for p in Produit.objects.filter(actif=True).select_related("categorie").order_by("code")
    ]
    from django.utils import timezone as tz
    return render(request, "ventes/proforma.html", {
        "ecole": ecole,
        "articles_js": articles_js,
        "today": tz.localdate().isoformat(),
    })


@login_required
def proforma_apercu(request):
    if request.method != "POST":
        return redirect("proforma_formulaire")

    client     = request.POST.get("client", "").strip()
    date_str   = request.POST.get("date", "")
    site_nom   = request.POST.get("site_nom", "")

    lignes = []
    i = 0
    while True:
        designation = request.POST.get(f"designation_{i}", "")
        if not designation:
            break
        try:
            quantite = int(request.POST.get(f"quantite_{i}", 1))
            prix     = int(request.POST.get(f"prix_{i}", 0))
        except (ValueError, TypeError):
            quantite, prix = 1, 0
        if quantite > 0:
            lignes.append({
                "designation": designation,
                "quantite": quantite,
                "prix": prix,
                "total": quantite * prix,
            })
        i += 1
        if i > 100:
            break

    total = sum(l["total"] for l in lignes)
    return render(request, "ventes/proforma_apercu.html", {
        "client": client,
        "date_str": date_str,
        "site_nom": site_nom,
        "lignes": lignes,
        "total": total,
    })


def _enregistrer(request, ecole):
    try:
        charge = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erreur": "Requête illisible."}, status=400)

    modes_valides = {c[0] for c in ModePaiement.choices}

    lignes_kit = []
    for item in charge.get("kits", []):
        kit = get_object_or_404(Kit, pk=item["id"], ecole=ecole, actif=True)
        mode = item.get("mode", ModePaiement.ESPECES)
        if mode not in modes_valides:
            mode = ModePaiement.ESPECES
        lignes_kit.append((kit, int(item["quantite"]), mode))

    lignes_detail = []
    for item in charge.get("detail", []):
        produit = get_object_or_404(Produit, pk=item["id"], actif=True)
        mode = item.get("mode", ModePaiement.ESPECES)
        if mode not in modes_valides:
            mode = ModePaiement.ESPECES
        lignes_detail.append((produit, int(item["quantite"]), mode))

    # Mode dominant de la vente (pour les clôtures et filtres)
    tous_modes = [m for _, _, m in lignes_kit + lignes_detail]
    mode_dominant = Counter(tous_modes).most_common(1)[0][0] if tous_modes else ModePaiement.ESPECES

    try:
        v = enregistrer_vente(
            ecole=ecole,
            vendeuse=request.user,
            kits=lignes_kit,
            detail=lignes_detail,
            mode_paiement=mode_dominant,
            appliquer_remise_convention=bool(charge.get("remise_convention")),
            uuid=charge.get("uuid"),
            telephone_client=(charge.get("telephone") or "").strip(),
            montant_recu=charge.get("montant_recu") or None,
        )
    except VenteDejaEnregistree as doublon:
        # La requête précédente avait abouti : on renvoie la vente existante.
        v = doublon.vente
    except ValidationError as e:
        return JsonResponse({"erreur": "; ".join(e.messages)}, status=400)

    return JsonResponse(
        {
            "numero": v.numero,
            "montant": f"{v.montant_total:,.0f}".replace(",", " "),
            "partielle": not v.est_complete,
            "manquants": [
                {"code": l.produit.code, "quantite": l.quantite_manquante} for l in v.reste_a_livrer
            ],
            "url_recu": f"/recu/{v.uuid}/",
        }
    )


@login_required
def file_livraison(request):
    """
    Remplace le reçu papier comme jeton entre la caissière et le commercial.
    Le commercial voit ce qu'il doit constituer, référence par référence.
    """
    u = request.user
    if not u.peut_voir_ventes():
        return redirect("hub_stock")
    sites = u.sites_autorises()
    attente = (
        Vente.objects.filter(ecole__in=sites, statut=StatutVente.EN_ATTENTE)
        .select_related("ecole", "vendeuse")
        .prefetch_related("lignes__kit", "lignes__produit", "lignes_produit__produit")
        .order_by("horodatage")
    )
    partielles = (
        Vente.objects.filter(ecole__in=sites, statut=StatutVente.PARTIELLE)
        .select_related("ecole")
        .prefetch_related("lignes_produit__produit")
        .order_by("horodatage")
    )
    return render(
        request,
        "ventes/livraison.html",
        {"attente": attente, "partielles": partielles, "maintenant": timezone.now()},
    )


@login_required
@require_POST
def livrer(request, uuid):
    v = get_object_or_404(Vente, uuid=uuid)
    if not request.user.peut_acceder_au_site(v.ecole):
        messages.error(request, "Vente hors de votre périmètre.")
        return redirect("file_livraison")
    marquer_livree(v, par=request.user)
    messages.success(request, f"Vente {v.numero} remise au client.")
    return redirect("file_livraison")


@login_required
@require_POST
def servir_solde(request, uuid):
    v = get_object_or_404(Vente, uuid=uuid)
    if not request.user.peut_acceder_au_site(v.ecole):
        messages.error(request, "Vente hors de votre périmètre.")
        return redirect("file_livraison")
    completer_livraison(v, par=request.user)
    if v.est_complete:
        messages.success(request, f"Solde de la vente {v.numero} servi intégralement.")
    else:
        messages.warning(request, f"Vente {v.numero} : stock encore insuffisant pour solder.")
    return redirect("file_livraison")


@login_required
def recu(request, uuid):
    if not request.user.peut_voir_ventes():
        return redirect("hub_stock")
    v = get_object_or_404(
        Vente.objects.select_related("ecole", "vendeuse").prefetch_related(
            "lignes__kit__lignes__produit", "lignes__produit", "lignes_produit__produit"
        ),
        uuid=uuid,
    )
    if not request.user.peut_acceder_au_site(v.ecole):
        messages.error(request, "Vente hors de votre périmètre.")
        return redirect("accueil")
    peut_demander_annulation = (
        v.statut != StatutVente.ANNULEE
        and not v.annulation_demandee
        and v.vendeuse_id == request.user.pk
    )
    return render(request, "ventes/recu.html", {
        "v": v,
        "peut_demander_annulation": peut_demander_annulation,
    })


@login_required
def recu_imprimer(request, uuid):
    """Page autonome (sans base.html) déclenchant window.print() à l'ouverture."""
    v = get_object_or_404(
        Vente.objects.select_related("ecole", "vendeuse").prefetch_related(
            "lignes__kit__lignes__produit", "lignes__produit", "lignes_produit__produit"
        ),
        uuid=uuid,
    )
    if not request.user.peut_acceder_au_site(v.ecole):
        return redirect("accueil")
    return render(request, "ventes/recu_imprimer.html", {"v": v})


@login_required
def tableau_bord(request):
    u = request.user
    sites = u.sites_autorises()
    ventes = Vente.objects.filter(ecole__in=sites).exclude(statut=StatutVente.ANNULEE)
    aujourdhui = ventes.filter(horodatage__date=timezone.localdate())

    par_ecole = (
        aujourdhui.values("ecole__nom")
        .annotate(ca=Sum("montant_total"), n=Count("id"))
        .order_by("-ca")
    )
    alertes = references_sous_seuil(sites=sites).select_related("site", "produit")[:25]

    return render(
        request,
        "ventes/tableau_bord.html",
        {
            "ca_jour": aujourdhui.aggregate(t=Sum("montant_total"))["t"] or 0,
            "nb_ventes_jour": aujourdhui.count(),
            "ca_total": ventes.aggregate(t=Sum("montant_total"))["t"] or 0,
            "par_ecole": par_ecole,
            "alertes": alertes,
            "en_attente": ventes.filter(statut=StatutVente.EN_ATTENTE).count(),
            "partielles": ventes.filter(statut=StatutVente.PARTIELLE).count(),
            "valeur_stock": SoldeStock.objects.filter(site__in=sites).aggregate(
                v=Sum("quantite")
            )["v"] or 0,
            "perimetre": "national" if u.acces_national else ", ".join(s.nom for s in sites[:5]),
        },
    )


# ─── Périmètres par rôle ─────────────────────────────────────────────────────


def _ecoles_perimetre(user):
    """Sites dont cet utilisateur peut consulter les ventes."""
    return user.sites_autorises().filter(actif=True)


def _sites_perimetre(user):
    """Sites dont cet utilisateur peut consulter le stock."""
    return user.sites_autorises()


def _perimetre_label(user):
    if user.acces_national:
        return "national"
    if user.site:
        return user.site.nom
    return "—"


# ─── Historique des ventes ───────────────────────────────────────────────────


@login_required
def historique_ventes(request):
    u = request.user
    if not u.peut_voir_ventes():
        return redirect("hub_stock")
    ecoles = _ecoles_perimetre(u)

    qs = (
        Vente.objects.filter(ecole__in=ecoles)
        .select_related("ecole", "vendeuse")
        .order_by("-horodatage")
    )

    # Les utilisateurs qui peuvent vendre ne voient que leurs propres ventes
    if u.peut_vendre() and not u.profil == Profil.DG:
        qs = qs.filter(vendeuse=u)

    # Filtres via GET
    debut      = request.GET.get("debut", "")
    fin        = request.GET.get("fin", "")
    statut     = request.GET.get("statut", "")
    ecole_id   = request.GET.get("ecole", "")

    if debut:
        try:
            qs = qs.filter(horodatage__date__gte=date_cls.fromisoformat(debut))
        except ValueError:
            debut = ""
    if fin:
        try:
            qs = qs.filter(horodatage__date__lte=date_cls.fromisoformat(fin))
        except ValueError:
            fin = ""
    if statut:
        qs = qs.filter(statut=statut)
    if ecole_id.isdigit():
        qs = qs.filter(ecole_id=ecole_id)

    qs_actives = qs.exclude(statut=StatutVente.ANNULEE)
    total = qs_actives.aggregate(t=Sum("montant_total"))["t"] or 0
    nb = qs_actives.count()

    page = Paginator(qs, 30).get_page(request.GET.get("page", 1))

    ecoles_list = list(ecoles.order_by("nom"))
    ecole_unique = ecoles_list[0] if len(ecoles_list) == 1 else None

    return render(request, "ventes/historique.html", {
        "page": page,
        "ecoles": ecoles_list,
        "ecole_unique": ecole_unique,
        "communes": [],
        "statuts": [
            (StatutVente.LIVREE, "Payée"),
            (StatutVente.ANNULEE, "Annulée"),
        ],
        "filtres": {"debut": debut, "fin": fin, "statut": statut, "ecole": ecole_id, "commune": ""},
        "total": total,
        "nb": nb,
        "perimetre": _perimetre_label(u),
        "caissiere": False,
        "multi_communes": False,
    })


# ─── Rapport kits vendus ─────────────────────────────────────────────────────


@login_required
def rapport_kits_vendus(request):
    from .models import LigneVente, LigneProduitVente
    u = request.user
    if not u.peut_voir_ventes():
        return redirect("hub_stock")

    ecoles = _ecoles_perimetre(u)
    debut_str = request.GET.get("debut", "")
    fin_str   = request.GET.get("fin", "")
    ecole_id  = request.GET.get("ecole", "")
    commune_id = request.GET.get("commune", "")

    try:
        debut = date_cls.fromisoformat(debut_str) if debut_str else None
    except ValueError:
        debut = None
        debut_str = ""
    try:
        fin = date_cls.fromisoformat(fin_str) if fin_str else None
    except ValueError:
        fin = None
        fin_str = ""

    if commune_id.isdigit():
        ecoles = ecoles.filter(commune_id=commune_id)
    if ecole_id.isdigit():
        ecoles = ecoles.filter(pk=ecole_id)

    ventes_qs = Vente.objects.filter(ecole__in=ecoles).exclude(statut=StatutVente.ANNULEE).select_related("ecole").order_by("-horodatage")
    if debut:
        ventes_qs = ventes_qs.filter(horodatage__date__gte=debut)
    if fin:
        ventes_qs = ventes_qs.filter(horodatage__date__lte=fin)

    ventes_ids_selectionnes = request.GET.getlist("vente")
    if ventes_ids_selectionnes:
        try:
            ventes_ids_selectionnes = [int(v) for v in ventes_ids_selectionnes]
        except ValueError:
            ventes_ids_selectionnes = []
        ventes_filtrees = ventes_qs.filter(pk__in=ventes_ids_selectionnes)
    else:
        ventes_filtrees = ventes_qs

    from decimal import Decimal as Dec

    # Calcul avec remise distribuée proportionnellement sur chaque ligne.
    # Pour chaque LigneVente : montant_effectif = montant_brut × (vente.montant_total / total_brut_vente)
    toutes_lignes = (
        LigneVente.objects
        .filter(vente__in=ventes_filtrees)
        .select_related("vente", "kit", "kit__classe", "produit")
        .order_by("vente_id", "pk")
    )

    # Totaux bruts par vente pour calculer le ratio remise
    gross_par_vente = {}
    for l in toutes_lignes:
        gross_par_vente[l.vente_id] = gross_par_vente.get(l.vente_id, Dec(0)) + l.quantite * l.prix_unitaire

    kits_map    = {}  # kit_libelle → {quantite, montant}
    articles_map = {}  # designation → {quantite, montant}

    for l in toutes_lignes:
        brut = l.quantite * l.prix_unitaire
        gross_vente = gross_par_vente.get(l.vente_id, brut)
        if gross_vente:
            effectif = brut * l.vente.montant_total / gross_vente
        else:
            effectif = brut

        if l.kit_id:
            key = f"Kit {l.kit.classe.libelle}"
            e = kits_map.setdefault(key, {"quantite": 0, "montant": Dec(0)})
            e["quantite"] += l.quantite
            e["montant"]  += effectif
        else:
            key = l.produit.designation
            e = articles_map.setdefault(key, {"quantite": 0, "montant": Dec(0)})
            e["quantite"] += l.quantite
            e["montant"]  += effectif

    kits_data = [
        {"libelle": k, "quantite": v["quantite"], "montant": v["montant"]}
        for k, v in sorted(kits_map.items())
    ]
    articles_data = [
        {"libelle": k, "quantite": v["quantite"], "montant": v["montant"]}
        for k, v in sorted(articles_map.items())
    ]

    sous_total_kits_qte = sum(r["quantite"] for r in kits_data)
    sous_total_kits_mnt = sum(r["montant"]  for r in kits_data)
    sous_total_art_qte  = sum(r["quantite"] for r in articles_data)
    sous_total_art_mnt  = sum(r["montant"]  for r in articles_data)

    # Total via montant_total — référence autoritaire, évite la dérive de l'arrondi.
    total_mnt = ventes_filtrees.aggregate(t=Sum("montant_total"))["t"] or 0

    communes = Site.objects.filter(pk__in=ecoles.values("commune_id")).distinct() if hasattr(Site, "commune") else []
    ecoles_list = _ecoles_perimetre(u).order_by("nom")

    filtres_get = ""
    if debut_str: filtres_get += f"&debut={debut_str}"
    if fin_str:   filtres_get += f"&fin={fin_str}"
    if ecole_id:  filtres_get += f"&ecole={ecole_id}"
    if commune_id: filtres_get += f"&commune={commune_id}"

    return render(request, "ventes/rapport_kits.html", {
        "ventes": ventes_qs,
        "ventes_ids_selectionnes": ventes_ids_selectionnes,
        "kits_data": kits_data,
        "articles_data": articles_data,
        "sous_total_kits_qte": sous_total_kits_qte,
        "sous_total_kits_mnt": sous_total_kits_mnt,
        "sous_total_art_qte": sous_total_art_qte,
        "sous_total_art_mnt": sous_total_art_mnt,
        "total_mnt": total_mnt,
        "ecoles": ecoles_list,
        "filtres": {"debut": debut_str, "fin": fin_str, "ecole": ecole_id, "commune": commune_id},
        "filtres_get": filtres_get.lstrip("&"),
        "perimetre": _perimetre_label(u),
    })


@login_required
def rapport_kits_detail(request):
    from .models import LigneProduitVente
    u = request.user
    if not u.peut_voir_ventes():
        return redirect("hub_stock")

    ecoles = _ecoles_perimetre(u)
    debut_str  = request.GET.get("debut", "")
    fin_str    = request.GET.get("fin", "")
    ecole_id   = request.GET.get("ecole", "")
    commune_id = request.GET.get("commune", "")

    try:
        debut = date_cls.fromisoformat(debut_str) if debut_str else None
    except ValueError:
        debut = None
        debut_str = ""
    try:
        fin = date_cls.fromisoformat(fin_str) if fin_str else None
    except ValueError:
        fin = None
        fin_str = ""

    if commune_id.isdigit():
        ecoles = ecoles.filter(commune_id=commune_id)
    if ecole_id.isdigit():
        ecoles = ecoles.filter(pk=ecole_id)

    ventes_ids = request.GET.getlist("vente")
    qs = LigneProduitVente.objects.filter(vente__ecole__in=ecoles).exclude(vente__statut=StatutVente.ANNULEE)
    if debut:
        qs = qs.filter(vente__horodatage__date__gte=debut)
    if fin:
        qs = qs.filter(vente__horodatage__date__lte=fin)

    if ventes_ids:
        try:
            qs = qs.filter(vente_id__in=[int(v) for v in ventes_ids])
        except ValueError:
            pass

    from django.db.models import Sum as DSum
    lignes = (
        qs
        .values("produit__designation")
        .annotate(total=DSum("quantite_due"))
        .order_by("produit__designation")
    )
    lignes = list(lignes)
    total_qte = sum(l["total"] for l in lignes)

    retour_get = request.GET.urlencode()

    return render(request, "ventes/rapport_kits_detail.html", {
        "lignes": lignes,
        "total_qte": total_qte,
        "filtres": {"debut": debut_str, "fin": fin_str, "ecole": ecole_id, "commune": commune_id},
        "retour_get": retour_get,
        "perimetre": _perimetre_label(u),
    })


# ─── Stock articles ──────────────────────────────────────────────────────────


@login_required
def stock_articles(request):
    u = request.user
    sites = _sites_perimetre(u)

    soldes = (
        SoldeStock.objects.filter(site__in=sites)
        .select_related("site", "produit", "produit__categorie")
        .order_by("produit__categorie__nom", "produit__code", "site__nom")
    )

    all_sites = list(sites.order_by("nom"))
    site_unique = all_sites[0] if len(all_sites) == 1 else None

    site_param = request.GET.get("site")
    if site_param is None:
        if u.is_superuser or u.profil == Profil.DG:
            site_id = ""
        elif u.site_id and sites.filter(pk=u.site_id).exists():
            site_id = str(u.site_id)
        else:
            site_id = ""
    else:
        site_id = site_param or ""
    commune_id = ""
    categorie_id = request.GET.get("categorie", "")
    etat = request.GET.get("etat", "")
    produit_id = request.GET.get("produit", "")

    if site_id.isdigit():
        soldes = soldes.filter(site_id=site_id)
    if categorie_id.isdigit():
        soldes = soldes.filter(produit__categorie_id=categorie_id)
    if etat == "rupture":
        soldes = soldes.filter(quantite__lte=0)
    elif etat == "alerte":
        soldes = soldes.filter(quantite__gt=0, quantite__lte=F("stock_securite"))
    elif etat == "surstock":
        soldes = soldes.filter(stock_maximum__gt=0, quantite__gt=F("stock_maximum"))
    elif etat == "ok":
        soldes = soldes.filter(quantite__gt=F("stock_securite")).exclude(
            stock_maximum__gt=0, quantite__gt=F("stock_maximum")
        )
    if produit_id.isdigit():
        soldes = soldes.filter(produit_id=produit_id)

    sites_dropdown = all_sites

    produits = Produit.objects.filter(actif=True).order_by("code")
    total = soldes.aggregate(t=Sum("quantite"))["t"] or 0

    # Avoirs ouverts par (produit, site) pour la colonne Avoir
    from django.db.models import OuterRef, Subquery
    avoirs_qs = (
        LigneProduitVente.objects
        .filter(
            vente__ecole=OuterRef("site"),
            produit=OuterRef("produit"),
            avoir_annule=False,
        )
        .exclude(quantite_servie=F("quantite_due"))
        .exclude(vente__statut=StatutVente.ANNULEE)
        .values("vente__ecole", "produit")
        .annotate(total=Sum(F("quantite_due") - F("quantite_servie")))
        .values("total")
    )
    soldes = soldes.annotate(quantite_avoir=Subquery(avoirs_qs[:1]))

    # La colonne Dû (avoirs) est visible par tous
    peut_voir_du = True
    peut_voir_valeur = u.profil == Profil.DG or u.is_superuser
    if peut_voir_valeur:
        soldes = soldes.annotate(
            valeur_stock=ExpressionWrapper(
                F("quantite") * F("produit__cout_achat"),
                output_field=DecimalField(),
            )
        )
        total_valeur = soldes.aggregate(v=Sum(ExpressionWrapper(
            F("quantite") * F("produit__cout_achat"),
            output_field=DecimalField(),
        )))["v"] or 0
    else:
        total_valeur = None

    return render(request, "ventes/stock_articles.html", {
        "soldes": soldes,
        "sites": sites_dropdown,
        "site_unique": site_unique,
        "produits": produits,
        "categories": CategorieProduit.objects.all(),
        "communes": [],
        "filtres": {
            "commune": "",
            "site": site_id,
            "categorie": categorie_id,
            "etat": etat,
            "produit": produit_id,
        },
        "perimetre": _perimetre_label(u),
        "total_articles": total,
        "peut_voir_valeur": peut_voir_valeur,
        "peut_voir_du": peut_voir_du,
        "total_valeur": total_valeur,
    })


# ─── Stock kits ───────────────────────────────────────────────────────────────


@login_required
def stock_kits(request):
    u = request.user

    toutes_ecoles = _ecoles_perimetre(u).order_by("nom")
    toutes_ecoles_list = list(toutes_ecoles)
    ecole_unique = toutes_ecoles_list[0] if len(toutes_ecoles_list) == 1 else None

    ecole_id = request.GET.get("ecole", "")
    niveau_filtre = request.GET.get("niveau", "")
    classe_id = request.GET.get("classe", "")
    non_constructibles = request.GET.get("nc", "")

    ecoles_filtrees = toutes_ecoles
    if ecole_id:
        ecoles_filtrees = ecoles_filtrees.filter(pk=ecole_id)

    magasin_stock = None

    donnees = []
    for ecole in ecoles_filtrees:
        kits = _kits_disponibles(ecole, stock_depuis=magasin_stock)
        if niveau_filtre:
            kits = [k for k in kits if k["kit"].classe.niveau == niveau_filtre]
        if classe_id.isdigit():
            kits = [k for k in kits if k["kit"].classe_id == int(classe_id)]
        if non_constructibles:
            kits = [k for k in kits if k["constructibles"] == 0]
        if kits:
            donnees.append({"ecole": ecole, "kits": kits})

    ecoles_dropdown = toutes_ecoles_list

    # Classes du périmètre, filtrées par niveau si sélectionné
    from kits.models import ClasseEcole
    classes_qs = ClasseEcole.objects.filter(ecole__in=toutes_ecoles)
    if niveau_filtre:
        classes_qs = classes_qs.filter(niveau=niveau_filtre)
    classes_dropdown = list(classes_qs.order_by("niveau", "libelle"))

    return render(request, "ventes/stock_kits.html", {
        "donnees": donnees,
        "perimetre": _perimetre_label(u),
        "toutes_ecoles": ecoles_dropdown,
        "ecole_unique": ecole_unique,
        "communes": [],
        "niveaux": Niveau.choices,
        "classes": classes_dropdown,
        "filtres": {
            "commune": "",
            "ecole": ecole_id,
            "niveau": niveau_filtre,
            "classe": classe_id,
            "nc": non_constructibles,
        },
    })


# ─── Facture détaillée ────────────────────────────────────────────────────────


@login_required
def facture_vente(request, uuid):
    if not request.user.peut_voir_ventes():
        return redirect("hub_stock")
    v = get_object_or_404(
        Vente.objects.select_related("ecole", "vendeuse", "livree_par").prefetch_related(
            "lignes__kit__lignes__produit",
            "lignes__produit",
            "lignes_produit__produit",
        ),
        uuid=uuid,
    )

    if not request.user.peut_acceder_au_site(v.ecole):
        messages.error(request, "Facture hors de votre périmètre.")
        return redirect("historique_ventes")

    # Les utilisateurs non-DG ne peuvent consulter que leurs propres factures si caissier
    if request.user.profil == Profil.CHEF_EQUIPE and v.vendeuse_id != request.user.pk and not request.user.peut_acceder_au_site(v.ecole):
        messages.error(request, "Vous ne pouvez consulter que vos propres factures.")
        return redirect("historique_ventes")

    peut_annuler = (
        v.annulation_demandee
        and v.statut != StatutVente.ANNULEE
        and request.user.profil == Profil.CHEF_EQUIPE
        and request.user.peut_acceder_au_site(v.ecole)
    )
    peut_demander_annulation = (
        v.statut != StatutVente.ANNULEE
        and not v.annulation_demandee
        and v.vendeuse_id == request.user.pk
    )
    peut_rejeter_annulation = (
        v.annulation_demandee
        and v.statut != StatutVente.ANNULEE
        and request.user.profil == Profil.CHEF_EQUIPE
        and request.user.peut_acceder_au_site(v.ecole)
    )
    return render(request, "ventes/facture.html", {
        "v": v,
        "peut_annuler": peut_annuler,
        "peut_demander_annulation": peut_demander_annulation,
        "peut_rejeter_annulation": peut_rejeter_annulation,
    })


@login_required
def vente_annuler(request, uuid):
    v = get_object_or_404(Vente, uuid=uuid)
    if request.user.profil != Profil.CHEF_EQUIPE:
        messages.error(request, "Seul un chef d'équipe peut annuler une vente.")
        return redirect("facture_vente", uuid=uuid)
    if not request.user.peut_acceder_au_site(v.ecole):
        messages.error(request, "Vente hors de votre périmètre.")
        return redirect("historique_ventes")
    if v.statut == StatutVente.ANNULEE:
        messages.warning(request, "Cette vente est déjà annulée.")
        return redirect("facture_vente", uuid=uuid)
    if request.method == "POST":
        motif = request.POST.get("motif", "").strip()
        if not motif:
            messages.error(request, "Veuillez sélectionner un motif d'annulation.")
        else:
            try:
                annuler_vente(v, par=request.user, motif=motif)
                creer_notification(
                    v.vendeuse,
                    type=TypeNotification.VENTE_ANNULEE,
                    titre=f"Vente {v.numero} annulée",
                    message=f"La vente {v.numero} ({v.montant_total:,.0f} F CFA) a été annulée par {request.user.get_full_name()}. Motif : {motif}",
                    lien=f"/recu/{v.uuid}/",
                )
                messages.success(request, f"Vente {v.numero} annulée.")
                return redirect("facture_vente", uuid=uuid)
            except ValidationError as e:
                messages.error(request, str(e))
    return render(request, "ventes/annuler.html", {"v": v})


@login_required
def vente_demander_annulation(request, uuid):
    """Le caissier soumet une demande d'annulation au chef d'équipe."""
    if not request.user.peut_vendre():
        messages.error(request, "Accès réservé à la caisse.")
        return redirect("facture_vente", uuid=uuid)
    v = get_object_or_404(Vente, uuid=uuid)
    if not request.user.peut_acceder_au_site(v.ecole):
        return redirect("historique_ventes")
    if v.statut == StatutVente.ANNULEE:
        messages.warning(request, "Cette vente est déjà annulée.")
        return redirect("facture_vente", uuid=uuid)
    if v.annulation_demandee:
        messages.info(request, "Une demande d'annulation est déjà en cours pour cette vente.")
        return redirect("facture_vente", uuid=uuid)
    if request.method == "POST":
        v.annulation_demandee = True
        v.motif_demande = ""
        v.save(update_fields=["annulation_demandee", "motif_demande"])
        notifier_chefs_equipe(
            v.ecole,
            type=TypeNotification.DEMANDE_ANNULATION,
            titre=f"Demande d'annulation — vente {v.numero}",
            message=f"{v.vendeuse.get_full_name()} demande l'annulation de la vente {v.numero} ({v.montant_total:,.0f} F CFA).",
            lien=f"/facture/{v.uuid}/",
        )
        messages.success(request, "Demande d'annulation transmise au chef d'équipe.")
        return redirect("facture_vente", uuid=uuid)
    return render(request, "ventes/demande_annulation.html", {"v": v})


@login_required
def vente_rejeter_annulation(request, uuid):
    """Le chef d'équipe rejette la demande d'annulation du commercial."""
    if request.user.profil != Profil.CHEF_EQUIPE:
        messages.error(request, "Accès réservé au chef d'équipe.")
        return redirect("facture_vente", uuid=uuid)
    v = get_object_or_404(Vente, uuid=uuid)
    if not request.user.peut_acceder_au_site(v.ecole):
        return redirect("historique_ventes")
    if not v.annulation_demandee:
        return redirect("facture_vente", uuid=uuid)
    if request.method == "POST":
        v.annulation_demandee = False
        v.motif_demande = ""
        v.save(update_fields=["annulation_demandee", "motif_demande"])
        creer_notification(
            v.vendeuse,
            type=TypeNotification.ANNULATION_REJETEE,
            titre=f"Demande d'annulation rejetée — {v.numero}",
            message=f"Votre demande d'annulation de la vente {v.numero} a été rejetée par {request.user.get_full_name()}.",
            lien=f"/recu/{v.uuid}/",
        )
        messages.success(request, "Demande d'annulation rejetée.")
        return redirect("facture_vente", uuid=uuid)
    return redirect("facture_vente", uuid=uuid)


@login_required
def demandes_annulation(request):
    return redirect("historique_annulations")


@login_required
def historique_annulations(request):
    """Vue unifiée : demandes en attente (chef d'équipe) + historique des annulations."""
    u = request.user
    if u.profil not in (Profil.CHEF_EQUIPE, Profil.DG) and not u.is_superuser:
        messages.error(request, "Accès non autorisé.")
        return redirect("hub_ventes")

    ecoles = u.sites_autorises()

    peut_traiter = u.profil == Profil.CHEF_EQUIPE or u.is_superuser
    demandes = (
        Vente.objects
        .filter(annulation_demandee=True, ecole__in=ecoles)
        .exclude(statut=StatutVente.ANNULEE)
        .select_related("ecole", "vendeuse")
        .order_by("-horodatage")
    ) if peut_traiter else Vente.objects.none()

    qs = (
        Vente.objects.filter(statut=StatutVente.ANNULEE, ecole__in=ecoles)
        .select_related("ecole", "vendeuse", "annulee_par")
        .prefetch_related("lignes")
        .order_by("-annulee_le")
    )

    debut      = request.GET.get("debut", "")
    fin        = request.GET.get("fin", "")
    ecole_id   = request.GET.get("ecole", "")

    if debut:
        qs = qs.filter(annulee_le__date__gte=debut)
    if fin:
        qs = qs.filter(annulee_le__date__lte=fin)
    if ecole_id.isdigit():
        qs = qs.filter(ecole_id=ecole_id)

    ecoles_list = list(ecoles.order_by("nom"))

    return render(request, "ventes/annulations.html", {
        "demandes": demandes,
        "nb_demandes": demandes.count(),
        "annulations": qs[:200],
        "ecoles": ecoles_list,
        "communes": [],
        "filtres": {"debut": debut, "fin": fin, "commune": "", "ecole": ecole_id},
        "nb": qs.count(),
        "multi_communes": False,
        "peut_traiter": peut_traiter,
    })


# ─── Clôture de caisse (M19) ─────────────────────────────────────────────────

def _finance_annotee(ventes_qs):
    """Annote chaque vente avec les montants par mode de paiement (depuis les lignes)."""
    montant_ligne = ExpressionWrapper(
        F("lignes__prix_unitaire") * F("lignes__quantite"),
        output_field=DecimalField(),
    )
    return ventes_qs.annotate(
        m_esp=Sum(Case(When(lignes__mode_paiement=ModePaiement.ESPECES, then=montant_ligne),
                       default=Value(0), output_field=DecimalField())),
        m_mob=Sum(Case(When(lignes__mode_paiement=ModePaiement.MOBILE_MONEY, then=montant_ligne),
                       default=Value(0), output_field=DecimalField())),
        m_aut=Sum(Case(When(lignes__mode_paiement=ModePaiement.AUTRE, then=montant_ligne),
                       default=Value(0), output_field=DecimalField())),
    )


@login_required
def hub_ventes(request):
    u = request.user
    if not u.peut_voir_ventes():
        return redirect("hub_stock")
    ecoles = _ecoles_perimetre(u)
    ventes = Vente.objects.filter(ecole__in=ecoles)
    ventes_actives = ventes.exclude(statut=StatutVente.ANNULEE)
    nb_demandes = 0
    if u.profil == Profil.CHEF_EQUIPE or u.is_superuser:
        nb_demandes = (
            Vente.objects.filter(annulation_demandee=True, ecole__in=ecoles)
            .exclude(statut=StatutVente.ANNULEE)
            .count()
        )
    nb_avoirs = (
        LigneProduitVente.objects
        .filter(vente__ecole__in=ecoles, avoir_annule=False)
        .exclude(quantite_servie=F("quantite_due"))
        .exclude(vente__statut=StatutVente.ANNULEE)
        .count()
    )
    return render(request, "ventes/hub.html", {
        "nb_jour":      ventes_actives.filter(horodatage__date=timezone.localdate()).count(),
        "nb_total":     ventes_actives.count(),
        "peut_vendre":  u.peut_vendre(),
        "nb_demandes":  nb_demandes,
        "nb_avoirs":    nb_avoirs,
    })


@login_required
def finances_entrees_sorties(request):
    from depenses.models import Depense, StatutDepense

    u          = request.user
    ecoles     = _ecoles_perimetre(u)
    tous_sites = u.sites_autorises()

    debut      = request.GET.get("debut", "")
    fin        = request.GET.get("fin", "")
    commune_id = ""
    site_id    = request.GET.get("site", "")
    mode_f     = request.GET.get("mode", "")

    sites_dispo = tous_sites.order_by("nom")

    dep_sites = tous_sites
    filtre_sup = site_id == "__sup__"
    if site_id.isdigit():
        ecoles    = ecoles.filter(pk=site_id)
        dep_sites = tous_sites.filter(pk=site_id)

    # ── Entrées (ventes) ──────────────────────────────────────
    ventes_qs = (
        Vente.objects.filter(ecole__in=ecoles)
        .exclude(statut=StatutVente.ANNULEE)
        .select_related("ecole", "vendeuse")
        .prefetch_related("lignes__kit", "lignes__produit")
    )
    if debut:
        try:
            ventes_qs = ventes_qs.filter(horodatage__date__gte=date_cls.fromisoformat(debut))
        except ValueError:
            debut = ""
    if fin:
        try:
            ventes_qs = ventes_qs.filter(horodatage__date__lte=date_cls.fromisoformat(fin))
        except ValueError:
            fin = ""
    if mode_f in {c[0] for c in ModePaiement.choices}:
        ventes_qs = ventes_qs.filter(lignes__mode_paiement=mode_f).distinct()

    finances = list(_finance_annotee(ventes_qs).order_by("-horodatage")[:200])
    for v in finances:
        if v.remise:
            brut = (v.m_esp or 0) + (v.m_mob or 0) + (v.m_aut or 0)
            if brut:
                facteur = 1 - v.remise / brut
                v.m_esp = (v.m_esp or 0) * facteur
                v.m_mob = (v.m_mob or 0) * facteur
                v.m_aut = (v.m_aut or 0) * facteur
    totaux = {
        "esp":   sum((v.m_esp or 0) for v in finances),
        "mob":   sum((v.m_mob or 0) for v in finances),
        "aut":   sum((v.m_aut or 0) for v in finances),
        "total": sum(v.montant_total for v in finances),
    }

    # ── Sorties (dépenses) ───────────────────────────────────
    from django.db.models import Q as _Q
    peut_voir_dep_sup = u.profil == Profil.DG or u.is_superuser
    _dep_q = _Q(site__in=dep_sites)

    dep_qs = (
        Depense.objects.filter(_dep_q)
        .select_related("site", "categorie", "cree_par")
        .order_by("-date_depense", "-pk")
    )
    dep_valide_qs = Depense.objects.filter(_dep_q, statut=StatutDepense.CONFIRME)

    if debut:
        try:
            d = date_cls.fromisoformat(debut)
            dep_qs        = dep_qs.filter(date_depense__gte=d)
            dep_valide_qs = dep_valide_qs.filter(date_depense__gte=d)
        except ValueError:
            pass
    if fin:
        try:
            d = date_cls.fromisoformat(fin)
            dep_qs        = dep_qs.filter(date_depense__lte=d)
            dep_valide_qs = dep_valide_qs.filter(date_depense__lte=d)
        except ValueError:
            pass
    depenses          = list(dep_qs[:200])
    total_sorties_val = dep_valide_qs.aggregate(t=Sum("montant_confirme"))["t"] or 0
    total_sorties_aff = sum((d.montant_confirme or 0) for d in depenses if d.statut == "CONFIRME")

    # ── Dons (transferts DON acceptés) ───────────────────────
    from transferts.models import TransfertLigne, StatutTransfert, TypeTransfert
    from collections import defaultdict

    don_qs = (
        TransfertLigne.objects
        .filter(
            transfert__site_origine__in=dep_sites,
            transfert__statut=StatutTransfert.ACCEPTE,
            transfert__type_transfert=TypeTransfert.DON,
        )
        .select_related("transfert__site_origine", "produit")
    )
    if debut:
        try:
            don_qs = don_qs.filter(transfert__traite_le__date__gte=date_cls.fromisoformat(debut))
        except ValueError:
            pass
    if fin:
        try:
            don_qs = don_qs.filter(transfert__traite_le__date__lte=date_cls.fromisoformat(fin))
        except ValueError:
            pass

    _dons_par_t = defaultdict(lambda: {"valeur": Decimal(0), "nb": 0, "date": None, "site_nom": "", "pk": None, "observations": ""})
    for ligne in don_qs:
        t   = ligne.transfert
        key = t.pk
        e   = _dons_par_t[key]
        e["pk"]           = t.pk
        e["date"]         = t.traite_le.date() if t.traite_le else t.cree_le.date()
        e["site_nom"]     = t.site_origine.nom
        e["observations"] = t.observations or ""
        e["valeur"]      += Decimal(ligne.quantite) * (ligne.produit.cout_achat or Decimal(0))
        e["nb"]          += 1

    dons_transfert = sorted(_dons_par_t.values(), key=lambda x: x["date"], reverse=True)
    total_dons     = sum(d["valeur"] for d in dons_transfert)

    total_sorties_val += total_dons
    total_sorties_aff += total_dons

    total_entrees = totaux["total"]
    solde         = total_entrees - total_sorties_val

    return render(request, "finances/entrees_sorties.html", {
        "finances":          finances,
        "totaux":            totaux,
        "depenses":          depenses,
        "dons_transfert":    dons_transfert,
        "total_entrees":     total_entrees,
        "total_sorties":     total_sorties_aff,
        "total_sorties_val": total_sorties_val,
        "solde":             solde,
        "filtres":           {"debut": debut, "fin": fin, "commune": "", "site": site_id, "mode": mode_f},
        "modes_paiement":    ModePaiement.choices,
        "sites_dispo":       sites_dispo,
        "communes":          [],
        "multi_communes":    False,
        "peut_voir_dep_sup": peut_voir_dep_sup,
        "libelle_sup":       None,
    })


@login_required
def finances_entrees_sorties_export(request):
    import io
    import openpyxl
    from django.http import HttpResponse
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from depenses.models import Depense, StatutDepense

    u          = request.user
    ecoles     = _ecoles_perimetre(u)
    tous_sites = u.sites_autorises()

    debut      = request.GET.get("debut", "")
    fin        = request.GET.get("fin", "")
    site_id    = request.GET.get("site", "")
    mode_f     = request.GET.get("mode", "")

    dep_sites  = tous_sites
    if site_id.isdigit():
        ecoles    = ecoles.filter(pk=site_id)
        dep_sites = tous_sites.filter(pk=site_id)

    # Entrées
    ventes_qs = (
        Vente.objects.filter(ecole__in=ecoles)
        .exclude(statut=StatutVente.ANNULEE)
        .select_related("ecole")
        .prefetch_related("lignes__kit", "lignes__produit")
    )
    if debut:
        try:
            ventes_qs = ventes_qs.filter(horodatage__date__gte=date_cls.fromisoformat(debut))
        except ValueError:
            pass
    if fin:
        try:
            ventes_qs = ventes_qs.filter(horodatage__date__lte=date_cls.fromisoformat(fin))
        except ValueError:
            pass
    if mode_f in {c[0] for c in ModePaiement.choices}:
        ventes_qs = ventes_qs.filter(lignes__mode_paiement=mode_f).distinct()
    finances = list(_finance_annotee(ventes_qs).order_by("-horodatage"))

    # Sorties
    _dep_q = _Q(site__in=dep_sites)

    dep_qs = Depense.objects.filter(_dep_q).select_related("site", "cree_par").order_by("-date_depense")
    if debut:
        try:
            dep_qs = dep_qs.filter(date_depense__gte=date_cls.fromisoformat(debut))
        except ValueError:
            pass
    if fin:
        try:
            dep_qs = dep_qs.filter(date_depense__lte=date_cls.fromisoformat(fin))
        except ValueError:
            pass
    depenses = list(dep_qs)

    wb = openpyxl.Workbook()
    HEADER = Font(bold=True, color="FFFFFF", size=11)
    FILL_E = PatternFill("solid", fgColor="1A6F3C")
    FILL_S = PatternFill("solid", fgColor="9B1C1C")
    CENTER = Alignment(horizontal="center", vertical="center")

    # Feuille Entrées
    ws_e = wb.active
    ws_e.title = "Entrées"
    entetes_e = ["Date", "Site", "N° vente", "Articles", "Espèces", "Mobile", "Autre", "Total"]
    for col, titre in enumerate(entetes_e, 1):
        c = ws_e.cell(row=1, column=col, value=titre)
        c.font = HEADER; c.fill = FILL_E; c.alignment = CENTER
    for row, v in enumerate(finances, 2):
        articles = ", ".join(f"{l.quantite}× {l.libelle}" for l in v.lignes.all())
        ws_e.cell(row=row, column=1, value=v.horodatage.strftime("%d/%m/%Y %H:%M"))
        ws_e.cell(row=row, column=2, value=v.ecole.nom)
        ws_e.cell(row=row, column=3, value=v.numero)
        ws_e.cell(row=row, column=4, value=articles)
        ws_e.cell(row=row, column=5, value=float(v.m_esp or 0))
        ws_e.cell(row=row, column=6, value=float(v.m_mob or 0))
        ws_e.cell(row=row, column=7, value=float(v.m_aut or 0))
        ws_e.cell(row=row, column=8, value=float(v.montant_total))
    for col in ws_e.columns:
        ws_e.column_dimensions[get_column_letter(col[0].column)].width = min(max(len(str(c.value or "")) for c in col) + 4, 50)

    # Feuille Sorties
    ws_s = wb.create_sheet("Sorties")
    entetes_s = ["Date", "Site", "Motif", "Statut", "Montant"]
    for col, titre in enumerate(entetes_s, 1):
        c = ws_s.cell(row=1, column=col, value=titre)
        c.font = HEADER; c.fill = FILL_S; c.alignment = CENTER
    for row, dep in enumerate(depenses, 2):
        if dep.site:
            site_str = dep.site.nom
        else:
            site_str = dep.cree_par.get_full_name()
        montant = float(dep.montant_confirme if dep.statut == "CONFIRME" and dep.montant_confirme is not None else dep.montant)
        ws_s.cell(row=row, column=1, value=dep.date_depense.strftime("%d/%m/%Y"))
        ws_s.cell(row=row, column=2, value=site_str)
        ws_s.cell(row=row, column=3, value=dep.motif)
        ws_s.cell(row=row, column=4, value=dep.get_statut_display())
        ws_s.cell(row=row, column=5, value=montant)
    for col in ws_s.columns:
        ws_s.column_dimensions[get_column_letter(col[0].column)].width = min(max(len(str(c.value or "")) for c in col) + 4, 50)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"entrees_sorties_{debut or 'debut'}_{fin or 'fin'}.xlsx"
    resp = HttpResponse(buf, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{fname}"'
    return resp


@login_required
def finances_ventes(request):
    u = request.user
    if not u.peut_voir_ventes():
        return redirect("hub_stock")
    ecoles = _ecoles_perimetre(u)

    debut      = request.GET.get("debut", "")
    fin        = request.GET.get("fin", "")
    mode_f     = request.GET.get("mode", "")
    type_f     = request.GET.get("type", "")
    ecole_id   = request.GET.get("ecole", "")

    qs = (
        Vente.objects.filter(ecole__in=ecoles)
        .exclude(statut=StatutVente.ANNULEE)
        .select_related("ecole", "vendeuse")
        .prefetch_related("lignes__kit", "lignes__produit")
    )
    if debut:
        try:
            qs = qs.filter(horodatage__date__gte=date_cls.fromisoformat(debut))
        except ValueError:
            debut = ""
    if fin:
        try:
            qs = qs.filter(horodatage__date__lte=date_cls.fromisoformat(fin))
        except ValueError:
            fin = ""
    if ecole_id.isdigit():
        qs = qs.filter(ecole_id=ecole_id)
    if mode_f in {c[0] for c in ModePaiement.choices}:
        qs = qs.filter(lignes__mode_paiement=mode_f).distinct()
    if type_f == "kit":
        qs = qs.filter(lignes__kit__isnull=False).distinct()
    elif type_f == "article":
        qs = qs.filter(lignes__produit__isnull=False).distinct()

    finances = list(_finance_annotee(qs).order_by("-horodatage")[:100])
    for v in finances:
        if v.remise:
            brut = (v.m_esp or 0) + (v.m_mob or 0) + (v.m_aut or 0)
            if brut:
                facteur = 1 - v.remise / brut
                v.m_esp = (v.m_esp or 0) * facteur
                v.m_mob = (v.m_mob or 0) * facteur
                v.m_aut = (v.m_aut or 0) * facteur
    totaux = {
        "esp":   sum((v.m_esp or 0) for v in finances),
        "mob":   sum((v.m_mob or 0) for v in finances),
        "aut":   sum((v.m_aut or 0) for v in finances),
        "total": sum(v.montant_total for v in finances),
    }
    ecoles_list = list(ecoles.order_by("nom"))
    ecole_unique = ecoles_list[0] if len(ecoles_list) == 1 else None

    return render(request, "ventes/finances.html", {
        "finances":       finances,
        "totaux":         totaux,
        "filtres":        {"debut": debut, "fin": fin, "mode": mode_f, "type": type_f, "commune": "", "ecole": ecole_id},
        "modes_paiement": ModePaiement.choices,
        "perimetre":      _perimetre_label(u),
        "ecoles":         ecoles_list,
        "ecole_unique":   ecole_unique,
        "communes":       [],
        "multi_communes": False,
    })


@login_required
def clotures_liste(request):
    if not request.user.peut_voir_ventes():
        return redirect("hub_stock")
    sites = request.user.sites_autorises()
    qs = (
        ClotureCaisse.objects
        .filter(ecole__in=sites)
        .select_related("ecole", "cloture_par")
        .order_by("-date")[:60]
    )
    return render(request, "ventes/clotures_liste.html", {
        "clotures": qs,
        "peut_cloturer": request.user.profil == Profil.CHEF_EQUIPE,
    })


@login_required
def cloturer_caisse(request):
    from django.db.models import Sum
    if request.user.profil != Profil.CHEF_EQUIPE:
        messages.error(request, "Seul le chef d'équipe peut clôturer la caisse.")
        return redirect("clotures_liste")
    sites = request.user.sites_autorises()

    if request.method == "POST":
        site_id = request.POST.get("ecole")
        date_str = request.POST.get("date")
        observations = request.POST.get("observations", "")
        if not sites.filter(pk=site_id).exists():
            messages.error(request, "Site non autorisé.")
        else:
            try:
                date = date_cls.fromisoformat(date_str)
            except (ValueError, TypeError):
                date = timezone.localdate()
            if ClotureCaisse.objects.filter(ecole_id=site_id, date=date).exists():
                messages.error(request, "Une clôture existe déjà pour ce site et cette date.")
            else:
                ventes_jour = (
                    Vente.objects
                    .filter(ecole_id=site_id, horodatage__date=date)
                    .exclude(statut=StatutVente.ANNULEE)
                )
                agg = ventes_jour.values("mode_paiement").annotate(t=Sum("montant_total"))
                totaux = {r["mode_paiement"]: r["t"] or 0 for r in agg}
                ClotureCaisse.objects.create(
                    ecole_id=site_id,
                    date=date,
                    montant_especes=totaux.get(ModePaiement.ESPECES, 0),
                    montant_mobile=totaux.get(ModePaiement.MOBILE_MONEY, 0),
                    montant_autre=totaux.get(ModePaiement.AUTRE, 0),
                    nb_ventes=ventes_jour.count(),
                    observations=observations,
                    cloture_par=request.user,
                )
                messages.success(request, f"Caisse clôturée pour le {date}.")
                return redirect("clotures_liste")

    sites_list = list(sites)
    site_unique = sites_list[0] if len(sites_list) == 1 else None
    return render(request, "ventes/cloturer_caisse.html", {"sites": sites_list, "site_unique": site_unique})


# ─── Hub Finances ─────────────────────────────────────────────────────────────


@login_required
def hub_finances(request):
    from depenses.models import Depense, StatutDepense

    u = request.user
    ecoles = _ecoles_perimetre(u)
    sites = u.sites_autorises()
    aujourd_hui = timezone.localdate()

    entrees_total = (
        Vente.objects.filter(ecole__in=ecoles)
        .exclude(statut=StatutVente.ANNULEE)
        .aggregate(t=Sum("montant_total"))["t"] or 0
    )
    from depenses.models import StatutVersement, Versement
    from django.db.models import Q as _Q
    from transferts.models import TransfertLigne, StatutTransfert, TypeTransfert
    _dep_q = _Q(site__in=sites)
    depenses_total = (
        Depense.objects.filter(_dep_q, statut=StatutDepense.CONFIRME)
        .aggregate(t=Sum("montant_confirme"))["t"] or 0
    )
    dons_total = (
        TransfertLigne.objects.filter(
            transfert__site_origine__in=sites,
            transfert__statut=StatutTransfert.ACCEPTE,
            transfert__type_transfert=TypeTransfert.DON,
        ).aggregate(t=Sum(ExpressionWrapper(
            F("quantite") * F("produit__cout_achat"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )))["t"] or 0
    )
    sorties_total = depenses_total + dons_total
    nb_depenses = Depense.objects.filter(_dep_q, statut=StatutDepense.SOUMIS).count()
    nb_depenses_confirmer = Depense.objects.filter(_dep_q, statut=StatutDepense.VALIDE, cree_par=u).count()
    nb_versements_attente = Versement.objects.filter(destinataire=u, statut=StatutVersement.EN_ATTENTE).count()
    par_ecole = (
        Vente.objects
        .filter(ecole__in=ecoles, horodatage__date=aujourd_hui)
        .exclude(statut=StatutVente.ANNULEE)
        .values("ecole__nom")
        .annotate(ca=Sum("montant_total"), n=Count("id"))
        .order_by("-ca")
    )
    return render(request, "finances/hub.html", {
        "entrees_total": entrees_total,
        "sorties_total": sorties_total,
        "nb_depenses": nb_depenses,
        "nb_depenses_confirmer": nb_depenses_confirmer,
        "nb_versements_attente": nb_versements_attente,
        "par_ecole": par_ecole,
        "perimetre": _perimetre_label(u),
    })


@login_required
def versements_liste(request):
    from depenses.models import Depense, StatutDepense, StatutVersement, Versement
    u = request.user
    if u.profil not in (Profil.CHEF_EQUIPE, Profil.DG) and not u.is_superuser:
        return redirect("hub_finances")

    # Filtres pour les versements effectués
    statut_f = request.GET.get("statut", "")
    debut_f  = request.GET.get("debut", "")
    fin_f    = request.GET.get("fin", "")
    vers_f   = request.GET.get("vers", "")

    # Filtres pour les versements reçus
    rstatut_f = request.GET.get("rstatut", "")
    rdebut_f  = request.GET.get("rdebut", "")
    rfin_f    = request.GET.get("rfin", "")

    # DG partage une caisse commune — on agrège sur tous les DG
    est_dg_manager = u.profil == Profil.DG or u.is_superuser
    if est_dg_manager:
        dg_managers = Utilisateur.objects.filter(profil=Profil.DG, is_active=True)
        verseur_q      = Q(verseur__in=dg_managers)
        destinataire_q = Q(destinataire__in=dg_managers)
    else:
        verseur_q      = Q(verseur=u)
        destinataire_q = Q(destinataire=u)

    # Ce que la caisse a versé et reçu
    envoyes = Versement.objects.filter(verseur_q).select_related("verseur", "destinataire").order_by("-cree_le")
    if statut_f:
        envoyes = envoyes.filter(statut=statut_f)
    if debut_f:
        envoyes = envoyes.filter(date__gte=debut_f)
    if fin_f:
        envoyes = envoyes.filter(date__lte=fin_f)
    if vers_f == "__banque__":
        envoyes = envoyes.filter(destinataire__isnull=True)
    elif vers_f:
        envoyes = envoyes.filter(destinataire_id=vers_f)

    dest_envoyes = (
        Utilisateur.objects.filter(versements_recus__in=Versement.objects.filter(verseur_q))
        .distinct().order_by("last_name", "first_name")
    )
    recus_base = Versement.objects.filter(destinataire_q).select_related("verseur", "destinataire").order_by("-cree_le")
    recus = recus_base
    if rstatut_f:
        recus = recus.filter(statut=rstatut_f)
    if rdebut_f:
        recus = recus.filter(date__gte=rdebut_f)
    if rfin_f:
        recus = recus.filter(date__lte=rfin_f)

    # Soldes — les versements EN_ATTENTE comptent comme déjà partis (revenus si rejetés)
    statuts_engages = [StatutVersement.CONFIRME, StatutVersement.EN_ATTENTE]
    envoyes_base     = Versement.objects.filter(verseur_q)
    envoye_engage    = envoyes_base.filter(statut__in=statuts_engages).aggregate(t=Sum("montant"))["t"] or 0
    envoye_confirme  = envoyes_base.filter(statut=StatutVersement.CONFIRME).aggregate(t=Sum("montant"))["t"] or 0
    verse_banque     = envoyes_base.filter(statut=StatutVersement.CONFIRME, destinataire__isnull=True).aggregate(t=Sum("montant"))["t"] or 0
    recu_confirme    = recus_base.filter(statut=StatutVersement.CONFIRME).aggregate(t=Sum("montant"))["t"] or 0
    en_attente_recus = recus_base.filter(statut=StatutVersement.EN_ATTENTE).count()

    # Pour le chef d'équipe : total ventes encaissées (non annulées)
    collecte_total = 0
    collecte_dg    = 0
    depenses_total = 0
    if u.profil == Profil.CHEF_EQUIPE:
        ecoles = u.sites_autorises()
        collecte_total = (
            Vente.objects.filter(ecole__in=ecoles)
            .exclude(statut=StatutVente.ANNULEE)
            .aggregate(t=Sum("montant_total"))["t"] or 0
        )
        depenses_total = (
            Depense.objects.filter(site__in=ecoles, statut=StatutDepense.CONFIRME)
            .aggregate(t=Sum("montant_confirme"))["t"] or 0
        )
    elif est_dg_manager:
        # Le DG vend directement : ses propres ventes alimentent sa caisse
        collecte_dg = (
            Vente.objects.filter(vendeuse__in=dg_managers)
            .exclude(statut=StatutVente.ANNULEE)
            .aggregate(t=Sum("montant_total"))["t"] or 0
        )
        depenses_total = (
            Depense.objects.filter(cree_par__in=dg_managers, statut=StatutDepense.CONFIRME)
            .aggregate(t=Sum("montant_confirme"))["t"] or 0
        )

    # Solde en main = collecté (ou reçu) − tout ce qui est parti − dépenses confirmées
    if u.profil == Profil.CHEF_EQUIPE:
        solde_en_main = collecte_total - envoye_engage - depenses_total
    elif est_dg_manager:
        solde_en_main = recu_confirme + collecte_dg - envoye_engage - depenses_total
    else:
        solde_en_main = recu_confirme - envoye_engage - depenses_total

    return render(request, "finances/versements.html", {
        "envoyes": envoyes[:100],
        "recus": recus[:50],
        "envoye_confirme": envoye_confirme,
        "recu_confirme": recu_confirme,
        "en_attente_recus": en_attente_recus,
        "collecte_total": collecte_total,
        "collecte_dg":    collecte_dg,
        "depenses_total": depenses_total,
        "verse_banque": verse_banque,
        "solde_en_main": solde_en_main,
        "est_chef": u.profil == Profil.CHEF_EQUIPE,
        "est_superviseur": False,
        "est_dg": u.profil == Profil.DG or u.is_superuser,
        "dest_envoyes": dest_envoyes,
        "filtres":  {"statut": statut_f,  "debut": debut_f,  "fin": fin_f, "vers": vers_f},
        "filtres_r": {"statut": rstatut_f, "debut": rdebut_f, "fin": rfin_f},
    })


@login_required
def versement_nouveau(request):
    from depenses.models import Depense, ModeVersement, StatutDepense, StatutVersement, Versement
    u = request.user
    profils_autorises = (Profil.CHEF_EQUIPE, Profil.DG)
    if u.profil not in profils_autorises and not u.is_superuser:
        return redirect("versements_liste")

    # Calcul du solde disponible — EN_ATTENTE compte comme déjà parti
    statuts_engages = [StatutVersement.CONFIRME, StatutVersement.EN_ATTENTE]
    est_dg_manager = u.profil == Profil.DG or u.is_superuser

    if u.profil == Profil.CHEF_EQUIPE:
        verse_engage = (
            Versement.objects.filter(verseur=u, statut__in=statuts_engages)
            .aggregate(t=Sum("montant"))["t"] or 0
        )
        ecoles = u.sites_autorises()
        collecte = (
            Vente.objects.filter(ecole__in=ecoles)
            .exclude(statut=StatutVente.ANNULEE)
            .aggregate(t=Sum("montant_total"))["t"] or 0
        )
        depenses = (
            Depense.objects.filter(site__in=ecoles, statut=StatutDepense.CONFIRME)
            .aggregate(t=Sum("montant_confirme"))["t"] or 0
        )
        solde_disponible = collecte - verse_engage - depenses
    else:
        # DG : caisse commune agrégée sur tous les DG
        dg_managers = Utilisateur.objects.filter(profil=Profil.DG, is_active=True)
        verse_engage = (
            Versement.objects.filter(verseur__in=dg_managers, statut__in=statuts_engages)
            .aggregate(t=Sum("montant"))["t"] or 0
        )
        recu_confirme = (
            Versement.objects.filter(destinataire__in=dg_managers, statut=StatutVersement.CONFIRME)
            .aggregate(t=Sum("montant"))["t"] or 0
        )
        depenses = (
            Depense.objects.filter(cree_par__in=dg_managers, statut=StatutDepense.CONFIRME)
            .aggregate(t=Sum("montant_confirme"))["t"] or 0
        )
        solde_disponible = recu_confirme - verse_engage - depenses

    # Destinataires selon le profil
    # CHEF_EQUIPE → DG ; DG → banque uniquement (sortie sans destinataire humain)
    vers_banque_seulement = u.profil == Profil.DG or u.is_superuser
    if u.profil == Profil.CHEF_EQUIPE:
        destinataires = list(
            Utilisateur.objects.filter(profil=Profil.DG, is_active=True)
            .order_by("last_name", "first_name")
        )
    else:
        destinataires = []

    if request.method == "POST":
        try:
            montant_str = request.POST.get("montant", "").replace(" ", "").replace("\xa0", "")
            montant = Decimal(montant_str)
            if montant <= 0:
                raise ValueError("Le montant doit être positif.")
            if montant > solde_disponible:
                raise ValueError(f"Montant supérieur au solde disponible ({solde_disponible:,.0f} F CFA).")
            date = timezone.localdate()
            mode = request.POST.get("mode", ModeVersement.ESPECES)
            reference = request.POST.get("reference", "").strip()
            note = request.POST.get("note", "").strip()
            vers_banque = request.POST.get("vers_banque") == "1" or vers_banque_seulement

            if vers_banque:
                # Sortie directe (dépôt banque) — auto-confirmée, pas de destinataire humain
                recu_banque = request.FILES.get("recu_banque") or None
                v = Versement.objects.create(
                    verseur=u,
                    destinataire=None,
                    montant=montant,
                    date=date,
                    mode=ModeVersement.VIREMENT_BANQUE if mode == ModeVersement.VIREMENT_BANQUE else mode,
                    reference=reference,
                    note=note,
                    statut=StatutVersement.CONFIRME,
                    recu_banque=recu_banque,
                )
                messages.success(request, f"Sortie de {montant:,.0f} F CFA enregistrée et déduite de votre solde.")
            else:
                destinataire_id = int(request.POST.get("destinataire", 0))
                dest = get_object_or_404(Utilisateur, pk=destinataire_id)
                if dest not in destinataires:
                    raise ValueError("Ce destinataire n'est pas autorisé pour votre zone.")
                v = Versement.objects.create(
                    verseur=u,
                    destinataire=dest,
                    montant=montant,
                    date=date,
                    mode=mode,
                    reference=reference,
                    note=note,
                )
                creer_notification(
                    dest,
                    type=TypeNotification.VERSEMENT_RECU,
                    titre=f"Versement de {montant:,.0f} F CFA — {u.get_full_name()}",
                    message=f"{u.get_full_name()} déclare vous avoir versé {montant:,.0f} F CFA ({v.get_mode_display()}).",
                    lien=f"/finances/versements/{v.pk}/traiter/",
                )
                messages.success(request, "Versement déclaré. Le destinataire a été notifié.")
            return redirect("versements_liste")
        except Exception as e:
            messages.error(request, f"Erreur : {e}")

    return render(request, "finances/versement_form.html", {
        "destinataires": destinataires,
        "modes": ModeVersement.choices,
        "today": timezone.localdate().isoformat(),
        "solde_disponible": solde_disponible,
        "vers_banque_seulement": vers_banque_seulement,
        "peut_vers_banque": u.profil == Profil.DG or u.is_superuser,
    })


@login_required
@login_required
def versement_detail(request, pk):
    from depenses.models import Versement
    u = request.user
    v = get_object_or_404(
        Versement.objects.select_related("verseur", "destinataire"),
        pk=pk,
    )
    if v.verseur_id != u.pk and (v.destinataire_id is None or v.destinataire_id != u.pk):
        if u.profil != Profil.DG and not u.is_superuser:
            messages.error(request, "Accès refusé.")
            return redirect("versements_liste")
    return render(request, "finances/versement_detail.html", {"v": v})


@login_required
def versement_traiter(request, pk):
    from depenses.models import StatutVersement, Versement
    u = request.user
    v = get_object_or_404(Versement, pk=pk, destinataire=u)

    if v.statut != StatutVersement.EN_ATTENTE:
        messages.error(request, "Ce versement a déjà été traité.")
        return redirect("versements_liste")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "confirmer":
            v.statut = StatutVersement.CONFIRME
            v.traite_le = timezone.now()
            v.save(update_fields=["statut", "traite_le"])
            creer_notification(
                v.verseur,
                type=TypeNotification.VERSEMENT_CONFIRME,
                titre=f"Versement confirmé par {u.get_full_name()}",
                message=f"Votre versement de {v.montant:,.0f} F CFA a été confirmé.",
                lien="/finances/versements/",
            )
            messages.success(request, "Versement confirmé.")
        elif action == "rejeter":
            motif = request.POST.get("motif_rejet", "").strip()
            v.statut = StatutVersement.REJETE
            v.traite_le = timezone.now()
            v.motif_rejet = motif
            v.save(update_fields=["statut", "traite_le", "motif_rejet"])
            creer_notification(
                v.verseur,
                type=TypeNotification.VERSEMENT_REJETE,
                titre=f"Versement rejeté par {u.get_full_name()}",
                message=f"Votre versement de {v.montant:,.0f} F CFA a été rejeté.{' Motif : ' + motif if motif else ''}",
                lien="/finances/versements/",
            )
            messages.error(request, "Versement rejeté.")
        return redirect("versements_liste")

    return render(request, "finances/versement_traiter.html", {"v": v})


@login_required
def versements_global(request):
    from depenses.models import StatutVersement, Versement

    u = request.user
    if u.profil != Profil.DG and not u.is_superuser:
        return redirect("versements_liste")

    statut_f = request.GET.get("statut", "")
    debut_f  = request.GET.get("debut", "")
    fin_f    = request.GET.get("fin", "")
    de_f     = request.GET.get("de", "")
    vers_f   = request.GET.get("vers", "")

    qs = Versement.objects.select_related("verseur", "destinataire").order_by("-cree_le")
    if statut_f:
        qs = qs.filter(statut=statut_f)
    if debut_f:
        qs = qs.filter(date__gte=debut_f)
    if fin_f:
        qs = qs.filter(date__lte=fin_f)
    if de_f:
        qs = qs.filter(verseur_id=de_f)
    if vers_f == "__banque__":
        qs = qs.filter(destinataire__isnull=True)
    elif vers_f:
        qs = qs.filter(destinataire_id=vers_f)

    total_envoye   = Versement.objects.filter(statut=StatutVersement.CONFIRME).aggregate(t=Sum("montant"))["t"] or 0
    total_attente  = Versement.objects.filter(statut=StatutVersement.EN_ATTENTE).aggregate(t=Sum("montant"))["t"] or 0
    total_banque   = Versement.objects.filter(statut=StatutVersement.CONFIRME, destinataire__isnull=True).aggregate(t=Sum("montant"))["t"] or 0
    en_attente_nb  = Versement.objects.filter(statut=StatutVersement.EN_ATTENTE).count()

    verseurs = (
        Utilisateur.objects.filter(versements_effectues__isnull=False)
        .distinct().order_by("last_name", "first_name")
    )
    destinataires = (
        Utilisateur.objects.filter(versements_recus__isnull=False)
        .distinct().order_by("last_name", "first_name")
    )

    return render(request, "finances/versements_global.html", {
        "versements": qs[:200],
        "total_confirme": total_envoye,
        "total_attente": total_attente,
        "total_banque": total_banque,
        "en_attente_nb": en_attente_nb,
        "verseurs": verseurs,
        "destinataires": destinataires,
        "filtres": {"statut": statut_f, "debut": debut_f, "fin": fin_f, "de": de_f, "vers": vers_f},
    })


@login_required
def versements_export(request):
    import io
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse
    from depenses.models import StatutVersement, Versement

    u = request.user
    section = request.GET.get("section", "envoyes")
    statut_f = request.GET.get("statut", "")
    debut_f  = request.GET.get("debut", "")
    fin_f    = request.GET.get("fin", "")

    est_dg_manager = u.profil == Profil.DG or u.is_superuser
    if est_dg_manager:
        dg_managers = Utilisateur.objects.filter(profil=Profil.DG, is_active=True)

    if section == "global":
        qs = Versement.objects.select_related("verseur", "destinataire").order_by("-cree_le")
    elif section == "recus":
        if est_dg_manager:
            qs = Versement.objects.filter(destinataire__in=dg_managers).select_related("verseur", "destinataire").order_by("-cree_le")
        else:
            qs = Versement.objects.filter(destinataire=u).select_related("verseur", "destinataire").order_by("-cree_le")
        statut_f = request.GET.get("rstatut", statut_f)
        debut_f  = request.GET.get("rdebut", debut_f)
        fin_f    = request.GET.get("rfin", fin_f)
    else:
        if est_dg_manager:
            qs = Versement.objects.filter(verseur__in=dg_managers).select_related("verseur", "destinataire").order_by("-cree_le")
        else:
            qs = Versement.objects.filter(verseur=u).select_related("verseur", "destinataire").order_by("-cree_le")

    if statut_f:
        qs = qs.filter(statut=statut_f)
    if debut_f:
        qs = qs.filter(date__gte=debut_f)
    if fin_f:
        qs = qs.filter(date__lte=fin_f)

    if section == "global":
        titre_feuille = "Tous les versements"
        fname = "versements_global.xlsx"
        entetes = ["Date", "De", "Vers", "Montant (F CFA)", "Mode", "Référence", "Note", "Statut"]
    elif section == "recus":
        titre_feuille = "Versements reçus"
        fname = "versements_recus.xlsx"
        entetes = ["Date", "De", "Montant (F CFA)", "Mode", "Référence", "Note", "Statut"]
    else:
        titre_feuille = "Versements effectués"
        fname = "versements_effectues.xlsx"
        entetes = ["Date", "À", "Montant (F CFA)", "Mode", "Référence", "Note", "Statut"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = titre_feuille

    for col, titre in enumerate(entetes, 1):
        c = ws.cell(row=1, column=col, value=titre)
        c.font = Font(bold=True, color="FFFFFF", size=11)
        c.fill = PatternFill("solid", fgColor="16233F")
        c.alignment = Alignment(horizontal="center", vertical="center")

    for row, v in enumerate(qs, 2):
        if section == "global":
            ws.cell(row=row, column=1, value=v.date.strftime("%d/%m/%Y"))
            ws.cell(row=row, column=2, value=v.verseur.get_full_name())
            ws.cell(row=row, column=3, value=v.destinataire.get_full_name() if v.destinataire else "Banque")
            ws.cell(row=row, column=4, value=float(v.montant))
            ws.cell(row=row, column=5, value=v.get_mode_display())
            ws.cell(row=row, column=6, value=v.reference or "")
            ws.cell(row=row, column=7, value=v.note or "")
            ws.cell(row=row, column=8, value=v.get_statut_display())
        else:
            tiers = v.verseur.get_full_name() if section == "recus" else (v.destinataire.get_full_name() if v.destinataire else "Banque")
            ws.cell(row=row, column=1, value=v.date.strftime("%d/%m/%Y"))
            ws.cell(row=row, column=2, value=tiers)
            ws.cell(row=row, column=3, value=float(v.montant))
            ws.cell(row=row, column=4, value=v.get_mode_display())
            ws.cell(row=row, column=5, value=v.reference or "")
            ws.cell(row=row, column=6, value=v.note or "")
            ws.cell(row=row, column=7, value=v.get_statut_display())

    for col in ws.columns:
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(
            max(len(str(c.value or "")) for c in col) + 4, 50
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(buf, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{fname}"'
    return response


@login_required
def rapport_financier(request):
    from datetime import date as date_type
    from depenses.models import Depense, StatutDepense, StatutVersement, Versement

    u     = request.user
    today = timezone.localdate()

    debut_str = request.GET.get("debut", "")
    fin_str   = request.GET.get("fin", "")

    try:
        debut = date_type.fromisoformat(debut_str) if debut_str else today
    except ValueError:
        debut = today
    try:
        fin = date_type.fromisoformat(fin_str) if fin_str else today
    except ValueError:
        fin = today
    if fin < debut:
        fin = debut

    # ── Périmètre ────────────────────────────────────────────────
    ecoles = u.sites_autorises()

    sups_qs = Utilisateur.objects.none()

    dgs_qs = (
        Utilisateur.objects.filter(profil=Profil.DG, is_active=True, site__isnull=True).order_by("last_name", "first_name")
        if u.acces_national else Utilisateur.objects.none()
    )

    # ── Synthèse par palier (colonnes pertinentes seulement) ─────
    # Colonnes période (date-filtrées) + En main (all-time)
    def agg(qs, champ="montant"):
        return qs.aggregate(t=Sum(champ))["t"] or 0

    enc_p  = agg(Vente.objects.filter(ecole__in=ecoles, horodatage__date__gte=debut, horodatage__date__lte=fin).exclude(statut=StatutVente.ANNULEE), "montant_total")
    vd_e_p = agg(Versement.objects.filter(verseur__site__in=ecoles, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin))
    enc_t  = agg(Vente.objects.filter(ecole__in=ecoles).exclude(statut=StatutVente.ANNULEE), "montant_total")
    vd_e_t = agg(Versement.objects.filter(verseur__site__in=ecoles, statut=StatutVersement.CONFIRME))
    dep_t  = agg(Depense.objects.filter(site__in=ecoles, statut=StatutDepense.CONFIRME), "montant_confirme")
    synt_ecoles = {"encaisse": enc_p, "verse": vd_e_p, "en_main": enc_t - vd_e_t - dep_t}

    vr_s_p = agg(Versement.objects.filter(destinataire__in=sups_qs, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin))
    vd_s_p = agg(Versement.objects.filter(verseur__in=sups_qs, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin))
    vr_s_t = agg(Versement.objects.filter(destinataire__in=sups_qs, statut=StatutVersement.CONFIRME))
    vd_s_t = agg(Versement.objects.filter(verseur__in=sups_qs, statut=StatutVersement.CONFIRME))
    synt_sups = {"recu": vr_s_p, "verse": vd_s_p, "en_main": vr_s_t - vd_s_t}

    vr_d_p = agg(Versement.objects.filter(destinataire__in=dgs_qs, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin))
    vr_d_t = agg(Versement.objects.filter(destinataire__in=dgs_qs, statut=StatutVersement.CONFIRME))
    synt_dg = {"recu": vr_d_p, "en_main": vr_d_t}

    # ── Détail par acteur (uniquement ceux avec activité sur la période) ──
    detail_ecoles = []
    for ecole in ecoles.order_by("nom"):
        enc = agg(Vente.objects.filter(ecole=ecole, horodatage__date__gte=debut, horodatage__date__lte=fin).exclude(statut=StatutVente.ANNULEE), "montant_total")
        vd  = agg(Versement.objects.filter(verseur__site=ecole, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin))
        if not enc and not vd:
            continue
        enc_t2 = agg(Vente.objects.filter(ecole=ecole).exclude(statut=StatutVente.ANNULEE), "montant_total")
        vd_t2  = agg(Versement.objects.filter(verseur__site=ecole, statut=StatutVersement.CONFIRME))
        dep_t2 = agg(Depense.objects.filter(site=ecole, statut=StatutDepense.CONFIRME), "montant_confirme")
        detail_ecoles.append({"nom": ecole.nom, "commune": "", "encaisse": enc, "verse": vd, "en_main": enc_t2 - vd_t2 - dep_t2})

    detail_sups = []
    for sup in sups_qs:
        vr = agg(Versement.objects.filter(destinataire=sup, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin))
        vd = agg(Versement.objects.filter(verseur=sup, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin))
        if not vr and not vd:
            continue
        vr_t2 = agg(Versement.objects.filter(destinataire=sup, statut=StatutVersement.CONFIRME))
        vd_t2 = agg(Versement.objects.filter(verseur=sup, statut=StatutVersement.CONFIRME))
        detail_sups.append({"nom": sup.get_full_name() or sup.username, "commune": "", "recu": vr, "verse": vd, "en_main": vr_t2 - vd_t2})

    detail_dg = []
    for dg in dgs_qs:
        vr = agg(Versement.objects.filter(destinataire=dg, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin))
        if not vr:
            continue
        vr_t2 = agg(Versement.objects.filter(destinataire=dg, statut=StatutVersement.CONFIRME))
        detail_dg.append({"nom": dg.get_full_name() or dg.username, "recu": vr, "en_main": vr_t2})

    return render(request, "finances/rapport_financier.html", {
        "synt_ecoles":   synt_ecoles,
        "synt_sups":     synt_sups,
        "synt_dg":       synt_dg,
        "detail_ecoles": detail_ecoles,
        "detail_sups":   detail_sups,
        "detail_dg":     detail_dg,
        "a_sups":        sups_qs.exists(),
        "a_dg":          dgs_qs.exists(),
        "debut":         debut,
        "fin":           fin,
        "filtres":       {"debut": str(debut), "fin": str(fin)},
    })


@login_required
def rapport_financier_export(request):
    import io
    import openpyxl
    from datetime import date as date_type
    from django.http import HttpResponse
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from depenses.models import Depense, StatutDepense, StatutVersement, Versement

    u     = request.user
    today = timezone.localdate()

    debut_str  = request.GET.get("debut", "")
    fin_str    = request.GET.get("fin", "")
    site_id    = request.GET.get("site", "")

    try:
        debut = date_type.fromisoformat(debut_str) if debut_str else today
    except ValueError:
        debut = today
    try:
        fin = date_type.fromisoformat(fin_str) if fin_str else today
    except ValueError:
        fin = today

    sites_qs = u.sites_autorises()
    if site_id:
        sites_qs = sites_qs.filter(pk=site_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rapport financier"

    entetes = ["Site", "Type", "Commune", "Initial (F CFA)", "Ventes", "Versements déclarés", "Versements reçus", "Autres sorties", "Final (F CFA)"]
    for col, titre in enumerate(entetes, 1):
        c = ws.cell(row=1, column=col, value=titre)
        c.font = Font(bold=True, color="FFFFFF", size=11)
        c.fill = PatternFill("solid", fgColor="16233F")
        c.alignment = Alignment(horizontal="center", vertical="center")

    for row, site in enumerate(sites_qs.order_by("type", "nom"), 2):
        ventes_avant      = (Vente.objects.filter(ecole=site, horodatage__date__lt=debut).exclude(statut=StatutVente.ANNULEE).aggregate(t=Sum("montant_total"))["t"] or 0)
        vers_declares_av  = (Versement.objects.filter(verseur__site=site, statut=StatutVersement.CONFIRME, date__lt=debut).aggregate(t=Sum("montant"))["t"] or 0)
        vers_recus_av     = (Versement.objects.filter(destinataire__site=site, statut=StatutVersement.CONFIRME, date__lt=debut).aggregate(t=Sum("montant"))["t"] or 0)
        dep_avant         = (Depense.objects.filter(site=site, statut=StatutDepense.CONFIRME, date_depense__lt=debut).aggregate(t=Sum("montant_confirme"))["t"] or 0)
        vers_declares     = (Versement.objects.filter(verseur__site=site, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin).aggregate(t=Sum("montant"))["t"] or 0)
        vers_recus        = (Versement.objects.filter(destinataire__site=site, statut=StatutVersement.CONFIRME, date__gte=debut, date__lte=fin).aggregate(t=Sum("montant"))["t"] or 0)
        autres_sorties    = (Depense.objects.filter(site=site, statut=StatutDepense.CONFIRME, date_depense__gte=debut, date_depense__lte=fin).aggregate(t=Sum("montant_confirme"))["t"] or 0)

        ventes_periode = (Vente.objects.filter(ecole=site, horodatage__date__gte=debut, horodatage__date__lte=fin).exclude(statut=StatutVente.ANNULEE).aggregate(t=Sum("montant_total"))["t"] or 0)
        initial = ventes_avant + vers_recus_av - vers_declares_av - dep_avant
        final   = initial + ventes_periode + vers_recus - vers_declares - autres_sorties

        ws.cell(row=row, column=1, value=site.nom)
        ws.cell(row=row, column=2, value=site.get_type_display())
        ws.cell(row=row, column=3, value="")
        ws.cell(row=row, column=4, value=float(initial))
        ws.cell(row=row, column=5, value=float(ventes_periode))
        ws.cell(row=row, column=6, value=float(vers_declares))
        ws.cell(row=row, column=7, value=float(vers_recus))
        ws.cell(row=row, column=8, value=float(autres_sorties))
        ws.cell(row=row, column=9, value=float(final))

    for col in ws.columns:
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(
            max(len(str(c.value or "")) for c in col) + 4, 50
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(buf, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="rapport_financier.xlsx"'
    return response


@login_required

@login_required
def tresorerie_globale(request):
    from datetime import date as date_type
    from django.db.models import Q
    from django.db.models.functions import Coalesce
    from depenses.models import Depense, StatutDepense
    from stock.models import MouvementStock, SoldeStock, TypeMouvement
    from transferts.models import TransfertLigne, StatutTransfert
    from achats.models import ReceptionLigne, StatutReception
    from .models import LigneProduitVente

    u     = request.user
    today = timezone.localdate()

    debut_str    = request.GET.get("debut", "")
    fin_str      = request.GET.get("fin", "")
    site_id_f    = request.GET.get("site", "")
    produit_id_f = request.GET.get("produit", "")

    try:
        debut = date_type.fromisoformat(debut_str) if debut_str else None
    except ValueError:
        debut = None
        debut_str = ""
    try:
        fin = date_type.fromisoformat(fin_str) if fin_str else None
    except ValueError:
        fin = None
        fin_str = ""
    if debut and fin and fin < debut:
        fin = debut

    tous_sites = u.sites_autorises()
    sites_dispo = tous_sites.order_by("nom")
    if site_id_f:
        tous_sites = tous_sites.filter(pk=site_id_f)
    ecoles = tous_sites

    produits_filtre = Produit.objects.filter(actif=True).order_by("code")
    pq = {}  # filtre produit appliqué à chaque queryset si renseigné
    if produit_id_f.isdigit():
        pq = {"produit_id": int(produit_id_f)}
    else:
        produit_id_f = ""

    def _dkw(gte_key, lte_key):
        """Construit les kwargs de filtre date uniquement si les dates sont renseignées."""
        d = {}
        if debut: d[gte_key] = debut
        if fin:   d[lte_key] = fin
        return d

    # ── 1. Valeur des achats (réceptions validées sur la période) ─────────────
    achats_map = {
        r["site_effectif_id"]: r["total"] or 0
        for r in ReceptionLigne.objects.filter(
            Q(reception__site_destination__in=ecoles) | Q(reception__commande__site_destination__in=ecoles),
            reception__statut__in=[StatutReception.VALIDE, StatutReception.CLOTURE],
            **_dkw("reception__valide_le__date__gte", "reception__valide_le__date__lte"),
            **pq,
        )
        .annotate(site_effectif_id=Coalesce(
            F("reception__site_destination_id"),
            F("reception__commande__site_destination_id"),
        ))
        .values("site_effectif_id")
        .annotate(total=Sum(ExpressionWrapper(
            F("quantite_recue") * F("prix_unitaire"),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )))
    }

    # ── 2. Recettes ───────────────────────────────────────────────────────────
    # Avec filtre produit : on calcule en Python pour distribuer la remise proportionnellement.
    # Sans filtre : montant_total de la vente (déjà net de remise).
    from .models import LigneVente
    from decimal import Decimal as _Dec
    if pq:
        prod_id = pq["produit_id"]
        lignes_prod = (
            LigneVente.objects
            .filter(
                vente__ecole__in=ecoles,
                produit_id=prod_id,
                **_dkw("vente__horodatage__date__gte", "vente__horodatage__date__lte"),
            )
            .exclude(vente__statut=StatutVente.ANNULEE)
            .select_related("vente")
        )
        vente_ids_prod = list(lignes_prod.values_list("vente_id", flat=True).distinct())
        gross_par_vente_prod = {
            r["vente_id"]: r["total"] or _Dec(0)
            for r in LigneVente.objects.filter(vente_id__in=vente_ids_prod)
            .values("vente_id")
            .annotate(total=Sum(ExpressionWrapper(
                F("quantite") * F("prix_unitaire"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )))
        }
        recettes_map = {}
        for _l in lignes_prod:
            _brut  = _l.quantite * _l.prix_unitaire
            _gross = gross_par_vente_prod.get(_l.vente_id, _brut)
            _eff   = _brut * _l.vente.montant_total / _gross if _gross else _brut
            recettes_map[_l.vente.ecole_id] = recettes_map.get(_l.vente.ecole_id, _Dec(0)) + _eff
    else:
        recettes_map = {
            r["ecole_id"]: r["total"] or 0
            for r in Vente.objects.filter(
                ecole__in=ecoles,
                **_dkw("horodatage__date__gte", "horodatage__date__lte"),
            ).exclude(statut=StatutVente.ANNULEE)
            .values("ecole_id").annotate(total=Sum("montant_total"))
        }

    # ── 3. Coût des marchandises vendues ──────────────────────────────────────
    cogs_map = {
        r["vente__ecole_id"]: r["total"] or 0
        for r in LigneProduitVente.objects.filter(
            vente__ecole__in=ecoles,
            **_dkw("vente__horodatage__date__gte", "vente__horodatage__date__lte"),
            **pq,
        ).exclude(vente__statut=StatutVente.ANNULEE)
        .values("vente__ecole_id")
        .annotate(total=Sum(ExpressionWrapper(
            F("quantite_servie") * F("produit__cout_achat"),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )))
    }

    # ── 4. Ajustements (MouvementStock type AJUSTEMENT, toutes sources : manuelle + inventaire)
    _adj_expr = ExpressionWrapper(
        F("quantite") * F("produit__cout_achat"),
        output_field=DecimalField(max_digits=14, decimal_places=2)
    )
    adj_base = MouvementStock.objects.filter(
        site__in=ecoles,
        type=TypeMouvement.AJUSTEMENT,
        **_dkw("horodatage__date__gte", "horodatage__date__lte"),
        **pq,
    )
    adj_pos_map = {
        r["site_id"]: r["total"] or 0
        for r in adj_base.filter(quantite__gt=0)
        .values("site_id")
        .annotate(total=Sum(_adj_expr))
    }
    adj_neg_map = {
        r["site_id"]: abs(r["total"] or 0)
        for r in adj_base.filter(quantite__lt=0)
        .values("site_id")
        .annotate(total=Sum(_adj_expr))
    }

    # ── 5. Dépenses diverses (pas de dimension produit) ───────────────────────
    dep_map = {}
    if not pq:
        dep_map = {
            r["site_id"]: r["total"] or 0
            for r in Depense.objects.filter(
                site__in=ecoles,
                statut=StatutDepense.CONFIRME,
                **_dkw("date_depense__gte", "date_depense__lte"),
            ).values("site_id").annotate(total=Sum("montant_confirme"))
        }

    # ── 6. Transferts normaux (valorisés au coût d'achat, DON/SURPLUS exclus) ──
    from transferts.models import TypeTransfert
    _trf_filtre = dict(
        transfert__statut=StatutTransfert.ACCEPTE,
        transfert__type_transfert=TypeTransfert.NORMAL,
        **_dkw("transfert__traite_le__date__gte", "transfert__traite_le__date__lte"),
    )
    _trf_expr = ExpressionWrapper(
        F("quantite") * F("produit__cout_achat"),
        output_field=DecimalField(max_digits=14, decimal_places=2)
    )
    trf_emis_map = {
        r["transfert__site_origine_id"]: r["total"] or 0
        for r in TransfertLigne.objects.filter(
            transfert__site_origine__in=ecoles, **_trf_filtre, **pq
        )
        .values("transfert__site_origine_id")
        .annotate(total=Sum(_trf_expr))
    }
    trf_recu_map = {
        r["transfert__site_destination_id"]: r["total"] or 0
        for r in TransfertLigne.objects.filter(
            transfert__site_destination__in=ecoles, **_trf_filtre, **pq
        )
        .values("transfert__site_destination_id")
        .annotate(total=Sum(_trf_expr))
    }

    # ── 6b. Transferts DON (valorisés au coût d'achat, dissociés des dépenses) ──
    don_map = {
        r["transfert__site_origine_id"]: r["total"] or 0
        for r in TransfertLigne.objects.filter(
            transfert__site_origine__in=ecoles,
            transfert__statut=StatutTransfert.ACCEPTE,
            transfert__type_transfert=TypeTransfert.DON,
            **_dkw("transfert__traite_le__date__gte", "transfert__traite_le__date__lte"),
            **pq,
        )
        .values("transfert__site_origine_id")
        .annotate(total=Sum(_trf_expr))
    }

    # ── 6c. Erreurs de saisie (SURPLUS acceptés) → déduites des achats ─────────
    # Le stock retiré n'a jamais été vraiment reçu, donc l'achat correspondant est fictif.
    surplus_map = {}
    for r in (
        TransfertLigne.objects.filter(
            transfert__site_origine__in=ecoles,
            transfert__statut=StatutTransfert.ACCEPTE,
            transfert__type_transfert=TypeTransfert.SURPLUS,
            **_dkw("transfert__traite_le__date__gte", "transfert__traite_le__date__lte"),
            **pq,
        )
        .values("transfert__site_origine_id")
        .annotate(total=Sum(_trf_expr))
    ):
        surplus_map[r["transfert__site_origine_id"]] = r["total"] or 0

    # ── 7. Stock actuel restant (snapshot temps réel, pas filtré par date) ────
    stock_map = {
        r["site_id"]: r["total"] or 0
        for r in SoldeStock.objects.filter(site__in=ecoles, **pq)
        .values("site_id")
        .annotate(total=Sum(ExpressionWrapper(
            F("quantite") * F("produit__cout_achat"),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )))
    }

    # ── Quantités globales pour les encarts ──────────────────────────────────
    def _agg(qs, field="quantite"):
        return qs.aggregate(t=Sum(field))["t"] or 0

    nb = {
        "achats":    _agg(ReceptionLigne.objects.filter(
            Q(reception__site_destination__in=ecoles) | Q(reception__commande__site_destination__in=ecoles),
            reception__statut__in=[StatutReception.VALIDE, StatutReception.CLOTURE],
            **_dkw("reception__valide_le__date__gte", "reception__valide_le__date__lte"),
            **pq,
        ), "quantite_recue"),
        "recettes":  _agg(LigneProduitVente.objects.filter(
            vente__ecole__in=ecoles,
            **_dkw("vente__horodatage__date__gte", "vente__horodatage__date__lte"),
            **pq,
        ).exclude(vente__statut=StatutVente.ANNULEE), "quantite_servie"),
        "adj_pos":   _agg(adj_base.filter(quantite__gt=0)),
        "adj_neg":   abs(_agg(adj_base.filter(quantite__lt=0))),
        "trf_emis":  _agg(TransfertLigne.objects.filter(
            transfert__site_origine__in=ecoles, **_trf_filtre, **pq
        )),
        "trf_recu":  _agg(TransfertLigne.objects.filter(
            transfert__site_destination__in=ecoles, **_trf_filtre, **pq
        )),
        "dons":      _agg(TransfertLigne.objects.filter(
            transfert__site_origine__in=ecoles,
            transfert__statut=StatutTransfert.ACCEPTE,
            transfert__type_transfert=TypeTransfert.DON,
            **_dkw("transfert__traite_le__date__gte", "transfert__traite_le__date__lte"),
            **pq,
        )),
        "depenses":  Depense.objects.filter(
            site__in=ecoles, statut=StatutDepense.CONFIRME,
            **_dkw("date_depense__gte", "date_depense__lte"),
        ).count() if not pq else 0,
        "stock":     _agg(SoldeStock.objects.filter(site__in=ecoles, quantite__gt=0, **pq)),
    }

    # ── Tableau par site ──────────────────────────────────────────────────────
    lignes = []
    for site in ecoles.order_by("nom"):
        pk  = site.pk
        rec = recettes_map.get(pk, 0)
        cog = cogs_map.get(pk, 0)
        dep = dep_map.get(pk, 0)
        don = don_map.get(pk, 0)
        ben = rec - cog - don - dep
        lignes.append({
            "nom":      site.nom,
            "achats":   achats_map.get(pk, 0) - surplus_map.get(pk, 0),
            "recettes": rec,
            "cogs":     cog,
            "adj_pos":  adj_pos_map.get(pk, 0),
            "adj_neg":  adj_neg_map.get(pk, 0),
            "trf_emis": trf_emis_map.get(pk, 0),
            "trf_recu": trf_recu_map.get(pk, 0),
            "dons":     don_map.get(pk, 0),
            "depenses": dep,
            "stock":    stock_map.get(pk, 0),
            "benefice": ben,
            "marge":    round(float(ben) / float(rec) * 100, 1) if rec else None,
        })

    # ── Totaux ────────────────────────────────────────────────────────────────
    def _s(key): return sum(l[key] for l in lignes)
    tot = {k: _s(k) for k in ("achats","recettes","cogs","adj_pos","adj_neg","trf_emis","trf_recu","dons","depenses","stock")}
    tot["benefice"] = tot["recettes"] - tot["cogs"] - tot["dons"] - tot["depenses"]
    tot["marge"]    = round(float(tot["benefice"]) / float(tot["recettes"]) * 100, 1) if tot["recettes"] else None

    return render(request, "finances/tresorerie.html", {
        "lignes": lignes,
        "tot":    tot,
        "nb":     nb,
        "sites_dispo":    sites_dispo,
        "produits_filtre": produits_filtre,
        "filtres": {"debut": str(debut) if debut else "", "fin": str(fin) if fin else "", "site": site_id_f, "produit": produit_id_f},
    })


@login_required
def finances_sorties(request):
    from depenses.models import CategorieDepense, Depense, StatutDepense

    u = request.user
    sites = u.sites_autorises()

    debut   = request.GET.get("debut", "")
    fin     = request.GET.get("fin", "")
    statut_f = request.GET.get("statut", "")

    qs = (
        Depense.objects
        .filter(site__in=sites)
        .select_related("site", "categorie", "cree_par")
        .order_by("-date_depense", "-pk")
    )
    if debut:
        try:
            qs = qs.filter(date_depense__gte=date_cls.fromisoformat(debut))
        except ValueError:
            debut = ""
    if fin:
        try:
            qs = qs.filter(date_depense__lte=date_cls.fromisoformat(fin))
        except ValueError:
            fin = ""
    if statut_f in {c[0] for c in StatutDepense.choices}:
        qs = qs.filter(statut=statut_f)

    depenses = list(qs[:100])
    total = sum(d.montant for d in depenses)
    return render(request, "finances/sorties.html", {
        "depenses": depenses,
        "total": total,
        "filtres": {"debut": debut, "fin": fin, "statut": statut_f},
        "statuts": StatutDepense.choices,
        "perimetre": _perimetre_label(u),
    })


@login_required
def finances_bilan(request):
    from depenses.models import Depense, StatutDepense

    u = request.user
    ecoles = _ecoles_perimetre(u)
    sites = u.sites_autorises()

    debut = request.GET.get("debut", "")
    fin   = request.GET.get("fin", "")

    ventes_qs = (
        Vente.objects.filter(ecole__in=ecoles)
        .exclude(statut=StatutVente.ANNULEE)
    )
    depenses_qs = Depense.objects.filter(site__in=sites, statut=StatutDepense.CONFIRME)

    if debut:
        try:
            d = date_cls.fromisoformat(debut)
            ventes_qs   = ventes_qs.filter(horodatage__date__gte=d)
            depenses_qs = depenses_qs.filter(date_depense__gte=d)
        except ValueError:
            debut = ""
    if fin:
        try:
            d = date_cls.fromisoformat(fin)
            ventes_qs   = ventes_qs.filter(horodatage__date__lte=d)
            depenses_qs = depenses_qs.filter(date_depense__lte=d)
        except ValueError:
            fin = ""

    total_entrees = ventes_qs.aggregate(t=Sum("montant_total"))["t"] or 0
    total_sorties = depenses_qs.aggregate(t=Sum("montant_confirme"))["t"] or 0

    return render(request, "finances/bilan.html", {
        "total_entrees": total_entrees,
        "total_sorties": total_sorties,
        "solde": total_entrees - total_sorties,
        "filtres": {"debut": debut, "fin": fin},
        "perimetre": _perimetre_label(u),
    })


# ─── Avoirs ───────────────────────────────────────────────────────────────────

from .models import LigneProduitVente


@login_required
def avoirs_liste(request):
    u = request.user
    if not u.peut_voir_ventes():
        return redirect("hub_stock")

    tous_sites = u.sites_autorises()

    site_id    = request.GET.get("site", "")
    commune_id = ""
    debut      = request.GET.get("debut", "")
    fin        = request.GET.get("fin", "")
    telephone  = request.GET.get("telephone", "").strip()
    produit_id = request.GET.get("produit", "")

    sites = tous_sites
    sites_dispo = sites.order_by("nom")
    if site_id.isdigit():
        sites = sites.filter(pk=site_id)

    ventes_avec_avoirs = (
        Vente.objects
        .filter(ecole__in=sites, statut=StatutVente.PARTIELLE)
        .select_related("ecole", "vendeuse")
        .prefetch_related("lignes_produit__produit")
        .order_by("horodatage")
    )
    if debut:
        try:
            ventes_avec_avoirs = ventes_avec_avoirs.filter(horodatage__date__gte=date_cls.fromisoformat(debut))
        except ValueError:
            debut = ""
    if fin:
        try:
            ventes_avec_avoirs = ventes_avec_avoirs.filter(horodatage__date__lte=date_cls.fromisoformat(fin))
        except ValueError:
            fin = ""
    if telephone:
        ventes_avec_avoirs = ventes_avec_avoirs.filter(telephone_client__icontains=telephone)
    if produit_id.isdigit():
        ventes_avec_avoirs = ventes_avec_avoirs.filter(
            lignes_produit__produit_id=produit_id,
            lignes_produit__avoir_annule=False,
        ).exclude(
            lignes_produit__quantite_servie=F("lignes_produit__quantite_due")
        ).distinct()

    # Produits qui apparaissent dans des avoirs sur ce périmètre (pour le select)
    produits_avoirs = (
        Produit.objects
        .filter(
            lignes_produit_vente__vente__ecole__in=tous_sites,
            lignes_produit_vente__vente__statut=StatutVente.PARTIELLE,
            lignes_produit_vente__avoir_annule=False,
        )
        .distinct()
        .order_by("code")
    )

    ventes_list = list(ventes_avec_avoirs)

    peut_livrer = u.profil in {Profil.CHEF_EQUIPE, Profil.DG} or u.is_superuser or u.peut_vendre()
    peut_annuler_avoir = u.is_superuser
    return render(request, "avoirs/liste.html", {
        "ventes":             ventes_list,
        "peut_livrer":        peut_livrer,
        "peut_annuler_avoir": peut_annuler_avoir,
        "communes":           [],
        "sites_dispo":        sites_dispo,
        "produits_avoirs":    produits_avoirs,
        "filtres":            {"commune": "", "site": site_id, "debut": debut, "fin": fin,
                               "telephone": telephone, "produit": produit_id},
    })


@login_required
@require_POST
def avoir_livrer(request, uuid):
    v = get_object_or_404(Vente, uuid=uuid)
    if not request.user.peut_acceder_au_site(v.ecole):
        messages.error(request, "Vente hors de votre périmètre.")
        return redirect("avoirs_liste")
    if v.statut == StatutVente.ANNULEE:
        messages.error(request, "Cette vente est annulée.")
        return redirect("avoirs_liste")
    completer_livraison(v, par=request.user)
    if v.est_complete:
        messages.success(request, f"Avoir {v.numero} soldé intégralement.")
    else:
        messages.warning(request, "Stock total insuffisant.")
    return redirect("avoir_document", uuid=uuid)


@login_required
@require_POST
def avoir_annuler_ligne(request, pk):
    ligne = get_object_or_404(LigneProduitVente, pk=pk)
    u = request.user
    if not u.is_superuser:
        messages.error(request, "Accès refusé.")
        return redirect("avoirs_liste")
    if not u.peut_acceder_au_site(ligne.vente.ecole):
        messages.error(request, "Vente hors de votre périmètre.")
        return redirect("avoirs_liste")
    try:
        annuler_avoir(ligne, par=u, motif=request.POST.get("motif", ""))
        messages.success(request, f"Avoir annulé — le client sera remboursé pour {ligne.produit.designation}.")
    except ValidationError as e:
        messages.error(request, "; ".join(e.messages))
    return redirect("avoirs_liste")


@login_required
def avoir_document(request, uuid):
    u = request.user
    v = get_object_or_404(
        Vente.objects.select_related("ecole", "vendeuse").prefetch_related(
            "lignes__kit__lignes__produit", "lignes__produit", "lignes_produit__produit"
        ),
        uuid=uuid,
    )
    if not u.peut_acceder_au_site(v.ecole):
        messages.error(request, "Accès refusé.")
        return redirect("avoirs_liste")
    stocks = {s.produit_id: s.quantite for s in SoldeStock.objects.filter(site=v.ecole)}
    for lp in v.lignes_produit.all():
        lp.stock_dispo = stocks.get(lp.produit_id, 0)
    peut_livrer = u.peut_vendre() or u.is_superuser
    peut_annuler_avoir = u.is_superuser
    return render(request, "avoirs/document_livraison.html", {
        "v": v,
        "peut_livrer": peut_livrer,
        "peut_annuler_avoir": peut_annuler_avoir,
    })


@login_required
@require_POST
def avoir_livrer_partiel(request, pk):
    from .models import LigneProduitVente
    lp = get_object_or_404(LigneProduitVente, pk=pk)
    u = request.user
    if not u.peut_acceder_au_site(lp.vente.ecole):
        messages.error(request, "Accès refusé.")
        return redirect("avoirs_liste")
    if not (u.peut_vendre() or u.is_superuser):
        messages.error(request, "Action non autorisée.")
        return redirect("avoir_document", uuid=lp.vente.uuid)
    try:
        qte = int(request.POST.get("quantite", 0))
    except (ValueError, TypeError):
        qte = 0
    if qte <= 0:
        messages.error(request, "Quantité invalide.")
        return redirect("avoir_document", uuid=lp.vente.uuid)
    stock = SoldeStock.objects.filter(site=lp.vente.ecole, produit=lp.produit).first()
    dispo = stock.quantite if stock else 0
    manquante = lp.quantite_due - lp.quantite_servie
    a_livrer = min(qte, dispo, manquante)
    if a_livrer <= 0:
        messages.warning(request, "Stock insuffisant ou quantité nulle.")
        return redirect("avoir_document", uuid=lp.vente.uuid)
    from stock.services import enregistrer_mouvement
    from stock.models import TypeMouvement
    enregistrer_mouvement(
        site=lp.vente.ecole,
        produit=lp.produit,
        type=TypeMouvement.SORTIE_VENTE,
        quantite=-a_livrer,
        auteur=u,
        reference_document=lp.vente.numero,
    )
    lp.quantite_servie += a_livrer
    lp.save(update_fields=["quantite_servie"])
    vente = lp.vente
    vente.statut = StatutVente.LIVREE if vente.est_complete else StatutVente.PARTIELLE
    vente.livree_le = vente.livree_le or timezone.now()
    vente.livree_par = u
    vente.save(update_fields=["statut", "livree_le", "livree_par"])
    messages.success(request, f"{a_livrer} unité(s) livrée(s) pour {lp.produit.designation}.")
    return redirect("avoir_document", uuid=vente.uuid)
