from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Medicament, MouvementStock
from patients.models import Patient
from consultation.models import Ordonnance
from comptes.decorators import role_required


# ── Helpers ──────────────────────────────────────────────────────

def _fmt(val):
    """Format un nombre avec l'espace comme séparateur de milliers."""
    try:
        return f"{int(val):,}".replace(',', ' ')
    except Exception:
        return '0'


def _stats():
    """Indicateurs globaux du stock (réutilisés par la liste et le tableau de bord)."""
    qs = Medicament.objects.filter(actif=True)
    en_alerte = [m for m in qs if m.est_en_alerte()]
    rupture   = [m for m in qs if m.est_rupture()]
    valeur = qs.aggregate(
        v=Coalesce(Sum(F('prix_unitaire') * F('quantite_stock'),
                       output_field=DecimalField(max_digits=14, decimal_places=2)), 0,
                   output_field=DecimalField(max_digits=14, decimal_places=2))
    )['v']
    return {
        'nb_total':   qs.count(),
        'nb_alerte':  len(en_alerte),
        'nb_rupture': len(rupture),
        'valeur':     valeur,
    }


# ── Médicaments ──────────────────────────────────────────────────

@role_required('admin', 'receptionniste')
def medicament_liste(request):
    qs = Medicament.objects.all().order_by('nom')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(nom__icontains=q) | qs.filter(dci__icontains=q)

    categorie = request.GET.get('categorie', '')
    if categorie:
        qs = qs.filter(categorie=categorie)

    # Filtre d'état : alerte / rupture (évalués en Python car dépendent du seuil)
    etat = request.GET.get('etat', '')
    medicaments = list(qs)
    if etat == 'alerte':
        medicaments = [m for m in medicaments if m.est_en_alerte()]
    elif etat == 'rupture':
        medicaments = [m for m in medicaments if m.est_rupture()]
    elif etat == 'peremption':
        medicaments = [m for m in medicaments if m.est_perime() or m.bientot_perime()]

    stats = _stats()
    return render(request, 'pharmacie/medicaments.html', {
        'medicaments':  medicaments,
        'categories':   Medicament.CATEGORIE_CHOICES,
        'q':            q,
        'categorie':    categorie,
        'etat':         etat,
        'nb_total':     stats['nb_total'],
        'nb_alerte':    stats['nb_alerte'],
        'nb_rupture':   stats['nb_rupture'],
        'valeur_stock': _fmt(stats['valeur']),
    })


@role_required('admin', 'receptionniste')
def medicament_ajouter(request):
    if request.method == 'POST':
        try:
            Medicament.objects.create(
                nom=request.POST['nom'].strip(),
                dci=request.POST.get('dci', '').strip(),
                forme=request.POST.get('forme', '').strip(),
                dosage=request.POST.get('dosage', '').strip(),
                categorie=request.POST.get('categorie', ''),
                unite=request.POST.get('unite', 'boîte').strip() or 'boîte',
                prix_unitaire=request.POST.get('prix_unitaire') or 0,
                quantite_stock=request.POST.get('quantite_stock') or 0,
                seuil_alerte=request.POST.get('seuil_alerte') or 0,
                date_peremption=request.POST.get('date_peremption') or None,
                actif='actif' in request.POST,
            )
            messages.success(request, 'Médicament ajouté au stock.')
            return redirect('pharmacie:medicaments')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/medicament_form.html', {
        'categories': Medicament.CATEGORIE_CHOICES,
        'action':     'Ajouter',
    })


@role_required('admin', 'receptionniste')
def medicament_modifier(request, pk):
    medicament = get_object_or_404(Medicament, pk=pk)
    if request.method == 'POST':
        try:
            medicament.nom            = request.POST['nom'].strip()
            medicament.dci            = request.POST.get('dci', '').strip()
            medicament.forme          = request.POST.get('forme', '').strip()
            medicament.dosage         = request.POST.get('dosage', '').strip()
            medicament.categorie      = request.POST.get('categorie', '')
            medicament.unite          = request.POST.get('unite', 'boîte').strip() or 'boîte'
            medicament.prix_unitaire  = request.POST.get('prix_unitaire') or 0
            medicament.seuil_alerte   = request.POST.get('seuil_alerte') or 0
            medicament.date_peremption = request.POST.get('date_peremption') or None
            medicament.actif          = 'actif' in request.POST
            # Le stock ne se modifie PAS ici : il passe par les entrées/sorties
            medicament.save()
            messages.success(request, 'Médicament mis à jour.')
            return redirect('pharmacie:medicaments')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/medicament_form.html', {
        'medicament': medicament,
        'categories': Medicament.CATEGORIE_CHOICES,
        'action':     'Modifier',
    })


