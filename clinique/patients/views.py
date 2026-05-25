from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils import timezone

from patients.models import Patient


@login_required
def dashboard(request):
    role = 'admin'
    try:
        role = request.user.profil.role
    except Exception:
        pass

    aujourd_hui = timezone.now().date()

    from consultation.models import Rendez_vous, Hospitalisation, ExamenMedical
    from facturation.models import Facture

    base_ctx = {
        'rdv_count':             Rendez_vous.objects.filter(date__date=aujourd_hui).count(),
        'examens_attente_count': ExamenMedical.objects.filter(statut='en_attente').count(),
        'factures_impayees':     Facture.objects.filter(statut='non payé').count(),
    }

    if role == 'admin':
        from facturation.models import Paiement
        paiements = Paiement.objects.all()
        total = sum(p.montant for p in paiements) if paiements else 0

        def pct(mode):
            count = paiements.filter(mode_paiement=mode).count()
            return round(count * 100 / paiements.count()) if paiements.count() else 0

        ctx = {
            **base_ctx,
            'total_patients':      Patient.objects.count(),
            'rdv_termines':        Rendez_vous.objects.filter(date__date=aujourd_hui, statut='termine').count(),
            'total_hospitalises':  Hospitalisation.objects.filter(date_sortie__isnull=True).count(),
            'recettes_mois':       f"{int(total):,}".replace(',', ' '),
            'rdv_aujourd_hui':     Rendez_vous.objects.filter(date__date=aujourd_hui).order_by('date')[:8],
            'patients_recents':    Patient.objects.order_by('-date_creation')[:6],
            'pct_especes':         pct('cash'),
            'pct_orange':          pct('orange_money'),
            'pct_moov':            pct('moov_money'),
            'pct_carte':           pct('carte'),
        }
        return render(request, 'admin/dashboard.html', ctx)

    elif role == 'medecin':
        from consultation.models import Consultation
        try:
            medecin = request.user.profil.medecin
        except Exception:
            medecin = None

        mes_rdv = Rendez_vous.objects.filter(date__date=aujourd_hui, medecin=medecin).order_by('date') if medecin else Rendez_vous.objects.none()

        ctx = {
            **base_ctx,
            'mes_rdv_count':          mes_rdv.count(),
            'rdv_termines':           mes_rdv.filter(statut='termine').count(),
            'mes_rdv_aujourd_hui':    mes_rdv[:8],
            'mes_consultations':      Consultation.objects.filter(rendez_vous__medecin=medecin).count() if medecin else 0,
            'mes_consultations_list': Consultation.objects.filter(rendez_vous__medecin=medecin).order_by('-date')[:5] if medecin else [],
            'mes_hospitalises':       Hospitalisation.objects.filter(medecin=medecin, date_sortie__isnull=True).count() if medecin else 0,
            'mes_hospitalises_list':  Hospitalisation.objects.filter(medecin=medecin, date_sortie__isnull=True)[:5] if medecin else [],
            'mes_ordonnances':        0,
        }
        return render(request, 'medecin/dashboard.html', ctx)

    elif role == 'laborantin':
        ctx = {
            **base_ctx,
            'examens_liste':       ExamenMedical.objects.filter(statut__in=['en_attente', 'en_cours']).order_by('id')[:10],
            'examens_en_cours':    ExamenMedical.objects.filter(statut='en_cours').count(),
            'examens_termines':    ExamenMedical.objects.filter(statut='termine').count(),
            'total_examens_mois':  ExamenMedical.objects.count(),
            'derniers_resultats':  ExamenMedical.objects.filter(statut='termine').order_by('-id')[:4],
        }
        return render(request, 'laborantin/dashboard.html', ctx)

    elif role == 'infirmier':
        from consultation.models import Traitement
        hospit = Hospitalisation.objects.filter(date_sortie__isnull=True)
        ctx = {
            **base_ctx,
            'total_hospitalises': hospit.count(),
            'hospitalisations':   hospit[:10],
            'traitements':        Traitement.objects.all()[:10],
        }
        return render(request, 'infirmier/dashboard.html', ctx)

    elif role == 'receptionniste':
        rdvs = Rendez_vous.objects.filter(date__date=aujourd_hui).order_by('date')
        ctx = {
            **base_ctx,
            'rdv_aujourd_hui':   rdvs[:10],
            'rdv_restants':      rdvs.filter(statut='programme').count(),
            'nouveaux_patients': Patient.objects.filter(date_creation__date=aujourd_hui).count(),
            'rdv_annules':       rdvs.filter(statut='annule').count(),
        }
        return render(request, 'receptionniste/dashboard.html', ctx)

    return redirect('dashboard')


