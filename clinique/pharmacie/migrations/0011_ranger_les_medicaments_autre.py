"""Range les medicaments qui attendaient dans « Autre ».

Ils y etaient faute de categorie adequate : il n'existait ni antifongique
ni neurologie/psychiatrie. Maintenant que ces categories existent, on les
remet a leur place, d'apres leur DCI.

Seuls les medicaments ENCORE en « Autre » sont touches : si le pharmacien
en a deja reclasse un a la main, son choix est respecte.
"""

from django.db import migrations

# DCI -> categorie. On travaille sur la DCI et non sur le nom commercial :
# c'est elle qui identifie la molecule.
RANGEMENT = {
    'Amitriptyline':  'neuro_psy',    # antidepresseur, douleurs neuropathiques
    'Carbamazepine':  'neuro_psy',    # antiepileptique
    'Carbamazépine':  'neuro_psy',
    'Levetiracetam':  'neuro_psy',    # antiepileptique
    'Lévétiracétam':  'neuro_psy',
    'Sumatriptan':    'neuro_psy',    # antimigraineux
    'Fluconazole':    'antifongique', # mycoses
}


def ranger(apps, schema_editor):
    Medicament = apps.get_model('pharmacie', 'Medicament')
    base = Medicament.objects.using(schema_editor.connection.alias)
    for dci, categorie in RANGEMENT.items():
        base.filter(categorie__in=['', 'autre'], dci=dci).update(categorie=categorie)


def remettre_en_autre(apps, schema_editor):
    Medicament = apps.get_model('pharmacie', 'Medicament')
    base = Medicament.objects.using(schema_editor.connection.alias)
    base.filter(dci__in=list(RANGEMENT)).update(categorie='autre')


class Migration(migrations.Migration):

    dependencies = [
        ('pharmacie', '0010_alter_medicament_categorie'),
    ]

    operations = [
        migrations.RunPython(ranger, remettre_en_autre),
    ]
