from django.urls import path

from . import views

urlpatterns = [
    # Tableau de bord
    path("", views.accueil, name="admin_accueil"),

    # Communes
    path("communes/", views.communes_liste, name="admin_communes"),
    path("communes/nouvelle/", views.commune_formulaire, name="admin_commune_nouvelle"),
    path("communes/<int:pk>/modifier/", views.commune_formulaire, name="admin_commune_modifier"),
    path("communes/<int:pk>/supprimer/", views.commune_supprimer, name="admin_commune_supprimer"),

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

    # Magasins
    path("magasins/", views.magasins_liste, name="admin_magasins"),
    path("magasins/nouveau/", views.magasin_formulaire, name="admin_magasin_nouveau"),
    path("magasins/<int:pk>/modifier/", views.magasin_formulaire, name="admin_magasin_modifier"),
    path("magasins/<int:pk>/activer/", views.magasin_activer, name="admin_magasin_activer"),

    # Écoles
    path("ecoles/", views.ecoles_liste, name="admin_ecoles"),
    path("ecoles/nouvelle/", views.ecole_formulaire, name="admin_ecole_nouvelle"),
    path("ecoles/<int:pk>/modifier/", views.ecole_formulaire, name="admin_ecole_modifier"),
    path("ecoles/<int:pk>/activer/", views.ecole_activer, name="admin_ecole_activer"),
    path("ecoles/<int:pk>/tarifs/", views.ecole_tarifs, name="admin_ecole_tarifs"),

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
