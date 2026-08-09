from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import models
from django.http import JsonResponse

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
from comptes.decorators import role_required, permission_required, get_role
from comptes.models import JournalAudit
from comptes.recherche import termes_q, nouveau_en_tete


def _get_personnel(user, attr):
    try:
        return getattr(user.profil, attr)
    except Exception:
        return None


# Rendez-vous

@permission_required('rdv.view')
def rdv_liste(request):
    import calendar as cal_module
    from datetime import date

    today = date.today()

    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    if month < 1:  month = 12; year -= 1
    if month > 12: month = 1;  year += 1

    all_rdvs = Rendez_vous.objects.select_related('patient', 'medecin').all()
    role = getattr(getattr(request.user, 'profil', None), 'role', None)
    if role and role.code == 'medecin':
        medecin = _get_personnel(request.user, 'medecin')
        if medecin:
            all_rdvs = all_rdvs.filter(medecin=medecin)

    # Recherche : si un terme est saisi, on liste les RDV correspondants
    # (tous mois confondus) au lieu d'afficher le calendrier.
    q = request.GET.get('q', '').strip()
    resultats_recherche = None
    if q:
        resultats_recherche = all_rdvs.filter(
            termes_q(q, 'patient__nom', 'patient__prenom',
                     'patient__telephone', 'medecin__nom')
        ).order_by('-date')[:100]

    cal = cal_module.Calendar(firstweekday=0)
    weeks = cal.monthdatescalendar(year, month)

    first_day = weeks[0][0]
    last_day  = weeks[-1][6]
    month_rdvs = all_rdvs.filter(date__date__gte=first_day, date__date__lte=last_day).order_by('date')

    rdvs_by_date = {}
    for rdv in month_rdvs:
        key = rdv.date.date().isoformat()
        rdvs_by_date.setdefault(key, []).append(rdv)

    today_rdvs = all_rdvs.filter(date__date=today).order_by('date')
    month_rdvs_count = all_rdvs.filter(date__year=year, date__month=month).count()

    # Rendez-vous déjà passés (jours précédents), du plus récent au plus ancien
    past_qs = all_rdvs.filter(date__date__lt=today).order_by('-date')
    past_rdvs_count = past_qs.count()
    past_rdvs = past_qs[:50]

    MOIS_FR = ['','Janvier','Fevrier','Mars','Avril','Mai','Juin',
               'Juillet','Aout','Septembre','Octobre','Novembre','Decembre']

    prev_month = month - 1 or 12
    prev_year  = year - 1 if month == 1 else year
    next_month = month % 12 + 1
    next_year  = year + 1 if month == 12 else year

    return render(request, 'consultation/rdv_liste.html', {
        'weeks':              weeks,
        'rdvs_by_date':       rdvs_by_date,
        'today_rdvs':         today_rdvs,
        'past_rdvs':          past_rdvs,
        'past_rdvs_count':    past_rdvs_count,
        'today':              today,
        'year':               year,
        'month':              month,
        'month_name':         MOIS_FR[month],
        'month_rdvs_count':   month_rdvs_count,
        'prev_year':          prev_year,
        'prev_month':         prev_month,
        'next_year':          next_year,
        'next_month':         next_month,
        'q':                  q,
        'resultats_recherche': resultats_recherche,
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

def _dossiers_visibles(request):
    """Dossiers qu'un utilisateur peut voir. Un médecin ne voit que les dossiers
    dont il est propriétaire OU qui lui ont été transmis (partagés). L'admin (et
    les autres rôles non liés à une fiche médecin) voient tout."""
    base = DossierMedical.objects.all()
    medecin = _get_personnel(request.user, 'medecin')
    if medecin:
        base = base.filter(
            models.Q(medecin=medecin) | models.Q(partage_avec=medecin)
        ).distinct()
    return base, medecin


@permission_required('dossier.view')
def dossiers(request):
    visibles, medecin = _dossiers_visibles(request)
    qs = visibles.select_related('patient', 'medecin').order_by('-date_creation')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(termes_q(q, 'patient__nom', 'patient__prenom'))

    today = timezone.localdate()
    total_dossiers     = visibles.count()
    nouveaux_mois      = visibles.filter(date_creation__year=today.year, date_creation__month=today.month).count()
    patients_suivis    = visibles.values('patient').distinct().count()
    avec_consultations = visibles.filter(consultations__isnull=False).distinct().count()

    return render(request, 'consultation/dossiers.html', {
        'dossiers':           qs,
        'q':                  q,
        'total_dossiers':     total_dossiers,
        'nouveaux_mois':      nouveaux_mois,
        'patients_suivis':    patients_suivis,
        'avec_consultations': avec_consultations,
        'mon_medecin_id':     medecin.pk if medecin else None,
    })


@permission_required('dossier.view')
def dossier_detail(request, pk):
    dossier = get_object_or_404(
        DossierMedical.objects.select_related('patient', 'medecin'), pk=pk)
    medecin = _get_personnel(request.user, 'medecin')
    if medecin and not dossier.est_accessible_par(medecin):
        messages.error(request, "Ce dossier médical ne vous a pas été transmis.")
        return redirect('consultation:dossiers')
    # Le partage est réservé au propriétaire du dossier (ou à l'admin).
    est_proprietaire = bool(medecin and dossier.medecin_id in (medecin.pk, None))
    peut_partager = get_role(request.user) == 'admin' or est_proprietaire
    return render(request, 'consultation/dossier_detail.html', {
        'dossier':       dossier,
        'peut_partager': peut_partager,
    })


@permission_required('dossier.view')
def dossier_pdf(request, pk):
    dossier = get_object_or_404(DossierMedical, pk=pk)
    medecin = _get_personnel(request.user, 'medecin')
    if medecin and not dossier.est_accessible_par(medecin):
        messages.error(request, "Ce dossier médical ne vous a pas été transmis.")
        return redirect('consultation:dossiers')
    from .pdf import dossier_pdf_response
    return dossier_pdf_response(dossier)


def _notifier_medecin_dossier(dossier, medecin_cible, expediteur):
    """Prévient un médecin qu'un confrère lui a transmis un dossier (cloche).
    Une erreur ici ne doit pas empêcher le partage."""
    try:
        user = getattr(getattr(medecin_cible, 'profil', None), 'user', None)
        if not user:
            return
        from comptes.models import Notification
        Notification.creer(
            user=user,
            titre="Dossier médical transmis",
            message=f"{dossier.patient} — transmis par {expediteur.get_username()}",
            url=reverse('consultation:dossier_detail', args=[dossier.pk]),
            icone='bi-folder-symlink-fill',
        )
    except Exception:
        pass


@role_required('admin', 'medecin')
def dossier_partager(request, pk):
    """Transmet le dossier d'un patient à un ou plusieurs autres médecins.
    Seul le médecin propriétaire (ou l'admin) peut le faire."""
    dossier = get_object_or_404(
        DossierMedical.objects.select_related('patient', 'medecin'), pk=pk)
    medecin = _get_personnel(request.user, 'medecin')

    # Un médecin ne peut transmettre que SES propres dossiers.
    if medecin and dossier.medecin_id not in (medecin.pk, None):
        messages.error(request, "Seul le médecin propriétaire peut transmettre ce dossier.")
        return redirect('consultation:dossiers')

    if request.method == 'POST':
        ids = request.POST.getlist('medecins')
        cibles = Medecin.objects.filter(pk__in=ids).exclude(pk=dossier.medecin_id)
        n = 0
        for cible in cibles:
            dossier.partage_avec.add(cible)
            _notifier_medecin_dossier(dossier, cible, request.user)
            n += 1
        if n:
            messages.success(request, f"Dossier transmis à {n} médecin(s).")
        else:
            messages.info(request, "Aucun médecin sélectionné.")
        return redirect('consultation:dossier_detail', pk=dossier.pk)

    autres = Medecin.objects.all().order_by('nom', 'prenom')
    if dossier.medecin_id:
        autres = autres.exclude(pk=dossier.medecin_id)
    deja_partage = set(dossier.partage_avec.values_list('pk', flat=True))
    return render(request, 'consultation/dossier_partager.html', {
        'dossier':      dossier,
        'medecins':     autres,
        'deja_partage': deja_partage,
    })


# Consultations

@permission_required('consultation.view')
def consultation_liste(request):
    consultations = (Consultation.objects
                     .select_related('rendez_vous__patient', 'rendez_vous__medecin')
                     .prefetch_related('ordonnance_set')
                     .order_by('rendez_vous__patient__nom',
                               'rendez_vous__patient__prenom'))
    medecin = _get_personnel(request.user, 'medecin')
    if medecin:
        consultations = consultations.filter(rendez_vous__medecin=medecin)

    q = request.GET.get('q', '').strip()
    if q:
        consultations = consultations.filter(
            termes_q(q, 'rendez_vous__patient__nom', 'rendez_vous__patient__prenom',
                     'rendez_vous__medecin__nom', 'motif', 'diagnostic')
        )

    nb_ordonnance = consultations.filter(ordonnance__isnull=False).distinct().count()
    consultations, new_pk = nouveau_en_tete(request, consultations)
    return render(request, 'consultation/liste.html', {
        'consultations': consultations,
        'q': q,
        'new_pk': new_pk,
        'consultations_ordonnance': nb_ordonnance,
    })


@role_required('admin', 'medecin')
def consultation_ajouter(request):
    if request.method == 'POST':
        try:
            c = Consultation.objects.create(
                rendez_vous_id=request.POST['rendez_vous'],
                motif=request.POST['motif'],
                diagnostic=request.POST.get('diagnostic', ''),
                observation=request.POST.get('observation', ''),
            )
            # Toute consultation doit se conclure par une ordonnance :
            # on enchaîne directement sur le formulaire de prescription.
            messages.success(request,
                             "Consultation enregistrée. Prescrivez maintenant "
                             "l'ordonnance du patient pour la clôturer.")
            return redirect(f"{reverse('consultation:ordonnance_ajouter')}?consultation={c.pk}")
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


@permission_required('consultation.view')
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

@permission_required('examen.view')
def examens(request):
    qs = ExamenMedical.objects.select_related(
        'consultation__rendez_vous__patient',
        'consultation__rendez_vous__medecin',
    ).all().order_by('patient__nom', 'patient__prenom')
    role = getattr(getattr(request.user, 'profil', None), 'role', None)
    if role and role.code == 'medecin':
        # Le médecin ne voit que les examens qu'il a demandés lui-même.
        medecin = _get_personnel(request.user, 'medecin')
        qs = qs.filter(medecin=medecin) if medecin else qs.none()
    elif role and role.code == 'laborantin':
        # Le laborantin ne voit QUE les examens qui lui sont adressés.
        labo = _get_personnel(request.user, 'laborantin')
        qs = qs.filter(laborantin=labo) if labo else qs.none()

    # Statistiques calculées sur le périmètre visible par l'utilisateur
    stats_qs = qs

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            termes_q(q, 'type_examen',
                     'consultation__rendez_vous__patient__nom',
                     'consultation__rendez_vous__patient__prenom')
        )

    qs = qs.prefetch_related('resultats')
    examens_liste, new_pk = nouveau_en_tete(request, qs)
    return render(request, 'consultation/examens.html', {
        'examens':          examens_liste,
        'new_pk':           new_pk,
        'examens_termines': stats_qs.filter(resultats__isnull=False).distinct().count(),
        'examens_encours':  stats_qs.filter(resultats__isnull=True).count(),
    })


# Types d'examen proposés dans le formulaire (alignés sur les tarifs d'examen).
EXAMEN_TYPES = ['Radiographie', 'Échographie', 'Scanner', 'IRM', 'Prise de sang',
                "Analyse d'urine", 'Électrocardiogramme (ECG)', 'Endoscopie']


def _type_examen_from_post(request, defaut=''):
    """Type d'examen choisi : valeur de la liste, ou texte libre si « Autre »."""
    val = (request.POST.get('type_examen') or '').strip()
    if val == '__autre__':
        val = (request.POST.get('type_examen_autre') or '').strip()
    return val or defaut


def _notifier_laborantin_examen(examen):
    """Prévient le laborantin qu'un médecin lui a adressé un examen à réaliser
    (cloche). Une erreur ici ne doit jamais empêcher l'enregistrement de l'examen."""
    try:
        labo = examen.laborantin if examen.laborantin_id else None
        if not labo:
            return
        user = getattr(getattr(labo, 'profil', None), 'user', None)
        if not user:
            return
        from comptes.models import Notification
        medecin = f"Dr. {examen.medecin.nom}" if examen.medecin_id else "Un médecin"
        Notification.creer(
            user=user,
            titre="Nouvel examen à réaliser",
            message=f"{examen.type_examen} — {examen.patient} ({medecin})",
            url=reverse('consultation:examen_detail', args=[examen.pk]),
            icone='bi-eyedropper',
        )
    except Exception:
        pass


@permission_required('examen.demander')
def examen_ajouter(request):
    if request.method == 'POST':
        try:
            medecin_id = request.POST.get('medecin') or None
            if not medecin_id:
                m = _get_personnel(request.user, 'medecin')
                medecin_id = m.id if m else None
            ex = ExamenMedical.objects.create(
                patient_id=request.POST['patient'],
                consultation_id=request.POST['consultation'],
                laborantin_id=request.POST.get('laborantin') or None,
                medecin_id=medecin_id,
                type_examen=_type_examen_from_post(request),
                motif=request.POST.get('motif', ''),
                date=request.POST.get('date') or None,
            )
            # Le laborantin désigné est prévenu de l'examen qui lui est adressé.
            _notifier_laborantin_examen(ex)
            messages.success(request, 'Examen demande.')
            return redirect(f"{reverse('consultation:examens')}?new={ex.pk}")
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/examen_form.html', {
        'patients': Patient.objects.all(),
        'consultations': Consultation.objects.all().order_by('-date'),
        'laborantins': Laborantin.objects.all(),
        'medecins': Medecin.objects.all(),
        'examen_types': EXAMEN_TYPES,
        'action': 'Ajouter',
    })


