from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone

from .models import (
    Rendez_vous,
    DossierMedical,
    Consultation,
    ExamenMedical,
    ResultatExamen,
    Ordonnance,
    Hospitalisation,
    Traitement,
    AdministrationTraitement,
    AssistanceInfirmier,
)
from patients.models import Patient
from personnel.models import Medecin, Laborantin, Infirmier
from comptes.decorators import role_required


def _get_personnel(user, attr):
    try:
        return getattr(user.profil, attr)
    except Exception:
        return None


# Rendez-vous

@role_required('admin', 'medecin', 'receptionniste')
def rdv_liste(request):
    rdvs = Rendez_vous.objects.all().order_by('-date')
    role = getattr(getattr(request.user, 'profil', None), 'role', None)
    if role and role.code == 'medecin':
        medecin = _get_personnel(request.user, 'medecin')
        if medecin:
            rdvs = rdvs.filter(medecin=medecin)
    return render(request, 'consultation/rdv_liste.html', {
        'rdvs': rdvs,
        'rdv_termines': rdvs.filter(statut='termine').count(),
        'rdv_en_cours': rdvs.filter(statut='programme').count(),
        'rdv_programmes': rdvs.filter(statut='programme').count(),
        'rdv_annules_count': rdvs.filter(statut='annule').count(),
    })


@role_required('admin', 'receptionniste')
def rdv_ajouter(request):
    if request.method == 'POST':
        try:
            Rendez_vous.objects.create(
                patient_id=request.POST['patient'],
                medecin_id=request.POST['medecin'],
                date=request.POST['date'],
                statut=request.POST.get('statut', 'programme'),
            )
            messages.success(request, 'Rendez-vous cree.')
            return redirect('consultation:rdv_liste')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/rdv_form.html', {
        'patients': Patient.objects.all().order_by('nom'),
        'medecins': Medecin.objects.all().order_by('nom'),
        'action': 'Ajouter',
    })


@role_required('admin', 'receptionniste')
def rdv_modifier(request, pk):
    rdv = get_object_or_404(Rendez_vous, pk=pk)
    if request.method == 'POST':
        try:
            rdv.patient_id = request.POST['patient']
            rdv.medecin_id = request.POST['medecin']
            rdv.date = request.POST['date']
            rdv.statut = request.POST.get('statut', rdv.statut)
            rdv.save()
            messages.success(request, 'Rendez-vous modifie.')
            return redirect('consultation:rdv_liste')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/rdv_form.html', {
        'rdv': rdv,
        'patients': Patient.objects.all().order_by('nom'),
        'medecins': Medecin.objects.all().order_by('nom'),
        'action': 'Modifier',
    })


@role_required('admin', 'receptionniste')
def rdv_supprimer(request, pk):
    rdv = get_object_or_404(Rendez_vous, pk=pk)
    if request.method == 'POST':
        rdv.delete()
        messages.success(request, 'Rendez-vous supprime.')
        return redirect('consultation:rdv_liste')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'RDV de {rdv.patient} avec Dr. {rdv.medecin}',
        'retour_url': '/consultation/rdv/',
    })


# Dossiers medicaux

@role_required('admin', 'medecin', 'infirmier')
def dossiers(request):
    return render(request, 'consultation/dossiers.html', {
        'dossiers': DossierMedical.objects.all().order_by('-date_creation'),
    })


@role_required('admin', 'medecin', 'infirmier')
def dossier_detail(request, pk):
    dossier = get_object_or_404(DossierMedical, pk=pk)
    return render(request, 'consultation/dossier_detail.html', {'dossier': dossier})


# Consultations

@role_required('admin', 'medecin')
def consultation_liste(request):
    consultations = Consultation.objects.all().order_by('-date')
    medecin = _get_personnel(request.user, 'medecin')
    if medecin:
        consultations = consultations.filter(rendez_vous__medecin=medecin)
    return render(request, 'consultation/liste.html', {
        'consultations': consultations,
    })


@role_required('admin', 'medecin')
def consultation_ajouter(request):
    if request.method == 'POST':
        try:
            Consultation.objects.create(
                rendez_vous_id=request.POST['rendez_vous'],
                motif=request.POST['motif'],
                diagnostic=request.POST.get('diagnostic', ''),
                observation=request.POST.get('observation', ''),
            )
            messages.success(request, 'Consultation enregistree.')
            return redirect('consultation:liste')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    rdvs = Rendez_vous.objects.filter(statut='programme').order_by('-date')
    medecin = _get_personnel(request.user, 'medecin')
    if medecin:
        rdvs = rdvs.filter(medecin=medecin)
    return render(request, 'consultation/form_consultation.html', {
        'rdvs': rdvs,
        'action': 'Ajouter',
    })


