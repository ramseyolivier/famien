from django.urls import path
from . import views
from .exports import export_commandes_fournisseur_excel, export_receptions_fournisseur_excel, export_reception_detail_excel, export_commande_detail_excel

urlpatterns = [
    path("commandes/", views.commandes_liste, name="commandes_liste"),
    path("commandes/export/", export_commandes_fournisseur_excel, name="export_commandes_fournisseur"),
    path("commandes/<int:pk>/export/", export_commande_detail_excel, name="export_commande_detail"),
    path("commandes/nouvelle/", views.commande_formulaire, name="commande_nouvelle"),
    path("commandes/<int:pk>/", views.commande_detail, name="commande_detail"),
    path("commandes/<int:pk>/modifier/", views.commande_modifier, name="commande_modifier"),
    path("commandes/<int:pk>/supprimer/", views.commande_supprimer, name="commande_supprimer"),
    path("commandes/<int:pk>/soumettre/", views.commande_soumettre, name="commande_soumettre"),
    path("commandes/<int:pk>/valider-n1/", views.commande_valider_n1, name="commande_valider_n1"),
    path("commandes/<int:pk>/valider/", views.commande_valider, name="commande_valider"),
    path("commandes/<int:pk>/rejeter/", views.commande_rejeter, name="commande_rejeter"),
    path("commandes/<int:pk>/cloturer/", views.commande_cloturer, name="commande_cloturer"),
    path("receptions/", views.receptions_liste, name="receptions_liste"),
    path("receptions/export/", export_receptions_fournisseur_excel, name="export_receptions_fournisseur"),
    path("receptions/nouvelle/<int:commande_pk>/", views.reception_formulaire, name="reception_nouvelle"),
    path("receptions/<int:pk>/modifier/", views.reception_modifier, name="reception_modifier"),
    path("receptions/libre/", views.reception_libre_formulaire, name="reception_libre"),
    path("receptions/<int:pk>/", views.reception_detail, name="reception_detail"),
    path("receptions/<int:pk>/export/", export_reception_detail_excel, name="export_reception_detail"),
    path("receptions/<int:pk>/valider/", views.reception_valider, name="reception_valider"),
    path("receptions/<int:pk>/supprimer/", views.reception_supprimer, name="reception_supprimer"),
]
