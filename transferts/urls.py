from django.urls import path

from . import views

urlpatterns = [
    path("", views.transferts_liste, name="transferts_liste"),
    path("export/", views.export_transferts, name="export_transferts"),
    path("nouveau/", views.transfert_formulaire, name="transfert_nouveau"),
    path("<int:pk>/", views.transfert_detail, name="transfert_detail"),
    path("<int:pk>/accepter/", views.transfert_accepter, name="transfert_accepter"),
    path("<int:pk>/rejeter/", views.transfert_rejeter, name="transfert_rejeter"),
]
