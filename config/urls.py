handler404 = "core.views.page_404"

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import RedirectView

from ventes import views as ventes_views
from ventes.exports import export_ventes_excel, export_kits_excel, export_annulations_excel
from stock import views as stock_views
from stock.exports import export_stock_excel, export_sous_seuil_excel, export_ruptures_excel
from achats import views as achats_views
from core import views as core_views

admin.site.site_header = "GROUPE FAMIEN — administration"
admin.site.site_title = "FAMIEN"
admin.site.index_title = "Paramétrage et référentiels"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("administration/", include("administration.urls")),
    path(
        "connexion/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="connexion",
    ),
    path("deconnexion/", core_views.deconnexion, name="deconnexion"),

    # ─── Accueil & hubs de section ───────────────────────────────────────────
    path("", ventes_views.accueil, name="accueil"),
    path("ventes/", ventes_views.hub_ventes, name="hub_ventes"),
    path("stock/", stock_views.hub_stock, name="hub_stock"),
    path("operations/", RedirectView.as_view(pattern_name="hub_approvisionnement", permanent=False), name="hub_operations"),

    # ─── Finances (M18) ──────────────────────────────────────────────────────
    path("finances/", ventes_views.hub_finances, name="hub_finances"),
    path("finances/entrees-sorties/", ventes_views.finances_entrees_sorties, name="finances_entrees_sorties"),
    path("finances/entrees-sorties/export/", ventes_views.finances_entrees_sorties_export, name="finances_entrees_sorties_export"),
    path("finances/entrees/", ventes_views.finances_ventes, name="finances_entrees"),
    path("finances/sorties/", ventes_views.finances_sorties, name="finances_sorties"),
    path("finances/bilan/", ventes_views.finances_bilan, name="finances_bilan"),
    path("finances/versements/", ventes_views.versements_liste, name="versements_liste"),
    path("finances/versements/nouveau/", ventes_views.versement_nouveau, name="versement_nouveau"),
    path("finances/versements/<int:pk>/", ventes_views.versement_detail, name="versement_detail"),
    path("finances/versements/<int:pk>/traiter/", ventes_views.versement_traiter, name="versement_traiter"),
    path("finances/versements/export/", ventes_views.versements_export, name="versements_export"),
    path("finances/versements/global/", ventes_views.versements_global, name="versements_global"),
    path("finances/rapport-journalier/", ventes_views.rapport_financier, name="rapport_financier"),
    path("finances/rapport-journalier/export/", ventes_views.rapport_financier_export, name="rapport_financier_export"),
    path("finances/tresorerie/", ventes_views.tresorerie_globale, name="tresorerie_globale"),

    # ─── Vente ───────────────────────────────────────────────────────────────
    path("vente/", ventes_views.vente, name="vente"),
    path("proforma/", ventes_views.proforma_formulaire, name="proforma_formulaire"),
    path("proforma/apercu/", ventes_views.proforma_apercu, name="proforma_apercu"),
    path("recu/<uuid:uuid>/", ventes_views.recu, name="recu"),
    path("recu/<uuid:uuid>/imprimer/", ventes_views.recu_imprimer, name="recu_imprimer"),
    path("historique/", ventes_views.historique_ventes, name="historique_ventes"),
    path("historique/kits/", ventes_views.rapport_kits_vendus, name="rapport_kits_vendus"),
    path("historique/kits/detail/", ventes_views.rapport_kits_detail, name="rapport_kits_detail"),
    path("ventes/finances/", ventes_views.finances_ventes, name="finances_ventes"),
    path("historique/export/", export_ventes_excel, name="export_ventes"),
    path("facture/<uuid:uuid>/", ventes_views.facture_vente, name="facture_vente"),
    path("vente/<uuid:uuid>/annuler/", ventes_views.vente_annuler, name="vente_annuler"),
    path("vente/<uuid:uuid>/demander-annulation/", ventes_views.vente_demander_annulation, name="vente_demander_annulation"),
    path("vente/<uuid:uuid>/rejeter-annulation/", ventes_views.vente_rejeter_annulation, name="vente_rejeter_annulation"),
    path("annulations/demandes/", ventes_views.demandes_annulation, name="demandes_annulation"),
    path("annulations/", ventes_views.historique_annulations, name="historique_annulations"),
    path("annulations/export/", export_annulations_excel, name="export_annulations"),

    # ─── Avoirs ──────────────────────────────────────────────────────────────
    path("avoirs/", ventes_views.avoirs_liste, name="avoirs_liste"),
    path("avoirs/<uuid:uuid>/livrer/", ventes_views.avoir_livrer, name="avoir_livrer"),
    path("avoirs/<int:pk>/annuler/", ventes_views.avoir_annuler_ligne, name="avoir_annuler_ligne"),
    path("avoirs/<int:pk>/livrer-partiel/", ventes_views.avoir_livrer_partiel, name="avoir_livrer_partiel"),
    path("avoirs/<uuid:uuid>/document/", ventes_views.avoir_document, name="avoir_document"),

    # ─── Créances (ventes à crédit) ──────────────────────────────────────────
    path("creances/", ventes_views.creances_liste, name="creances_liste"),
    path("creances/<int:pk>/", ventes_views.creance_detail, name="creance_detail"),

    # ─── Clôtures de caisse (M19) ────────────────────────────────────────────
    path("clotures/", ventes_views.clotures_liste, name="clotures_liste"),
    path("clotures/nouvelle/", ventes_views.cloturer_caisse, name="cloturer_caisse"),

    # ─── Stock ───────────────────────────────────────────────────────────────
    path("stock/articles/", ventes_views.stock_articles, name="stock_articles"),
    path("stock/export/", export_stock_excel, name="export_stock"),
    path("stock/kits/", ventes_views.stock_kits, name="stock_kits"),
    path("stock/kits/export/", export_kits_excel, name="export_kits"),
    path("stock/ajustements/", stock_views.ajustements_liste, name="ajustements_liste"),
    path("stock/ajustements/nouveau/", stock_views.ajustement_formulaire, name="ajustement_nouveau"),
    path("stock/ajustements/<int:pk>/valider/", stock_views.ajustement_valider, name="ajustement_valider"),
    path("stock/seuils/", stock_views.parametres_seuils, name="parametres_seuils"),
    path("stock/sous-seuil/", stock_views.stock_sous_seuil, name="stock_sous_seuil"),
    path("stock/sous-seuil/export/", export_sous_seuil_excel, name="export_sous_seuil"),
    path("stock/ruptures/", stock_views.stock_ruptures, name="stock_ruptures"),
    path("stock/ruptures/export/", export_ruptures_excel, name="export_ruptures"),
    path("stock/rapport-journalier/", stock_views.rapport_journalier, name="rapport_journalier"),
    path("stock/rapport-journalier/export/", stock_views.rapport_journalier_export, name="rapport_journalier_export"),
    path("stock/rapport-journalier-pousse/", stock_views.rapport_journalier_pousse, name="rapport_journalier_pousse"),
    path("stock/rapport-journalier-pousse/export/", stock_views.rapport_journalier_pousse_export, name="rapport_journalier_pousse_export"),

    # ─── Transferts (M11) ────────────────────────────────────────────────────
    path("transferts/", include("transferts.urls")),

    # ─── Inventaires (M10) ───────────────────────────────────────────────────
    path("inventaires/", include("inventaires.urls")),

    # ─── Dépenses (M20) ──────────────────────────────────────────────────────
    path("depenses/", include("depenses.urls")),

    # ─── Notifications (M25) ─────────────────────────────────────────────────
    path("notifications/", core_views.notifications_liste, name="notifications_liste"),
    path("notifications/count/", core_views.notifications_count, name="notifications_count"),
    path("notifications/<int:pk>/lire/", core_views.notification_marquer_lue, name="notification_lire"),

    # ─── Approvisionnement écoles (M16) ──────────────────────────────────────
    path("approvisionnement/", include("approvisionnement.urls")),

    # ─── Non-conformités (M21) ───────────────────────────────────────────────
    path("nonconformites/", include("nonconformites.urls")),

    # ─── Redirection ancienne URL pilotage ───────────────────────────────────
    path("pilotage/", RedirectView.as_view(pattern_name="admin_accueil", permanent=True), name="tableau_bord"),

    # ─── Pages d'erreur (prévisualisation en développement) ──────────────────
    path("404/", core_views.page_404, name="page_404"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