# ──────────────────────────────────────────────
#  PATIENTS
# ──────────────────────────────────────────────


@login_required
def patient_liste(request):
    q = request.GET.get('q', '')
    sexe = request.GET.get('sexe', '')
    qs = Patient.objects.all().order_by('-date_creation')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) |
            Q(prenom__icontains=q) |
            Q(telephone__icontains=q) |
            Q(email__icontains=q)
        )
    if sexe:
        qs = qs.filter(sexe=sexe)

    return render(request, 'patients/liste.html', {'patients': qs, 'q': q})


@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    from consultation.models import DossierMedical, Rendez_vous, Consultation, ExamenMedical
    from facturation.models import Facture

    try:
        dossier = patient.dossiermedical
    except Exception:
        dossier = None

    return render(request, 'patients/detail.html', {
        'patient': patient,
        'dossier': dossier,
        'rdvs': Rendez_vous.objects.filter(patient=patient).order_by('-date')[:5],
        'consultations': Consultation.objects.filter(rendez_vous__patient=patient).order_by('-date')[:5],
        'examens': ExamenMedical.objects.filter(patient=patient).order_by('-id')[:5],
        'factures': Facture.objects.filter(patient=patient).order_by('-id')[:5],
    })


@login_required
def patient_ajouter(request):
    if request.method == 'POST':
        try:
            Patient.objects.create(
                nom=request.POST['nom'],
                prenom=request.POST['prenom'],
                sexe=request.POST.get('sexe', ''),
                date_naissance=request.POST['date_naissance'],
                adresse=request.POST.get('adresse', ''),
                telephone=request.POST['telephone'],
                email=request.POST.get('email', ''),
                numero_urgence=request.POST.get('numero_urgence', ''),
            )
            messages.success(request, 'Patient ajouté avec succès.')
            return redirect('patients:liste')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'patients/form.html', {'action': 'Ajouter'})


@login_required
def patient_modifier(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        try:
            patient.nom = request.POST['nom']
            patient.prenom = request.POST['prenom']
            patient.sexe = request.POST.get('sexe', patient.sexe)
            patient.date_naissance = request.POST['date_naissance']
            patient.adresse = request.POST.get('adresse', patient.adresse)
            patient.telephone = request.POST['telephone']
            patient.email = request.POST.get('email', patient.email)
            patient.numero_urgence = request.POST.get('numero_urgence', patient.numero_urgence)
            patient.save()
            messages.success(request, 'Patient modifié avec succès.')
            return redirect('patients:detail', pk=patient.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'patients/form.html', {'patient': patient, 'action': 'Modifier'})


@login_required
def patient_supprimer(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        patient.delete()
        messages.success(request, 'Patient supprimé.')
        return redirect('patients:liste')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'{patient.nom} {patient.prenom}',
        'retour_url': '/patients/',
    })


@login_required
def accueil_patients(request):
    from consultation.models import Rendez_vous
    rdvs = Rendez_vous.objects.filter(date__date=timezone.now().date()).order_by('date')
    return render(request, 'receptionniste/dashboard.html', {
        'rdv_aujourd_hui': rdvs,
        'rdv_count': rdvs.count(),
    })