import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinique.settings')
django.setup()
from consultation.models import ExamenMedical, ResultatExamen, DossierMedical

print("=== EXAMENS ===")
for e in ExamenMedical.objects.all():
    res = list(e.resultatexamen_set.values_list('pk', 'resultat'))
    print(f"Examen #{e.pk}: type={e.type_examen} | patient={e.patient_id} | dossier={e.dossier_id} | consultation={e.consultation_id} | resultats={res}")

print("\n=== RESULTATS ===")
for r in ResultatExamen.objects.all():
    print(f"Resultat #{r.pk}: examen={r.examen_id} | patient={r.patient_id} | dossier={r.dossier_id} | text={r.resultat[:50]}")

print("\n=== DOSSIERS ===")
for d in DossierMedical.objects.all():
    print(f"Dossier #{d.pk} - {d.patient}: examens={d.examens.count()}, examens_ids={list(d.examens.values_list('pk', flat=True))}")
