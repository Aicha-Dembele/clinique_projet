from django.db import migrations


def vers_rendez_vous(apps, schema_editor):
    """Rattache les factures de consultation existantes à leur rendez-vous.

    La consultation se facture désormais sur le rendez-vous (paiement avant
    d'être reçu). Les factures créées avant ce changement pointent encore sur
    la consultation : on les déplace sur le rendez-vous correspondant pour que
    tout le monde parle du même acte. Le montant ne bouge pas — c'est le même
    tarif, calculé depuis la même spécialité de médecin.
    """
    Facture = apps.get_model('facturation', 'Facture')
    a_migrer = (Facture.objects
                .filter(consultation__isnull=False, rendez_vous__isnull=True)
                .select_related('consultation'))
    for facture in a_migrer:
        facture.rendez_vous_id = facture.consultation.rendez_vous_id
        facture.consultation = None
        facture.save(update_fields=['rendez_vous', 'consultation'])


def retour(apps, schema_editor):
    """Remet les factures sur la consultation du rendez-vous, quand elle existe."""
    Facture = apps.get_model('facturation', 'Facture')
    Consultation = apps.get_model('consultation', 'Consultation')
    consult_par_rdv = dict(
        Consultation.objects.values_list('rendez_vous_id', 'id'))
    for facture in Facture.objects.filter(rendez_vous__isnull=False):
        consultation_id = consult_par_rdv.get(facture.rendez_vous_id)
        if consultation_id:
            facture.consultation_id = consultation_id
            facture.rendez_vous = None
            facture.save(update_fields=['rendez_vous', 'consultation'])


class Migration(migrations.Migration):

    dependencies = [
        ('facturation', '0011_facture_rendez_vous'),
        ('consultation', '0017_backfill_dossier_proprietaire'),
    ]

    operations = [
        migrations.RunPython(vers_rendez_vous, retour),
    ]