@permission_required('examen.view')
def examen_detail(request, pk):
    """Vue en lecture seule d'un examen médical.

    Le laborantin ne peut pas ajouter ni modifier un examen : il consulte ici
    l'examen que le médecin lui a transmis et qu'il doit réaliser."""
    examen = get_object_or_404(
        ExamenMedical.objects.select_related(
            'consultation__rendez_vous__patient',
            'consultation__rendez_vous__medecin',
            'patient', 'medecin', 'laborantin',
        ).prefetch_related('resultats'),
        pk=pk,
    )
    return render(request, 'consultation/examen_detail.html', {'examen': examen})


# La demande et la modification d'un examen sont réservées au médecin (et à
# l'admin). Le laborantin, lui, ne fait que consulter (voir examen_detail).
@role_required('admin', 'medecin')
def examen_modifier(request, pk):
    examen = get_object_or_404(ExamenMedical, pk=pk)
    if request.method == 'POST':
        ancien_labo = examen.laborantin_id
        examen.type_examen = _type_examen_from_post(request, examen.type_examen)
        examen.motif = request.POST.get('motif', examen.motif)
        examen.date = request.POST.get('date') or examen.date
        if request.POST.get('laborantin'):
            examen.laborantin_id = request.POST['laborantin']
        examen.save()
        # Nouveau laborantin affecté (différent de l'ancien) → on le prévient.
        if examen.laborantin_id and examen.laborantin_id != ancien_labo:
            _notifier_laborantin_examen(examen)
        messages.success(request, 'Examen modifie.')
        return redirect('consultation:examens')

    return render(request, 'consultation/examen_form.html', {
        'examen': examen,
        'patients': Patient.objects.all(),
        'consultations': Consultation.objects.all().order_by('-date'),
        'laborantins': Laborantin.objects.all(),
        'medecins': Medecin.objects.all(),
        'examen_types': EXAMEN_TYPES,
        'action': 'Modifier',
    })


