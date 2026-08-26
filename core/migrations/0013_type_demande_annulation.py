from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_alter_notification_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="type",
            field=__import__("django.db.models", fromlist=["CharField"]).CharField(
                choices=[
                    ("RUPTURE_STOCK", "Rupture de stock"),
                    ("DEMANDE_SOUMISE", "Demande d'achat soumise"),
                    ("DEMANDE_VALIDEE", "Demande d'achat validée"),
                    ("DEMANDE_REJETEE", "Demande d'achat rejetée"),
                    ("DEPENSE_SOUMISE", "Dépense soumise"),
                    ("DEPENSE_VALIDEE", "Dépense validée"),
                    ("TRANSFERT_RECU", "Transfert reçu"),
                    ("TRANSFERT_ACCEPTE", "Transfert accepté"),
                    ("TRANSFERT_REJETE", "Transfert rejeté"),
                    ("TRANSFERT_VALIDE", "Transfert validé"),
                    ("INVENTAIRE_VALIDE", "Inventaire validé"),
                    ("VENTE_ANNULEE", "Vente annulée"),
                    ("DEMANDE_ANNULATION", "Demande d'annulation de vente"),
                    ("LIVRAISON_PRETE", "Livraison prête à réceptionner"),
                    ("LIVRAISON_CONFIRMEE", "Livraison confirmée"),
                    ("LIVRAISON_REFUSEE", "Livraison refusée"),
                    ("INFO", "Information"),
                    ("NON_CONFORMITE", "Non-conformité signalée"),
                ],
                max_length=20,
            ),
        ),
    ]
