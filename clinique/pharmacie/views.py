import re
import unicodedata
from datetime import timedelta
from decimal import Decimal

from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.db import models
from django.db.models import Sum, F, Q, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from django.db import transaction
from django.db.models import Count

from .models import (
    Commande, Fournisseur, LigneCommande, Lot, Medicament, MouvementStock,
    Specialite)
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


def grouper_par_categorie(medicaments):
    """Range une liste de médicaments par catégorie, pour l'affichage.

    L'ordre des groupes est celui de `Medicament.CATEGORIE_CHOICES`, qui suit
    l'ordre où un soignant y pense : la douleur et les infections d'abord,
    les consommables à la fin. Les groupes vides ne sont pas renvoyés, et un
    médicament sans catégorie atterrit dans « Non classé » plutôt que de
    disparaître de la liste.
    """
    restants = list(medicaments)
    groupes = []
    for code, libelle in Medicament.CATEGORIE_CHOICES:
        membres = [m for m in restants if m.categorie == code]
        if membres:
            groupes.append({'code': code, 'libelle': libelle, 'medicaments': membres})
    connus = {code for code, _ in Medicament.CATEGORIE_CHOICES}
    sans = [m for m in restants if m.categorie not in connus]
    if sans:
        groupes.append({'code': '', 'libelle': 'Non classé', 'medicaments': sans})
    return groupes


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
        'nb_total':      qs.count(),
        'nb_alerte':     len(en_alerte),
        'nb_rupture':    len(rupture),
        'nb_peremption': sum(1 for m in qs if m.est_perime() or m.bientot_perime()),
        'valeur':        valeur,
    }


def _facture_pour_dispensation(patient_id, ordonnance_id):
    """Facture pharmacie sur laquelle porter un médicament dispensé.

    Chaque service est facturé à part : les médicaments ne sont plus portés sur
    la facture de la consultation, ils ont leur PROPRE facture, rattachée à
    l'ordonnance. Une ordonnance = une facture pharmacie, même si le patient
    revient chercher le reste de ses médicaments un autre jour.

    Le patient de la sortie fait FOI : on ne rattache jamais le médicament à
    l'ordonnance d'un autre patient. Sans ordonnance valide, on ne facture rien
    (`_verifier_ordonnance_vente` a déjà interdit ce cas pour une vente).
    """
    from facturation.models import Facture
    from consultation.models import Ordonnance

    try:
        patient_id = int(patient_id)
    except (TypeError, ValueError):
        return None
    if not ordonnance_id:
        return None

    ordo = (Ordonnance.objects
            .select_related('consultation__rendez_vous')
            .filter(pk=ordonnance_id).first())
    # L'ordonnance n'est retenue que si sa consultation est bien CELLE du patient
    try:
        appartient = ordo.consultation.rendez_vous.patient_id == patient_id
    except AttributeError:
        appartient = False
    if not appartient:
        return None

    facture = Facture.objects.filter(ordonnance=ordo).first()
    if facture is None:
        facture = Facture(patient_id=patient_id, ordonnance=ordo)
        facture.save()
    return facture


