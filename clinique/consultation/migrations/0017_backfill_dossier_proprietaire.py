from django.db import migrations


def backfill_proprietaire(apps, schema_editor):
    """Attribue un médecin propriétaire aux dossiers existants (sans propriétaire).

    On retient le premier médecin ayant agi sur le dossier : la consultation la
    plus ancienne, sinon le premier examen, sinon la première hospitalisation."""
    DossierMedical = apps.get_model('consultation', 'DossierMedical')
    Consultation = apps.get_model('consultation', 'Consultation')
    ExamenMedical = apps.get_model('consultation', 'ExamenMedical')
    Hospitalisation = apps.get_model('consultation', 'Hospitalisation')

    for dossier in DossierMedical.objects.filter(medecin__isnull=True):
        medecin_id = None

        consultation = (Consultation.objects
                        .filter(dossier=dossier, rendez_vous__isnull=False)
                        .select_related('rendez_vous')
                        .order_by('date').first())
        if consultation and consultation.rendez_vous_id:
            medecin_id = consultation.rendez_vous.medecin_id

        if not medecin_id:
            examen = (ExamenMedical.objects
                      .filter(dossier=dossier, medecin__isnull=False)
                      .order_by('id').first())
            if examen:
                medecin_id = examen.medecin_id

        if not medecin_id:
            hospit = (Hospitalisation.objects
                      .filter(dossier=dossier)
                      .order_by('id').first())
            if hospit:
                medecin_id = hospit.medecin_id

        if medecin_id:
            dossier.medecin_id = medecin_id
            dossier.save(update_fields=['medecin'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('consultation', '0016_dossiermedical_medecin_dossiermedical_partage_avec'),
    ]

    operations = [
        migrations.RunPython(backfill_proprietaire, noop),
    ]
