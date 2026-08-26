from django.urls import path
from . import views

urlpatterns = [
    path("", views.depenses_liste, name="depenses_liste"),
    path("nouvelle/", views.depense_formulaire, name="depense_nouvelle"),
    path("<int:pk>/", views.depense_detail, name="depense_detail"),
    path("<int:pk>/modifier/", views.depense_modifier, name="depense_modifier"),
    path("<int:pk>/soumettre/", views.depense_soumettre, name="depense_soumettre"),
    path("<int:pk>/valider/", views.depense_valider, name="depense_valider"),
    path("<int:pk>/rejeter/", views.depense_rejeter, name="depense_rejeter"),
    path("<int:pk>/confirmer/", views.depense_confirmer, name="depense_confirmer"),
    path("<int:pk>/supprimer/", views.depense_supprimer, name="depense_supprimer"),
]
