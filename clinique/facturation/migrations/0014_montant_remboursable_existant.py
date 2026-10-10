"""Initialise la part remboursable des factures deja en base.

Jusqu'ici l'assurance s'appliquait sur la TOTALITE de chaque facture. Le
nouveau champ `montant_remboursable` vaut 0 par defaut : sans cette
migration, toutes les factures existantes verraient leur part assurance
tomber a zero, et leur reste a charge exploser.

On recopie donc le total : c'est exactement ce qui etait pris en charge
jusqu'a aujourd'hui. Les medicaments non rembourses ne commenceront a sortir
de l'assiette qu'a partir des prochaines facturations.
"""

from django.db import migrations, models


def recopier_le_total(apps, schema_editor):
    Facture = apps.get_model('facturation', 'Facture')
    (Facture.objects.using(schema_editor.connection.alias)
            .update(montant_remboursable=models.F('montant_total')))


def remettre_a_zero(apps, schema_editor):
    Facture = apps.get_model('facturation', 'Facture')
    (Facture.objects.using(schema_editor.connection.alias)
            .update(montant_remboursable=0))


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0013_facture_montant_remboursable_lignefacture_rembourse'),
    ]

    operations = [
        migrations.RunPython(recopier_le_total, remettre_a_zero),
    ]
