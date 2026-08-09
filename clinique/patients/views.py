from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone

from patients.models import Patient
from comptes.decorators import (role_required, role_required_strict, get_role,
                                permission_required)
from comptes.recherche import termes_q, nouveau_en_tete


def _medecin_courant(request):
    """Médecin lié au compte connecté, ou None."""
    return getattr(getattr(request.user, 'profil', None), 'medecin', None)


def _patients_du_medecin(medecin):
    """Patients suivis par ce médecin : ceux avec qui il a un lien de soin
    (rendez-vous, hospitalisation ou examen). Sert à ce qu'un médecin ne voie
    que ses propres patients, pas ceux d'un confrère."""
    return Patient.objects.filter(
        Q(rendez_vous__medecin=medecin) |
        Q(hospitalisation__medecin=medecin) |
        Q(examenmedical__medecin=medecin)
    )


def _restreindre_au_medecin(request, qs):
    """Si l'utilisateur connecté est un médecin, ne garde que ses patients.
    Les autres rôles (admin, accueil, infirmier, labo) voient tous les patients."""
    if get_role(request.user) != 'medecin':
        return qs
    medecin = _medecin_courant(request)
    if not medecin:
        return qs.none()
    return qs.filter(
        Q(rendez_vous__medecin=medecin) |
        Q(hospitalisation__medecin=medecin) |
        Q(examenmedical__medecin=medecin)
    ).distinct()


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


@permission_required('patient.view')
def patient_liste(request):
    q = request.GET.get('q', '')
    sexe = request.GET.get('sexe', '')
    qs = Patient.objects.select_related('assurance').order_by('nom', 'prenom')
    qs = _restreindre_au_medecin(request, qs)

    if q:
        qs = qs.filter(termes_q(q, 'nom', 'prenom', 'telephone', 'email'))
    if sexe:
        qs = qs.filter(sexe=sexe)

    aujourd_hui = timezone.now()
    stats = qs.aggregate(
        # istartswith : tolère « Feminin » sans accent ou « M »/« F » d'anciennes saisies
        nb_hommes=Count('pk', distinct=True, filter=Q(sexe__istartswith='m')),
        nb_femmes=Count('pk', distinct=True, filter=Q(sexe__istartswith='f')),
        nb_nouveaux=Count('pk', distinct=True,
                          filter=Q(date_creation__year=aujourd_hui.year,
                                   date_creation__month=aujourd_hui.month)),
    )

    patients_liste, new_pk = nouveau_en_tete(request, qs)
    page = Paginator(patients_liste, 25).get_page(request.GET.get('page'))
    return render(request, 'patients/liste.html',
                  {'patients': page, 'q': q, 'new_pk': new_pk, **stats})


@permission_required('patient.view')
def patient_export(request):
    """Exporte la liste des patients (filtres de recherche appliqués) en CSV."""
    from facturation.exports import csv_response
    q = request.GET.get('q', '')
    sexe = request.GET.get('sexe', '')
    qs = Patient.objects.select_related('assurance').order_by('nom', 'prenom')
    qs = _restreindre_au_medecin(request, qs)
    if q:
        qs = qs.filter(termes_q(q, 'nom', 'prenom', 'telephone', 'email'))
    if sexe:
        qs = qs.filter(sexe=sexe)

    headers = ['Nom', 'Prénom', 'Sexe', 'Date de naissance', 'Téléphone',
               'Email', 'Adresse', 'Assurance', 'N° assuré']
    rows = [[
        p.nom, p.prenom, p.sexe,
        p.date_naissance.strftime('%d/%m/%Y') if p.date_naissance else '',
        p.telephone, p.email, p.adresse,
        p.assurance.nom if p.assurance_id else '', p.numero_assure,
    ] for p in qs]
    return csv_response('patients.csv', headers, rows)


