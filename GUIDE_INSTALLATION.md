# Guide de mise en ligne — pas à pas

Ce guide part du principe que vous n'avez jamais loué de serveur. Chaque étape
indique ce que vous devez taper, et surtout **ce que vous devez voir** si tout
va bien. Si l'écran ne correspond pas, arrêtez-vous : ne passez pas à l'étape
suivante en espérant que ça se rattrape.

Comptez deux heures pour la première fois, en une seule séance.

**Vocabulaire minimal**

| Mot | Ce que c'est |
|---|---|
| Terminal | La fenêtre noire où l'on tape des commandes. Sur Windows : PowerShell. |
| VPS / serveur | Un ordinateur loué, allumé en permanence, que vous pilotez à distance. |
| SSH | Le moyen de se connecter à ce serveur depuis chez vous. |
| Docker | Un outil qui installe et fait tourner l'application sans rien casser. |
| Dépôt / repo | L'endroit où vit le code (GitHub). C'est lui qui fait référence. |
| Domaine | L'adresse tapée par vos utilisateurs, par exemple gestion.lepad.ci. |

---

# PARTIE A — Sur votre ordinateur

Ne louez rien tant que l'application ne tourne pas chez vous. On ne met pas en
ligne quelque chose qu'on n'a jamais vu fonctionner.

## Étape A1 — Installer Docker Desktop

Docker installe tout ce dont l'application a besoin (Python, PostgreSQL,
serveur web) sans polluer votre machine. C'est le seul outil à installer.

1. Allez sur **docker.com**, section Docker Desktop, et téléchargez la version
   correspondant à votre système.
2. Installez, puis **redémarrez l'ordinateur**. Sous Windows, l'installateur
   peut réclamer d'activer WSL 2 ; acceptez, cela fait partie de l'installation.
3. Lancez Docker Desktop et laissez-le démarrer. Attendez que l'indicateur en
   bas à gauche passe au vert.

**Vérification.** Ouvrez un terminal et tapez :

```bash
docker --version
```

Vous devez voir une ligne du type `Docker version 27.x.x`. Si le terminal
répond « commande introuvable », Docker n'est pas installé ou n'est pas
démarré : reprenez le point 3.

## Étape A2 — Installer Git

Git sert à transporter le code de votre machine vers le serveur.

- **Windows** : téléchargez sur **git-scm.com**, installez en gardant toutes
  les options par défaut.
- **macOS** : tapez `git --version` ; le système propose l'installation.
- **Linux (Ubuntu/Debian)** : `sudo apt install git`

**Vérification.**

```bash
git --version
```

Vous devez voir un numéro de version.

Puis dites à Git qui vous êtes — ces informations apparaîtront dans
l'historique du code :

```bash
git config --global user.name "Votre Nom"
git config --global user.email "votre@email.com"
```

## Étape A3 — Récupérer le projet

Décompressez `lepad.zip` dans un dossier facile à retrouver, par exemple
`C:\Projets\lepad` sous Windows, ou `~/Projets/lepad` sur macOS et Linux.

Ouvrez un terminal **dans ce dossier** :

- **Windows** : ouvrez le dossier dans l'explorateur, tapez `powershell` dans la
  barre d'adresse, puis Entrée.
- **macOS** : clic droit sur le dossier → Services → Nouveau terminal au dossier.
- **Linux** : clic droit dans le dossier → Ouvrir un terminal ici.

**Vérification.** Tapez `dir` (Windows) ou `ls` (macOS/Linux). Vous devez voir
`manage.py`, `Dockerfile`, `README.md` et les dossiers `core`, `ventes`, `stock`.

Si vous ne les voyez pas, vous n'êtes pas dans le bon dossier.

## Étape A4 — Démarrer l'application chez vous

Une seule commande :

```bash
docker compose -f docker-compose.local.yml up --build
```

La première fois, comptez cinq à dix minutes : Docker télécharge PostgreSQL et
Python. Vous verrez défiler beaucoup de texte, c'est normal.

**Vérification.** Vous devez voir apparaître, vers la fin :

```
Chargé : 5 sites, 26 références, 4 kits, 3 utilisateurs.
Starting development server at http://0.0.0.0:8000/
```

Ouvrez alors votre navigateur sur **http://localhost:8000**

Connectez-vous avec `vendeuse` / `lepad2026`. Vous devez arriver sur l'écran de
vente, avec les kits 6e, 5e, 4e et 3e de l'école Mamie Fétaï.

