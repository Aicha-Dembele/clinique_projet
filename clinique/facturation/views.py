from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum
from decimal import Decimal

from .models import Facture, LigneFacture, Paiement, Tarif, Assurance
from patients.models import Patient
from comptes.decorators import role_required


# ── Helpers ──────────────────────────────────────────────────────

def _fmt(val):
    """Format number with spaces as thousand separator."""
    try:
        return f"{int(val):,}".replace(',', ' ')
    except Exception:
        return '0'


# ── Factures ─────────────────────────────────────────────────────

@role_required('admin', 'receptionniste')
def facture_liste(request):
    qs = Facture.objects.select_related('patient', 'assurance').prefetch_related('lignes', 'paiements').order_by('-id')

    # Filtre statut
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)

    # Recherche patient
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(patient__nom__icontains=q) | qs.filter(patient__prenom__icontains=q)

    all_f = Facture.objects.all()
    total_paye    = all_f.filter(statut='payé').aggregate(t=Sum('montant_total'))['t'] or 0
    total_attente = all_f.filter(statut='non payé').aggregate(t=Sum('montant_total'))['t'] or 0

    return render(request, 'facturation/liste.html', {
        'factures':          qs,
        'total_paye':        _fmt(total_paye),
        'total_attente':     _fmt(total_attente),
        'factures_impayees': all_f.filter(statut='non payé').count(),
        'total_factures':    all_f.count(),
        'statut_filtre':     statut,
        'q':                 q,
    })


@role_required('admin', 'receptionniste')
def facture_detail(request, pk):
    facture = get_object_or_404(
        Facture.objects.select_related('patient', 'consultation', 'hospitalisation')
                       .prefetch_related('lignes', 'paiements'),
        pk=pk
    )
    return render(request, 'facturation/detail.html', {
        'facture':  facture,
        'montant_paye':    facture.montant_paye(),
        'montant_restant': facture.montant_restant(),
    })


@role_required('admin', 'receptionniste')
def facture_pdf(request, pk):
    """Télécharge / affiche la facture au format PDF (généré côté serveur)."""
    from .pdf import facture_pdf_response
    facture = get_object_or_404(
        Facture.objects.select_related('patient', 'assurance')
                       .prefetch_related('lignes', 'paiements'),
        pk=pk,
    )
    return facture_pdf_response(facture)


