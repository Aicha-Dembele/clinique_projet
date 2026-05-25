from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .models import (
    Rendez_vous,
    DossierMedical,
    Consultation,
    ExamenMedical,
    Ordonnance,
    Hospitalisation,
    Traitement,
)
from patients.models import Patient
from personnel.models import Medecin, Laborantin

# ── Rendez-vous ──────────────────────────────────────────

@login_required
def rdv_liste(request):
    rdvs = Rendez_vous.objects.all().order_by('-date')
    return render(request, 'consultation/rdv_liste.html', {
        'rdvs': rdvs,
        'rdv_termines': rdvs.filter(statut='termine').count(),
        'rdv_en_cours': rdvs.filter(statut='en_cours').count(),
        'rdv_programmes': rdvs.filter(statut='programme').count(),
        'rdv_annules_count': rdvs.filter(statut='annule').count(),
    })

@login_required
def rdv_ajouter(request):
    if request.method == 'POST':
        try:
            Rendez_vous.objects.create(
                patient_id=request.POST['patient'],
                medecin_id=request.POST['medecin'],
                date=request.POST['date'],
                statut=request.POST.get('statut', 'programme'),
            )
            messages.success(request, 'Rendez-vous créé.')
            return redirect('consultation:rdv_liste')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/rdv_form.html', {
        'patients': Patient.objects.all().order_by('nom'),
        'medecins': Medecin.objects.all().order_by('nom'),
        'action': 'Ajouter',
    })

@login_required
def rdv_modifier(request, pk):
    rdv = get_object_or_404(Rendez_vous, pk=pk)
    if request.method == 'POST':
        try:
            rdv.patient_id = request.POST['patient']
            rdv.medecin_id = request.POST['medecin']
            rdv.date = request.POST['date']
            rdv.statut = request.POST.get('statut', rdv.statut)
            rdv.save()
            messages.success(request, 'Rendez-vous modifié.')
            return redirect('consultation:rdv_liste')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/rdv_form.html', {
        'rdv': rdv,
        'patients': Patient.objects.all().order_by('nom'),
        'medecins': Medecin.objects.all().order_by('nom'),
        'action': 'Modifier',
    })

@login_required
def rdv_supprimer(request, pk):
    rdv = get_object_or_404(Rendez_vous, pk=pk)
    if request.method == 'POST':
        rdv.delete()
        messages.success(request, 'Rendez-vous supprimé.')
        return redirect('consultation:rdv_liste')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'RDV de {rdv.patient} avec Dr. {rdv.medecin}',
        'retour_url': '/consultation/rdv/',
    })

# ── Dossiers médicaux ────────────────────────────────────

@login_required
def dossiers(request):
    return render(request, 'consultation/dossiers.html', {
        'dossiers': DossierMedical.objects.all().order_by('-date_creation'),
    })

@login_required
def dossier_detail(request, pk):
    dossier = get_object_or_404(DossierMedical, pk=pk)
    return render(request, 'consultation/dossier_detail.html', {'dossier': dossier})

# ── Consultations ────────────────────────────────────────

@login_required
def consultation_liste(request):
    return render(request, 'consultation/liste.html', {
        'consultations': Consultation.objects.all().order_by('-date'),
    })

@login_required
def consultation_ajouter(request):
    if request.method == 'POST':
        try:
            Consultation.objects.create(
                rendez_vous_id=request.POST['rendez_vous'],
                motif=request.POST['motif'],
                diagnostic=request.POST.get('diagnostic', ''),
                observation=request.POST.get('observation', ''),
            )
            messages.success(request, 'Consultation enregistrée.')
            return redirect('consultation:liste')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/form_consultation.html', {
        'rdvs': Rendez_vous.objects.filter(statut='programme').order_by('-date'),
        'action': 'Ajouter',
    })

@login_required
def consultation_detail(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    return render(request, 'consultation/detail_consultation.html', {'consultation': consultation})

@login_required
def consultation_modifier(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    if request.method == 'POST':
        consultation.motif = request.POST['motif']
        consultation.diagnostic = request.POST.get('diagnostic', '')
        consultation.observation = request.POST.get('observation', '')
        consultation.save()
        messages.success(request, 'Consultation modifiée.')
        return redirect('consultation:detail', pk=consultation.pk)

    return render(request, 'consultation/form_consultation.html', {
        'consultation': consultation,
        'rdvs': Rendez_vous.objects.all().order_by('-date'),
        'action': 'Modifier',
    })

@login_required
def consultation_supprimer(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    if request.method == 'POST':
        consultation.delete()
        messages.success(request, 'Consultation supprimée.')
        return redirect('consultation:liste')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Consultation #{pk}',
        'retour_url': '/consultation/',
    })

# ── Examens ──────────────────────────────────────────────

@login_required
def examens(request):
    qs = ExamenMedical.objects.all().order_by('-id')
    return render(request, 'consultation/examens.html', {
        'examens': qs,
        'examens_attente_count': qs.filter(statut='en_attente').count(),
        'examens_cours_count': qs.filter(statut='en_cours').count(),
        'examens_termines_count': qs.filter(statut='termine').count(),
    })

@login_required
def examen_ajouter(request):
    if request.method == 'POST':
        try:
            ExamenMedical.objects.create(
                patient_id=request.POST['patient'],
                consultation_id=request.POST['consultation'],
                laborantin_id=request.POST.get('laborantin') or None,
                medecin_id=request.POST.get('medecin') or None,
                type_examen=request.POST['type_examen'],
                statut=request.POST.get('statut', 'en_attente'),
                resultat=request.POST.get('resultat', ''),
            )
            messages.success(request, 'Examen créé.')
            return redirect('consultation:examens')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/examen_form.html', {
        'patients': Patient.objects.all(),
        'consultations': Consultation.objects.all().order_by('-date'),
        'laborantins': Laborantin.objects.all(),
        'medecins': Medecin.objects.all(),
        'action': 'Ajouter',
    })