@role_required('admin')
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

@permission_required('resultat.view')
def resultats(request):
    qs = ResultatExamen.objects.select_related('patient', 'examen').order_by(
        'patient__nom', 'patient__prenom')
    role = getattr(getattr(request.user, 'profil', None), 'role', None)
    if role and role.code == 'laborantin':
        labo = _get_personnel(request.user, 'laborantin')
        if labo:
            qs = qs.filter(laborantin=labo)
    elif role and role.code == 'medecin':
        medecin = _get_personnel(request.user, 'medecin')
        if medecin:
            qs = qs.filter(examen__medecin=medecin, transmis=True)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(termes_q(q, 'patient__nom', 'patient__prenom', 'examen__type_examen'))

    resultats_liste, new_pk = nouveau_en_tete(request, qs)
    page = Paginator(resultats_liste, 25).get_page(request.GET.get('page'))
    return render(request, 'consultation/resultats_liste.html',
                  {'resultats': page, 'q': q, 'new_pk': new_pk})


@role_required('admin', 'laborantin')
def resultat_ajouter(request):
    examen_id = request.GET.get('examen')
    if request.method == 'POST':
        try:
            examen = get_object_or_404(ExamenMedical, pk=request.POST['examen'])
            labo = _get_personnel(request.user, 'laborantin')
            res = ResultatExamen.objects.create(
                patient=examen.patient,
                examen=examen,
                medecin=examen.medecin,
                laborantin=labo,
                resultat=request.POST['resultat'],
                observations=request.POST.get('observations', ''),
                image=request.FILES.get('image'),
            )
            messages.success(request, 'Resultat enregistre.')
            return redirect(f"{reverse('consultation:resultats')}?new={res.pk}")
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
        if request.FILES.get('image'):
            res.image = request.FILES['image']
        res.save()
        JournalAudit.enregistrer(request.user, 'modification', res)
        messages.success(request, 'Resultat modifie.')
        return redirect('consultation:resultats')
    return render(request, 'consultation/resultat_form.html', {
        'resultat': res,
        'action': 'Modifier',
    })