def _verifier_ordonnance_vente(patient_id, ordonnance_id):
    """Règle de la clinique : pas de vente de médicaments sans ordonnance.

    Toute sortie destinée à un patient (donc facturée) doit être liée à une
    ordonnance appartenant bien à CE patient. Les sorties internes (péremption,
    soin infirmier, ajustement) — sans patient ni ordonnance — restent permises.
    Lève ValueError avec un message clair si la règle n'est pas respectée.
    """
    if not patient_id and not ordonnance_id:
        return  # sortie interne : pas une vente
    if not ordonnance_id:
        raise ValueError(
            "Vente sans ordonnance interdite : sélectionnez l'ordonnance du patient "
            "(le médecin doit d'abord la créer si elle n'existe pas).")
    if not patient_id:
        raise ValueError(
            "Sélectionnez le patient de l'ordonnance : une dispensation est toujours "
            "facturée au patient.")
    ordo = (Ordonnance.objects
            .select_related('consultation__rendez_vous')
            .filter(pk=ordonnance_id).first())
    try:
        ordo_patient_id = ordo.consultation.rendez_vous.patient_id
    except AttributeError:
        ordo_patient_id = None
    try:
        patient_id = int(patient_id)
    except (TypeError, ValueError):
        patient_id = None
    if ordo_patient_id is None or patient_id is None or ordo_patient_id != patient_id:
        raise ValueError("Ordonnance introuvable ou n'appartenant pas à ce patient.")


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
    try:
        _verifier_ordonnance_vente(patient_id, ordonnance_id)
    except ValueError as e:
        messages.error(request, str(e))
        return None

    facture = _facture_pour_dispensation(patient_id, ordonnance_id)
    faits, erreurs, ignores = [], [], []
    # Garde-fou anti-doublon : un médicament déjà dispensé pour CETTE ordonnance
    # n'est pas re-servi (sinon la facture et le stock se regonflent à chaque
    # passage — double-clic, retour-arrière, re-dispensation). Dédoublonnage par
    # couple (ordonnance, médicament) : les autres médicaments restent servables.
    deja = set()
    if ordonnance_id:
        deja = set(MouvementStock.objects
                   .filter(type_mouvement='sortie', ordonnance_id=ordonnance_id)
                   .values_list('medicament_id', flat=True))
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
        if ordonnance_id and med.pk in deja:
            ignores.append(med.nom)
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
        deja.add(med.pk)   # bloque aussi un doublon dans la même soumission
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
    if ignores:
        messages.warning(request, "Déjà dispensé(s) pour cette ordonnance — ignoré(s) pour éviter un doublon : " + ', '.join(ignores) + '.')
    if not faits and not erreurs and not ignores:
        messages.info(request, "Aucun médicament sélectionné à dispenser.")
        return None

    # Les medicaments se reglent ICI, au comptoir de la pharmacie, et non a la
    # reception (cf. facturation/regles.py, « Qui encaisse quoi »). On emmene
    # donc le pharmacien droit sur l'encaissement de ce qu'il vient de servir.
    if facture is not None and faits and not facture.est_reglee():
        return redirect(
            f"{reverse('facturation:paiement_ajouter')}?facture={facture.pk}")

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
        'groupes':      grouper_par_categorie(medicaments),
        'categories':   Medicament.CATEGORIE_CHOICES,
        'q':            q,
        'categorie':    categorie,
        'etat':         etat,
        'nb_total':     stats['nb_total'],
        'nb_alerte':    stats['nb_alerte'],
        'nb_rupture':   stats['nb_rupture'],
        'nb_peremption': stats['nb_peremption'],
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
                rembourse='rembourse' in request.POST,
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
            medicament.rembourse      = 'rembourse' in request.POST
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

            mouvement = MouvementStock(
                medicament=medicament,
                type_mouvement='entree',
                quantite=quantite,
                prix_unitaire=prix,
                motif=request.POST.get('motif', '').strip() or 'Réapprovisionnement',
                utilisateur=request.user,
            )
            # Precisions du bon de livraison : elles partent dans le lot que
            # le save() va creer (cf. MouvementStock._creer_le_lot).
            prix_achat = request.POST.get('prix_achat')
            mouvement.lot_numero = request.POST.get('numero_lot', '').strip()
            mouvement.lot_peremption = request.POST.get('date_peremption') or None
            mouvement.lot_prix_achat = Decimal(prix_achat) if prix_achat else None
            mouvement.lot_fournisseur_id = request.POST.get('fournisseur') or None
            if mouvement.lot_fournisseur_id:
                mouvement.lot_fournisseur = get_object_or_404(
                    Fournisseur, pk=mouvement.lot_fournisseur_id)
            mouvement.save()

            messages.success(
                request,
                f'+{quantite} {medicament.unite} ajoutés au stock de {medicament.nom}.'
                + (f" Lot {mouvement.lot_numero}." if mouvement.lot_numero else ''))
            return redirect('pharmacie:medicaments')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/entree_form.html', {
        'medicaments':    Medicament.objects.filter(actif=True).order_by('nom'),
        'fournisseurs':   Fournisseur.objects.filter(actif=True),
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

            # Règle clinique : pas de vente à un patient sans son ordonnance
            _verifier_ordonnance_vente(patient_id, ordonnance_id)

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


