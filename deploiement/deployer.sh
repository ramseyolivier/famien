#!/bin/sh
# Déploiement en production. À lancer depuis /opt/lepad sur le serveur.
# Sauvegarde d'abord, migre ensuite : dans cet ordre, jamais l'inverse.
set -eu
cd "$(dirname "$0")/.."

echo "→ Sauvegarde avant migration"
./deploiement/sauvegarde.sh

echo "→ Récupération du code"
git pull --ff-only

echo "→ Reconstruction et redémarrage"
docker compose up -d --build

echo "→ Vérification de la configuration"
docker compose exec -T web python manage.py check --deploy

echo "→ Déploiement terminé"
docker compose ps