@permission_required('patient.view')
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)

    # Un médecin ne peut consulter que le dossier de ses propres patients.
    if get_role(request.user) == 'medecin':
        medecin = _medecin_courant(request)
        if not medecin or not _patients_du_medecin(medecin).filter(pk=patient.pk).exists():
            messages.error(request, "Ce patient ne fait pas partie de vos patients.")
            return redirect('patients:liste')

    from consultation.models import (DossierMedical, Rendez_vous, Consultation,
                                     ExamenMedical, Hospitalisation)
    from facturation.models import Facture

    try:
        dossier = patient.dossiermedical
    except Exception:
        dossier = None

    # Cloisonnement : un médecin ne voit le dossier que s'il en est le
    # propriétaire ou s'il lui a été transmis. Sinon on le masque ici.
    if dossier and get_role(request.user) == 'medecin':
        med = _medecin_courant(request)
        if med and not dossier.est_accessible_par(med):
            dossier = None

    # Le médecin soigne, il ne facture pas : la situation financière du patient
    # ne lui est pas envoyée du tout (et pas seulement masquée à l'affichage).
    if get_role(request.user) == 'medecin':
        factures = Facture.objects.none()
    else:
        factures = Facture.objects.filter(patient=patient).order_by('-id')[:5]

    # Séjours du patient. Même cloisonnement que la liste des hospitalisations :
    # un médecin ne voit que les séjours dont il est le médecin traitant.
    hospitalisations = Hospitalisation.objects.filter(patient=patient).select_related('medecin')
    med_courant = _medecin_courant(request)
    if get_role(request.user) == 'medecin' and med_courant:
        hospitalisations = hospitalisations.filter(medecin=med_courant)
    hospitalisations = hospitalisations.order_by('-date_entree')[:5]

    return render(request, 'patients/detail.html', {
        'patient': patient,
        'dossier': dossier,
        'rdvs': Rendez_vous.objects.filter(patient=patient).order_by('-date')[:5],
        'consultations': Consultation.objects.filter(rendez_vous__patient=patient).order_by('-date')[:5],
        'examens': ExamenMedical.objects.filter(patient=patient).order_by('-id')[:5],
        'hospitalisations': hospitalisations,
        'factures': factures,
    })


# Fiches patient : réservées à la réception. L'administrateur en est exclu
# (séparation des tâches) — d'où role_required_strict, qui ne lui laisse
# aucun passe-droit, contrairement à role_required.
@role_required_strict('receptionniste')
def patient_ajouter(request):
    from facturation.models import Assurance

    if request.method == 'POST':
        try:
            p = Patient.objects.create(
                nom=request.POST['nom'],
                prenom=request.POST['prenom'],
                sexe=request.POST.get('sexe', ''),
                date_naissance=request.POST['date_naissance'],
                adresse=request.POST.get('adresse', ''),
                telephone=request.POST['telephone'],
                email=request.POST.get('email', ''),
                numero_urgence=request.POST.get('numero_urgence', ''),
                photo=request.FILES.get('photo'),
                assurance_id=request.POST.get('assurance') or None,
                numero_assure=request.POST.get('numero_assure', ''),
            )
            messages.success(request, 'Patient ajouté avec succès.')
            return redirect(f"{reverse('patients:liste')}?new={p.pk}")
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'patients/form.html', {
        'action': 'Ajouter',
        'assurances': Assurance.objects.filter(actif=True),
    })


@role_required_strict('receptionniste')
def patient_modifier(request, pk):
    from facturation.models import Assurance

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
            if request.FILES.get('photo'):
                patient.photo = request.FILES['photo']
            patient.assurance_id = request.POST.get('assurance') or None
            patient.numero_assure = request.POST.get('numero_assure', '')
            patient.save()
            messages.success(request, 'Patient modifié avec succès.')
            return redirect('patients:detail', pk=patient.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'patients/form.html', {
        'patient': patient,
        'action': 'Modifier',
        'assurances': Assurance.objects.filter(actif=True),
    })


@role_required_strict('receptionniste')
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


@role_required('admin', 'receptionniste')
def accueil_patients(request):
    from consultation.models import Rendez_vous
    rdvs = Rendez_vous.objects.filter(date__date=timezone.now().date()).order_by('date')
    return render(request, 'receptionniste/dashboard.html', {
        'rdv_aujourd_hui': rdvs,
        'rdv_count': rdvs.count(),
    })