@role_required('admin', 'medecin', 'infirmier')
def consultation_detail(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    return render(request, 'consultation/detail_consultation.html', {'consultation': consultation})


@role_required('admin', 'medecin')
def consultation_modifier(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    if request.method == 'POST':
        consultation.motif = request.POST['motif']
        consultation.diagnostic = request.POST.get('diagnostic', '')
        consultation.observation = request.POST.get('observation', '')
        consultation.save()
        messages.success(request, 'Consultation modifiee.')
        return redirect('consultation:detail', pk=consultation.pk)

    return render(request, 'consultation/form_consultation.html', {
        'consultation': consultation,
        'rdvs': Rendez_vous.objects.all().order_by('-date'),
        'action': 'Modifier',
    })


@role_required('admin', 'medecin')
def consultation_supprimer(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    if request.method == 'POST':
        consultation.delete()
        messages.success(request, 'Consultation supprimee.')
        return redirect('consultation:liste')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Consultation #{pk}',
        'retour_url': '/consultation/',
    })


# Examens

@role_required('admin', 'medecin', 'laborantin')
def examens(request):
    qs = ExamenMedical.objects.all().order_by('-id')
    role = getattr(getattr(request.user, 'profil', None), 'role', None)
    if role and role.code == 'medecin':
        medecin = _get_personnel(request.user, 'medecin')
        if medecin:
            qs = qs.filter(medecin=medecin)
    elif role and role.code == 'laborantin':
        labo = _get_personnel(request.user, 'laborantin')
        if labo:
            qs = qs.filter(laborantin=labo) | qs.filter(laborantin__isnull=True)
    return render(request, 'consultation/examens.html', {
        'examens': qs,
        'examens_attente_count': qs.filter(statut='en_attente').count(),
        'examens_cours_count': qs.filter(statut='en_cours').count(),
        'examens_termines_count': qs.filter(statut='termine').count(),
    })


@role_required('admin', 'medecin')
def examen_ajouter(request):
    if request.method == 'POST':
        try:
            medecin_id = request.POST.get('medecin') or None
            if not medecin_id:
                m = _get_personnel(request.user, 'medecin')
                medecin_id = m.id if m else None
            ExamenMedical.objects.create(
                patient_id=request.POST['patient'],
                consultation_id=request.POST['consultation'],
                laborantin_id=request.POST.get('laborantin') or None,
                medecin_id=medecin_id,
                type_examen=request.POST['type_examen'],
                statut=request.POST.get('statut', 'en_attente'),
            )
            messages.success(request, 'Examen demande.')
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


@role_required('admin', 'medecin', 'laborantin')
def examen_modifier(request, pk):
    examen = get_object_or_404(ExamenMedical, pk=pk)
    if request.method == 'POST':
        examen.type_examen = request.POST.get('type_examen', examen.type_examen)
        examen.statut = request.POST.get('statut', examen.statut)
        if request.POST.get('laborantin'):
            examen.laborantin_id = request.POST['laborantin']
        examen.save()
        messages.success(request, 'Examen modifie.')
        return redirect('consultation:examens')

    return render(request, 'consultation/examen_form.html', {
        'examen': examen,
        'patients': Patient.objects.all(),
        'consultations': Consultation.objects.all().order_by('-date'),
        'laborantins': Laborantin.objects.all(),
        'medecins': Medecin.objects.all(),
        'action': 'Modifier',
    })


@role_required('admin', 'medecin')
def examen_supprimer(request, pk):
    examen = get_object_or_404(ExamenMedical, pk=pk)
    if request.method == 'POST':
        examen.delete()
        messages.success(request, 'Examen supprime.')
        return redirect('consultation:examens')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Examen #{pk} - {examen.type_examen}',
        'retour_url': '/consultation/examens/',
    })


# Resultats d'examen (laborantin)

