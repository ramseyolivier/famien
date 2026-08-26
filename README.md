# LEPAD — gestion des stocks et des ventes

Application web de gestion pour GROUPE LEPAD : référentiel produit, kits scolaires
par établissement, stock par site, vente au stand et file de livraison.

Django 6 · PostgreSQL 16 · déploiement Docker.

---

## Ce qui est construit

| Module du cahier des charges | État |
|---|---|
| 1 · Utilisateurs et droits d'accès | Fait — 6 profils, cloisonnement par zone et par site |
| 2 · Fournisseurs | Fait (administration) |
| 4 · Magasins | Fait (administration) |
| 5 · Écoles | Fait (administration) |
| 6 · Kits scolaires | Fait — composition, coût de revient, règle de prix, versionnage |
| 7 · Stocks | Fait — journal immuable, solde dérivé, seuils |
| 8 · Ventes | Fait — écran de vente, livraison partielle, reçu, annulation |
| 12 · Tableaux de bord | Partiel — indicateurs du jour, CA par école, alertes de seuil |
| 3 · Achats | À faire — workflow de validation à trois niveaux |
| 9 · Transferts | À faire |
| 10 · Inventaires | À faire |
| 11 · Dépenses | À faire |
| 13 · Rapports Excel / PDF | À faire |
| 14 · Alertes push et e-mail | À faire — la détection existe, pas l'envoi |
| 15 · Non-conformités | À faire |

Le module 17 (hors-ligne) est écarté par décision du maître d'ouvrage.
Voir « Points à trancher avec le client » plus bas.

---

## Trois décisions de conception

**Le stock est un journal, pas un nombre.** `MouvementStock` est en ajout seul :
aucun `UPDATE`, aucun `DELETE`, la classe lève une exception si on essaie. La
quantité en stock est la somme des mouvements ; `SoldeStock.quantite` n'est
qu'un cache, recalculable à tout instant par `solde.recalculer()`. C'est ce
qu'impose la section 10 du cahier des charges, et c'est ce qui permet de
répondre trois mois plus tard à la question « pourquoi ce stock est faux ».
Toute correction passe par un mouvement compensatoire tracé.

**L'identifiant de vente est généré par le navigateur.** Sur un réseau
instable, une requête qui expire côté client a pu aboutir côté serveur. La
vendeuse voit une erreur et retape la vente. La contrainte d'unicité sur
`Vente.uuid` rend le réenregistrement inoffensif : le serveur renvoie la vente
déjà créée au lieu d'en créer une seconde.

**Magasins et écoles sont une seule table.** Le MCD du cahier des charges les
sépare, mais fait porter à `MOUVEMENT_STOCK`, `TRANSFERT` et `INVENTAIRE` un
champ « site_id (magasin ou école) » que la base ne peut pas contraindre. Un
seul modèle `Site` avec un discriminant `type` rend toutes ces clés étrangères
vérifiables.

---

## Installation en local

```bash
git clone <votre-dépôt> lepad && cd lepad
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# PostgreSQL doit tourner et la base exister
createdb lepad

cp .env.example .env        # puis DEBUG=True, DB_HOST=localhost
python manage.py migrate
python manage.py donnees_demarrage
python manage.py runserver
```

`donnees_demarrage` charge le réseau réel (4 magasins, école Mamie Fétaï), les
26 références de l'annexe A, les kits 6e à 3e du tableau 8, et trois comptes de
démonstration — `dg`, `superviseur`, `vendeuse`, mot de passe `lepad2026`.
**Supprimez ces comptes avant la mise en production.**

Les tests reprennent les critères de recette de la section 20 :

```bash
python manage.py test
```

---

## Mise en ligne

### Ce qu'il faut

Un VPS à 1 vCPU / 2 Go suffit largement pour 4 magasins et 30 écoles. Hetzner,
OVH, Scaleway, DigitalOcean : comptez 5 à 10 € par mois. Prenez une région
européenne : la latence vers Abidjan tourne autour de 100 à 150 ms, ce qui est
sans effet perceptible sur une application web, et c'est moins cher qu'un
hébergeur local.