@role_required('admin')
def medicament_supprimer(request, pk):
    medicament = get_object_or_404(Medicament, pk=pk)
    if request.method == 'POST':
        medicament.delete()
        messages.success(request, 'Médicament supprimé.')
        return redirect('pharmacie:medicaments')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet':      f'Médicament « {medicament.nom} » ({medicament.quantite_stock} {medicament.unite})',
        'retour_url': '/pharmacie/',
    })


# ── Entrée de stock (réapprovisionnement) ────────────────────────

@role_required('admin', 'receptionniste')
def entree_stock(request):
    pre_medicament = request.GET.get('medicament', '')
    if request.method == 'POST':
        try:
            medicament = get_object_or_404(Medicament, pk=request.POST['medicament'])
            quantite = int(request.POST.get('quantite') or 0)
            if quantite <= 0:
                raise ValueError("La quantité doit être supérieure à zéro.")
            MouvementStock.objects.create(
                medicament=medicament,
                type_mouvement='entree',
                quantite=quantite,
                motif=request.POST.get('motif', '').strip() or 'Réapprovisionnement',
                utilisateur=request.user,
            )
            messages.success(request, f'+{quantite} {medicament.unite} ajoutés au stock de {medicament.nom}.')
            return redirect('pharmacie:medicaments')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/entree_form.html', {
        'medicaments':    Medicament.objects.filter(actif=True).order_by('nom'),
        'pre_medicament': pre_medicament,
    })


# ── Sortie de stock (dispensation) ───────────────────────────────

@role_required('admin', 'receptionniste')
def sortie_stock(request):
    pre_medicament = request.GET.get('medicament', '')
    if request.method == 'POST':
        try:
            medicament = get_object_or_404(Medicament, pk=request.POST['medicament'])
            quantite = int(request.POST.get('quantite') or 0)
            if quantite <= 0:
                raise ValueError("La quantité doit être supérieure à zéro.")
            if quantite > medicament.quantite_stock:
                raise ValueError(
                    f"Stock insuffisant : seulement {medicament.quantite_stock} {medicament.unite} disponible(s).")
            MouvementStock.objects.create(
                medicament=medicament,
                type_mouvement='sortie',
                quantite=quantite,
                motif=request.POST.get('motif', '').strip() or 'Dispensation',
                patient_id=request.POST.get('patient') or None,
                ordonnance_id=request.POST.get('ordonnance') or None,
                utilisateur=request.user,
            )
            messages.success(request, f'-{quantite} {medicament.unite} dispensés de {medicament.nom}.')
            return redirect('pharmacie:medicaments')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/sortie_form.html', {
        'medicaments':    Medicament.objects.filter(actif=True).order_by('nom'),
        'patients':       Patient.objects.order_by('nom'),
        'ordonnances':    Ordonnance.objects.select_related(
                              'consultation__rendez_vous__patient').order_by('-date')[:100],
        'pre_medicament': pre_medicament,
    })


# ── Historique des mouvements ────────────────────────────────────

@role_required('admin', 'receptionniste')
def mouvement_liste(request):
    qs = MouvementStock.objects.select_related('medicament', 'patient', 'utilisateur').order_by('-date')

    type_m = request.GET.get('type', '')
    if type_m in ('entree', 'sortie'):
        qs = qs.filter(type_mouvement=type_m)

    medicament_id = request.GET.get('medicament', '')
    if medicament_id:
        qs = qs.filter(medicament_id=medicament_id)

    return render(request, 'pharmacie/mouvements.html', {
        'mouvements':  qs[:300],
        'medicaments': Medicament.objects.order_by('nom'),
        'type_filtre': type_m,
        'medicament_filtre': medicament_id,
        'nb_entrees':  MouvementStock.objects.filter(type_mouvement='entree').count(),
        'nb_sorties':  MouvementStock.objects.filter(type_mouvement='sortie').count(),
    })


@role_required('admin')
def mouvement_supprimer(request, pk):
    mouvement = get_object_or_404(MouvementStock, pk=pk)
    if request.method == 'POST':
        mouvement.delete()   # annule l'effet sur le stock
        messages.success(request, 'Mouvement annulé — stock réajusté.')
        return redirect('pharmacie:mouvements')
    return render(request, 'partials/confirmer_suppression.html', {
        'objet':      f'Mouvement {mouvement.get_type_mouvement_display()} de {mouvement.quantite} '
                      f'{mouvement.medicament.unite} ({mouvement.medicament.nom})',
        'retour_url': '/pharmacie/mouvements/',
    })