**Essayez une vraie vente** : touchez le kit 6e deux fois, choisissez Espèces,
appuyez sur Encaisser. Vous devez obtenir un reçu numéroté. Retournez sur
l'écran de vente : le nombre disponible a baissé.

**Pour arrêter**, revenez au terminal et faites `Ctrl + C`. Pour redémarrer plus
tard, la même commande sans `--build` suffit et prend dix secondes.

**Si ça bloque**

| Message | Cause | Solution |
|---|---|---|
| `port is already allocated` | Le port 8000 est pris | Fermez l'autre programme, ou changez `8000:8000` en `8001:8000` |
| `Cannot connect to the Docker daemon` | Docker Desktop n'est pas lancé | Lancez-le, attendez le voyant vert |
| `no such file or directory` | Mauvais dossier | Refaites l'étape A3 |

---

# PARTIE B — Mettre le code sur GitHub

Le serveur ne recevra jamais vos fichiers à la main. Il ira les chercher sur
GitHub. C'est ce qui vous permettra plus tard de mettre à jour en une commande.

## Étape B1 — Créer le compte et le dépôt

1. Créez un compte sur **github.com** si vous n'en avez pas.
2. Cliquez sur **New repository**.
3. Nom : `lepad`. Cochez **Private** — le code de votre client n'a rien à faire
   en public.
4. **Ne cochez rien d'autre** : pas de README, pas de .gitignore. Le projet en a
   déjà.
5. Créez. GitHub affiche une page avec une adresse du type
   `https://github.com/votrecompte/lepad.git`. Gardez-la sous la main.

## Étape B2 — Envoyer le code

Dans le terminal, toujours dans le dossier du projet :

```bash
git init
git add .
git commit -m "Version initiale : socle, kits, stock, ventes"
git branch -M main
git remote add origin https://github.com/votrecompte/lepad.git
git push -u origin main
```

GitHub vous demandera de vous authentifier. Suivez la fenêtre qui s'ouvre dans
le navigateur.

**Vérification.** Rechargez la page de votre dépôt sur github.com. Vous devez y
voir tous les fichiers.

**Vérifiez aussi qu'il n'y a pas de fichier `.env`** dans la liste. Il contient
des mots de passe et ne doit jamais être publié. Le `.gitignore` du projet
l'exclut déjà, mais regardez : c'est l'erreur la plus fréquente.

---

# PARTIE C — Louer et préparer le serveur

## Étape C1 — Fabriquer votre clé SSH

Faites-le **avant** de créer le serveur : on vous la demandera pendant la
création.

Une clé SSH remplace le mot de passe pour se connecter au serveur. Elle est
faite de deux fichiers : une partie publique que vous donnez au serveur, et une
partie privée qui ne quitte jamais votre ordinateur.

```bash
ssh-keygen -t ed25519 -C "lepad"
```

Trois questions vous sont posées :
- L'emplacement du fichier : appuyez sur Entrée pour accepter le défaut.
- Une phrase secrète : **mettez-en une** et notez-la dans votre gestionnaire de
  mots de passe. Elle protège la clé si votre ordinateur est volé.
- La confirmation de cette phrase.

Affichez ensuite la partie publique :

```bash
# Windows PowerShell
type $env:USERPROFILE\.ssh\id_ed25519.pub

# macOS / Linux
cat ~/.ssh/id_ed25519.pub
```

Vous obtenez une longue ligne commençant par `ssh-ed25519 AAAA...`.
Copiez-la entièrement, elle servira à l'étape suivante.

**La partie privée — le fichier sans `.pub` — ne se copie jamais, ne s'envoie
jamais, ne se colle nulle part.**

## Étape C2 — Créer le serveur

Cette étape se fait sur le site de l'hébergeur, avec votre carte bancaire.
C'est vous qui la réalisez ; personne d'autre ne doit saisir vos moyens de
paiement à votre place.

Prenez **Hetzner** (hetzner.com) si le prix compte, **OVH** si vous préférez un
support francophone, **DigitalOcean** si vous voulez l'interface la plus simple.

Configuration à choisir :

| Réglage | Valeur | Pourquoi |
|---|---|---|
| Région | Allemagne ou France | 100 à 150 ms vers Abidjan, imperceptible sur le web |
| Image / OS | Ubuntu 24.04 LTS | Version supportée jusqu'en 2029 |
| Type | 2 vCPU, 4 Go RAM, 40 Go disque | Confortable pour 4 magasins et 30 écoles |
| Clé SSH | Collez la ligne de l'étape C1 | Évite les mots de passe |
| Sauvegardes | Activez si proposé (~20 % du prix) | Filet de sécurité en plus des vôtres |

