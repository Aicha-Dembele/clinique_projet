"""Cree un « lot initial » pour tout medicament qui a deja du stock.

Sans cela, le jour de la mise en service, aucun medicament n'aurait de lot :
la somme des lots vaudrait zero alors que le stock compte des centaines de
boites, et la premiere dispensation ne trouverait rien a decrementer.

On fabrique donc un lot par medicament en stock, qui reprend telle quelle sa
quantite et sa date de peremption actuelles. C'est fidele : jusqu'ici, tout
le stock d'un medicament partageait bien une seule date.
"""

from django.db import migrations


def creer_les_lots_initiaux(apps, schema_editor):
    Medicament = apps.get_model('pharmacie', 'Medicament')
    Lot = apps.get_model('pharmacie', 'Lot')
    base = schema_editor.connection.alias

    lots = [
        Lot(
            medicament=medicament,
            numero='LOT-INITIAL',
            date_peremption=medicament.date_peremption,
            quantite_initiale=medicament.quantite_stock,
            quantite_restante=medicament.quantite_stock,
            prix_achat=medicament.prix_unitaire or 0,
        )
        for medicament in Medicament.objects.using(base).filter(quantite_stock__gt=0)
    ]
    Lot.objects.using(base).bulk_create(lots)


def supprimer_les_lots_initiaux(apps, schema_editor):
    Lot = apps.get_model('pharmacie', 'Lot')
    (Lot.objects.using(schema_editor.connection.alias)
        .filter(numero='LOT-INITIAL').delete())


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacie', '0012_fournisseur_lot_sortielot'),
    ]

    operations = [
        migrations.RunPython(creer_les_lots_initiaux, supprimer_les_lots_initiaux),
    ]
