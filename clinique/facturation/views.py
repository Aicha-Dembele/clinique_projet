from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from .models import Facture, Paiement, Tarif
from patients.models import Patient

@login_required
def facture_liste(request):
    qs = Facture.objects.all().order_by('-id')
    total_paye = sum(f.montant_total for f in qs.filter(statut='payé'))
    total_attente = sum(f.montant_total for f in qs.filter(statut='non payé'))
    return render(request, 'facturation/liste.html', {
        'factures': qs,
        'total_paye': f"{int(total_paye):,}".replace(',', ' '),
        'total_attente': f"{int(total_attente):,}".replace(',', ' '),
        'factures_impayees': qs.filter(statut='non payé').count(),
        'total_factures': qs.count(),
    })

@login_required
def facture_detail(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    return render(request, 'facturation/detail.html', {'facture': facture})

@login_required
def facture_ajouter(request):
    if request.method == 'POST':
        try:
            Facture.objects.create(
                patient_id=request.POST['patient'],
                consultation_id=request.POST.get('consultation') or None,
                examen_id=request.POST.get('examen') or None,
                hospitalisation_id=request.POST.get('hospitalisation') or None,
            )
            messages.success(request, 'Facture créée.')
            return redirect('facturation:liste')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    from consultation.models import Consultation, ExamenMedical, Hospitalisation
    return render(request, 'facturation/form.html', {
        'patients': Patient.objects.all().order_by('nom'),
        'consultations': Consultation.objects.all().order_by('-date'),
        'examens': ExamenMedical.objects.all(),
        'hospitalisations': Hospitalisation.objects.all(),
        'action': 'Créer',
    })

@login_required
def facture_modifier(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    if request.method == 'POST':
        try:
            facture.patient_id = request.POST['patient']
            facture.consultation_id = request.POST.get('consultation') or None
            facture.examen_id = request.POST.get('examen') or None
            facture.hospitalisation_id = request.POST.get('hospitalisation') or None
            facture.statut = request.POST.get('statut', facture.statut)
            facture.save()
            messages.success(request, 'Facture modifiée.')
            return redirect('facturation:detail', pk=facture.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    from consultation.models import Consultation, ExamenMedical, Hospitalisation
    return render(request, 'facturation/form.html', {
        'facture': facture,
        'patients': Patient.objects.all().order_by('nom'),
        'consultations': Consultation.objects.all().order_by('-date'),
        'examens': ExamenMedical.objects.all(),
        'hospitalisations': Hospitalisation.objects.all(),
        'action': 'Modifier',
    })

@login_required
def facture_supprimer(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    if request.method == 'POST':
        facture.delete()
        messages.success(request, 'Facture supprimée.')
        return redirect('facturation:liste')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Facture FAC-{str(pk).zfill(4)}',
        'retour_url': '/facturation/',
    })

# ── Paiements ────────────────────────────────────────────

@login_required
def paiement_liste(request):
    paiements = Paiement.objects.all().order_by('-date')
    total = sum(p.montant for p in paiements)
    return render(request, 'facturation/paiements.html', {
        'paiements': paiements,
        'total_encaisse': f"{int(total):,}".replace(',', ' '),
    })

@login_required
def paiement_ajouter(request):
    facture_id = request.GET.get('facture')
    if request.method == 'POST':
        try:
            Paiement.objects.create(
                facture_id=request.POST['facture'],
                montant=request.POST['montant'],
                mode_paiement=request.POST['mode_paiement'],
            )
            facture = Facture.objects.get(pk=request.POST['facture'])
            facture.statut = 'payé'
            facture.save()
            messages.success(request, 'Paiement enregistré avec succès.')
            return redirect('facturation:paiements')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/paiement.html', {
        'factures': Facture.objects.filter(statut='non payé'),
        'modes': Paiement.MODE_CHOICES,
        'facture_id': facture_id,
        'action': 'Enregistrer',
    })

