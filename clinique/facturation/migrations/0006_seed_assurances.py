from decimal import Decimal

from django.db import migrations


def seed_assurances(apps, schema_editor):
    """Crée quelques assurances courantes au Mali (modifiables ensuite)."""
    Assurance = apps.get_model('facturation', 'Assurance')
    defaults = [
        ("AMO",              Decimal('70'), "Assurance Maladie Obligatoire (gérée par la CANAM)"),
        ("INPS",             Decimal('70'), "Institut National de Prévoyance Sociale"),
        ("Mutuelle",         Decimal('50'), "Mutuelle de santé"),
        ("Assurance privée", Decimal('80'), "Compagnie d'assurance privée"),
    ]
    for nom, taux, desc in defaults:
        Assurance.objects.get_or_create(
            nom=nom,
            defaults={'taux_prise_en_charge': taux, 'description': desc, 'actif': True},
        )


def unseed_assurances(apps, schema_editor):
    Assurance = apps.get_model('facturation', 'Assurance')
    Assurance.objects.filter(
        nom__in=["AMO", "INPS", "Mutuelle", "Assurance privée"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0005_assurance_facture_taux_prise_en_charge_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_assurances, unseed_assurances),
    ]
