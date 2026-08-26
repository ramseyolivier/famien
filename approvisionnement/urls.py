from django.urls import include, path

from . import views
from .exports import (
    export_commande_ecole_detail_excel,
    export_commande_magasin_detail_excel,
    export_commandes_ecole_excel,
    export_commandes_magasin_excel,
    export_livraisons_ecole_excel,
    export_livraisons_magasin_excel,
    export_receptions_ecole_excel,
    export_receptions_magasin_excel,
)

urlpatterns = [
    path("", views.hub_approvisionnement, name="hub_approvisionnement"),
    # École — commandes
    path("ecole/commande/", views.commandes_liste, name="commandes_ecole_liste"),
    path("ecole/commande/export/", export_commandes_ecole_excel, name="export_commandes_ecole"),
    path("ecole/commande/nouvelle/", views.commande_formulaire, name="commande_ecole_nouvelle"),
    path("ecole/commande/<int:pk>/", views.commande_detail, name="commande_ecole_detail"),
    path("ecole/commande/<int:pk>/export/", export_commande_ecole_detail_excel, name="export_commande_ecole_detail"),
    path("ecole/commande/<int:pk>/modifier/", views.commande_modifier, name="commande_ecole_modifier"),
    path("ecole/commande/<int:pk>/supprimer/", views.commande_supprimer, name="commande_ecole_supprimer"),
    path("ecole/commande/<int:pk>/soumettre/", views.commande_soumettre, name="commande_ecole_soumettre"),
    path("ecole/commande/<int:pk>/valider/", views.commande_ecole_valider, name="commande_ecole_valider"),
    path("ecole/commande/<int:pk>/rejeter/", views.commande_ecole_rejeter, name="commande_ecole_rejeter"),
    # École — réceptions
    path("ecole/reception/", views.receptions_liste, name="receptions_ecole_liste"),
    path("ecole/reception/export/", export_receptions_ecole_excel, name="export_receptions_ecole"),
    path("ecole/reception/<int:pk>/", views.reception_valider, name="reception_ecole_valider"),
    # École — livraisons
    path("ecole/livraison/", views.livraisons_liste, name="livraisons_liste"),
    path("ecole/livraison/export/", export_livraisons_ecole_excel, name="export_livraisons_ecole"),
    path("ecole/livraison/<int:pk>/", views.livraison_traiter, name="livraison_traiter"),
    path("ecole/livraison/<int:pk>/refuser/", views.commande_ecole_refuser_livraison, name="commande_ecole_refuser_livraison"),
    path("ecole/livraison/directe/", views.livraison_directe_ecole, name="livraison_directe_ecole"),
    path("ecole/livraison/directe/<int:pk>/", views.livraison_directe_ecole_detail, name="livraison_directe_ecole_detail"),
    path("ecole/livraison/directe/<int:pk>/valider/", views.livraison_directe_ecole_valider, name="livraison_directe_ecole_valider"),
    path("ecole/livraison/directe/<int:pk>/modifier/", views.livraison_directe_ecole_modifier, name="livraison_directe_ecole_modifier"),
    path("ecole/livraison/directe/<int:pk>/supprimer/", views.livraison_directe_ecole_supprimer, name="livraison_directe_ecole_supprimer"),
    # Gestionnaire de magasin — stock réservé magasin
    path("magasin/stockreserver/", views.stock_reserve, name="stock_reserve"),
    # Approvisionnement magasin (M17)
    path("magasin/commandes/", views.commandes_magasin_liste, name="commandes_magasin_liste"),
    path("magasin/commandes/export/", export_commandes_magasin_excel, name="export_commandes_magasin"),
    path("magasin/nouvelle/", views.commande_magasin_formulaire, name="commande_magasin_nouvelle"),
    path("magasin/livraisons/", views.livraisons_magasin_liste, name="livraisons_magasin_liste"),
    path("magasin/livraisons/export/", export_livraisons_magasin_excel, name="export_livraisons_magasin"),
    path("magasin/livraisons/directe/", views.livraison_directe_magasin, name="livraison_directe_magasin"),
    path("magasin/livraisons/directe/<int:pk>/", views.livraison_directe_detail, name="livraison_directe_detail"),
    path("magasin/livraisons/directe/<int:pk>/valider/", views.livraison_directe_valider, name="livraison_directe_valider"),
    path("magasin/livraisons/directe/<int:pk>/modifier/", views.livraison_directe_modifier, name="livraison_directe_modifier"),
    path("magasin/livraisons/directe/<int:pk>/supprimer/", views.livraison_directe_supprimer, name="livraison_directe_supprimer"),
    path("magasin/reception/", views.receptions_magasin_liste, name="receptions_magasin_liste"),
    path("magasin/reception/export/", export_receptions_magasin_excel, name="export_receptions_magasin"),
    path("magasin/reception/directe/", views.reception_directe_magasin, name="reception_directe_magasin"),
    # Stock réservé dépôt — avant le include fournisseurs/
    path("fournisseurs/stockreserver/", views.stock_reserve_depot, name="stock_reserve_depot"),
    # Pilotage commandes magasin (M17 — décision achat dépôt)
    path("magasin/pilotage/", views.pilotage_commandes_depot, name="pilotage_commandes_depot"),
    path("magasin/pilotage/export/", views.pilotage_export, name="pilotage_export"),
    # Pilotage commandes école (M16 — déficits magasin vs demandes école)
    path("ecole/pilotage/", views.pilotage_commandes_ecole, name="pilotage_commandes_ecole"),
    path("ecole/pilotage/export/", views.pilotage_ecole_export, name="pilotage_ecole_export"),
    path("magasin/<int:pk>/", views.commande_magasin_detail, name="commande_magasin_detail"),
    path("magasin/<int:pk>/export/", export_commande_magasin_detail_excel, name="export_commande_magasin_detail"),
    path("magasin/<int:pk>/supprimer/", views.commande_magasin_supprimer, name="commande_magasin_supprimer"),
    path("magasin/<int:pk>/modifier/", views.commande_magasin_modifier, name="commande_magasin_modifier"),
    path("magasin/<int:pk>/soumettre/", views.commande_magasin_soumettre, name="commande_magasin_soumettre"),
    path("magasin/<int:pk>/valider/", views.commande_magasin_valider, name="commande_magasin_valider"),
    path("magasin/<int:pk>/rejeter/", views.commande_magasin_rejeter, name="commande_magasin_rejeter"),
    path("magasin/<int:pk>/livraison/", views.commande_magasin_livraison, name="commande_magasin_livraison"),
    path("magasin/<int:pk>/refuser-livraison/", views.commande_magasin_refuser_livraison, name="commande_magasin_refuser_livraison"),
    path("magasin/<int:pk>/reception/", views.commande_magasin_reception, name="commande_magasin_reception"),
    # Achats fournisseurs (M13-M15) — sous /approvisionnement/fournisseurs/
    path("fournisseurs/", include("achats.urls")),
]
