import re
import unicodedata
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum, F, Q, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Medicament, MouvementStock, Specialite
from patients.models import Patient
from consultation.models import Ordonnance
from comptes.decorators import role_required, permission_required
from comptes.recherche import termes_q


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


def _facture_pour_dispensation(patient_id, ordonnance_id):
    """Facture sur laquelle porter un médicament dispensé à un patient.

    Le patient de la sortie fait FOI : on ne rattache jamais le médicament à la
    facture d'un autre patient. L'ordonnance n'est utilisée que si sa consultation
    appartient bien à ce patient.

    - Ordonnance valide (même patient) → facture de sa consultation (créée si besoin).
    - Sinon → dernière facture non soldée du patient (créée si aucune).
    """
    from facturation.models import Facture
    from consultation.models import Ordonnance

    try:
        patient_id = int(patient_id)
    except (TypeError, ValueError):
        return None

    consultation = None
    if ordonnance_id:
        ordo = (Ordonnance.objects
                .select_related('consultation__rendez_vous')
                .filter(pk=ordonnance_id).first())
        # On n'utilise l'ordonnance que si sa consultation est bien CELLE du patient
        if ordo and ordo.consultation and ordo.consultation.rendez_vous.patient_id == patient_id:
            consultation = ordo.consultation

    if consultation:
        facture = Facture.objects.filter(consultation=consultation).first()
        if facture is None:
            facture = Facture(patient_id=patient_id, consultation=consultation)
            facture.save()
        return facture

    # Repli : on porte le médicament sur une facture non soldée du patient
    facture = (Facture.objects
               .filter(patient_id=patient_id)
               .exclude(statut='payé')
               .order_by('-date_creation')
               .first())
    if facture is None:
        facture = Facture(patient_id=patient_id)
        facture.save()
    return facture


# ── Ordonnance → stock (analyse pour la dispensation) ────────────

def _norm_nom(s):
    """Normalise un nom de médicament : sans accents, casse ni espaces superflus."""
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(s.lower().replace('-', ' ').split())


def _index_medicaments():
    """Index des médicaments par libellé ET par nom normalisés (matching O(1), sans N+1)."""
    idx = {}
    for m in Medicament.objects.all():
        idx.setdefault(_norm_nom(m.libelle()), m)
        idx.setdefault(_norm_nom(m.nom), m)
        if m.dosage:
            idx.setdefault(_norm_nom(f"{m.nom} {m.dosage}"), m)
    return idx


def _analyser_ordonnance(ordonnance, index):
    """Découpe le texte libre d'une ordonnance en lignes médicament + statut de stock.

    Le médecin saisit une ligne par médicament, au format « - Libellé : posologie »
    (l'assistant de prescription insère le libellé exact du catalogue). On rattache
    chaque ligne au médicament du stock pour signaler sa disponibilité :
      - 'disponible' : présent au catalogue et en stock
      - 'rupture'    : présent au catalogue mais stock épuisé
      - 'absent'     : introuvable au catalogue (pas géré par notre pharmacie)
    """
    lignes = []
    for brute in (ordonnance.medicaments or '').splitlines():
        texte = brute.strip().lstrip('-•*').strip()
        if not texte:
            continue
        nom_part, _, posologie = texte.partition(':')
        nom_part = nom_part.strip()
        if not nom_part:
            continue
        med = index.get(_norm_nom(nom_part))
        if med is None:
            # Réessaie en retirant la forme entre parenthèses, ex. « (comprimé) ».
            med = index.get(_norm_nom(re.sub(r'\(.*?\)', '', nom_part)))
        if med is None:
            statut = 'absent'
        elif med.quantite_stock > 0:
            statut = 'disponible'
        else:
            statut = 'rupture'
        lignes.append({
            'nom':           nom_part,
            'posologie':     posologie.strip(),
            'medicament_id': med.pk if med else None,
            'statut':        statut,
            'stock':         med.quantite_stock if med else 0,
            'unite':         med.unite if med else '',
            'prix':          float(med.prix_unitaire) if med else 0,
        })
    return lignes


def _ordonnances_par_patient():
    """Carte { patient_id (str) : [ordonnances analysées] } pour le formulaire de sortie."""
    index = _index_medicaments()
    ordonnances = (Ordonnance.objects
                   .select_related('consultation__rendez_vous__patient')
                   .order_by('-date')[:100])
    data = {}
    for o in ordonnances:
        try:
            pid = o.consultation.rendez_vous.patient_id
        except Exception:
            pid = None
        if not pid:
            continue
        data.setdefault(str(pid), []).append({
            'id':     o.pk,
            'date':   o.date.strftime('%d/%m/%Y') if o.date else '',
            'lignes': _analyser_ordonnance(o, index),
        })
    return data