Comptez 5 à 8 € par mois. Après création, l'hébergeur affiche l'**adresse IP**
du serveur, du type `91.107.х.х`. Notez-la.

## Étape C3 — Première connexion

```bash
ssh root@VOTRE_IP
```

À la première connexion, une question apparaît sur l'authenticité de l'hôte :
répondez `yes`. Puis saisissez la phrase secrète de votre clé.

**Vérification.** Votre invite de commande change et ressemble à
`root@lepad-01:~#`. Vous n'êtes plus sur votre ordinateur, vous êtes sur le
serveur. Tout ce que vous taperez maintenant s'exécute là-bas.

## Étape C4 — Mettre à jour et installer Docker

```bash
apt update && apt upgrade -y
apt install -y docker.io docker-compose-plugin git ufw
```

**Vérification.**

```bash
docker --version
docker compose version
```

Les deux doivent répondre un numéro de version.

## Étape C5 — Créer un utilisateur non privilégié

Travailler en permanence en `root` est le meilleur moyen de casser le serveur
d'une faute de frappe.

```bash
adduser lepad
```

Un mot de passe vous est demandé — choisissez-en un long et notez-le. Les
questions suivantes (nom complet, téléphone) peuvent rester vides : Entrée.

```bash
usermod -aG sudo,docker lepad
mkdir -p /home/lepad/.ssh
cp /root/.ssh/authorized_keys /home/lepad/.ssh/
chown -R lepad:lepad /home/lepad/.ssh
chmod 700 /home/lepad/.ssh
chmod 600 /home/lepad/.ssh/authorized_keys
```

**Vérification.** Sans fermer la session actuelle, ouvrez un **second** terminal
sur votre ordinateur et tapez :

```bash
ssh lepad@VOTRE_IP
```

Vous devez arriver sur une invite `lepad@lepad-01:~$`. Gardez impérativement la
première session `root` ouverte tant que celle-ci ne fonctionne pas — c'est
votre porte de secours.

## Étape C6 — Fermer le serveur aux intrus

Toujours dans la session `root` :

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

On n'ouvre que trois portes : la connexion SSH, le web et le web sécurisé.

Puis on interdit la connexion par mot de passe, qui est ce que les robots
tentent en permanence :

```bash
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart ssh
```

**Vérification.** `ufw status` doit lister les trois ports en `ALLOW`. Et votre
seconde session `lepad@` doit toujours répondre.

Vous pouvez maintenant quitter la session `root` : `exit`.

---

# PARTIE D — Le nom de domaine

## Étape D1 — Acheter

Chez **Namecheap**, **Gandi** ou **OVH**, comptez 10 à 15 € par an pour un
`.com`. Le `.ci` passe par le NIC ivoirien : plus cher, plus long, à réserver au
cas où l'image locale compte pour le client.

## Étape D2 — Faire pointer le domaine vers le serveur

Dans l'interface du registrar, cherchez « Zone DNS » ou « Gestion des
enregistrements », et créez :

| Type | Nom | Valeur | TTL |
|---|---|---|---|
| A | `gestion` | VOTRE_IP | 3600 |

Cela crée `gestion.votredomaine.com`. Si vous voulez utiliser le domaine nu,
mettez `@` à la place de `gestion`.

## Étape D3 — Attendre et vérifier

La propagation prend de quelques minutes à quelques heures.

```bash
nslookup gestion.votredomaine.com
```

La réponse doit contenir votre adresse IP. **Ne passez pas à la partie E tant
que ce n'est pas le cas** : Caddy ne pourra pas obtenir le certificat HTTPS.

---

# PARTIE E — Installer l'application sur le serveur

Connectez-vous en tant que `lepad` :

```bash
ssh lepad@VOTRE_IP
```

## Étape E1 — Autoriser le serveur à lire votre dépôt privé

Le serveur a besoin de sa propre clé pour accéder à GitHub.

```bash
ssh-keygen -t ed25519 -C "serveur-lepad"
```

Acceptez le défaut, et cette fois **laissez la phrase secrète vide** (Entrée
deux fois) : le serveur doit pouvoir se connecter sans intervention humaine.

```bash
cat ~/.ssh/id_ed25519.pub
```