# ─────────────────────────────────────────────────────────────────
#  Quels médicaments l'assurance prend-elle en charge ?
# ─────────────────────────────────────────────────────────────────

def proposition_remboursement(medicament):
    """Faut-il, a priori, cocher « remboursé » pour ce médicament ?

    Ce n'est qu'une PROPOSITION, à relire avec le pharmacien : la liste qui
    fait foi est celle de l'assureur (la CANAM pour l'AMO). Elle repose sur
    deux constats du terrain :

    - un consommable (compresses, gants, aiguilles) n'est pas un médicament
      et ne relève pas du remboursement de médicaments ;
    - l'assurance rembourse le GÉNÉRIQUE, désigné par sa DCI, et pas la
      spécialité de marque : Paracétamol oui, Doliprane non.

    On reconnaît donc un générique au fait que son nom EST sa DCI, ou la
    contient (« Povidone iodée (Bétadine) » reste un générique).
    """
    if medicament.categorie == 'consommable':
        return False
    if not medicament.dci:
        return False        # DCI inconnue : à vérifier, donc non coché
    nom, dci = _sans_dosage(medicament.nom), _sans_dosage(medicament.dci)
    return bool(dci) and (dci in nom or nom in dci)


def _sans_dosage(libelle):
    """« Povidone iodée 10% » → « povidone iodee ».

    Le dosage fait partie du libellé mais pas de l'identité du produit :
    sans ce nettoyage, « Povidone iodée (Bétadine) » et sa DCI « Povidone
    iodée 10% » passeraient pour deux produits différents, et le générique
    serait pris pour une marque.
    """
    texte = _norm_nom(libelle)
    texte = re.sub(r'\d+[\d,.]*\s*(mg|g|ml|ui|%|°|mg/ml|g/l)?', ' ', texte)
    return ' '.join(texte.split()).strip(' ()-')


@permission_required('medicament.manage')
def remboursement_liste(request):
    """Cocher d'un seul écran les médicaments pris en charge par l'assurance.

    Évite d'ouvrir les quarante fiches une par une. Le bouton « proposition »
    ne fait que pré-cocher : rien n'est enregistré tant qu'on ne valide pas.
    """
    if request.method == 'POST':
        rembourses = {
            int(cle.removeprefix('rembourse_'))
            for cle in request.POST if cle.startswith('rembourse_')
        }
        tous = list(Medicament.objects.all())
        for medicament in tous:
            medicament.rembourse = medicament.pk in rembourses
        Medicament.objects.bulk_update(tous, ['rembourse'])

        pris = len(rembourses)
        messages.success(
            request,
            f"Prise en charge enregistrée : {pris} médicament(s) remboursé(s), "
            f"{len(tous) - pris} à la charge du patient.")
        return redirect('pharmacie:remboursement')

    libelles = dict(Medicament.CATEGORIE_CHOICES)
    groupes = {}
    for medicament in Medicament.objects.all().order_by('categorie', 'nom'):
        groupe = groupes.setdefault(
            medicament.categorie,
            {'libelle': libelles.get(medicament.categorie, 'Non classé'),
             'medicaments': []})
        medicament.propose = proposition_remboursement(medicament)
        groupe['medicaments'].append(medicament)

    return render(request, 'pharmacie/remboursement.html', {
        'groupes':      list(groupes.values()),
        'nb_total':     Medicament.objects.count(),
        'nb_rembourse': Medicament.objects.filter(rembourse=True).count(),
    })



# ─────────────────────────────────────────────────────────────────
#  Approvisionnement : fournisseurs et commandes
# ─────────────────────────────────────────────────────────────────

@permission_required('pharmacie.view')
def fournisseur_liste(request):
    fournisseurs = Fournisseur.objects.annotate(
        nb_commandes=Count('commandes', distinct=True))
    q = request.GET.get('q', '').strip()
    if q:
        fournisseurs = fournisseurs.filter(termes_q(q, 'nom', 'contact', 'telephone'))
    return render(request, 'pharmacie/fournisseurs.html',
                  {'fournisseurs': fournisseurs, 'q': q})


