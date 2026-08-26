# Conventions du projet LEPAD

Fichier lu automatiquement par Claude Code à chaque session. Il évite de
réexpliquer le projet et empêche la dérive de style entre deux sessions.

## Contexte

Application de gestion pour GROUPE LEPAD, distributeur de fournitures scolaires
à Abidjan. Le cahier des charges fonctionnel est le document de référence : les
numéros de section cités dans le code y renvoient. Web uniquement, pas de mobile
natif, pas de mode hors-ligne (écartés par le maître d'ouvrage).

Django 6 · PostgreSQL 16 · gunicorn · Caddy · Docker.

## Règles non négociables

**Le stock ne s'écrase jamais.** `MouvementStock` est en ajout seul : `save()`
sur une ligne existante et `delete()` lèvent une exception, c'est voulu. Toute
correction passe par un mouvement compensatoire. `SoldeStock.quantite` est un
cache ; `recalculer()` doit toujours retomber sur la même valeur, et un test le
vérifie.

**Aucune écriture de stock hors de `stock/services.py`.** Ne jamais appeler
`MouvementStock.objects.create()` ailleurs. Le service est le seul endroit qui
garantit que le mouvement et le solde restent cohérents, sous verrou de ligne.

**Ordre de verrouillage constant : le site d'abord, puis les soldes par code
produit croissant.** Toute nouvelle opération multi-produits doit respecter cet
ordre, sinon interblocage entre deux caissières.

**Les identifiants d'opération viennent du client.** Toute opération
déclenchée depuis un écran porte un `uuid` généré par le navigateur, avec
contrainte d'unicité. C'est ce qui rend un rejeu après timeout inoffensif.

**Cloisonnement systématique.** Toute vue filtre sur
`request.user.sites_autorises()`. Jamais de `Model.objects.all()` dans une vue.

## Style

- Modèles, champs, méthodes et variables en français. Le domaine métier est
  français, le mélange franglais rend le code illisible pour le client.
- Couche service pour toute logique métier ; les vues orchestrent, elles ne
  calculent pas.
- Montants en `DecimalField`, jamais en `float`. Devise : F CFA, sans décimales
  à l'affichage.
- Docstrings expliquant *pourquoi*, pas *quoi*. Citer la section du cahier des
  charges quand la règle en vient.

## Tests

`ventes/tests.py`, `stock/tests.py` et `kits/tests.py` reprennent les critères
de recette de la section 20. Chaque nouveau module ajoute ses critères.
Lancer `python manage.py test` avant tout commit. Ne jamais désactiver un test
pour faire passer une livraison.

## Interface

Identité du cahier d'écolier : encre `--encre`, réglure `--reglure`, filet de
marge `--marge`. Le rouge sert uniquement à signaler une rupture ou un manque,
jamais à décorer. Écrans de saisie pensés pour un pouce sur Android en plein
soleil : cibles tactiles d'au moins 44 px, action principale collée en bas.
Pas de dépendance JavaScript externe.

## Ce qui reste à construire

Achats (workflow de validation à trois niveaux), transferts, inventaires,
dépenses, rapports Excel et PDF, envoi des alertes, non-conformités.
Ordre conseillé : transferts et inventaires d'abord — ils alimentent le stock,
donc les achats en dépendent.

## À ne pas faire

- Modifier des fichiers directement sur le serveur de production.
- Lancer une migration en production sans sauvegarde préalable.
- Committer le fichier `.env`.
- Ajouter une bibliothèque JavaScript sans nécessité démontrée.
