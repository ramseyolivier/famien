"""
Service d'écriture du stock.

Toute écriture passe par ici. C'est le seul endroit du projet autorisé à créer
un MouvementStock, ce qui garantit qu'un mouvement et son solde ne peuvent pas
diverger.

Point critique : deux caissières de la même école qui vendent le dernier kit à
la même seconde. Le verrou de ligne (`select_for_update`) sérialise les deux
transactions sur le couple site/produit, si bien que la seconde lit le solde
déjà décrémenté par la première.
"""

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import F

from .models import MouvementStock, SoldeStock, TypeMouvement


class StockInsuffisant(ValidationError):
    """Levée quand une sortie dépasse le disponible et que le découvert est refusé."""


def get_ou_cree_solde(site, produit):
    solde, _ = SoldeStock.objects.get_or_create(site=site, produit=produit)
    return solde


@transaction.atomic
def enregistrer_mouvement(
    *, site, produit, type, quantite, auteur=None, reference_document="", commentaire="",
    autoriser_negatif=False,
):
    """
    Écrit une ligne au journal et met à jour le solde, dans la même transaction.

    `quantite` est signée : positive pour une entrée, négative pour une sortie.
    """
    if quantite == 0:
        raise ValidationError("Un mouvement de stock ne peut pas être de quantité nulle.")

    solde = (
        SoldeStock.objects.select_for_update()
        .filter(site=site, produit=produit)
        .first()
    )
    if solde is None:
        SoldeStock.objects.get_or_create(site=site, produit=produit)
        solde = SoldeStock.objects.select_for_update().get(site=site, produit=produit)

    nouveau = solde.quantite + quantite
    if nouveau < 0 and not autoriser_negatif:
        raise StockInsuffisant(
            f"Stock insuffisant pour {produit.code} à {site.nom} : "
            f"{solde.quantite} en stock, {abs(quantite)} demandés."
        )

    mouvement = MouvementStock.objects.create(
        site=site,
        produit=produit,
        type=type,
        quantite=quantite,
        auteur=auteur,
        reference_document=reference_document,
        commentaire=commentaire,
    )
    SoldeStock.objects.filter(pk=solde.pk).update(quantite=nouveau)
    solde.quantite = nouveau
    return mouvement, solde


@transaction.atomic
def annuler_mouvement(mouvement, *, auteur=None, motif=""):
    """Corrige une erreur par mouvement compensatoire, sans jamais toucher l'original."""
    return enregistrer_mouvement(
        site=mouvement.site,
        produit=mouvement.produit,
        type=TypeMouvement.ANNULATION,
        quantite=-mouvement.quantite,
        auteur=auteur,
        reference_document=mouvement.reference_document,
        commentaire=motif or f"Annulation du mouvement #{mouvement.pk}",
        autoriser_negatif=True,
    )


def references_sous_seuil(sites=None):
    """Références ayant atteint leur stock de sécurité — alimente les alertes (section 7.14)."""
    qs = SoldeStock.objects.select_related("site", "produit").filter(
        quantite__lte=F("stock_securite")
    )
    if sites is not None:
        qs = qs.filter(site__in=sites)
    return qs.order_by("site__nom", "produit__code")


def references_en_rupture(sites=None):
    """Références dont le stock est à zéro."""
    qs = SoldeStock.objects.select_related("site", "produit").filter(quantite=0)
    if sites is not None:
        qs = qs.filter(site__in=sites)
    return qs.order_by("site__nom", "produit__code")


def dates_passage_rupture(site_ids):
    """
    Pour chaque (site_id, produit_id) en rupture, retourne la date du dernier
    franchissement à zéro (cumul passé de positif à ≤ 0).
    Résultat : dict {(site_id, produit_id): datetime}.
    """
    if not site_ids:
        return {}
    ids = list(site_ids)
    with connection.cursor() as cur:
        cur.execute(
            """
            WITH cumuls AS (
                SELECT m.site_id, m.produit_id, m.horodatage,
                       SUM(m.quantite) OVER (
                           PARTITION BY m.site_id, m.produit_id
                           ORDER BY m.horodatage
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                       ) AS cumul
                FROM stock_mouvementstock m
                WHERE m.site_id = ANY(%s)
            ),
            avec_prev AS (
                SELECT site_id, produit_id, horodatage, cumul,
                       LAG(cumul) OVER (
                           PARTITION BY site_id, produit_id
                           ORDER BY horodatage
                       ) AS cumul_prev
                FROM cumuls
            ),
            transitions AS (
                SELECT site_id, produit_id, horodatage
                FROM avec_prev
                WHERE cumul <= 0 AND (cumul_prev IS NULL OR cumul_prev > 0)
            )
            SELECT site_id, produit_id, MAX(horodatage)
            FROM transitions
            GROUP BY site_id, produit_id
            """,
            [ids],
        )
        return {(r[0], r[1]): r[2] for r in cur.fetchall()}


def dates_passage_sous_seuil(site_ids):
    """
    Pour chaque (site_id, produit_id) sous seuil, retourne la date du dernier
    franchissement descendant du seuil de sécurité.
    Résultat : dict {(site_id, produit_id): datetime}.
    """
    if not site_ids:
        return {}
    ids = list(site_ids)
    with connection.cursor() as cur:
        cur.execute(
            """
            WITH cumuls AS (
                SELECT m.site_id, m.produit_id, m.horodatage,
                       SUM(m.quantite) OVER (
                           PARTITION BY m.site_id, m.produit_id
                           ORDER BY m.horodatage
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                       ) AS cumul
                FROM stock_mouvementstock m
                WHERE m.site_id = ANY(%s)
            ),
            avec_prev AS (
                SELECT site_id, produit_id, horodatage, cumul,
                       LAG(cumul) OVER (
                           PARTITION BY site_id, produit_id
                           ORDER BY horodatage
                       ) AS cumul_prev
                FROM cumuls
            ),
            transitions AS (
                SELECT a.site_id, a.produit_id, a.horodatage
                FROM avec_prev a
                JOIN stock_soldestock s
                    ON s.site_id = a.site_id AND s.produit_id = a.produit_id
                WHERE a.cumul <= s.stock_securite
                  AND (a.cumul_prev IS NULL OR a.cumul_prev > s.stock_securite)
            )
            SELECT site_id, produit_id, MAX(horodatage) AS date_passage
            FROM transitions
            GROUP BY site_id, produit_id
            """,
            [ids],
        )
        return {(r[0], r[1]): r[2] for r in cur.fetchall()}


@transaction.atomic
def valider_ajustement(ajustement, *, par):
    """Valide un ajustement : génère les mouvements compensatoires."""
    from stock.models import StatutAjustement

    if ajustement.statut != StatutAjustement.BROUILLON:
        raise ValidationError("Seul un brouillon peut être validé.")
    if not ajustement.lignes.exists():
        raise ValidationError("L'ajustement ne contient aucune ligne.")
    ref = f"AJU-{ajustement.pk}"
    for ligne in ajustement.lignes.select_related("produit").order_by("produit__code"):
        enregistrer_mouvement(
            site=ajustement.site,
            produit=ligne.produit,
            type=TypeMouvement.AJUSTEMENT,
            quantite=ligne.quantite,
            auteur=par,
            reference_document=ref,
            commentaire=ajustement.motif,
            autoriser_negatif=True,
        )
    from django.utils import timezone as tz

    ajustement.statut = StatutAjustement.VALIDE
    ajustement.valide_le = tz.now()
    ajustement.valide_par = par
    ajustement.save(update_fields=["statut", "valide_le", "valide_par"])
    return ajustement
