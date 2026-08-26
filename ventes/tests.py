"""
Tests dérivés des critères de recette (section 20 du cahier des charges).
Quand ils passent tous, le module de vente est livrable.
"""

import threading

from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase

from catalogue.models import Produit
from core.models import Commune, Profil, Site, TypeSite, Utilisateur
from kits.models import ClasseEcole, Kit, KitLigne, Niveau
from stock.models import MouvementStock, SoldeStock, TypeMouvement
from stock.services import enregistrer_mouvement

from .models import StatutVente, Vente
from .services import VenteDejaEnregistree, annuler_vente, completer_livraison, enregistrer_vente


def monter_decor(stock_c200=100, stock_c100=100):
    commune = Commune.objects.create(nom="Bingerville")
    magasin = Site.objects.create(type=TypeSite.MAGASIN, nom="Bingerville", commune=commune)
    ecole = Site.objects.create(
        type=TypeSite.ECOLE, nom="Mamie Fétaï", commune=commune, magasin_rattachement=magasin
    )
    c100 = Produit.objects.create(code="C100", designation="Cahier 100 pages", cout_achat=380, prix_detail=600)
    c200 = Produit.objects.create(code="C200", designation="Cahier 200 pages", cout_achat=540, prix_detail=850)

    classe = ClasseEcole.objects.create(ecole=ecole, niveau=Niveau.SIXIEME, libelle="6ème A")
    kit = Kit.objects.create(ecole=ecole, classe=classe, prix_vente=2000)
    KitLigne.objects.create(kit=kit, produit=c100, quantite=1)
    KitLigne.objects.create(kit=kit, produit=c200, quantite=2)

    vendeuse = Utilisateur.objects.create_user(
        "awa", password="x", profil=Profil.COMMERCIAL, site=ecole
    )
    for produit, quantite in ((c100, stock_c100), (c200, stock_c200)):
        enregistrer_mouvement(
            site=ecole, produit=produit, type=TypeMouvement.ENTREE_TRANSFERT, quantite=quantite
        )
    return dict(commune=commune, magasin=magasin, ecole=ecole, c100=c100, c200=c200, kit=kit, vendeuse=vendeuse)