@permission_required('medicament.manage')
def fournisseur_form(request, pk=None):
    """Création et modification d'un fournisseur, par le même formulaire."""
    fournisseur = get_object_or_404(Fournisseur, pk=pk) if pk else None

    if request.method == 'POST':
        try:
            champs = {
                'nom':       request.POST['nom'].strip(),
                'contact':   request.POST.get('contact', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'email':     request.POST.get('email', '').strip(),
                'adresse':   request.POST.get('adresse', '').strip(),
                'actif':     'actif' in request.POST,
            }
            if not champs['nom']:
                raise ValueError("Le nom du fournisseur est obligatoire.")
            if fournisseur:
                for cle, valeur in champs.items():
                    setattr(fournisseur, cle, valeur)
                fournisseur.save()
                messages.success(request, f"Fournisseur « {fournisseur.nom} » mis à jour.")
            else:
                fournisseur = Fournisseur.objects.create(**champs)
                messages.success(request, f"Fournisseur « {fournisseur.nom} » ajouté.")
            return redirect('pharmacie:fournisseurs')
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/fournisseur_form.html', {
        'fournisseur': fournisseur,
        'action': 'Modifier' if fournisseur else 'Ajouter',
    })


@permission_required('pharmacie.view')
def commande_liste(request):
    commandes = (Commande.objects.select_related('fournisseur')
                 .prefetch_related('lignes'))
    statut = request.GET.get('statut', '')
    if statut:
        commandes = commandes.filter(statut=statut)
    return render(request, 'pharmacie/commandes.html', {
        'commandes': commandes,
        'statuts':   Commande.Statut.choices,
        'statut':    statut,
    })


@permission_required('stock.entree')
def commande_ajouter(request):
    """Passe une commande : un fournisseur, et des lignes médicament/quantité."""
    if request.method == 'POST':
        try:
            with transaction.atomic():
                commande = Commande.objects.create(
                    fournisseur=get_object_or_404(
                        Fournisseur, pk=request.POST['fournisseur']),
                    reference=request.POST.get('reference', '').strip(),
                    notes=request.POST.get('notes', '').strip(),
                    statut=request.POST.get('statut', Commande.Statut.BROUILLON),
                    utilisateur=request.user,
                )
                lignes = _lignes_du_formulaire(request, commande)
                if not lignes:
                    raise ValueError("Ajoutez au moins un médicament à la commande.")
                LigneCommande.objects.bulk_create(lignes)

            messages.success(request, f'{commande} enregistrée — {len(lignes)} ligne(s).')
            return redirect('pharmacie:commande_detail', pk=commande.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/commande_form.html', {
        'fournisseurs': Fournisseur.objects.filter(actif=True),
        'medicaments':  Medicament.objects.filter(actif=True).order_by('nom'),
        'statuts':      Commande.Statut.choices,
    })


def _lignes_du_formulaire(request, commande):
    """Lit les lignes saisies : medicament_1, quantite_1, prix_achat_1, …

    Les lignes vides sont ignorées : le formulaire en propose plusieurs, on
    ne force personne à toutes les remplir.
    """
    lignes = []
    for cle in request.POST:
        if not cle.startswith('medicament_'):
            continue
        indice = cle.removeprefix('medicament_')
        medicament_id = request.POST.get(cle)
        quantite = request.POST.get(f'quantite_{indice}')
        if not medicament_id or not quantite:
            continue
        quantite = int(quantite)
        if quantite <= 0:
            continue
        prix = request.POST.get(f'prix_achat_{indice}') or 0
        lignes.append(LigneCommande(
            commande=commande, medicament_id=medicament_id,
            quantite=quantite, prix_achat=Decimal(prix)))
    return lignes


@permission_required('pharmacie.view')
def commande_detail(request, pk):
    commande = get_object_or_404(
        Commande.objects.select_related('fournisseur')
                .prefetch_related('lignes__medicament'), pk=pk)
    return render(request, 'pharmacie/commande_detail.html', {'commande': commande})


