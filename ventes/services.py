"""
Enregistrement d'une vente : le cœur métier de l'application.

Une vente touche trois tables et le journal de stock. Tout doit réussir ou tout
doit échouer — d'où la transaction unique. L'ordre de verrouillage est toujours
le même (école, puis soldes par code produit croissant), ce qui écarte les
interblocages entre deux caissières servant en parallèle.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from catalogue.models import Produit, PrixEcole
from core.models import SequenceCompteur, Site
from kits.models import Kit
from stock.models import TypeMouvement
from stock.services import enregistrer_mouvement, get_ou_cree_solde

from .models import LigneProduitVente, LigneVente, StatutVente, Vente


class VenteDejaEnregistree(Exception):
    """L'uuid client existe déjà : la requête précédente avait abouti."""

    def __init__(self, vente):
        self.vente = vente
        super().__init__(f"Vente {vente.numero} déjà enregistrée.")


def _numero_suivant(ecole):
    """Génère VTE-{code}-{NNNNN} sous verrou de séquence, compteur continu par école (§3.2 du SRS)."""
    code = ecole.code.upper() if ecole.code else str(ecole.pk)
    cle = f"VTE-{code}"
    compteur, _ = SequenceCompteur.objects.select_for_update().get_or_create(cle=cle)
    compteur.valeur += 1
    compteur.save(update_fields=["valeur"])
    return f"{cle}-{compteur.valeur:05d}"


def _besoins_en_produits(lignes_kit, lignes_detail):
    """Éclate les kits en références et fusionne avec les ventes au détail."""
    besoins = {}
    for kit, quantite, *_ in lignes_kit:
        for ligne in kit.lignes.select_related("produit"):
            besoins[ligne.produit] = besoins.get(ligne.produit, 0) + ligne.quantite * quantite
    for produit, quantite, *_ in lignes_detail:
        besoins[produit] = besoins.get(produit, 0) + quantite
    return besoins


@transaction.atomic
def enregistrer_vente(
    *, ecole, vendeuse, kits=(), detail=(), mode_paiement="ESPECES", observations="",
    appliquer_remise_convention=False, uuid=None, telephone_client="", montant_recu=None,
    a_credit=False, client_nom="", client_prenom="",
):
    """
    kits   : itérable de (Kit, quantité, mode_paiement)
    detail : itérable de (Produit, quantité, mode_paiement)

    Sert autant que le stock le permet ; le manquant devient un avoir rattaché
    à la vente. La vente est LIVREE si tout est servi, PARTIELLE sinon.
    """
    if not vendeuse.peut_acceder_au_site(ecole):
        raise ValidationError("Cette vendeuse n'est pas rattachée à cette école.")
    if not kits and not detail:
        raise ValidationError("Une vente doit comporter au moins un kit ou un article.")

    if uuid:
        existante = Vente.objects.filter(uuid=uuid).first()
        if existante:
            raise VenteDejaEnregistree(existante)

    # Verrou n°1 : l'école, pour sérialiser la numérotation.
    Site.objects.select_for_update().get(pk=ecole.pk)

    montant = Decimal("0")
    for kit, quantite, *_ in kits:
        if kit.ecole_id != ecole.pk:
            raise ValidationError(f"Le kit {kit} n'appartient pas à cette école.")
        if not kit.actif:
            raise ValidationError(f"Le kit {kit} n'est plus la version active.")
        montant += kit.prix_vente * quantite
    for produit, quantite, *_ in detail:
        montant += produit.prix_pour_ecole(ecole) * quantite

    remise = Decimal("0")
    if appliquer_remise_convention and ecole.remise_convention:
        remise = (montant * ecole.remise_convention / Decimal("100")).quantize(Decimal("1"))

    vente = Vente.objects.create(
        **({"uuid": uuid} if uuid else {}),
        numero=_numero_suivant(ecole),
        ecole=ecole,
        vendeuse=vendeuse,
        montant_total=montant - remise,
        remise=remise,
        mode_paiement=mode_paiement,
        observations=observations,
        telephone_client=telephone_client or "",
        a_credit=bool(a_credit),
        client_nom=client_nom or "",
        client_prenom=client_prenom or "",
        **({"montant_recu": Decimal(str(montant_recu))} if montant_recu else {}),
    )

    from .models import ModePaiement as MP
    LigneVente.objects.bulk_create(
        [LigneVente(vente=vente, kit=kit, quantite=q,
                    prix_unitaire=kit.prix_vente,
                    mode_paiement=(rest[0] if rest else MP.ESPECES))
         for kit, q, *rest in kits]
        + [LigneVente(vente=vente, produit=p, quantite=q,
                      prix_unitaire=p.prix_pour_ecole(ecole),
                      mode_paiement=(rest[0] if rest else MP.ESPECES))
           for p, q, *rest in detail]
    )

    besoins = _besoins_en_produits(kits, detail)
    # Verrou n°2 : les soldes, toujours dans l'ordre du code produit.
    a_des_avoirs = False
    deduction_credit = Decimal("0")
    for produit in sorted(besoins, key=lambda p: p.code):
        due = besoins[produit]
        solde = get_ou_cree_solde(ecole, produit)
        servie = max(min(due, solde.quantite), 0)
        if servie:
            enregistrer_mouvement(
                site=ecole,
                produit=produit,
                type=TypeMouvement.SORTIE_VENTE,
                quantite=-servie,
                auteur=vendeuse,
                reference_document=vente.numero,
            )
        prix_u = produit.prix_pour_ecole(ecole)
        if a_credit and servie < due:
            # Vente à crédit : pas d'avoir, le client prend ce qui est dispo.
            deduction_credit += (due - servie) * prix_u
            due = servie
        LigneProduitVente.objects.create(
            vente=vente, produit=produit, quantite_due=due, quantite_servie=servie,
            prix_unitaire_avoir=prix_u,
        )
        if servie < due:
            a_des_avoirs = True

    if a_credit and deduction_credit:
        vente.montant_total = max(Decimal("0"), vente.montant_total - deduction_credit)
        vente.save(update_fields=["montant_total"])

    now = timezone.now()
    if a_des_avoirs:
        vente.statut = StatutVente.PARTIELLE
        vente.livree_le = now
        vente.livree_par = vendeuse
    else:
        vente.statut = StatutVente.LIVREE
        vente.livree_le = now
        vente.livree_par = vendeuse
    vente.save(update_fields=["statut", "livree_le", "livree_par"])

    return vente


