"""Le pharmacien réclame lui-même aux assurances leur part sur les médicaments.

Marquer une créance « réclamée » ou « remboursée » demandait jusqu'ici
`facture.change` ou `rapport.view`, que le pharmacien n'a pas — et ne doit
pas avoir : la première lui ouvrirait la modification des factures, la
seconde les rapports de toute la clinique.

Cette migration :
  - crée la permission `creance.marquer` ;
  - l'accorde au pharmacien et à l'administrateur.

Elle n'ajoute que cette permission : les autres réglages faits depuis l'écran
« Rôles & permissions » ne sont pas touchés. Ce que chacun peut marquer reste
limité à ce qu'il voit (facturation/regles.py, factures_visibles) : le
pharmacien, les seules ordonnances.
"""

from django.db import migrations

ROLES_BENEFICIAIRES = ['pharmacien', 'admin']


def ajouter_permission(apps, schema_editor):
    # Sans `using(db)`, une migration de données écrit toujours dans la base
    # « default » — donc dans MySQL même lancée avec `--database sqlite`.
    db = schema_editor.connection.alias
    Permission = apps.get_model('comptes', 'Permission')
    Role = apps.get_model('comptes', 'Role')

    permission, _ = Permission.objects.using(db).get_or_create(
        code='creance.marquer',
        defaults={'libelle': 'Marquer les creances assurances (reclamees, remboursees)'})
    for role in Role.objects.using(db).filter(code__in=ROLES_BENEFICIAIRES):
        role.permissions.add(permission)


def retirer_permission(apps, schema_editor):
    db = schema_editor.connection.alias
    Permission = apps.get_model('comptes', 'Permission')
    Permission.objects.using(db).filter(code='creance.marquer').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('comptes', '0005_permission_tarif_add'),
    ]

    operations = [
        migrations.RunPython(ajouter_permission, retirer_permission),
    ]