def _notifier_medecin_resultat(res):
    """Notifie le médecin qui a demandé l'examen que le résultat est disponible.
    Une erreur ici ne doit jamais empêcher la transmission du résultat."""
    try:
        from django.urls import reverse
        from comptes.models import Notification
        medecin = res.examen.medecin if res.examen_id else None
        if not medecin:
            return
        try:
            user = medecin.profil.user
        except Exception:
            user = None
        if not user:
            return
        Notification.creer(
            user=user,
            titre="Résultat d'examen disponible",
            message=f"{res.examen.type_examen} — {res.patient}",
            url=reverse('consultation:resultat_detail', args=[res.pk]),
            icone='bi-flask-fill',
        )
    except Exception:
        pass


@role_required('admin', 'laborantin')
def resultat_transmettre(request, pk):
    res = get_object_or_404(ResultatExamen, pk=pk)
    res.transmis = True
    res.date_transmission = timezone.now()
    # (Re)transmission → le médecin doit le (re)lire
    res.lu_par_medecin = False
    res.date_lecture = None
    res.save()
    _notifier_medecin_resultat(res)
    messages.success(request, 'Resultat transmis au medecin.')
    return redirect('consultation:resultats')


@permission_required('resultat.view')
def resultat_detail(request, pk):
    res = get_object_or_404(ResultatExamen, pk=pk)
    # Ouverture par le médecin concerné → résultat marqué comme lu
    # (update ciblé pour ne pas déclencher les effets de bord de save())
    medecin = _get_personnel(request.user, 'medecin')
    if (medecin and res.transmis and not res.lu_par_medecin
            and res.examen_id and res.examen.medecin_id == medecin.pk):
        ResultatExamen.objects.filter(pk=res.pk).update(
            lu_par_medecin=True, date_lecture=timezone.now())
        res.lu_par_medecin = True
    return render(request, 'consultation/resultat_detail.html', {'resultat': res})