class VenteEtStock(TestCase):
    def setUp(self):
        self.d = monter_decor()

    def test_critere_1_la_vente_decremente_le_stock(self):
        """Critère n°1 : une vente de kit décrémente immédiatement le stock de l'école."""
        enregistrer_vente(ecole=self.d["ecole"], vendeuse=self.d["vendeuse"], kits=[(self.d["kit"], 2)])
        self.assertEqual(SoldeStock.objects.get(site=self.d["ecole"], produit=self.d["c100"]).quantite, 98)
        self.assertEqual(SoldeStock.objects.get(site=self.d["ecole"], produit=self.d["c200"]).quantite, 96)

    def test_le_solde_reste_egal_a_la_somme_du_journal(self):
        enregistrer_vente(ecole=self.d["ecole"], vendeuse=self.d["vendeuse"], kits=[(self.d["kit"], 3)])
        solde = SoldeStock.objects.get(site=self.d["ecole"], produit=self.d["c200"])
        cache = solde.quantite
        self.assertEqual(cache, solde.recalculer())

    def test_montant_calcule_automatiquement(self):
        v = enregistrer_vente(ecole=self.d["ecole"], vendeuse=self.d["vendeuse"], kits=[(self.d["kit"], 3)])
        self.assertEqual(v.montant_total, 6000)
        self.assertTrue(v.numero.endswith("00001"))

    def test_remise_conventionnelle(self):
        self.d["ecole"].remise_convention = 10
        self.d["ecole"].save()
        v = enregistrer_vente(
            ecole=self.d["ecole"], vendeuse=self.d["vendeuse"], kits=[(self.d["kit"], 1)],
            appliquer_remise_convention=True,
        )
        self.assertEqual(v.montant_total, 1800)

    def test_critere_5_cloisonnement_entre_ecoles(self):
        """Critère n°5 : un commercial ne peut pas vendre pour une autre école que la sienne."""
        autre = Site.objects.create(
            type=TypeSite.ECOLE, nom="Autre école", commune=self.d["commune"],
            magasin_rattachement=self.d["magasin"],
        )
        self.assertFalse(self.d["vendeuse"].peut_acceder_au_site(autre))
        with self.assertRaises(ValidationError):
            enregistrer_vente(ecole=autre, vendeuse=self.d["vendeuse"], kits=[(self.d["kit"], 1)])

    def test_superviseur_voit_sa_commune_seulement(self):
        autre_commune = Commune.objects.create(nom="Cocody")
        hors_commune = Site.objects.create(type=TypeSite.MAGASIN, nom="Cocody", commune=autre_commune)
        superviseur = Utilisateur.objects.create_user(
            "yao", password="x", profil=Profil.SUPERVISEUR, commune=self.d["commune"]
        )
        self.assertTrue(superviseur.peut_acceder_au_site(self.d["ecole"]))
        self.assertFalse(superviseur.peut_acceder_au_site(hors_commune))

    def test_idempotence_sur_uuid_client(self):
        """Une requête rejouée après un timeout réseau ne crée pas de doublon."""
        identifiant = "11111111-2222-3333-4444-555555555555"
        enregistrer_vente(
            ecole=self.d["ecole"], vendeuse=self.d["vendeuse"], kits=[(self.d["kit"], 1)], uuid=identifiant
        )
        with self.assertRaises(VenteDejaEnregistree):
            enregistrer_vente(
                ecole=self.d["ecole"], vendeuse=self.d["vendeuse"], kits=[(self.d["kit"], 1)], uuid=identifiant
            )
        self.assertEqual(Vente.objects.count(), 1)
        self.assertEqual(SoldeStock.objects.get(site=self.d["ecole"], produit=self.d["c100"]).quantite, 99)

    def test_livraison_partielle_cree_un_solde_a_livrer(self):
        d = self.d
        SoldeStock.objects.filter(site=d["ecole"], produit=d["c200"]).delete()
        MouvementStock.objects.filter(site=d["ecole"], produit=d["c200"]).delete()
        enregistrer_mouvement(
            site=d["ecole"], produit=d["c200"], type=TypeMouvement.ENTREE_TRANSFERT, quantite=1
        )
        v = enregistrer_vente(ecole=d["ecole"], vendeuse=d["vendeuse"], kits=[(d["kit"], 1)])
        self.assertFalse(v.est_complete)
        manquant = v.reste_a_livrer[0]
        self.assertEqual(manquant.produit, d["c200"])
        self.assertEqual(manquant.quantite_manquante, 1)

        enregistrer_mouvement(
            site=d["ecole"], produit=d["c200"], type=TypeMouvement.ENTREE_ACHAT, quantite=10
        )
        completer_livraison(v, par=d["vendeuse"])
        v.refresh_from_db()
        self.assertEqual(v.statut, StatutVente.LIVREE)
        self.assertEqual(SoldeStock.objects.get(site=d["ecole"], produit=d["c200"]).quantite, 9)

    def test_annulation_par_mouvement_compensatoire(self):
        """Section 10 : aucune vente validée n'est écrasée, on compense."""
        v = enregistrer_vente(ecole=self.d["ecole"], vendeuse=self.d["vendeuse"], kits=[(self.d["kit"], 1)])
        mouvements_avant = MouvementStock.objects.count()
        annuler_vente(v, par=self.d["vendeuse"], motif="erreur de caisse")
        v.refresh_from_db()
        self.assertEqual(v.statut, StatutVente.ANNULEE)
        self.assertEqual(MouvementStock.objects.count(), mouvements_avant + 2)
        self.assertEqual(SoldeStock.objects.get(site=self.d["ecole"], produit=self.d["c100"]).quantite, 100)


class ConcurrenceSurLeDernierKit(TransactionTestCase):
    """
    Deux caissières vendent le dernier kit à la même seconde.
    Sans verrou de ligne, le stock finit négatif et l'inventaire est faux.
    """

    def test_le_stock_ne_passe_pas_negatif(self):
        d = monter_decor(stock_c100=1, stock_c200=2)
        resultats = []

        def vendre():
            try:
                v = enregistrer_vente(ecole=d["ecole"], vendeuse=d["vendeuse"], kits=[(d["kit"], 1)])
                resultats.append(v.est_complete)
            finally:
                connections.close_all()

        fils = [threading.Thread(target=vendre) for _ in range(2)]
        for f in fils:
            f.start()
        for f in fils:
            f.join()

        self.assertEqual(len(resultats), 2)
        self.assertEqual(sorted(resultats), [False, True])  # une complète, une partielle
        for produit in (d["c100"], d["c200"]):
            solde = SoldeStock.objects.get(site=d["ecole"], produit=produit)
            self.assertGreaterEqual(solde.quantite, 0)
            self.assertEqual(solde.quantite, solde.recalculer())
