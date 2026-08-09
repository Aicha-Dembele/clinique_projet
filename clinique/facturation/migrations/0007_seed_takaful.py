from decimal import Decimal

from django.db import migrations


def seed_takaful(apps, schema_editor):
    """Garantit AMO à 70 % et ajoute les deux formules Takaful (70 % et 100 %)."""
    Assurance = apps.get_model('facturation', 'Assurance')

    # AMO : créée si absente, taux réaligné à 70 % sinon
    Assurance.objects.update_or_create(
        nom="AMO",
        defaults={
            'taux_prise_en_charge': Decimal('70'),
            'description': "Assurance Maladie Obligatoire (gérée par la CANAM)",
            'actif': True,
        },
    )

    # Takaful : deux formules de prise en charge au choix
    for nom, taux, desc in [
        ("Takaful 70%",  Decimal('70'),  "Assurance Takaful — formule 70 %"),
        ("Takaful 100%", Decimal('100'), "Assurance Takaful — formule 100 % (prise en charge intégrale)"),
    ]:
        Assurance.objects.get_or_create(
            nom=nom,
            defaults={'taux_prise_en_charge': taux, 'description': desc, 'actif': True},
        )


def unseed_takaful(apps, schema_editor):
    Assurance = apps.get_model('facturation', 'Assurance')
    Assurance.objects.filter(nom__in=["Takaful 70%", "Takaful 100%"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0006_seed_assurances'),
    ]

    operations = [
        migrations.RunPython(seed_takaful, unseed_takaful),
    ]