@permission_required('stock.entree')
def commande_receptionner(request, pk):
    """Enregistre ce qui est réellement arrivé, et le fait entrer en stock.

    Chaque ligne reçue crée une entrée de stock, donc un lot, avec sa
    péremption et le fournisseur de la commande. Une livraison partielle est
    acceptée : la commande ne passe en « Reçue » que lorsqu'il ne reste plus
    rien à recevoir.
    """
    commande = get_object_or_404(Commande, pk=pk)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                recus = 0
                for ligne in commande.lignes.select_related('medicament'):
                    mouvement = ligne.receptionner(
                        request.POST.get(f'recu_{ligne.pk}'),
                        numero_lot=request.POST.get(f'lot_{ligne.pk}', '').strip(),
                        date_peremption=request.POST.get(f'peremption_{ligne.pk}') or None,
                        utilisateur=request.user,
                    )
                    if mouvement:
                        recus += 1

                if not recus:
                    raise ValueError("Aucune quantité reçue n'a été saisie.")

                if not commande.reste_a_recevoir():
                    commande.statut = Commande.Statut.RECUE
                    commande.date_reception = timezone.localdate()
                    commande.save(update_fields=['statut', 'date_reception'])

            messages.success(
                request,
                f'{recus} ligne(s) reçue(s) et entrée(s) en stock.'
                + ('' if commande.est_receptionnee()
                   else " La commande reste ouverte : il manque des quantités."))
            return redirect('pharmacie:commande_detail', pk=commande.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    return render(request, 'pharmacie/commande_reception.html', {
        'commande': commande,
        'lignes':   commande.lignes.select_related('medicament'),
    })


# ─────────────────────────────────────────────────────────────────
#  Les lots : voir ce qu'on a vraiment en stock, et quand ça périme
# ─────────────────────────────────────────────────────────────────

@permission_required('pharmacie.view')
def lot_liste(request):
    """Le stock arrivage par arrivage, et non plus médicament par médicament.

    C'est la contrepartie visible des lots : sans cet écran, le pharmacien
    sait qu'un médicament périme bientôt, mais pas QUEL lot, ni combien de
    boîtes sont concernées, ni s'il peut encore les écouler.

    Par défaut on montre ce qui reste en stock ; les lots épuisés ne
    disparaissent pas pour autant, ils restent consultables par le filtre
    (c'est la traçabilité : savoir quel lot est parti et quand).
    """
    lots = (Lot.objects.select_related('medicament', 'fournisseur')
            .order_by(models.F('date_peremption').asc(nulls_last=True), 'pk'))

    q = request.GET.get('q', '').strip()
    if q:
        lots = lots.filter(termes_q(q, 'medicament__nom', 'medicament__dci', 'numero'))

    medicament_id = request.GET.get('medicament', '')
    if medicament_id:
        lots = lots.filter(medicament_id=medicament_id)

    etat = request.GET.get('etat', 'stock')
    aujourdhui = timezone.localdate()
    limite = aujourdhui + timedelta(days=Medicament.JOURS_AVANT_PEREMPTION)

    if etat == 'stock':
        lots = lots.filter(quantite_restante__gt=0)
    elif etat == 'epuise':
        lots = lots.filter(quantite_restante=0)
    elif etat == 'perime':
        lots = lots.filter(quantite_restante__gt=0,
                           date_peremption__lt=aujourdhui)
    elif etat == 'bientot':
        lots = lots.filter(quantite_restante__gt=0,
                           date_peremption__gte=aujourdhui,
                           date_peremption__lte=limite)
    # etat == 'tous' : aucun filtre

    lots = list(lots)
    valeur = sum((l.quantite_restante * (l.prix_achat or 0)) for l in lots)

    en_stock = Lot.objects.filter(quantite_restante__gt=0)
    return render(request, 'pharmacie/lots.html', {
        'lots':         lots,
        'q':            q,
        'etat':         etat,
        'medicament':   Medicament.objects.filter(pk=medicament_id).first()
                        if medicament_id else None,
        'nb_stock':     en_stock.count(),
        'nb_perimes':   en_stock.filter(date_peremption__lt=aujourdhui).count(),
        'nb_bientot':   en_stock.filter(date_peremption__gte=aujourdhui,
                                        date_peremption__lte=limite).count(),
        'valeur_achat': _fmt(valeur),
    })
