"""
Données de démarrage production.

Le réseau de sites, le référentiel produit, les marques, les catégories
et les comptes utilisateurs sont saisis directement dans l'interface
d'administration.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Commande de démarrage (sans effet — données saisies via l'admin)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Rien à charger."))