@role_required('admin', 'medecin', 'laborantin')
def resultats(request):
    qs = ResultatExamen.objects.all().order_by('-date_examen')
    role = getattr(getattr(request.user, 'profil', None), 'role', None)
    if role and role.code == 'laborantin':
        labo = _get_personnel(request.user, 'laborantin')
        if labo:
            qs = qs.filter(laborantin=labo)
    elif role and role.code == 'medecin':
        medecin = _get_personnel(request.user, 'medecin')
        if medecin:
            qs = qs.filter(examen__medecin=medecin, transmis=True)
    return render(request, 'consultation/resultats_liste.html', {'resultats': qs})


@role_required('admin', 'laborantin')
def resultat_ajouter(request):
    examen_id = request.GET.get('examen')
    if request.method == 'POST':
        try:
            examen = get_object_or_404(ExamenMedical, pk=request.POST['examen'])
            labo = _get_personnel(request.user, 'laborantin')
            ResultatExamen.objects.create(
                patient=examen.patient,
                examen=examen,
                medecin=examen.medecin,
                laborantin=labo,
                resultat=request.POST['resultat'],
                observations=request.POST.get('observations', ''),
            )
            messages.success(request, 'Resultat enregistre.')
            return redirect('consultation:resultats')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    examens_qs = ExamenMedical.objects.filter(statut__in=['en_attente', 'en_cours']).order_by('-id')
    return render(request, 'consultation/resultat_form.html', {
        'examens': examens_qs,
        'examen_id': examen_id,
        'action': 'Enregistrer',
    })


@role_required('admin', 'laborantin')
def resultat_modifier(request, pk):
    res = get_object_or_404(ResultatExamen, pk=pk)
    if request.method == 'POST':
        res.resultat = request.POST['resultat']
        res.observations = request.POST.get('observations', '')
        res.save()
        messages.success(request, 'Resultat modifie.')
        return redirect('consultation:resultats')
    return render(request, 'consultation/resultat_form.html', {
        'resultat': res,
        'action': 'Modifier',
    })


@role_required('admin', 'laborantin')
def resultat_transmettre(request, pk):
    res = get_object_or_404(ResultatExamen, pk=pk)
    res.transmis = True
    res.date_transmission = timezone.now()
    res.save()
    messages.success(request, 'Resultat transmis au medecin.')
    return redirect('consultation:resultats')


@role_required('admin', 'medecin', 'laborantin')
def resultat_detail(request, pk):
    res = get_object_or_404(ResultatExamen, pk=pk)
    return render(request, 'consultation/resultat_detail.html', {'resultat': res})


# Ordonnances

@role_required('admin', 'medecin')
def ordonnances(request):
    return render(request, 'consultation/ordonnances.html', {
        'ordonnances': Ordonnance.objects.all().order_by('-date'),
    })


@role_required('admin', 'medecin')
def ordonnance_ajouter(request):
    if request.method == 'POST':
        try:
            Ordonnance.objects.create(
                consultation_id=request.POST['consultation'],
                date=request.POST['date'],
                medicaments=request.POST['medicaments'],
            )
            messages.success(request, 'Ordonnance creee.')
            return redirect('consultation:ordonnances')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    consultation_id = request.GET.get('consultation')
    return render(request, 'consultation/ordonnance_form.html', {
        'consultations': Consultation.objects.all().order_by('-date'),
        'consultation_id': consultation_id,
        'action': 'Creer',
    })


@role_required('admin', 'medecin')
def ordonnance_detail(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    return render(request, 'consultation/ordonnance_detail.html', {'ordonnance': ordonnance})


@role_required('admin', 'medecin')
def ordonnance_supprimer(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    if request.method == 'POST':
        ordonnance.delete()
        messages.success(request, 'Ordonnance supprimee.')
        return redirect('consultation:ordonnances')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Ordonnance #{pk}',
        'retour_url': '/consultation/ordonnances/',
    })


# Hospitalisations

@role_required('admin', 'medecin', 'infirmier', 'receptionniste')
def hospitalisations(request):
    qs = Hospitalisation.objects.all().order_by('-date_entree')
    return render(request, 'consultation/hospitalisations.html', {
        'hospitalisations': qs,
        'total_en_cours': qs.filter(date_sortie__isnull=True).count(),
        'total_sorties': qs.filter(date_sortie__isnull=False).count(),
        'longues_durees': qs.filter(nombre_jours__gt=7).count(),
    })


@role_required('admin', 'medecin', 'receptionniste')
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
            messages.success(request, 'Hospitalisation enregistree.')
            return redirect('consultation:hospitalisations')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/hospit_form.html', {
        'patients': Patient.objects.all(),
        'medecins': Medecin.objects.all(),
        'action': 'Ajouter',
    })


