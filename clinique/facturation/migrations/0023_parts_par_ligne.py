"""Chaque ligne de facture enregistre sa part assurance et sa part patient.

Sur une ordonnance, l'AMO se calcule médicament par médicament, puis on additionne.
Les lignes déjà en base reçoivent ici leurs parts, et leur facture la somme : ce sont
ces montants que la pharmacie réclame à l'assurance à la fin du mois.
"""
from decimal import Decimal

from django.db import migrations, models


def partager_les_lignes_existantes(apps, schema_editor):
    alias = schema_editor.connection.alias
    Facture = apps.get_model('facturation', 'Facture')
    LigneFacture = apps.get_model('facturation', 'LigneFacture')

    for facture in Facture.objects.using(alias).prefetch_related('lignes'):
        lignes = list(facture.lignes.all())
        if not lignes:
            # Rien à additionner : montant_assurance reste vide, et la facture
            # garde son ancien calcul.
            continue
        taux = facture.taux_prise_en_charge or Decimal('0')
        for ligne in lignes:
            sous_total = ligne.prix_unitaire * ligne.quantite
            if ligne.rembourse and taux > 0:
                ligne.part_assurance = (sous_total * taux / Decimal('100')).quantize(Decimal('1'))
            else:
                ligne.part_assurance = Decimal('0')
            ligne.part_patient = sous_total - ligne.part_assurance
        LigneFacture.objects.using(alias).bulk_update(lignes, ['part_assurance', 'part_patient'])
        Facture.objects.using(alias).filter(pk=facture.pk).update(
            montant_assurance=sum((l.part_assurance for l in lignes), Decimal('0')))


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0022_retirer_takaful'),
    ]

    operations = [
        migrations.AddField(
            model_name='facture',
            name='montant_assurance',
            field=models.DecimalField(blank=True, decimal_places=2, default=None, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='lignefacture',
            name='part_assurance',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="part de l'assurance"),
        ),
        migrations.AddField(
            model_name='lignefacture',
            name='part_patient',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='part du patient'),
        ),
        migrations.RunPython(partager_les_lignes_existantes, migrations.RunPython.noop),
    ]