Un nom de domaine pointant vers l'IP du serveur, enregistrement `A`.

### Les étapes

```bash
# 1. Sur le serveur, en root
apt update && apt install -y docker.io docker-compose-plugin git
adduser lepad && usermod -aG docker lepad

# 2. En tant que lepad
git clone <votre-dépôt> /opt/lepad && cd /opt/lepad

# 3. Configurer
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # SECRET_KEY
nano .env                    # SECRET_KEY, DB_PASSWORD, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS
nano Caddyfile               # remplacer gestion.lepad.ci par votre domaine

# 4. Démarrer — les migrations s'appliquent seules
docker compose up -d --build

# 5. Créer le premier administrateur
docker compose exec web python manage.py createsuperuser

# 6. Charger le référentiel de départ
docker compose exec web python manage.py donnees_demarrage
```

C'est tout. Caddy obtient le certificat Let's Encrypt automatiquement au premier
accès et le renouvelle seul. Le site répond en HTTPS sur votre domaine.

### Vérifier avant de livrer

```bash
docker compose exec web python manage.py check --deploy
```

Aucun avertissement ne doit rester. `DEBUG=False` active automatiquement HSTS,
la redirection HTTPS et les cookies sécurisés.

### Mettre à jour

```bash
cd /opt/lepad && ./deploiement/deployer.sh
```

Le script sauvegarde, récupère le code, reconstruit et vérifie. Il ne migre
jamais sans avoir sauvegardé d'abord.

### Sauvegardes

Le script `sauvegardes/sauvegarde.sh` produit un dump compressé et purge au-delà
de 30 jours, conformément à la section 11.

```bash
chmod +x sauvegardes/sauvegarde.sh
crontab -e
# 15 2 * * * /opt/lepad/sauvegardes/sauvegarde.sh >> /var/log/lepad-sauvegarde.log 2>&1
```

Décommentez la ligne `rclone` du script pour copier hors du serveur. Une
sauvegarde qui reste sur la machine sauvegardée ne protège de rien.

**Testez la restauration avant la mise en production**, pas après l'incident :

```bash
gunzip -c sauvegardes/lepad_2026-07-29_0215.sql.gz | \
  docker compose exec -T base psql -U lepad -d lepad
```

---

## Points à trancher avec le client

**Le tableau 8 ne tombe pas juste.** Les compositions de kits données pour
Mamie Fétaï annoncent 14, 15 et 16 cahiers, alors que le détail des références
en totalise systématiquement un de moins. L'écart est constant sur les quatre
niveaux, ce qui suggère une référence oubliée à la transcription plutôt qu'une
erreur de calcul. Le fichier `core/management/commands/donnees_demarrage.py`
reprend le détail écrit ; à corriger dès que la table réelle est fournie.

**Les prix d'achat et de détail sont absents du cahier des charges.** Ceux du
jeu de démarrage sont des valeurs de travail, cohérentes entre elles mais
inventées. Le coût de revient et la marge affichés ne veulent rien dire tant
que les tarifs réels ne sont pas saisis.

**Le mobile et le hors-ligne restent au contrat.** Le livrable n°5 (section 19)
exige une application Android et le critère de recette n°8 (section 20) exige
la saisie hors réseau. Les deux sont écartés du présent périmètre. Faites-le
acter par écrit avant la recette, sinon le client peut refuser la livraison en
s'appuyant sur son propre document.

**Prévoyez un repli papier.** Sans mode hors-ligne, une coupure réseau arrête
la vente. Un carnet de reçus en réserve sur chaque stand et un écran de saisie
a posteriori coûtent deux jours et évitent une matinée de rentrée bloquée.

**Renvois erronés dans le cahier des charges.** La numérotation des
sous-sections décroche en sections 12, 14, 16 et 18 ; la numérotation des
tableaux saute du 12 au 19 ; les critères de recette renvoient à la « section
14 » pour la matrice de droits, qui est en section 15. À signaler au client.
