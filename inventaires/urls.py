from django.urls import path

from . import views
from .exports import export_inventaire_excel

urlpatterns = [
    path("", views.inventaires_liste, name="inventaires_liste"),
    path("export/", views.inventaires_liste_export, name="inventaires_liste_export"),
    path("global/", views.inventaires_global, name="inventaires_global"),
    path("global/export/", views.inventaires_global_export, name="inventaires_global_export"),
    path("nouveau/", views.inventaire_nouveau, name="inventaire_nouveau"),
    path("<int:pk>/saisir/", views.inventaire_saisir, name="inventaire_saisir"),
    path("<int:pk>/detail/", views.inventaire_detail, name="inventaire_detail"),
    path("<int:pk>/valider/", views.inventaire_valider, name="inventaire_valider"),
    path("<int:pk>/export/", export_inventaire_excel, name="inventaire_export"),
]