Copiez la ligne affichée. Sur GitHub : votre dépôt → **Settings** → **Deploy
keys** → **Add deploy key**. Titre : `serveur production`. Collez la clé.
Laissez « Allow write access » décoché — le serveur n'a besoin que de lire.

**Vérification.**

```bash
ssh -T git@github.com
```

Vous devez lire un message de bienvenue mentionnant votre nom d'utilisateur.

## Étape E2 — Récupérer le code

```bash
sudo mkdir -p /opt/lepad
sudo chown lepad:lepad /opt/lepad
git clone git@github.com:votrecompte/lepad.git /opt/lepad
cd /opt/lepad
```

**Vérification.** `ls` doit afficher `manage.py`, `Dockerfile`, `README.md`.

## Étape E3 — Configurer

Fabriquez une clé secrète — elle protège les sessions et les mots de passe :

```bash
docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copiez la longue chaîne obtenue, puis :

```bash
cp .env.example .env
nano .env
```

`nano` est un éditeur de texte dans le terminal. Modifiez ainsi :

```
DEBUG=False
SECRET_KEY=collez_ici_la_chaine_generee
ALLOWED_HOSTS=gestion.votredomaine.com
CSRF_TRUSTED_ORIGINS=https://gestion.votredomaine.com

DB_NAME=lepad
DB_USER=lepad
DB_PASSWORD=inventez_un_mot_de_passe_long_et_notez_le
DB_HOST=base
DB_PORT=5432
```

Pour enregistrer et quitter nano : `Ctrl + O`, Entrée, puis `Ctrl + X`.

Puis le domaine dans la configuration du serveur web :

```bash
nano Caddyfile
```

Remplacez `gestion.lepad.ci` par votre domaine réel. Une seule ligne à changer.
Enregistrez de la même façon.

## Étape E4 — Démarrer

```bash
docker compose up -d --build
```

Cinq à dix minutes la première fois. Le `-d` signifie que l'application tourne
en arrière-plan : elle continuera même après votre déconnexion.

**Vérification.**

```bash
docker compose ps
```

Les trois services `base`, `web` et `proxy` doivent être `Up`. Si `web` est en
`Restarting`, lisez la cause :

```bash
docker compose logs web --tail 50
```

## Étape E5 — Créer votre compte administrateur

```bash
docker compose exec web python manage.py createsuperuser
```

Choisissez un identifiant, une adresse e-mail et un mot de passe long. C'est
votre accès de secours : notez-le dans un gestionnaire de mots de passe.

## Étape E6 — Charger le référentiel

```bash
docker compose exec web python manage.py donnees_demarrage
```

Cela crée les 4 magasins, les 26 références et les kits de Mamie Fétaï.

## Étape E7 — Ouvrir le site

Rendez-vous sur **https://gestion.votredomaine.com**

Le certificat HTTPS est obtenu automatiquement au premier accès : le cadenas
doit apparaître dans la barre d'adresse. Si le navigateur affiche une erreur de
certificat, c'est que le DNS n'était pas encore propagé à l'étape D3.

**Vérification finale, à faire réellement :**

1. Connectez-vous avec votre compte administrateur.
2. Allez sur **Paramétrage**, ouvrez les kits, vérifiez que les compositions
   s'affichent avec coût de revient et marge.
3. Connectez-vous en navigation privée avec `vendeuse` / `lepad2026`,
   enregistrez une vente, vérifiez le reçu.
4. Sur **Livraisons**, la vente doit apparaître dans la file. Cliquez sur
   « Remis au client ».
5. Sur **Pilotage**, le chiffre d'affaires du jour doit refléter cette vente.

## Étape E8 — Supprimer les comptes de démonstration

Ne sautez pas cette étape. Les mots de passe des comptes de démonstration sont
écrits dans le code, donc publics.

Dans **Paramétrage** → Utilisateurs, supprimez `dg`, `superviseur` et
`vendeuse`, puis créez les vrais comptes de l'équipe avec le bon profil et le
bon rattachement (une école pour une commerciale, un magasin pour un
gestionnaire).

**Vérification.**

```bash
docker compose exec web python manage.py check --deploy
```

Doit répondre `System check identified no issues`.

---

# PARTIE F — Sauvegardes

Un serveur se perd. Une base de données perdue, c'est l'activité de l'année.

## Étape F1 — Programmer la sauvegarde quotidienne

```bash
cd /opt/lepad
chmod +x sauvegardes/sauvegarde.sh deploiement/deployer.sh
crontab -e
```

Choisissez `nano` si l'éditeur vous est demandé. Ajoutez en fin de fichier :

```
15 2 * * * cd /opt/lepad && ./sauvegardes/sauvegarde.sh >> /var/log/lepad-sauvegarde.log 2>&1
```

Une sauvegarde compressée sera produite chaque nuit à 2 h 15, avec purge
automatique au-delà de 30 jours.

## Étape F2 — Vérifier tout de suite

```bash
./sauvegardes/sauvegarde.sh
ls -lh sauvegardes/
```

Vous devez voir un fichier `lepad_AAAA-MM-JJ_HHMM.sql.gz` de taille non nulle.

## Étape F3 — Sortir les sauvegardes du serveur

Une sauvegarde stockée sur la machine sauvegardée ne protège de rien. Louez un
espace de stockage (Hetzner Storage Box, Backblaze B2 : 3 à 4 € par mois),
installez `rclone`, configurez-le, puis décommentez la dernière ligne de
`sauvegardes/sauvegarde.sh`.

## Étape F4 — Tester la restauration

À faire **maintenant**, pas le jour de l'incident. Sur un serveur de test ou en
local :

```bash
gunzip -c sauvegardes/lepad_2026-07-29_0215.sql.gz | \
  docker compose exec -T base psql -U lepad -d lepad
