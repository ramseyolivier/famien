#!/bin/sh
# Sauvegarde quotidienne. Rétention 30 jours glissants (section 11 du cahier des charges).
# Installation : chmod +x deploiement/sauvegarde.sh
#                crontab -e  →  15 2 * * * /opt/famien/deploiement/sauvegarde.sh
set -eu
cd "$(dirname "$0")/.."
HORODATAGE=$(date +%Y-%m-%d_%H%M)
FICHIER="sauvegardes/famien_${HORODATAGE}.sql.gz"

docker compose exec -T base pg_dump -U "${DB_USER:-famien}" "${DB_NAME:-famien}" | gzip > "$FICHIER"
echo "Sauvegarde écrite : $FICHIER"

find sauvegardes -name 'famien_*.sql.gz' -mtime +30 -delete

# Copie hors du serveur : sans cette ligne, un disque perdu emporte les sauvegardes.
# rclone copy "$FICHIER" distant:famien-sauvegardes/