@login_required
def paiement_modifier(request, pk):
    paiement = get_object_or_404(Paiement, pk=pk)
    if request.method == 'POST':
        try:
            paiement.montant = request.POST['montant']
            paiement.mode_paiement = request.POST['mode_paiement']
            new_facture_id = request.POST.get('facture')
            if new_facture_id and str(paiement.facture_id) != new_facture_id:
                paiement.facture_id = new_facture_id
            paiement.save()
            messages.success(request, 'Paiement modifié.')
            return redirect('facturation:paiements')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/paiement.html', {
        'paiement': paiement,
        'factures': Facture.objects.all(),
        'modes': Paiement.MODE_CHOICES,
        'facture_id': paiement.facture_id,
        'action': 'Modifier',
    })

@login_required
def paiement_supprimer(request, pk):
    paiement = get_object_or_404(Paiement, pk=pk)
    if request.method == 'POST':
        facture = paiement.facture
        paiement.delete()
        if not facture.paiements.exists():
            facture.statut = 'non payé'
            facture.save()
        messages.success(request, 'Paiement supprimé.')
        return redirect('facturation:paiements')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Paiement #{pk} — {paiement.montant} FCFA',
        'retour_url': '/facturation/paiements/',
    })

@login_required
def paiement_recu(request, pk):
    paiement = get_object_or_404(Paiement, pk=pk)
    return render(request, 'facturation/recu.html', {'paiement': paiement})

@login_required
def rapports(request):
    paiements = Paiement.objects.all()
    factures = Facture.objects.all()

    def pct(mode):
        count = paiements.filter(mode_paiement=mode).count()
        return round(count * 100 / paiements.count()) if paiements.count() else 0

    return render(request, 'facturation/rapports.html', {
        'total_factures': factures.count(),
        'total_paye': factures.filter(statut='payé').count(),
        'total_impaye': factures.filter(statut='non payé').count(),
        'pct_especes': pct('cash'),
        'pct_orange': pct('orange_money'),
        'pct_moov': pct('moov_money'),
        'pct_carte': pct('carte'),
    })

# ── Tarifs ───────────────────────────────────────────────

@login_required
def tarif_liste(request):
    tarifs = Tarif.objects.all().order_by('type_service', 'prix')
    return render(request, 'facturation/tarifs.html', {
        'tarifs': tarifs,
        'nb_consultation': tarifs.filter(type_service='consultation').count(),
        'nb_examen': tarifs.filter(type_service='examen').count(),
        'nb_hospit': tarifs.filter(type_service='hospitalisation').count(),
    })

@login_required
def tarif_ajouter(request):
    if request.method == 'POST':
        try:
            Tarif.objects.create(
                nom=request.POST['nom'],
                type_service=request.POST['type_service'],
                specialite=request.POST.get('specialite') or None,
                prix=request.POST['prix'],
            )
            messages.success(request, 'Tarif créé avec succès.')
            return redirect('facturation:tarifs')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/tarif_form.html', {
        'types': Tarif.TYPE_CHOICES,
        'action': 'Créer',
    })

@login_required
def tarif_modifier(request, pk):
    tarif = get_object_or_404(Tarif, pk=pk)
    if request.method == 'POST':
        try:
            tarif.nom = request.POST['nom']
            tarif.type_service = request.POST['type_service']
            tarif.specialite = request.POST.get('specialite') or None
            tarif.prix = request.POST['prix']
            tarif.save()
            messages.success(request, 'Tarif modifié.')
            return redirect('facturation:tarifs')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'facturation/tarif_form.html', {
        'tarif': tarif,
        'types': Tarif.TYPE_CHOICES,
        'action': 'Modifier',
    })

@login_required
def tarif_supprimer(request, pk):
    tarif = get_object_or_404(Tarif, pk=pk)
    if request.method == 'POST':
        tarif.delete()
        messages.success(request, 'Tarif supprimé.')
        return redirect('facturation:tarifs')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet': f'Tarif "{tarif.nom}" — {tarif.prix} FCFA',
        'retour_url': '/facturation/tarifs/',
    })