@transaction.atomic
def marquer_livree(vente, *, par):
    """Le commercial a remis le kit au client. Ferme la ligne de la file de livraison."""
    if vente.statut == StatutVente.ANNULEE:
        raise ValidationError("Une vente annulée ne peut pas être livrée.")
    vente.statut = StatutVente.LIVREE if vente.est_complete else StatutVente.PARTIELLE
    vente.livree_le = timezone.now()
    vente.livree_par = par
    vente.save(update_fields=["statut", "livree_le", "livree_par"])
    return vente


@transaction.atomic
def completer_livraison(vente, *, par):
    """Sert le solde d'une livraison partielle dès que le réassort est arrivé."""
    reste = 0
    for ligne in vente.lignes_produit.select_related("produit"):
        manquant = ligne.quantite_manquante
        if not manquant:
            continue
        solde = get_ou_cree_solde(vente.ecole, ligne.produit)
        servie = max(min(manquant, solde.quantite), 0)
        if servie:
            enregistrer_mouvement(
                site=vente.ecole,
                produit=ligne.produit,
                type=TypeMouvement.SORTIE_VENTE,
                quantite=-servie,
                auteur=par,
                reference_document=vente.numero,
                commentaire="Solde de livraison partielle",
            )
            ligne.quantite_servie += servie
            ligne.save(update_fields=["quantite_servie"])
        reste += manquant - servie

    vente.statut = StatutVente.LIVREE if reste == 0 else StatutVente.PARTIELLE
    vente.livree_le = vente.livree_le or timezone.now()
    vente.livree_par = par
    vente.save(update_fields=["statut", "livree_le", "livree_par"])
    return vente


@transaction.atomic
def annuler_vente(vente, *, par, motif):
    """
    Aucune vente validée n'est modifiée ni supprimée (section 10). On remet en
    stock par mouvements compensatoires, on marque la vente annulée, et on
    clôture tous les avoirs restants (argent des avoirs retourné au client).
    """
    if vente.statut == StatutVente.ANNULEE:
        raise ValidationError("Vente déjà annulée.")
    now = timezone.now()
    for ligne in vente.lignes_produit.select_related("produit"):
        if ligne.quantite_servie:
            enregistrer_mouvement(
                site=vente.ecole,
                produit=ligne.produit,
                type=TypeMouvement.ANNULATION,
                quantite=ligne.quantite_servie,
                auteur=par,
                reference_document=vente.numero,
                commentaire=f"Annulation : {motif}",
            )
        if not ligne.avoir_annule and ligne.quantite_manquante:
            ligne.avoir_annule = True
            ligne.avoir_annule_par = par
            ligne.avoir_annule_le = now
            ligne.save(update_fields=["avoir_annule", "avoir_annule_par", "avoir_annule_le"])
    vente.statut = StatutVente.ANNULEE
    vente.annulee_par = par
    vente.annulee_le = now
    vente.motif_annulation = motif
    vente.save(update_fields=["statut", "annulee_par", "annulee_le", "motif_annulation"])
    return vente


@transaction.atomic
def annuler_avoir(ligne, *, par, motif=""):
    """
    Annule l'avoir restant sur une ligne produit : l'argent correspondant
    est remboursé au client. Aucun mouvement de stock — rien n'a été sorti.
    Si c'était le dernier avoir ouvert de la vente, la vente passe à LIVREE.
    """
    if ligne.avoir_annule:
        raise ValidationError("Cet avoir est déjà annulé.")
    if ligne.quantite_manquante == 0:
        raise ValidationError("Il n'y a plus rien à livrer sur cette ligne.")
    now = timezone.now()
    ligne.avoir_annule = True
    ligne.avoir_annule_par = par
    ligne.avoir_annule_le = now
    ligne.save(update_fields=["avoir_annule", "avoir_annule_par", "avoir_annule_le"])

    vente = ligne.vente
    encore_ouverts = vente.lignes_produit.filter(avoir_annule=False).exclude(
        quantite_servie=models.F("quantite_due")
    ).exists()
    if not encore_ouverts:
        vente.statut = StatutVente.LIVREE
        vente.save(update_fields=["statut"])
    return ligne