def _dispenser_groupe(request):
    """Dispense en une fois les médicaments cochés d'une ordonnance.

    Retourne une HttpResponse de redirection si une action a eu lieu, sinon None
    (pour que la vue ré-affiche le formulaire avec les messages d'erreur).
    """
    patient_id = request.POST.get('patient') or None
    ordonnance_id = request.POST.get('ordonnance') or None
    if not patient_id:
        messages.error(request, "Sélectionnez d'abord le patient pour dispenser son ordonnance.")
        return None

    facture = _facture_pour_dispensation(patient_id, ordonnance_id)
    faits, erreurs = [], []
    for mid, q in zip(request.POST.getlist('ligne_med'), request.POST.getlist('ligne_qte')):
        med = Medicament.objects.filter(pk=mid).first()
        if not med:
            continue
        try:
            qte = int(q or 0)
        except ValueError:
            qte = 0
        if qte <= 0:
            continue
        if qte > med.quantite_stock:
            erreurs.append(f"{med.nom} (stock : {med.quantite_stock} {med.unite})")
            continue
        MouvementStock.objects.create(
            medicament=med, type_mouvement='sortie', quantite=qte,
            prix_unitaire=med.prix_unitaire or Decimal('0'),
            motif='Dispensation ordonnance',
            patient_id=patient_id, ordonnance_id=ordonnance_id,
            utilisateur=request.user, facture=facture,
        )
        faits.append(f"{med.nom} ×{qte}")

    if facture is not None and faits:
        facture.save()  # recalcule la facture en incluant les médicaments dispensés

    if faits:
        msg = f"{len(faits)} médicament(s) dispensé(s) : " + ', '.join(faits) + '.'
        if facture is not None:
            msg += (f" Facturé à {facture.patient} (FAC-{facture.pk:04d} — "
                    f"{facture.montant_total:,.0f} FCFA).").replace(',', ' ')
        messages.success(request, msg)
    if erreurs:
        messages.error(request, "Stock insuffisant, non dispensé(s) : " + ', '.join(erreurs) + '.')
    if not faits and not erreurs:
        messages.info(request, "Aucun médicament sélectionné à dispenser.")
        return None
    return redirect('pharmacie:medicaments')


# ── Médicaments ──────────────────────────────────────────────────

@permission_required('pharmacie.view')
def medicament_liste(request):
    qs = Medicament.objects.all().order_by('nom')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(termes_q(q, 'nom', 'dci'))

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


@role_required('admin', 'receptionniste', 'pharmacien')
def medicament_ajouter(request):
    if request.method == 'POST':
        try:
            medicament = Medicament.objects.create(
                nom=request.POST['nom'].strip(),
                dci=request.POST.get('dci', '').strip(),
                forme=request.POST.get('forme', '').strip(),
                dosage=request.POST.get('dosage', '').strip(),
                categorie=request.POST.get('categorie', ''),
                indication=request.POST.get('indication', '').strip(),
                commun='commun' in request.POST,
                unite=request.POST.get('unite', 'boîte').strip() or 'boîte',
                prix_unitaire=request.POST.get('prix_unitaire') or 0,
                quantite_stock=request.POST.get('quantite_stock') or 0,
                seuil_alerte=request.POST.get('seuil_alerte') or 0,
                date_peremption=request.POST.get('date_peremption') or None,
                actif='actif' in request.POST,
            )
            medicament.specialites.set(
                Specialite.objects.filter(code__in=request.POST.getlist('specialites')))
            messages.success(request, 'Médicament ajouté au stock.')
            return redirect('pharmacie:medicaments')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/medicament_form.html', {
        'categories':  Medicament.CATEGORIE_CHOICES,
        'specialites': Specialite.objects.all(),
        'action':      'Ajouter',
    })


@role_required('admin', 'receptionniste', 'pharmacien')
def medicament_modifier(request, pk):
    medicament = get_object_or_404(Medicament, pk=pk)
    if request.method == 'POST':
        try:
            medicament.nom            = request.POST['nom'].strip()
            medicament.dci            = request.POST.get('dci', '').strip()
            medicament.forme          = request.POST.get('forme', '').strip()
            medicament.dosage         = request.POST.get('dosage', '').strip()
            medicament.categorie      = request.POST.get('categorie', '')
            medicament.indication     = request.POST.get('indication', '').strip()
            medicament.commun         = 'commun' in request.POST
            medicament.unite          = request.POST.get('unite', 'boîte').strip() or 'boîte'
            medicament.prix_unitaire  = request.POST.get('prix_unitaire') or 0
            medicament.seuil_alerte   = request.POST.get('seuil_alerte') or 0
            medicament.date_peremption = request.POST.get('date_peremption') or None
            medicament.actif          = 'actif' in request.POST
            # Le stock ne se modifie PAS ici : il passe par les entrées/sorties
            medicament.save()
            medicament.specialites.set(
                Specialite.objects.filter(code__in=request.POST.getlist('specialites')))
            messages.success(request, 'Médicament mis à jour.')
            return redirect('pharmacie:medicaments')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/medicament_form.html', {
        'medicament':       medicament,
        'categories':       Medicament.CATEGORIE_CHOICES,
        'specialites':      Specialite.objects.all(),
        'medic_spec_codes': list(medicament.specialites.values_list('code', flat=True)),
        'action':           'Modifier',
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

