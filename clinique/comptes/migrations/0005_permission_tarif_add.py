"""Sépare « ajouter un tarif » de « gérer les tarifs ».

Jusqu'ici les vues d'ajout/modification/suppression de tarif étaient
verrouillées en dur sur le rôle administrateur (`@role_required('admin')`),
alors qu'une permission `tarif.manage` existait sans être jamais vérifiée.

Cette migration :
  - crée la permission `tarif.add` (ajouter un tarif) ;
  - l'accorde à la réception, qui pouvait consulter les tarifs mais pas
    en créer ;
  - l'accorde aussi à tout rôle possédant déjà `tarif.manage` (dont
    l'administrateur), pour qu'il ne perde rien.

`tarif.manage` couvre désormais la modification et la suppression.
"""

from django.db import migrations

ROLES_BENEFICIAIRES = ['receptionniste']


def ajouter_permission(apps, schema_editor):
    # Sans `using(db)`, une migration de données écrit toujours dans la base
    # « default » — donc dans MySQL même lancée avec `--database sqlite`.
    db = schema_editor.connection.alias
    Permission = apps.get_model('comptes', 'Permission')
    Role = apps.get_model('comptes', 'Role')

    tarif_add, _ = Permission.objects.using(db).get_or_create(
        code='tarif.add', defaults={'libelle': 'Ajouter un tarif'})

    Permission.objects.using(db).filter(code='tarif.manage').update(
        libelle='Gerer les tarifs (modifier, supprimer)')

    # Les rôles qui gèrent déjà les tarifs doivent aussi pouvoir en ajouter.
    codes = set(ROLES_BENEFICIAIRES)
    codes.update(
        Role.objects.using(db).filter(permissions__code='tarif.manage')
        .values_list('code', flat=True)
    )

    for role in Role.objects.using(db).filter(code__in=codes):
        role.permissions.add(tarif_add)


def retirer_permission(apps, schema_editor):
    db = schema_editor.connection.alias
    Permission = apps.get_model('comptes', 'Permission')
    Permission.objects.using(db).filter(code='tarif.add').delete()
    Permission.objects.using(db).filter(code='tarif.manage').update(
        libelle='Gerer les tarifs')


class Migration(migrations.Migration):

    dependencies = [
        ('comptes', '0004_profil_pharmacien_alter_role_code'),
    ]

    operations = [
        migrations.RunPython(ajouter_permission, retirer_permission),
    ]
