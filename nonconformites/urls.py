from django.urls import path

from . import views

urlpatterns = [
    path("", views.nc_liste, name="nc_liste"),
    path("nouvelle/", views.nc_formulaire, name="nc_nouveau"),
    path("<int:pk>/", views.nc_detail, name="nc_detail"),
    path("<int:pk>/supprimer/", views.nc_supprimer, name="nc_supprimer"),
    path("<int:pk>/exporter/", views.nc_exporter_word, name="nc_exporter_word"),
]