@role_required('admin', 'receptionniste', 'pharmacien')
def entree_stock(request):
    pre_medicament = request.GET.get('medicament', '')
    if request.method == 'POST':
        try:
            medicament = get_object_or_404(Medicament, pk=request.POST['medicament'])
            quantite = int(request.POST.get('quantite') or 0)
            if quantite <= 0:
                raise ValueError("La quantité doit être supérieure à zéro.")
            prix = request.POST.get('prix_unitaire')
            prix = Decimal(prix) if prix else (medicament.prix_unitaire or Decimal('0'))
            MouvementStock.objects.create(
                medicament=medicament,
                type_mouvement='entree',
                quantite=quantite,
                prix_unitaire=prix,
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

@role_required('admin', 'receptionniste', 'pharmacien')
def sortie_stock(request):
    pre_medicament = request.GET.get('medicament', '')
    if request.method == 'POST' and 'ligne_med' in request.POST:
        # ── Dispensation groupée depuis l'ordonnance du patient ──
        reponse = _dispenser_groupe(request)
        if reponse is not None:
            return reponse
    elif request.method == 'POST':
        # ── Sortie manuelle d'un seul médicament (hors ordonnance) ──
        try:
            medicament = get_object_or_404(Medicament, pk=request.POST['medicament'])
            quantite = int(request.POST.get('quantite') or 0)
            if quantite <= 0:
                raise ValueError("La quantité doit être supérieure à zéro.")
            if quantite > medicament.quantite_stock:
                raise ValueError(
                    f"Stock insuffisant : seulement {medicament.quantite_stock} {medicament.unite} disponible(s).")
            prix = request.POST.get('prix_unitaire')
            prix = Decimal(prix) if prix else (medicament.prix_unitaire or Decimal('0'))
            patient_id = request.POST.get('patient') or None
            ordonnance_id = request.POST.get('ordonnance') or None

            # Dispensation à un patient → portée automatiquement sur sa facture
            facture = _facture_pour_dispensation(patient_id, ordonnance_id) if patient_id else None

            MouvementStock.objects.create(
                medicament=medicament,
                type_mouvement='sortie',
                quantite=quantite,
                prix_unitaire=prix,
                motif=request.POST.get('motif', '').strip() or 'Dispensation',
                patient_id=patient_id,
                ordonnance_id=ordonnance_id,
                utilisateur=request.user,
                facture=facture,
            )
            if facture is not None:
                facture.save()  # recalcule la facture en incluant ce médicament
                messages.success(
                    request,
                    f'-{quantite} {medicament.unite} dispensés. Médicament facturé à '
                    f'{facture.patient} (FAC-{facture.pk:04d} — {facture.montant_total:,.0f} FCFA).'
                    .replace(',', ' '))
            else:
                messages.success(request, f'-{quantite} {medicament.unite} dispensés de {medicament.nom}.')
            return redirect('pharmacie:medicaments')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/sortie_form.html', {
        'medicaments':      Medicament.objects.filter(actif=True).order_by('nom'),
        'patients':         Patient.objects.order_by('nom'),
        'ordonnances':      Ordonnance.objects.select_related(
                                'consultation__rendez_vous__patient').order_by('-date')[:100],
        'ordo_par_patient': _ordonnances_par_patient(),
        'pre_medicament':   pre_medicament,
    })


# ── Historique des mouvements ────────────────────────────────────

@permission_required('pharmacie.view')
def mouvement_liste(request):
    qs = MouvementStock.objects.select_related('medicament', 'patient', 'utilisateur', 'facture').order_by('-date')

    type_m = request.GET.get('type', '')
    if type_m in ('entree', 'sortie'):
        qs = qs.filter(type_mouvement=type_m)

    medicament_id = request.GET.get('medicament', '')
    if medicament_id:
        qs = qs.filter(medicament_id=medicament_id)

    # Totaux valorisés (prix figé × quantité), calculés sur les mouvements filtrés
    _dec = DecimalField(max_digits=16, decimal_places=2)
    montant = F('prix_unitaire') * F('quantite')
    totaux = qs.aggregate(
        val_entrees=Coalesce(Sum(montant, filter=Q(type_mouvement='entree'), output_field=_dec), 0, output_field=_dec),
        val_sorties=Coalesce(Sum(montant, filter=Q(type_mouvement='sortie'), output_field=_dec), 0, output_field=_dec),
    )

    return render(request, 'pharmacie/mouvements.html', {
        'mouvements':  qs[:300],
        'medicaments': Medicament.objects.order_by('nom'),
        'type_filtre': type_m,
        'medicament_filtre': medicament_id,
        'nb_entrees':  qs.filter(type_mouvement='entree').count(),
        'nb_sorties':  qs.filter(type_mouvement='sortie').count(),
        'val_entrees': _fmt(totaux['val_entrees']),
        'val_sorties': _fmt(totaux['val_sorties']),
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
