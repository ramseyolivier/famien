from django.core.exceptions import ValidationError
from django.test import TestCase

from catalogue.models import Produit
from core.models import Commune, Site, TypeSite

from .models import ClasseEcole, Kit, KitLigne, Niveau


class RegleDePrixEtVersionnage(TestCase):
    def setUp(self):
        commune = Commune.objects.create(nom="Bingerville")
        magasin = Site.objects.create(type=TypeSite.MAGASIN, nom="Bingerville", commune=commune)
        self.ecole = Site.objects.create(
            type=TypeSite.ECOLE, nom="Mamie Fétaï", commune=commune, magasin_rattachement=magasin
        )
        self.classe = ClasseEcole.objects.create(
            ecole=self.ecole, niveau=Niveau.SIXIEME, libelle="6ème A"
        )
        self.c100 = Produit.objects.create(code="C100", designation="Cahier 100", cout_achat=380, prix_detail=600)
        self.c200 = Produit.objects.create(code="C200", designation="Cahier 200", cout_achat=540, prix_detail=850)

    def _kit(self, prix):
        kit = Kit.objects.create(ecole=self.ecole, classe=self.classe, prix_vente=prix)
        KitLigne.objects.create(kit=kit, produit=self.c100, quantite=1)
        KitLigne.objects.create(kit=kit, produit=self.c200, quantite=2)
        return kit

    def test_calculs_automatiques(self):
        kit = self._kit(2000)
        self.assertEqual(kit.cout_revient, 380 + 2 * 540)      # 1460
        self.assertEqual(kit.total_prix_detail, 600 + 2 * 850)  # 2300
        self.assertEqual(kit.marge, 540)
        self.assertEqual(kit.economie_client, 300)
        self.assertEqual(kit.nombre_articles, 3)

    def test_prix_du_kit_superieur_au_cout_de_revient(self):
        # cout_revient = 380 + 2*540 = 1460
        self._kit(2000).verifier_regle_de_prix()   # 2000 > 1460 → valide
        Kit.objects.all().delete()
        with self.assertRaises(ValidationError):
            self._kit(1400).verifier_regle_de_prix()  # 1400 <= 1460 → invalide

    def test_une_seule_version_active_par_classe(self):
        kit = self._kit(2000)
        suivant = kit.nouvelle_version()
        kit.refresh_from_db()
        self.assertFalse(kit.actif)
        self.assertTrue(suivant.actif)
        self.assertEqual(suivant.version, 2)
        self.assertEqual(suivant.lignes.count(), 2)
        self.assertEqual(Kit.objects.filter(classe=self.classe, actif=True).count(), 1)