@login_required
def examen_modifier(request, pk):
    examen = get_object_or_404(ExamenMedical, pk=pk)
    if request.method == 'POST':
        examen.type_examen = request.POST['type_examen']
        examen.statut = request.POST.get('statut', examen.statut)
        examen.resultat = request.POST.get('resultat', '')
        examen.save()
        messages.success(request, 'Examen modifié.')
        return redirect('consultation:examens')

    return render(request, 'consultation/examen_form.html', {
        'examen': examen,
        'patients': Patient.objects.all(),
        'consultations': Consultation.objects.all().order_by('-date'),
        'laborantins': Laborantin.objects.all(),
        'medecins': Medecin.objects.all(),
        'action': 'Modifier',
    })

@login_required
def examen_supprimer(request, pk):
    examen = get_object_or_404(ExamenMedical, pk=pk)
    if request.method == 'POST':
        examen.delete()
        messages.success(request, 'Examen supprimé.')
        return redirect('consultation:examens')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Examen #{pk} — {examen.type_examen}',
        'retour_url': '/consultation/examens/',
    })

# ── Ordonnances ──────────────────────────────────────────

@login_required
def ordonnances(request):
    return render(request, 'consultation/ordonnances.html', {
        'ordonnances': Ordonnance.objects.all().order_by('-date'),
    })

@login_required
def ordonnance_ajouter(request):
    if request.method == 'POST':
        try:
            Ordonnance.objects.create(
                consultation_id=request.POST['consultation'],
                date=request.POST['date'],
                medicaments=request.POST['medicaments'],
            )
            messages.success(request, 'Ordonnance créée.')
            return redirect('consultation:ordonnances')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    consultation_id = request.GET.get('consultation')
    return render(request, 'consultation/ordonnance_form.html', {
        'consultations': Consultation.objects.all().order_by('-date'),
        'consultation_id': consultation_id,
        'action': 'Créer',
    })

@login_required
def ordonnance_detail(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    return render(request, 'consultation/ordonnance_detail.html', {'ordonnance': ordonnance})

@login_required
def ordonnance_supprimer(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    if request.method == 'POST':
        ordonnance.delete()
        messages.success(request, 'Ordonnance supprimée.')
        return redirect('consultation:ordonnances')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Ordonnance #{pk}',
        'retour_url': '/consultation/ordonnances/',
    })

# ── Hospitalisations ─────────────────────────────────────

@login_required
def hospitalisations(request):
    qs = Hospitalisation.objects.all().order_by('-date_entree')
    return render(request, 'consultation/hospitalisations.html', {
        'hospitalisations': qs,
        'total_en_cours': qs.filter(date_sortie__isnull=True).count(),
        'total_sorties': qs.filter(date_sortie__isnull=False).count(),
        'longues_durees': qs.filter(nombre_jours__gt=7).count(),
    })

@login_required
def hospit_ajouter(request):
    if request.method == 'POST':
        try:
            Hospitalisation.objects.create(
                patient_id=request.POST['patient'],
                medecin_id=request.POST['medecin'],
                type_chambre=request.POST['type_chambre'],
                numero_chambre=request.POST['numero_chambre'],
                nombre_jours=request.POST['nombre_jours'],
                date_entree=request.POST['date_entree'],
                date_sortie=request.POST.get('date_sortie') or None,
            )
            messages.success(request, 'Hospitalisation enregistrée.')
            return redirect('consultation:hospitalisations')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/hospit_form.html', {
        'patients': Patient.objects.all(),
        'medecins': Medecin.objects.all(),
        'action': 'Ajouter',
    })

@login_required
def hospit_modifier(request, pk):
    hospit = get_object_or_404(Hospitalisation, pk=pk)
    if request.method == 'POST':
        hospit.type_chambre = request.POST['type_chambre']
        hospit.numero_chambre = request.POST['numero_chambre']
        hospit.nombre_jours = request.POST['nombre_jours']
        hospit.date_sortie = request.POST.get('date_sortie') or None
        hospit.save()
        messages.success(request, 'Hospitalisation modifiée.')
        return redirect('consultation:hospitalisations')

    return render(request, 'consultation/hospit_form.html', {
        'hospit': hospit,
        'patients': Patient.objects.all(),
        'medecins': Medecin.objects.all(),
        'action': 'Modifier',
    })

@login_required
def hospit_supprimer(request, pk):
    hospit = get_object_or_404(Hospitalisation, pk=pk)
    if request.method == 'POST':
        hospit.delete()
        messages.success(request, 'Hospitalisation supprimée.')
        return redirect('consultation:hospitalisations')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Hospitalisation de {hospit.patient}',
        'retour_url': '/consultation/hospitalisations/',
    })

# ── Traitements ──────────────────────────────────────────

@login_required
def traitements(request):
    return render(request, 'consultation/traitements.html', {
        'traitements': Traitement.objects.all().order_by('-id'),
    })