```

Une sauvegarde jamais restaurée n'est pas une sauvegarde, c'est une supposition.

---

# PARTIE G — Vie quotidienne

## Ajouter une fonctionnalité

Le cycle est toujours le même, et **jamais l'inverse** :

```
Votre ordinateur          GitHub              Serveur
─────────────────         ──────              ───────
1. modifier le code
2. lancer les tests
3. git push          →    reçoit
                                        →    4. ./deploiement/deployer.sh
```

Sur votre machine :

```bash
docker compose -f docker-compose.local.yml exec web python manage.py test
git add .
git commit -m "Ajout du module transferts"
git push
```

Sur le serveur :

```bash
cd /opt/lepad && ./deploiement/deployer.sh
```

Le script sauvegarde la base, récupère le code, reconstruit et vérifie la
configuration.

## Commandes utiles sur le serveur

| Besoin | Commande |
|---|---|
| Voir si tout tourne | `docker compose ps` |
| Lire les erreurs | `docker compose logs web --tail 100` |
| Suivre en direct | `docker compose logs -f web` |
| Redémarrer | `docker compose restart web` |
| Espace disque restant | `df -h` |
| Ouvrir la base | `docker compose exec base psql -U lepad -d lepad` |

## Ce qu'il ne faut jamais faire

- **Modifier un fichier directement sur le serveur.** La prochaine mise à jour
  l'écrasera sans prévenir. Toute modification passe par votre machine et Git.
- **Migrer sans sauvegarder.** Utilisez `deployer.sh`, il s'en charge.
- **Committer le fichier `.env`.** Il contient les mots de passe.
- **Travailler en `root`.** Utilisez le compte `lepad`.
- **Laisser les comptes de démonstration actifs.**
- **Reporter le test de restauration.**

---

# En cas de problème

| Symptôme | Cause probable | Que faire |
|---|---|---|
| Le site ne répond pas | Conteneurs arrêtés | `docker compose ps` puis `docker compose up -d` |
| Erreur de certificat HTTPS | DNS pas encore propagé | Vérifier `nslookup`, attendre, `docker compose restart proxy` |
| `DisallowedHost` | Domaine absent de la configuration | Ajouter le domaine dans `ALLOWED_HOSTS` du `.env`, redémarrer |
| Erreur 500 après mise à jour | Migration non appliquée | `docker compose exec web python manage.py migrate` |
| `web` redémarre en boucle | Erreur de configuration | `docker compose logs web --tail 50` et lire la dernière erreur |
| Connexion SSH refusée | Pare-feu ou clé | Utiliser la console de secours de l'hébergeur |
| Disque plein | Images Docker accumulées | `docker system prune -a` puis `df -h` |

Quand vous demandez de l'aide, apportez toujours la sortie complète de
`docker compose logs web --tail 50`. Le message d'erreur exact vaut mieux que
toute description.

---

# Récapitulatif des coûts

| Poste | Coût mensuel |
|---|---|
| Serveur (2 vCPU, 4 Go) | 5 à 8 € |
| Sauvegardes hébergeur | 1 à 2 € |
| Stockage des sauvegardes hors serveur | 3 à 4 € |
| Nom de domaine | ~1 € (12 à 15 € par an) |
| **Total** | **10 à 15 € par mois** |
