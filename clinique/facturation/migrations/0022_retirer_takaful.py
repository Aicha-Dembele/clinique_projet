from django.db import migrations


def retirer_takaful(apps, schema_editor):
    """La clinique ne travaille plus qu'avec l'AMO.

    Les patients quittent Takaful (et son numéro d'assuré, qui ne vaudrait pas
    pour une autre assurance). Une formule déjà portée par des factures n'est pas
    supprimée, car les factures perdraient leur prise en charge et les patients
    devraient la totalité : elle devient inactive, donc impossible à choisir.
    """
    db = schema_editor.connection.alias
    Assurance = apps.get_model('facturation', 'Assurance')
    Facture = apps.get_model('facturation', 'Facture')
    Patient = apps.get_model('patients', 'Patient')

    formules = list(Assurance.objects.using(db).filter(nom__startswith='Takaful'))
    (Patient.objects.using(db)
     .filter(assurance__in=[f.pk for f in formules])
     .update(assurance=None, numero_assure=''))
    for formule in formules:
        if Facture.objects.using(db).filter(assurance=formule).exists():
            formule.actif = False
            formule.save(using=db, update_fields=['actif'])
        else:
            formule.delete(using=db)


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0021_cloturecaisse_paiement_cloture'),
        ('patients', '0006_patient_identite_provisoire'),
    ]

    operations = [
        # Pas de retour en arrière : on ne saurait plus quels patients avaient Takaful.
        migrations.RunPython(retirer_takaful, migrations.RunPython.noop),
    ]