def resultat_pdf(request, pk):
    res = get_object_or_404(ResultatExamen, pk=pk)
    from .pdf import resultat_pdf_response
    return resultat_pdf_response(res)


@role_required('admin', 'laborantin')
def resultat_supprimer(request, pk):
    res = get_object_or_404(ResultatExamen, pk=pk)
    if request.method == 'POST':
        JournalAudit.enregistrer(request.user, 'suppression', res)
        res.delete()
        messages.success(request, 'Resultat supprime.')
        return redirect('consultation:resultats')

    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Resultat RES-{pk:04d} - {res.examen.type_examen} ({res.patient})',
        'retour_url': '/consultation/resultats/',
    })


# Ordonnances

@permission_required('ordonnance.view')
def ordonnances(request):
    # nb_achats / date_achat : sorties de stock liées à l'ordonnance → indique
    # que les médicaments ont été achetés dans NOTRE pharmacie (et quand).
    qs = (Ordonnance.objects
          .select_related('consultation__rendez_vous__patient',
                          'consultation__rendez_vous__medecin')
          .annotate(
              nb_achats=models.Count(
                  'dispensations',
                  filter=models.Q(dispensations__type_mouvement='sortie')),
              date_achat=models.Max(
                  'dispensations__date',
                  filter=models.Q(dispensations__type_mouvement='sortie')),
          )
          .order_by('consultation__rendez_vous__patient__nom',
                    'consultation__rendez_vous__patient__prenom'))
    medecin = _get_personnel(request.user, 'medecin')
    if medecin:
        qs = qs.filter(consultation__rendez_vous__medecin=medecin)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            termes_q(q, 'consultation__rendez_vous__patient__nom',
                     'consultation__rendez_vous__patient__prenom',
                     'consultation__rendez_vous__medecin__nom', 'medicaments')
        )

    ordonnances_liste, new_pk = nouveau_en_tete(request, qs)
    return render(request, 'consultation/ordonnances.html', {
        'ordonnances': ordonnances_liste,
        'q': q,
        'new_pk': new_pk,
    })


@permission_required('ordonnance.add')
def ordonnance_ajouter(request):
    if request.method == 'POST':
        try:
            o = Ordonnance.objects.create(
                consultation_id=request.POST['consultation'],
                date=request.POST['date'],
                medicaments=request.POST['medicaments'],
            )
            messages.success(request, 'Ordonnance creee.')
            return redirect(f"{reverse('consultation:ordonnances')}?new={o.pk}")
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    from pharmacie.models import Medicament
    from pharmacie.specialites import code_specialite, SPECIALITES_DICT

    consultation_id = request.GET.get('consultation')
    consultations = list(Consultation.objects.select_related(
        'rendez_vous__patient', 'rendez_vous__medecin').order_by('-date'))
    for c in consultations:
        c.code_spec = code_specialite(c.rendez_vous.medecin.specialite) or ''

    catalogue = [{
        'libelle':     m.libelle(),
        'indication':  m.indication,
        'commun':      m.commun,
        'specialites': [s.code for s in m.specialites.all()],
    } for m in Medicament.objects.filter(actif=True).prefetch_related('specialites').order_by('nom')]

    return render(request, 'consultation/ordonnance_form.html', {
        'consultations':   consultations,
        'consultation_id': consultation_id,
        'catalogue':       catalogue,
        'specialites_map': SPECIALITES_DICT,
        'action':          'Creer',
    })


