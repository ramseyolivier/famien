from django.core.exceptions import ValidationError
from django.test import TestCase

from catalogue.models import Produit
from core.models import Site, TypeSite

from .models import MouvementStock, SoldeStock, TypeMouvement
from .services import StockInsuffisant, annuler_mouvement, enregistrer_mouvement, references_sous_seuil


class JournalImmuable(TestCase):
    def setUp(self):
        self.site = Site.objects.create(type=TypeSite.SITE, nom="Cocody")
        self.produit = Produit.objects.create(code="C200", designation="Cahier 200 pages")

    def test_un_mouvement_ne_peut_pas_etre_modifie(self):
        m, _ = enregistrer_mouvement(
            site=self.site, produit=self.produit, type=TypeMouvement.ENTREE_ACHAT, quantite=50
        )
        m.quantite = 999
        with self.assertRaises(ValidationError):
            m.save()

    def test_un_mouvement_ne_peut_pas_etre_supprime(self):
        m, _ = enregistrer_mouvement(
            site=self.site, produit=self.produit, type=TypeMouvement.ENTREE_ACHAT, quantite=50
        )
        with self.assertRaises(ValidationError):
            m.delete()

    def test_correction_par_compensation(self):
        m, _ = enregistrer_mouvement(
            site=self.site, produit=self.produit, type=TypeMouvement.ENTREE_ACHAT, quantite=50
        )
        annuler_mouvement(m, motif="saisie erronée")
        self.assertEqual(SoldeStock.objects.get(site=self.site, produit=self.produit).quantite, 0)
        self.assertEqual(MouvementStock.objects.count(), 2)

    def test_sortie_superieure_au_stock_refusee(self):
        enregistrer_mouvement(
            site=self.site, produit=self.produit, type=TypeMouvement.ENTREE_ACHAT, quantite=5
        )
        with self.assertRaises(StockInsuffisant):
            enregistrer_mouvement(
                site=self.site, produit=self.produit, type=TypeMouvement.PERTE, quantite=-6
            )

    def test_critere_7_alerte_sous_le_stock_de_securite(self):
        """Critère n°7 : la référence remonte dès qu'elle atteint son seuil."""
        enregistrer_mouvement(
            site=self.site, produit=self.produit, type=TypeMouvement.ENTREE_ACHAT, quantite=30
        )
        solde = SoldeStock.objects.get(site=self.site, produit=self.produit)
        solde.stock_securite = 20
        solde.save()
        self.assertNotIn(solde, list(references_sous_seuil()))

        enregistrer_mouvement(
            site=self.site, produit=self.produit, type=TypeMouvement.SORTIE_VENTE, quantite=-11
        )
        self.assertIn(solde.pk, [s.pk for s in references_sous_seuil()])