@role_required('admin', 'medecin', 'receptionniste')
def hospit_modifier(request, pk):
    hospit = get_object_or_404(Hospitalisation, pk=pk)
    if request.method == 'POST':
        hospit.type_chambre = request.POST['type_chambre']
        hospit.numero_chambre = request.POST['numero_chambre']
        hospit.nombre_jours = request.POST['nombre_jours']
        hospit.date_sortie = request.POST.get('date_sortie') or None
        hospit.save()
        messages.success(request, 'Hospitalisation modifiee.')
        return redirect('consultation:hospitalisations')

    return render(request, 'consultation/hospit_form.html', {
        'hospit': hospit,
        'patients': Patient.objects.all(),
        'medecins': Medecin.objects.all(),
        'action': 'Modifier',
    })


@role_required('admin', 'receptionniste')
def hospit_supprimer(request, pk):
    hospit = get_object_or_404(Hospitalisation, pk=pk)
    if request.method == 'POST':
        hospit.delete()
        messages.success(request, 'Hospitalisation supprimee.')
        return redirect('consultation:hospitalisations')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Hospitalisation de {hospit.patient}',
        'retour_url': '/consultation/hospitalisations/',
    })


# Traitements

@role_required('admin', 'medecin', 'infirmier')
def traitements(request):
    return render(request, 'consultation/traitements.html', {
        'traitements': Traitement.objects.all().order_by('-id'),
    })


@role_required('admin', 'medecin')
def traitement_ajouter(request):
    if request.method == 'POST':
        try:
            Traitement.objects.create(
                patient_id=request.POST['patient'],
                consultation_id=request.POST.get('consultation') or None,
                infirmier_id=request.POST.get('infirmier') or None,
                description=request.POST['description'],
                duree=request.POST.get('duree', 1),
            )
            messages.success(request, 'Traitement prescrit.')
            return redirect('consultation:traitements')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/traitement_form.html', {
        'patients': Patient.objects.all(),
        'consultations': Consultation.objects.all().order_by('-date'),
        'infirmiers': Infirmier.objects.all(),
        'action': 'Ajouter',
    })


@role_required('admin', 'medecin', 'infirmier')
def traitement_detail(request, pk):
    t = get_object_or_404(Traitement, pk=pk)
    return render(request, 'consultation/traitement_detail.html', {'traitement': t})


@role_required('admin', 'infirmier')
def traitement_administrer(request, pk):
    t = get_object_or_404(Traitement, pk=pk)
    if request.method == 'POST':
        infirmier = _get_personnel(request.user, 'infirmier')
        AdministrationTraitement.objects.create(
            traitement=t,
            infirmier=infirmier,
            note=request.POST.get('note', ''),
        )
        if t.statut == 'prescrit':
            t.statut = 'en_cours'
            t.save()
        messages.success(request, "Administration enregistree dans le dossier.")
        return redirect('consultation:traitement_detail', pk=t.pk)
    return render(request, 'consultation/traitement_administrer.html', {'traitement': t})


@role_required('admin', 'medecin')
def traitement_supprimer(request, pk):
    t = get_object_or_404(Traitement, pk=pk)
    if request.method == 'POST':
        t.delete()
        messages.success(request, 'Traitement supprime.')
        return redirect('consultation:traitements')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Traitement #{pk}',
        'retour_url': '/consultation/traitements/',
    })


# Assistance infirmier

@role_required('admin', 'medecin', 'infirmier')
def assistances(request):
    qs = AssistanceInfirmier.objects.all().order_by('-date')
    role = getattr(getattr(request.user, 'profil', None), 'role', None)
    if role and role.code == 'infirmier':
        infirmier = _get_personnel(request.user, 'infirmier')
        if infirmier:
            qs = qs.filter(infirmier=infirmier)
    return render(request, 'consultation/assistances_liste.html', {'assistances': qs})


@role_required('admin', 'infirmier')
def assistance_ajouter(request):
    if request.method == 'POST':
        infirmier = _get_personnel(request.user, 'infirmier')
        AssistanceInfirmier.objects.create(
            patient_id=request.POST['patient'],
            infirmier=infirmier,
            description=request.POST['description'],
        )
        messages.success(request, 'Assistance enregistree.')
        return redirect('consultation:assistances')
    return render(request, 'consultation/assistance_form.html', {
        'patients': Patient.objects.all().order_by('nom'),
    })