@permission_required('ordonnance.view')
def ordonnance_detail(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    return render(request, 'consultation/ordonnance_detail.html', {'ordonnance': ordonnance})


@permission_required('ordonnance.view')
def ordonnance_imprimer(request, pk):
    ordonnance = get_object_or_404(
        Ordonnance.objects.select_related(
            'consultation__rendez_vous__patient',
            'consultation__rendez_vous__medecin',
        ),
        pk=pk,
    )
    from .pdf import ordonnance_pdf_response
    return ordonnance_pdf_response(ordonnance)


@permission_required('ordonnance.delete')
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

@permission_required('hospitalisation.view')
def hospitalisations(request):
    from datetime import date, timedelta
    qs = Hospitalisation.objects.select_related('patient', 'medecin').all().order_by(
        'patient__nom', 'patient__prenom')

    # Un médecin ne voit que les hospitalisations dont il est le médecin traitant.
    # L'admin (non lié à une fiche médecin) voit tout.
    medecin = _get_personnel(request.user, 'medecin')
    if medecin:
        qs = qs.filter(medecin=medecin)

    # Filtre service (type_chambre)
    service_filtre = request.GET.get('service', '')
    if service_filtre:
        qs = qs.filter(type_chambre__iexact=service_filtre)

    # Recherche (patient, médecin, chambre)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            termes_q(q, 'patient__nom', 'patient__prenom', 'medecin__nom',
                     'numero_chambre', 'type_chambre')
        )

    # Stats et grille chambres également limitées au médecin connecté.
    base_h = Hospitalisation.objects.all()
    if medecin:
        base_h = base_h.filter(medecin=medecin)
    total_en_cours   = base_h.filter(date_sortie__isnull=True).count()
    patients_critiques = base_h.filter(etat_clinique='critique', date_sortie__isnull=True).count()
    today = date.today()
    sorties_prevues  = base_h.filter(date_sortie=today).count()

    # Services distincts pour le filtre
    services = Hospitalisation.objects.values_list('type_chambre', flat=True).distinct().order_by('type_chambre')

    # Grille chambres : plan fixe 101-110 (VIP), 201-210/301-302 (double), 303-310/401-410 (simple)
    occ_par_chambre = {}
    for h in (base_h.filter(date_sortie__isnull=True)
              .select_related('patient', 'medecin')):
        occ_par_chambre.setdefault(h.numero_chambre, []).append(h)
    sorties_jour = set(
        base_h.filter(date_sortie=today)
        .values_list('numero_chambre', flat=True)
    )
    type_par_num = dict(Hospitalisation.plan_chambres())

    etages = []
    chambres_libres = 0
    for centaine in [100, 200, 300, 400]:
        rangee = []
        for i in range(1, 11):
            num = str(centaine + i)
            type_ = type_par_num.get(num, 'simple')
            cap = Hospitalisation.capacite_pour(type_)
            occs = occ_par_chambre.get(num, [])
            n = len(occs)
            if n >= cap:
                statut_c = 'occupee'      # pleine
            elif n > 0:
                statut_c = 'partiel'      # des places restent libres
            elif num in sorties_jour:
                statut_c = 'nettoyage'
            else:
                statut_c = 'libre'
            if n < cap:
                chambres_libres += 1
            premier = occs[0] if occs else None
            rangee.append({
                'num': num,
                'statut': statut_c,
                'type': type_,
                'nom_type': _nom_chambre(type_),
                'occupants': n,
                'capacite': cap,
                'patient': f'{premier.patient.prenom} {premier.patient.nom}' if premier else '',
                'service': premier.type_chambre if premier else type_,
                'medecin': f'Dr. {premier.medecin.nom}' if premier else '',
            })
        etages.append(rangee)

    hospit_liste, new_pk = nouveau_en_tete(request, qs)
    return render(request, 'consultation/hospitalisations.html', {
        'hospitalisations': hospit_liste,
        'new_pk':           new_pk,
        'total_en_cours':   total_en_cours,
        'chambres_libres':  chambres_libres,
        'patients_critiques': patients_critiques,
        'sorties_prevues':  sorties_prevues,
        'services':         services,
        'service_filtre':   service_filtre,
        'q':                q,
        'etages':           etages,
        'total_chambres':   40,
    })


def _nom_chambre(type_chambre):
    """Libellé lisible d'un type de chambre (VIP / Double / Simple)."""
    return {'vip': 'VIP', 'double': 'Double', 'simple': 'Simple'}.get(
        (type_chambre or '').strip().lower(), (type_chambre or '').capitalize())


def _chambre_pleine(numero_chambre, type_chambre, exclure_pk=None):
    """Renvoie un message d'erreur si la chambre est déjà à sa capacité maximale, sinon None."""
    capacite = Hospitalisation.capacite_pour(type_chambre)
    occupants = Hospitalisation.occupants_actifs(numero_chambre, exclure_pk=exclure_pk)
    if occupants < capacite:
        return None
    numero = (numero_chambre or '').strip()
    nom = _nom_chambre(type_chambre)
    if capacite == 1:
        return (f"La chambre {numero} ({nom}) est déjà occupée : une chambre {nom} "
                f"ne peut accueillir qu'un seul patient à la fois.")
    return (f"La chambre {numero} ({nom}) est déjà remplie ({occupants}/{capacite}) : "
            f"une chambre {nom} ne peut accueillir que {capacite} patients.")


def _chambres_context(exclure_pk=None):
    """Liste des 40 chambres du plan avec leur occupation, pour le menu déroulant du formulaire."""
    chambres = []
    for numero, type_ in Hospitalisation.plan_chambres():
        cap = Hospitalisation.capacite_pour(type_)
        occ = Hospitalisation.occupants_actifs(numero, exclure_pk=exclure_pk)
        chambres.append({
            'numero': numero,
            'type': type_,
            'capacite': cap,
            'occupants': occ,
            'pleine': occ >= cap,
            'groupe': f"{_nom_chambre(type_)} — {cap} patient{'s' if cap > 1 else ''} max",
        })
    return chambres