@role_required('admin', 'receptionniste')
def facture_ajouter(request):
    from consultation.models import Consultation, Hospitalisation

    if request.method == 'POST':
        try:
            patient_id      = request.POST['patient']
            consultation_id = request.POST.get('consultation') or None
            hospit_id       = request.POST.get('hospitalisation') or None

            facture = Facture(
                patient_id=patient_id,
                consultation_id=consultation_id,
                hospitalisation_id=hospit_id,
                assurance_id=request.POST.get('assurance') or None,
                notes=request.POST.get('notes', ''),
            )
            taux = request.POST.get('taux_prise_en_charge', '')
            if taux:
                facture.taux_prise_en_charge = Decimal(taux)
            facture.save()   # génère les lignes et calcule le total

            messages.success(request, f'Facture FAC-{str(facture.pk).zfill(4)} créée — Total : {_fmt(facture.montant_total)} FCFA')
            return redirect('facturation:detail', pk=facture.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    # GET — pré-sélection depuis URL (ex: ?patient=3&consultation=5)
    pre_patient      = request.GET.get('patient', '')
    pre_consultation = request.GET.get('consultation', '')
    pre_hospit       = request.GET.get('hospitalisation', '')

    consultations = Consultation.objects.select_related(
        'rendez_vous__patient', 'rendez_vous__medecin'
    ).prefetch_related('examenmedical_set').order_by('-date')

    # Toutes les hospitalisations (terminées ET en cours)
    hospitalisations = Hospitalisation.objects.select_related('patient').order_by('-date_entree')

    return render(request, 'facturation/form.html', {
        'patients':         Patient.objects.select_related('assurance').order_by('nom'),
        'consultations':    consultations,
        'hospitalisations': hospitalisations,
        'assurances':       Assurance.objects.filter(actif=True),
        'action':           'Créer',
        'pre_patient':      pre_patient,
        'pre_consultation': pre_consultation,
        'pre_hospit':       pre_hospit,
        'tarifs':           Tarif.objects.all().order_by('type_service', 'nom'),
    })


@role_required('admin', 'receptionniste')
def facture_modifier(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    from consultation.models import Consultation, Hospitalisation

    if request.method == 'POST':
        try:
            facture.patient_id         = request.POST['patient']
            facture.consultation_id    = request.POST.get('consultation') or None
            facture.hospitalisation_id = request.POST.get('hospitalisation') or None
            facture.assurance_id       = request.POST.get('assurance') or None
            taux = request.POST.get('taux_prise_en_charge', '')
            # taux saisi → on l'applique ; champ vidé → save() reprendra celui de l'assurance (ou 0)
            facture.taux_prise_en_charge = Decimal(taux) if taux else Decimal('0')
            facture.notes              = request.POST.get('notes', '')
            facture.save()   # recalcule tout

            messages.success(request, 'Facture mise à jour.')
            return redirect('facturation:detail', pk=facture.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    consultations_qs = Consultation.objects.select_related(
        'rendez_vous__patient', 'rendez_vous__medecin'
    ).prefetch_related('examenmedical_set').order_by('-date')

    return render(request, 'facturation/form.html', {
        'facture':          facture,
        'patients':         Patient.objects.select_related('assurance').order_by('nom'),
        'consultations':    consultations_qs,
        'hospitalisations': Hospitalisation.objects.select_related('patient').order_by('-date_entree'),
        'assurances':       Assurance.objects.filter(actif=True),
        'action':           'Modifier',
        'pre_patient':      '',
        'pre_consultation': '',
        'pre_hospit':       '',
        'tarifs':           Tarif.objects.all().order_by('type_service', 'nom'),
    })


@role_required('admin', 'receptionniste')
def facture_supprimer(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    if request.method == 'POST':
        facture.delete()
        messages.success(request, 'Facture supprimée.')
        return redirect('facturation:liste')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet':      f'Facture FAC-{str(pk).zfill(4)}',
        'retour_url': '/facturation/',
    })


# ── Recalcul manuel ──────────────────────────────────────────────

@role_required('admin', 'receptionniste')
def facture_recalculer(request, pk):
    """Force le recalcul d'une facture (utile si les tarifs ont changé)."""
    facture = get_object_or_404(Facture, pk=pk)
    facture.save()
    messages.success(request, f'Facture recalculée — Nouveau total : {_fmt(facture.montant_total)} FCFA')
    return redirect('facturation:detail', pk=pk)


# ── Paiements ────────────────────────────────────────────────────

@role_required('admin', 'receptionniste')
def paiement_liste(request):
    paiements = Paiement.objects.select_related('facture__patient').order_by('-date')
    total = paiements.aggregate(t=Sum('montant'))['t'] or 0
    return render(request, 'facturation/paiements.html', {
        'paiements':       paiements,
        'total_encaisse':  _fmt(total),
    })


@role_required('admin', 'receptionniste')
def paiement_ajouter(request):
    facture_id = request.GET.get('facture')
    if request.method == 'POST':
        try:
            facture = get_object_or_404(Facture, pk=request.POST['facture'])
            montant = Decimal(request.POST['montant'])
            if montant <= 0:
                raise ValueError("Le montant doit être positif.")
            if montant > facture.montant_restant():
                raise ValueError(f"Montant dépasse le restant dû ({_fmt(facture.montant_restant())} FCFA).")

            Paiement.objects.create(
                facture=facture,
                montant=montant,
                mode_paiement=request.POST['mode_paiement'],
                note=request.POST.get('note', ''),
            )
            messages.success(request, f'Paiement de {_fmt(montant)} FCFA enregistré.')
            return redirect('facturation:detail', pk=facture.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/paiement.html', {
        'factures':   Facture.objects.filter(statut__in=['non payé', 'partiel'])
                                     .select_related('patient', 'assurance')
                                     .prefetch_related('paiements'),
        'modes':      Paiement.MODE_CHOICES,
        'facture_id': facture_id,
        'action':     'Enregistrer',
    })


@role_required('admin', 'receptionniste')
def paiement_modifier(request, pk):
    paiement = get_object_or_404(Paiement, pk=pk)
    if request.method == 'POST':
        try:
            paiement.montant       = Decimal(request.POST['montant'])
            paiement.mode_paiement = request.POST['mode_paiement']
            paiement.note          = request.POST.get('note', '')
            new_fid = request.POST.get('facture')
            if new_fid and str(paiement.facture_id) != new_fid:
                paiement.facture_id = new_fid
            paiement.save()
            messages.success(request, 'Paiement modifié.')
            return redirect('facturation:paiements')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/paiement.html', {
        'paiement':   paiement,
        'factures':   Facture.objects.all().select_related('patient'),
        'modes':      Paiement.MODE_CHOICES,
        'facture_id': paiement.facture_id,
        'action':     'Modifier',
    })


@role_required('admin', 'receptionniste')
def paiement_supprimer(request, pk):
    paiement = get_object_or_404(Paiement, pk=pk)
    if request.method == 'POST':
        facture = paiement.facture
        paiement.delete()
        facture.update_statut()
        messages.success(request, 'Paiement supprimé.')
        return redirect('facturation:paiements')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet':      f'Paiement #{pk} — {paiement.montant:,.0f} FCFA',
        'retour_url': '/facturation/paiements/',
    })


