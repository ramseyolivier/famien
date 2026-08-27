from django.urls import path

from . import views

urlpatterns = [
    # Tableau de bord
    path("", views.accueil, name="admin_accueil"),

    # Sites
    path("sites/", views.sites_liste, name="admin_sites"),
    path("sites/nouveau/", views.site_formulaire, name="admin_site_nouveau"),
    path("sites/<int:pk>/modifier/", views.site_formulaire, name="admin_site_modifier"),
    path("sites/<int:pk>/activer/", views.site_activer, name="admin_site_activer"),
    path("sites/<int:pk>/tarifs/", views.site_tarifs, name="admin_site_tarifs"),

    # Catégories produit
    path("categories/", views.categories_liste, name="admin_categories"),
    path("categories/nouvelle/", views.categorie_formulaire, name="admin_categorie_nouvelle"),
    path("categories/<int:pk>/modifier/", views.categorie_formulaire, name="admin_categorie_modifier"),
    path("categories/<int:pk>/supprimer/", views.categorie_supprimer, name="admin_categorie_supprimer"),

    # Marques
    path("marques/", views.marques_liste, name="admin_marques"),
    path("marques/nouvelle/", views.marque_formulaire, name="admin_marque_nouvelle"),
    path("marques/<int:pk>/modifier/", views.marque_formulaire, name="admin_marque_modifier"),
    path("marques/<int:pk>/supprimer/", views.marque_supprimer, name="admin_marque_supprimer"),

    # Produits
    path("produits/", views.produits_liste, name="admin_produits"),
    path("produits/nouveau/", views.produit_formulaire, name="admin_produit_nouveau"),
    path("produits/<int:pk>/modifier/", views.produit_formulaire, name="admin_produit_modifier"),
    path("produits/<int:pk>/activer/", views.produit_activer, name="admin_produit_activer"),
    path("produits/<int:pk>/tarifs/", views.produit_tarifs, name="admin_produit_tarifs"),

    # Classes d'école
    path("classes/", views.classes_liste, name="admin_classes"),
    path("classes/nouvelle/", views.classe_formulaire, name="admin_classe_nouveau"),
    path("classes/<int:pk>/modifier/", views.classe_formulaire, name="admin_classe_modifier"),
    path("classes/<int:pk>/supprimer/", views.classe_supprimer, name="admin_classe_supprimer"),

    # Kits
    path("kits/", views.kits_liste, name="admin_kits"),
    path("kits/nouveau/", views.kit_formulaire, name="admin_kit_nouveau"),
    path("kits/<int:pk>/modifier/", views.kit_formulaire, name="admin_kit_modifier"),
    path("kits/<int:pk>/supprimer/", views.kit_supprimer, name="admin_kit_supprimer"),

    # Utilisateurs
    path("utilisateurs/connexions/", views.utilisateurs_connexions, name="admin_utilisateurs_connexions"),
    path("utilisateurs/", views.utilisateurs_liste, name="admin_utilisateurs"),
    path("utilisateurs/nouveau/", views.utilisateur_formulaire, name="admin_utilisateur_nouveau"),
    path("utilisateurs/<int:pk>/modifier/", views.utilisateur_formulaire, name="admin_utilisateur_modifier"),
    path("utilisateurs/<int:pk>/activer/", views.utilisateur_activer, name="admin_utilisateur_activer"),
    path("utilisateurs/<int:pk>/mdp/", views.utilisateur_reset_mdp, name="admin_utilisateur_mdp"),
]