def _form_context(action, hospit=None, form_data=None, exclure_pk=None):
    ctx = {
        'patients': Patient.objects.all(),
        'medecins': Medecin.objects.all(),
        'action': action,
        'chambres': _chambres_context(exclure_pk=exclure_pk),
    }
    if hospit is not None:
        ctx['hospit'] = hospit
    if form_data is not None:
        ctx['form_data'] = form_data
    return ctx


@permission_required('hospitalisation.add')
def hospit_ajouter(request):
    if request.method == 'POST':
        numero = (request.POST.get('numero_chambre') or '').strip()
        type_chambre = Hospitalisation.type_pour_numero(numero)
        if not type_chambre:
            erreur = f"La chambre {numero} n'existe pas dans le plan de l'établissement."
        else:
            erreur = _chambre_pleine(numero, type_chambre)
        if erreur:
            messages.error(request, erreur)
            return render(request, 'consultation/hospit_form.html',
                          _form_context('Ajouter', form_data=request.POST))
        try:
            h = Hospitalisation.objects.create(
                patient_id=request.POST['patient'],
                medecin_id=request.POST['medecin'],
                type_chambre=type_chambre,
                numero_chambre=numero,
                etat_clinique=request.POST.get('etat_clinique') or 'stable',
                nombre_jours=request.POST['nombre_jours'],
                date_entree=request.POST['date_entree'],
                date_sortie=request.POST.get('date_sortie') or None,
            )
            messages.success(request, 'Hospitalisation enregistree.')
            return redirect(f"{reverse('consultation:hospitalisations')}?new={h.pk}")
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/hospit_form.html', _form_context('Ajouter'))


@permission_required('hospitalisation.change')
def hospit_modifier(request, pk):
    hospit = get_object_or_404(Hospitalisation, pk=pk)
    if request.method == 'POST':
        numero = (request.POST.get('numero_chambre') or '').strip()
        type_chambre = Hospitalisation.type_pour_numero(numero)
        if not type_chambre:
            erreur = f"La chambre {numero} n'existe pas dans le plan de l'établissement."
        else:
            erreur = _chambre_pleine(numero, type_chambre, exclure_pk=hospit.pk)
        if erreur:
            messages.error(request, erreur)
            return render(request, 'consultation/hospit_form.html',
                          _form_context('Modifier', hospit=hospit, exclure_pk=hospit.pk))
        hospit.type_chambre = type_chambre
        hospit.numero_chambre = numero
        hospit.etat_clinique = request.POST.get('etat_clinique') or 'stable'
        hospit.nombre_jours = request.POST['nombre_jours']
        hospit.date_sortie = request.POST.get('date_sortie') or None
        hospit.save()
        messages.success(request, 'Hospitalisation modifiee.')
        return redirect('consultation:hospitalisations')

    return render(request, 'consultation/hospit_form.html',
                  _form_context('Modifier', hospit=hospit, exclure_pk=hospit.pk))


@permission_required('hospitalisation.change')
def hospit_sortie(request, pk):
    """Marque la sortie du patient (date de sortie = aujourd'hui)."""
    hospit = get_object_or_404(Hospitalisation, pk=pk)
    if request.method == 'POST':
        if hospit.date_sortie:
            messages.info(request, f'{hospit.patient} est déjà sorti(e).')
        else:
            hospit.date_sortie = timezone.localdate()
            hospit.save()
            messages.success(request, f'Sortie enregistrée pour {hospit.patient}.')
    return redirect('consultation:hospitalisations')


@permission_required('hospitalisation.delete')
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

@permission_required('traitement.view')
def traitements(request):
    qs = Traitement.objects.select_related(
        'patient',
        'consultation__rendez_vous__patient',
        'consultation__rendez_vous__medecin',
    ).order_by('patient__nom', 'patient__prenom')

    # Un médecin ne voit que les traitements qu'il a prescrits (rattachés à sa
    # consultation). L'admin (non lié à une fiche médecin) voit tout.
    medecin = _get_personnel(request.user, 'medecin')
    if medecin:
        qs = qs.filter(consultation__rendez_vous__medecin=medecin)

    # Recherche (patient, médecin, description)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            termes_q(q, 'patient__nom', 'patient__prenom',
                     'consultation__rendez_vous__medecin__nom', 'description')
        )

    base = Traitement.objects.all()
    if medecin:
        base = base.filter(consultation__rendez_vous__medecin=medecin)
    traitements_liste, new_pk = nouveau_en_tete(request, qs)
    return render(request, 'consultation/traitements.html', {
        'traitements': traitements_liste,
        'q': q,
        'new_pk': new_pk,
        'traitements_prescrits_count': base.filter(statut='prescrit').count(),
        'traitements_en_cours_count': base.filter(statut='en_cours').count(),
        'traitements_termines_count': base.filter(statut='termine').count(),
    })