@role_required('admin', 'receptionniste')
def paiement_recu(request, pk):
    paiement = get_object_or_404(Paiement.objects.select_related('facture__patient'), pk=pk)
    return render(request, 'facturation/recu.html', {'paiement': paiement})


# ── Rapports ─────────────────────────────────────────────────────

@role_required('admin')
def rapports(request):
    paiements = Paiement.objects.all()
    factures  = Facture.objects.all()

    def pct(mode):
        count = paiements.filter(mode_paiement=mode).count()
        return round(count * 100 / paiements.count()) if paiements.count() else 0

    return render(request, 'facturation/rapports.html', {
        'total_factures': factures.count(),
        'total_paye':     factures.filter(statut='payé').count(),
        'total_impaye':   factures.filter(statut='non payé').count(),
        'pct_especes':    pct('cash'),
        'pct_orange':     pct('orange_money'),
        'pct_moov':       pct('moov_money'),
        'pct_carte':      pct('carte'),
    })


# ── Tarifs ───────────────────────────────────────────────────────

@role_required('admin', 'receptionniste')
def tarif_liste(request):
    tarifs = Tarif.objects.all().order_by('type_service', 'nom')
    return render(request, 'facturation/tarifs.html', {
        'tarifs':          tarifs,
        'nb_consultation': tarifs.filter(type_service='consultation').count(),
        'nb_examen':       tarifs.filter(type_service='examen').count(),
        'nb_hospit':       tarifs.filter(type_service='hospitalisation').count(),
    })


@role_required('admin')
def tarif_ajouter(request):
    if request.method == 'POST':
        try:
            Tarif.objects.create(
                nom=request.POST['nom'],
                type_service=request.POST['type_service'],
                specialite=request.POST.get('specialite') or None,
                prix=request.POST['prix'],
            )
            messages.success(request, 'Tarif créé.')
            return redirect('facturation:tarifs')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/tarif_form.html', {
        'types':  Tarif.TYPE_CHOICES,
        'action': 'Créer',
    })


@role_required('admin')
def tarif_modifier(request, pk):
    tarif = get_object_or_404(Tarif, pk=pk)
    if request.method == 'POST':
        try:
            tarif.nom          = request.POST['nom']
            tarif.type_service = request.POST['type_service']
            tarif.specialite   = request.POST.get('specialite') or None
            tarif.prix         = request.POST['prix']
            tarif.save()
            messages.success(request, 'Tarif modifié.')
            return redirect('facturation:tarifs')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/tarif_form.html', {
        'tarif':  tarif,
        'types':  Tarif.TYPE_CHOICES,
        'action': 'Modifier',
    })


@role_required('admin')
def tarif_supprimer(request, pk):
    tarif = get_object_or_404(Tarif, pk=pk)
    if request.method == 'POST':
        tarif.delete()
        messages.success(request, 'Tarif supprimé.')
        return redirect('facturation:tarifs')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet':      f'Tarif "{tarif.nom}" — {tarif.prix:,.0f} FCFA',
        'retour_url': '/facturation/tarifs/',
    })


# ── Assurances ───────────────────────────────────────────────────

@role_required('admin', 'receptionniste')
def assurance_liste(request):
    assurances = Assurance.objects.all()
    return render(request, 'facturation/assurances.html', {
        'assurances':  assurances,
        'nb_actives':  assurances.filter(actif=True).count(),
        'nb_patients': Patient.objects.filter(assurance__isnull=False).count(),
    })


@role_required('admin')
def assurance_ajouter(request):
    if request.method == 'POST':
        try:
            Assurance.objects.create(
                nom=request.POST['nom'],
                taux_prise_en_charge=Decimal(request.POST.get('taux_prise_en_charge') or '0'),
                description=request.POST.get('description', ''),
                actif='actif' in request.POST,
            )
            messages.success(request, 'Assurance créée.')
            return redirect('facturation:assurances')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/assurance_form.html', {'action': 'Créer'})


@role_required('admin')
def assurance_modifier(request, pk):
    assurance = get_object_or_404(Assurance, pk=pk)
    if request.method == 'POST':
        try:
            assurance.nom                  = request.POST['nom']
            assurance.taux_prise_en_charge = Decimal(request.POST.get('taux_prise_en_charge') or '0')
            assurance.description          = request.POST.get('description', '')
            assurance.actif                = 'actif' in request.POST
            assurance.save()
            messages.success(request, 'Assurance modifiée.')
            return redirect('facturation:assurances')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/assurance_form.html', {
        'assurance': assurance,
        'action':    'Modifier',
    })


@role_required('admin')
def assurance_supprimer(request, pk):
    assurance = get_object_or_404(Assurance, pk=pk)
    if request.method == 'POST':
        assurance.delete()
        messages.success(request, 'Assurance supprimée.')
        return redirect('facturation:assurances')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet':      f'Assurance "{assurance.nom}" ({assurance.taux_prise_en_charge:.0f} %)',
        'retour_url': '/facturation/assurances/',
    })