def _notifier_infirmier_traitement(traitement):
    """Prévient l'infirmier qu'un médecin lui a confié le suivi d'un traitement
    (cloche). Une erreur ici ne doit jamais empêcher l'enregistrement du traitement."""
    try:
        infirmier = traitement.infirmier if traitement.infirmier_id else None
        if not infirmier:
            return
        user = getattr(getattr(infirmier, 'profil', None), 'user', None)
        if not user:
            return
        from comptes.models import Notification
        desc = (traitement.description or '').strip()
        if len(desc) > 80:
            desc = desc[:79] + '…'
        Notification.creer(
            user=user,
            titre="Nouveau traitement à suivre",
            message=f"{traitement.patient} — {desc}",
            url=reverse('consultation:traitement_detail', args=[traitement.pk]),
            icone='bi-capsule',
        )
    except Exception:
        pass


@role_required('admin', 'medecin')
def traitement_ajouter(request):
    if request.method == 'POST':
        try:
            t = Traitement.objects.create(
                patient_id=request.POST['patient'],
                consultation_id=request.POST.get('consultation') or None,
                infirmier_id=request.POST.get('infirmier') or None,
                description=request.POST['description'],
                duree=request.POST.get('duree', 1),
            )
            # L'infirmier désigné est prévenu du traitement dont il a la charge.
            _notifier_infirmier_traitement(t)
            messages.success(request, 'Traitement prescrit.')
            return redirect(f"{reverse('consultation:traitements')}?new={t.pk}")
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'consultation/traitement_form.html', {
        'patients': Patient.objects.all(),
        'consultations': Consultation.objects.all().order_by('-date'),
        'infirmiers': Infirmier.objects.all(),
        'action': 'Ajouter',
    })


def _progression_traitement(t):
    """Avancement d'un traitement : jour courant / durée, % et nb d'administrations.

    Sert au suivi de l'évolution : la progression par jour est dérivée de la date
    de prescription et de la durée prescrite ; un traitement terminé est à 100 %."""
    from datetime import date
    debut = timezone.localtime(t.date_creation).date() if t.date_creation else date.today()
    duree = t.duree or 0
    jours_ecoules = max(1, (date.today() - debut).days + 1)
    if t.statut == 'termine':
        pourcentage = 100
    elif duree > 0:
        pourcentage = min(100, round(jours_ecoules * 100 / duree))
    else:
        pourcentage = 0
    return {
        'jour_courant': min(jours_ecoules, duree) if duree else jours_ecoules,
        'duree': duree,
        'jours_restants': max(0, duree - jours_ecoules) if duree else 0,
        'pourcentage': pourcentage,
        'nb_administrations': t.administrations.count(),
    }


@permission_required('traitement.view')
def traitement_detail(request, pk):
    t = get_object_or_404(
        Traitement.objects.select_related('patient', 'infirmier'), pk=pk)
    administrations = t.administrations.select_related('infirmier').order_by('-date')
    return render(request, 'consultation/traitement_detail.html', {
        'traitement': t,
        'administrations': administrations,
        'progression': _progression_traitement(t),
    })


@permission_required('traitement.view')
def traitement_suivi(request, pk):
    """Évolution d'un traitement au format JSON (interrogé périodiquement par la
    page de détail pour un suivi en temps réel, sans rechargement)."""
    t = get_object_or_404(Traitement, pk=pk)
    prog = _progression_traitement(t)
    labels = dict(Traitement._meta.get_field('statut').choices)
    administrations = [{
        'id': a.id,
        'date': timezone.localtime(a.date).strftime('%d/%m/%Y'),
        'heure': timezone.localtime(a.date).strftime('%H:%M'),
        'infirmier': str(a.infirmier) if a.infirmier else '—',
        'note': a.note or '',
    } for a in t.administrations.select_related('infirmier').order_by('-date')]
    return JsonResponse({
        'statut': t.statut,
        'statut_label': labels.get(t.statut, t.statut),
        'pourcentage': prog['pourcentage'],
        'jour_courant': prog['jour_courant'],
        'duree': prog['duree'],
        'count': len(administrations),
        'administrations': administrations,
        'maj': timezone.localtime(timezone.now()).strftime('%H:%M:%S'),
    })


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


@role_required('admin', 'medecin', 'infirmier')
def traitement_statut(request, pk):
    """Change le statut d'un traitement (prescrit / en_cours / termine)."""
    t = get_object_or_404(Traitement, pk=pk)
    if request.method == 'POST':
        nouveau = request.POST.get('statut', '')
        valides = dict(Traitement._meta.get_field('statut').choices)
        if nouveau in valides:
            t.statut = nouveau
            t.save(update_fields=['statut'])
            messages.success(request, f'Traitement marqué « {valides[nouveau]} ».')
        else:
            messages.error(request, 'Statut invalide.')
    return redirect(request.META.get('HTTP_REFERER') or 'consultation:traitements')


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