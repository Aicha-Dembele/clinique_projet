from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.utils.http import urlencode
from decimal import Decimal

from .models import Facture, LigneFacture, Paiement, Tarif, Assurance
from patients.models import Patient
from comptes.decorators import role_required, permission_required
from comptes.recherche import termes_q


# ── Helpers ──────────────────────────────────────────────────────

def _fmt(val):
    """Format number with spaces as thousand separator."""
    try:
        return f"{int(val):,}".replace(',', ' ')
    except Exception:
        return '0'


def _patients_facturables(inclure_pk=None):
    """Patients qui ont réellement quelque chose à facturer.

    Une facture se rattache toujours à un acte : un rendez-vous, un examen, une
    hospitalisation ou une ordonnance dispensée. Proposer dans la liste
    déroulante un patient qui n'a aucun de ces actes ne mène qu'à une facture
    vide à 0 FCFA — la réception perdait du temps à faire défiler des noms non
    facturables.

    `inclure_pk` garde le patient déjà enregistré sur une facture existante,
    pour que le formulaire de modification ne perde jamais sa valeur.
    """
    condition = (Q(rendez_vous__isnull=False) |
                 Q(examenmedical__isnull=False) |
                 Q(hospitalisation__isnull=False))
    if inclure_pk:
        condition |= Q(pk=inclure_pk)
    return (Patient.objects.filter(condition)
            .select_related('assurance').distinct().order_by('nom'))


# ── Factures ─────────────────────────────────────────────────────

@permission_required('facture.view')
def facture_liste(request):
    qs = Facture.objects.select_related('patient', 'assurance').prefetch_related('lignes', 'paiements').order_by('-id')

    # Filtre statut
    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)

    # Recherche patient
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(termes_q(q, 'patient__nom', 'patient__prenom'))

    all_f = Facture.objects.all()
    total_paye    = all_f.filter(statut='payé').aggregate(t=Sum('montant_total'))['t'] or 0
    total_attente = all_f.filter(statut='non payé').aggregate(t=Sum('montant_total'))['t'] or 0

    page = Paginator(qs, 25).get_page(request.GET.get('page'))
    return render(request, 'facturation/liste.html', {
        'factures':          page,
        'total_paye':        _fmt(total_paye),
        'total_attente':     _fmt(total_attente),
        'factures_impayees': all_f.filter(statut='non payé').count(),
        'total_factures':    all_f.count(),
        'statut_filtre':     statut,
        'q':                 q,
    })


@permission_required('facture.view')
def facture_detail(request, pk):
    facture = get_object_or_404(
        Facture.objects.select_related('patient', 'rendez_vous__medecin',
                                       'consultation', 'hospitalisation')
                       .prefetch_related('lignes', 'paiements'),
        pk=pk
    )
    return render(request, 'facturation/detail.html', {
        'facture':  facture,
        'montant_paye':    facture.montant_paye(),
        'montant_restant': facture.montant_restant(),
    })


@permission_required('facture.view')
def facture_pdf(request, pk):
    """Télécharge / affiche la facture au format PDF (généré côté serveur)."""
    from .pdf import facture_pdf_response
    facture = get_object_or_404(
        Facture.objects.select_related('patient', 'assurance')
                       .prefetch_related('lignes', 'paiements'),
        pk=pk,
    )
    return facture_pdf_response(facture)


@permission_required('paiement.view')
def paiement_pdf(request, pk):
    """Affiche le reçu de paiement au format PDF (avec logo, généré côté serveur)."""
    from .pdf import paiement_pdf_response
    paiement = get_object_or_404(
        Paiement.objects.select_related(
            'facture__patient', 'facture__assurance',
            'facture__rendez_vous__medecin',
            'facture__consultation__rendez_vous__medecin',
            'facture__hospitalisation'),
        pk=pk,
    )
    return paiement_pdf_response(paiement)


def _enregistrer_service(request, facture):
    """Rattache à `facture` le SEUL service choisi dans le formulaire.

    Une facture = un service. Le formulaire envoie `service` (le type) puis
    l'identifiant de l'acte dans le champ du même nom. Les trois autres liens
    sont remis à vide : impossible de se retrouver avec une facture hybride.

    Lève ValueError si rien n'est choisi, ou si l'acte est déjà facturé.
    """
    libelles = dict(Facture.SERVICES)
    service = (request.POST.get('service') or '').strip()
    if service not in libelles:
        raise ValueError("Choisissez le type de service à facturer.")

    objet_id = request.POST.get(service) or None
    if not objet_id:
        # Cas fréquent : tous les actes de ce service sont déjà facturés, la liste
        # ne contient donc que des lignes grisées et rien n'a pu être sélectionné.
        raise ValueError(
            f"Aucun acte sélectionné pour « {libelles[service]} ». "
            f"Si toutes les lignes de la liste sont grisées, c'est qu'elles sont "
            f"déjà facturées : il n'y a plus rien à facturer pour ce service.")

    # Un même acte ne peut pas être facturé deux fois.
    deja = (Facture.objects
            .filter(**{f'{service}_id': objet_id})
            .exclude(pk=facture.pk) if facture.pk else
            Facture.objects.filter(**{f'{service}_id': objet_id}))
    deja = deja.first()
    if deja:
        raise ValueError(
            f"{libelles[service]} déjà facturé sur FAC-{str(deja.pk).zfill(4)}. "
            f"Supprimez cette facture d'abord pour en créer une nouvelle.")

    # On vide TOUS les liens possibles, y compris l'ancien `consultation` : sans
    # cela, modifier une vieille facture laisserait deux services rattachés.
    for code in Facture.LIENS:
        setattr(facture, f'{code}_id', objet_id if code == service else None)


def _contexte_form(request, facture=None):
    """Listes proposées dans le formulaire de facture, service par service.

    Chaque acte déjà facturé est signalé (et désactivé) dans sa liste, pour que
    la réception voie d'un coup d'œil ce qui reste à facturer.
    """
    from consultation.models import Rendez_vous, Hospitalisation, ExamenMedical, Ordonnance

    exclure = {'pk': facture.pk} if facture and facture.pk else None

    def deja_factures(champ):
        qs = Facture.objects.filter(**{f'{champ}__isnull': False})
        if exclure:
            qs = qs.exclude(**exclure)
        return set(qs.values_list(f'{champ}_id', flat=True))

    # Pharmacie : seules les ordonnances réellement dispensées ont un montant.
    ordonnances = (Ordonnance.objects
                   .filter(dispensations__type_mouvement='sortie')
                   .select_related('consultation__rendez_vous__patient')
                   .distinct().order_by('-date'))
    for o in ordonnances:
        o.montant_dispense = sum(
            (mv.montant() for mv in o.dispensations.filter(type_mouvement='sortie')),
            Decimal('0'))

    # Consultation : c'est le RENDEZ-VOUS que l'on facture, avant que le patient
    # ne soit reçu. Un rendez-vous annulé n'a plus rien à facturer.
    rendez_vous      = (Rendez_vous.objects.exclude(statut='annule')
                        .select_related('patient', 'medecin').order_by('-date'))
    examens          = ExamenMedical.objects.select_related('patient', 'medecin').order_by('-id')
    hospitalisations = Hospitalisation.objects.select_related('patient').order_by('-date_entree')

    faits = {
        'rendez_vous':     deja_factures('rendez_vous'),
        'examen':          deja_factures('examen'),
        'hospitalisation': deja_factures('hospitalisation'),
        'ordonnance':      deja_factures('ordonnance'),
    }
    actes = {
        'rendez_vous':     rendez_vous,
        'examen':          examens,
        'hospitalisation': hospitalisations,
        'ordonnance':      ordonnances,
    }

    # Combien d'actes restent à facturer par service. Sans ce compte, la réception
    # choisissait un type de service dont TOUS les actes étaient déjà facturés,
    # se retrouvait devant une liste entièrement grisée, et ne comprenait pas
    # pourquoi l'enregistrement était refusé.
    services = []
    total_restants = 0
    for code, libelle in Facture.SERVICES:
        restants = sum(1 for a in actes[code] if a.pk not in faits[code])
        total_restants += restants
        services.append({'code': code, 'libelle': libelle, 'restants': restants})

    return {
        'patients':         _patients_facturables(
                                inclure_pk=facture.patient_id if facture else None),
        'rendez_vous':      rendez_vous,
        'examens':          examens,
        'hospitalisations': hospitalisations,
        'ordonnances':      ordonnances,
        'rdv_factures':      faits['rendez_vous'],
        'examen_factures':   faits['examen'],
        'hospit_facturees':  faits['hospitalisation'],
        'ordo_facturees':    faits['ordonnance'],
        'services':         services,
        'total_restants':   total_restants,
        'assurances':       Assurance.objects.filter(actif=True),
        'tarifs':           Tarif.objects.all().order_by('type_service', 'nom'),
    }


@role_required('admin', 'receptionniste')
def facture_ajouter(request):
    if request.method == 'POST':
        try:
            facture = Facture(
                patient_id=request.POST['patient'],
                assurance_id=request.POST.get('assurance') or None,
                notes=request.POST.get('notes', ''),
            )
            _enregistrer_service(request, facture)
            taux = request.POST.get('taux_prise_en_charge', '')
            if taux:
                facture.taux_prise_en_charge = Decimal(taux)
            facture.save()   # génère les lignes et calcule le total

            messages.success(
                request,
                f'Facture FAC-{str(facture.pk).zfill(4)} créée — '
                f'{facture.service_libelle()} — Total : {_fmt(facture.montant_total)} FCFA')
            return redirect('facturation:detail', pk=facture.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    ctx = _contexte_form(request)
    ctx.update({
        'action':           'Créer',
        # Pré-sélection depuis l'URL (ex: ?service=consultation&consultation=5)
        'pre_service':      request.GET.get('service', ''),
        'pre_patient':      request.GET.get('patient', ''),
        'pre_rendez_vous':  request.GET.get('rendez_vous', ''),
        'pre_examen':       request.GET.get('examen', ''),
        'pre_hospit':       request.GET.get('hospitalisation', ''),
        'pre_ordonnance':   request.GET.get('ordonnance', ''),
    })
    return render(request, 'facturation/form.html', ctx)


@role_required('admin', 'receptionniste')
def facture_modifier(request, pk):
    facture = get_object_or_404(Facture, pk=pk)

    if request.method == 'POST':
        try:
            facture.patient_id   = request.POST['patient']
            facture.assurance_id = request.POST.get('assurance') or None
            taux = request.POST.get('taux_prise_en_charge', '')
            # taux saisi → on l'applique ; champ vidé → save() reprendra celui de l'assurance (ou 0)
            facture.taux_prise_en_charge = Decimal(taux) if taux else Decimal('0')
            facture.notes = request.POST.get('notes', '')
            _enregistrer_service(request, facture)

            facture.save()   # recalcule tout

            messages.success(request, 'Facture mise à jour.')
            return redirect('facturation:detail', pk=facture.pk)
        except Exception as e:
            messages.error(request, f'Erreur : {e}')

    ctx = _contexte_form(request, facture=facture)
    ctx.update({
        'facture':          facture,
        'action':           'Modifier',
        'pre_service':      facture.service() or '',
        'pre_patient':      '',
        'pre_rendez_vous':  '',
        'pre_examen':       '',
        'pre_hospit':       '',
        'pre_ordonnance':   '',
    })
    return render(request, 'facturation/form.html', ctx)


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

@permission_required('paiement.view')
def paiement_liste(request):
    paiements = Paiement.objects.select_related('facture__patient').order_by('-date')

    q = request.GET.get('q', '').strip()
    if q:
        paiements = paiements.filter(
            termes_q(q, 'facture__patient__nom', 'facture__patient__prenom', 'note'))

    total = paiements.aggregate(t=Sum('montant'))['t'] or 0
    return render(request, 'facturation/paiements.html', {
        'paiements':       paiements,
        'total_encaisse':  _fmt(total),
        'q':               q,
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

            # Carte bancaire → paiement simulé via Stripe Checkout (mode test) :
            # redirection vers la page de paiement Stripe, l'enregistrement du
            # Paiement se fait au retour dans paiement_carte_succes.
            if request.POST['mode_paiement'] == 'carte':
                return _rediriger_vers_stripe(request, facture, montant,
                                              request.POST.get('note', ''))

            # Orange Money → page reproduisant la procédure #144# (simulation) :
            # l'enregistrement du Paiement se fait après validation du code.
            if request.POST['mode_paiement'] == 'orange_money':
                request.session['paiement_orange'] = {
                    'facture_id': facture.pk, 'montant': str(montant),
                    'note': request.POST.get('note', ''),
                }
                return redirect('facturation:paiement_orange_money')

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


# ── Paiement par carte : Stripe Checkout en mode test ────────────
# (cf. Django 4 By Example, chap. 9 : la carte de test 4242 4242 4242 4242
#  simule un paiement réussi, aucune somme réelle n'est débitée.)

def _rediriger_vers_stripe(request, facture, montant, note):
    """Démarre le paiement par carte : page Stripe Checkout si une clé de test
    est configurée, sinon simulateur local (même principe, aucune clé requise).
    Le FCFA (XOF) est une devise « sans décimales » chez Stripe :
    unit_amount = montant en francs, tel quel."""
    import stripe
    from django.conf import settings
    from django.urls import reverse

    if not settings.STRIPE_SECRET_KEY:
        # Pas de clé Stripe : on passe par la page locale de simulation
        request.session['paiement_carte'] = {
            'facture_id': facture.pk, 'montant': str(montant), 'note': note,
        }
        return redirect('facturation:paiement_carte_simulation')

    stripe.api_key = settings.STRIPE_SECRET_KEY
    success_url = (request.build_absolute_uri(reverse('facturation:paiement_carte_succes'))
                   + '?session_id={CHECKOUT_SESSION_ID}')
    cancel_url = (request.build_absolute_uri(reverse('facturation:paiement_carte_annule'))
                  + f'?facture={facture.pk}')

    session = stripe.checkout.Session.create(
        mode='payment',
        client_reference_id=str(facture.pk),
        success_url=success_url,
        cancel_url=cancel_url,
        line_items=[{
            'price_data': {
                'unit_amount': int(montant),
                'currency': 'xof',
                'product_data': {
                    'name': f'Facture FAC-{facture.pk:04d} — Clinique Nevroglie',
                    'description': f'Patient : {facture.patient}',
                },
            },
            'quantity': 1,
        }],
        metadata={'facture_id': str(facture.pk), 'note': note[:400]},
    )
    return redirect(session.url)


@role_required('admin', 'receptionniste')
def paiement_carte_succes(request):
    """Retour de Stripe après paiement : vérifie la session côté serveur
    (statut « paid ») puis enregistre le Paiement — une seule fois, même si
    la page de retour est rechargée."""
    import stripe
    from django.conf import settings

    session_id = request.GET.get('session_id', '')
    if not session_id:
        messages.error(request, "Retour de paiement invalide (session manquante).")
        return redirect('facturation:paiements')

    try:
        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        messages.error(request, f'Vérification du paiement impossible : {e}')
        return redirect('facturation:paiements')

    facture = get_object_or_404(Facture, pk=session.metadata.get('facture_id')
                                or session.client_reference_id)
    if session.payment_status != 'paid':
        messages.error(request, "Le paiement n'a pas été confirmé par Stripe.")
        return redirect('facturation:detail', pk=facture.pk)

    # Idempotent : la session Stripe est tracée dans la note du paiement
    ref = f'Stripe {session_id}'
    if not Paiement.objects.filter(facture=facture, note__contains=session_id).exists():
        note = (session.metadata.get('note') or '').strip()
        montant = Decimal(session.amount_total)  # XOF sans décimales : déjà en francs
        Paiement.objects.create(
            facture=facture,
            montant=montant,
            mode_paiement='carte',
            note=(f'{note} · {ref}' if note else ref)[:200],
        )
        messages.success(
            request,
            f'Paiement par carte de {_fmt(montant)} FCFA confirmé par Stripe (mode test).')
    return redirect('facturation:detail', pk=facture.pk)


def _valider_carte_test(numero, expiration, cvc):
    """Valide une carte de test (mêmes cartes que Stripe). Retourne un message
    d'erreur, ou None si le paiement simulé est accepté.
    4242 4242 4242 4242 → succès ; 4000 0000 0000 0002 → refus banque."""
    import re
    from datetime import date

    if numero == '4000000000000002':
        return "Carte refusée par la banque émettrice (carte de test « paiement refusé »)."
    if numero != '4242424242424242':
        return "Numéro de carte non reconnu — en mode test, utilisez la carte 4242 4242 4242 4242."
    m = re.fullmatch(r'(\d{2})\s*/?\s*(\d{2})', expiration)
    if not m:
        return "Date d'expiration invalide (format MM/AA, ex. 12/29)."
    mois, annee = int(m.group(1)), 2000 + int(m.group(2))
    if not 1 <= mois <= 12:
        return "Mois d'expiration invalide."
    auj = date.today()
    if (annee, mois) < (auj.year, auj.month):
        return "Carte expirée : choisissez une date d'expiration future."
    if not re.fullmatch(r'\d{3,4}', cvc):
        return "CVC invalide (3 chiffres au dos de la carte)."
    return None


@role_required('admin', 'receptionniste')
def paiement_carte_simulation(request):
    """Page locale simulant la procédure de paiement par carte bancaire
    (utilisée quand aucune clé Stripe n'est configurée). Reproduit le
    comportement des cartes de test Stripe sans appel réseau."""
    import re

    data = request.session.get('paiement_carte')
    if not data:
        messages.error(request, "Aucun paiement par carte en cours — sélectionnez d'abord la facture.")
        return redirect('facturation:paiement_ajouter')

    facture = get_object_or_404(Facture, pk=data['facture_id'])
    montant = Decimal(data['montant'])

    erreur = None
    if request.method == 'POST':
        numero = re.sub(r'\D', '', request.POST.get('numero', ''))
        expiration = request.POST.get('expiration', '').strip()
        cvc = request.POST.get('cvc', '').strip()

        if montant > facture.montant_restant():
            erreur = (f"Le montant dépasse le restant dû "
                      f"({_fmt(facture.montant_restant())} FCFA) — la facture a peut-être été réglée entre-temps.")
        else:
            erreur = _valider_carte_test(numero, expiration, cvc)

        if erreur is None:
            note = (data.get('note') or '').strip()
            ref = f'PayPal (simulation) — carte •••• {numero[-4:]}'
            Paiement.objects.create(
                facture=facture,
                montant=montant,
                mode_paiement='carte',
                note=(f'{note} · {ref}' if note else ref)[:200],
            )
            request.session.pop('paiement_carte', None)
            messages.success(
                request,
                f'Paiement PayPal de {_fmt(montant)} FCFA accepté (simulation — carte •••• {numero[-4:]}).')
            return redirect('facturation:detail', pk=facture.pk)

    return render(request, 'facturation/carte_simulation.html', {
        'facture': facture,
        'montant': montant,
        'erreur':  erreur,
    })


@role_required('admin', 'receptionniste')
def paiement_carte_annule(request):
    """Retour de Stripe quand l'utilisateur abandonne le paiement."""
    facture_id = request.GET.get('facture')
    messages.info(request, "Paiement par carte annulé — aucun montant n'a été débité.")
    if facture_id:
        return redirect(f"/facturation/paiements/ajouter/?facture={facture_id}")
    return redirect('facturation:paiements')


# ── Paiement Orange Money : simulation de la procédure mobile money ──────
# Reproduit le parcours Orange Money (#144#) pour la démonstration :
# aucune transaction réelle, aucun compte débité.
ORANGE_MONEY_CODE_DEMO = '1234'


def _valider_orange_money(numero, code):
    """Valide le numéro Orange Money et le code de confirmation (simulation).
    Retourne un message d'erreur, ou None si tout est correct."""
    if len(numero) < 8:
        return "Numéro Orange Money invalide — saisissez un numéro d'au moins 8 chiffres."
    if not code:
        return "Saisissez le code de confirmation reçu par SMS."
    if code != ORANGE_MONEY_CODE_DEMO:
        return (f"Code de confirmation incorrect. "
                f"En mode démonstration, saisissez {ORANGE_MONEY_CODE_DEMO}.")
    return None


@role_required('admin', 'receptionniste')
def paiement_orange_money(request):
    """Page locale reproduisant la procédure de paiement Orange Money (#144#).
    Simulation pour la démo : aucun mouvement d'argent réel."""
    import re

    data = request.session.get('paiement_orange')
    if not data:
        messages.error(request, "Aucun paiement Orange Money en cours — sélectionnez d'abord la facture.")
        return redirect('facturation:paiement_ajouter')

    facture = get_object_or_404(Facture, pk=data['facture_id'])
    montant = Decimal(data['montant'])

    erreur = None
    if request.method == 'POST':
        numero = re.sub(r'\D', '', request.POST.get('numero', ''))
        code = request.POST.get('code', '').strip()

        if montant > facture.montant_restant():
            erreur = (f"Le montant dépasse le restant dû "
                      f"({_fmt(facture.montant_restant())} FCFA) — la facture a peut-être été réglée entre-temps.")
        else:
            erreur = _valider_orange_money(numero, code)

        if erreur is None:
            note = (data.get('note') or '').strip()
            ref = f'Orange Money (simulation) — {numero[:2]}••••{numero[-2:]}'
            Paiement.objects.create(
                facture=facture,
                montant=montant,
                mode_paiement='orange_money',
                note=(f'{note} · {ref}' if note else ref)[:200],
            )
            request.session.pop('paiement_orange', None)
            messages.success(
                request,
                f'Paiement Orange Money de {_fmt(montant)} FCFA accepté (simulation).')
            return redirect('facturation:detail', pk=facture.pk)

    return render(request, 'facturation/orange_money_simulation.html', {
        'facture':   facture,
        'montant':   montant,
        'erreur':    erreur,
        'code_demo': ORANGE_MONEY_CODE_DEMO,
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


@permission_required('paiement.view')
def paiement_recu(request, pk):
    paiement = get_object_or_404(Paiement.objects.select_related('facture__patient'), pk=pk)
    return render(request, 'facturation/recu.html', {'paiement': paiement})


# ── Rapports ─────────────────────────────────────────────────────

@permission_required('rapport.view')
def rapports(request):
    from django.db.models import F, DecimalField
    from django.db.models.functions import TruncMonth
    _dec = DecimalField(max_digits=16, decimal_places=2)

    MOIS_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
               'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

    # ── Mois disponibles pour le sélecteur (ceux qui ont des paiements) ──
    mois_options = []
    for r in (Paiement.objects.annotate(mo=TruncMonth('date'))
              .values('mo').distinct().order_by('-mo')):
        d = r['mo']
        if d:
            mois_options.append({'value': f'{d.year}-{d.month:02d}',
                                 'label': f'{MOIS_FR[d.month]} {d.year}'})

    # ── Période sélectionnée : ?mois=YYYY-MM (vide = toutes périodes) ──
    annee = mois = None
    mois_param = (request.GET.get('mois') or '').strip()
    if mois_param:
        try:
            y, m = mois_param.split('-')
            y, m = int(y), int(m)
            if 1 <= m <= 12:
                annee, mois = y, m
        except (ValueError, TypeError):
            annee = mois = None

    paiements = Paiement.objects.all()
    factures  = Facture.objects.all()
    lignes    = LigneFacture.objects.all()

    if annee and mois:
        paiements = paiements.filter(date__year=annee, date__month=mois)
        factures  = factures.filter(date_creation__year=annee, date_creation__month=mois)
        lignes    = lignes.filter(facture__date_creation__year=annee,
                                  facture__date_creation__month=mois)
        periode_label    = f'{MOIS_FR[mois]} {annee}'
        mois_selectionne = f'{annee}-{mois:02d}'
    else:
        periode_label    = 'Toutes périodes'
        mois_selectionne = ''

    # Total encaissé sur la période (les « revenus » du mois)
    recettes_periode = paiements.aggregate(t=Sum('montant'))['t'] or 0

    nb_paiements = paiements.count()

    def pct(mode):
        count = paiements.filter(mode_paiement=mode).count()
        return round(count * 100 / nb_paiements) if nb_paiements else 0

    # ── Revenus par service (facturé, sur la période) ────────────────
    # Somme des LigneFacture par type_service, en une seule requête (sans N+1).
    rev_map = {
        r['type_service']: (r['total'] or 0)
        for r in (lignes.values('type_service')
                  .annotate(total=Sum(F('prix_unitaire') * F('quantite'),
                                      output_field=_dec)))
    }
    rev_c = rev_map.get('consultation', 0)
    rev_h = rev_map.get('hospitalisation', 0)
    rev_e = rev_map.get('examen', 0)
    rev_p = rev_map.get('medicament', 0)       # médicaments dispensés → Pharmacie
    rev_g = sum(rev_map.values()) or 0

    def pct_rev(v):
        return round(float(v) * 100 / float(rev_g)) if rev_g else 0

    return render(request, 'facturation/rapports.html', {
        # Sélecteur de période
        'mois_options':      mois_options,
        'mois_selectionne':  mois_selectionne,
        'periode_label':     periode_label,
        'recettes_periode':  _fmt(recettes_periode),
        'total_factures': factures.count(),
        'total_paye':     factures.filter(statut='payé').count(),
        'total_impaye':   factures.filter(statut='non payé').count(),
        'pct_especes':    pct('cash'),
        'pct_orange':     pct('orange_money'),
        'pct_carte':      pct('carte'),
        # Revenus par service (montants formatés + parts en %)
        'rev_consultation':    _fmt(rev_c),
        'rev_hospitalisation': _fmt(rev_h),
        'rev_examen':          _fmt(rev_e),
        'rev_pharmacie':       _fmt(rev_p),
        'rev_global':          _fmt(rev_g),
        'pct_rev_consultation':    pct_rev(rev_c),
        'pct_rev_hospitalisation': pct_rev(rev_h),
        'pct_rev_examen':          pct_rev(rev_e),
        'pct_rev_pharmacie':       pct_rev(rev_p),
    })


# ── Exports CSV (Excel) ──────────────────────────────────────────

# ── Créances assurances ──────────────────────────────────────────
# Ce que la clinique doit RÉCLAMER à chaque assureur : la part prise en charge
# n'est jamais encaissée auprès du patient, elle reste due par l'assurance.

MOIS_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
           'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']


def _periode(request):
    """(annee, mois, libelle, valeur) depuis ?mois=YYYY-MM. Vide = toutes périodes."""
    mois_param = (request.GET.get('mois') or '').strip()
    if mois_param:
        try:
            y, m = mois_param.split('-')
            y, m = int(y), int(m)
            if 1 <= m <= 12:
                return y, m, f'{MOIS_FR[m]} {y}', f'{y}-{m:02d}'
        except (ValueError, TypeError):
            pass
    return None, None, 'Toutes périodes', ''


def _factures_prises_en_charge(request, avec_filtre_statut=True):
    """Factures dont une part revient à une assurance, sur la période choisie.

    `?statut=a_reclamer|reclame|rembourse` restreint au stade de recouvrement
    voulu — c'est ainsi qu'on isole « ce qui reste à réclamer ce mois-ci ».
    """
    annee, mois, libelle, valeur = _periode(request)
    qs = (Facture.objects
          .filter(assurance__isnull=False, taux_prise_en_charge__gt=0)
          .select_related('patient', 'assurance', 'rendez_vous', 'consultation',
                          'examen', 'hospitalisation', 'ordonnance')
          .order_by('assurance__nom', 'patient__nom', 'pk'))
    if annee and mois:
        qs = qs.filter(date_creation__year=annee, date_creation__month=mois)
    if avec_filtre_statut:
        statut = (request.GET.get('statut') or '').strip()
        if statut in dict(Facture.STATUT_ASSURANCE_CHOICES):
            qs = qs.filter(statut_assurance=statut)
    return qs, libelle, valeur


@permission_required('facture.view', 'rapport.view')
def creances_assurances(request):
    """État des sommes à réclamer aux assurances, regroupées par assureur.

    Chaque facture porte un taux de prise en charge : la part assurance n'est
    pas encaissée auprès du patient, c'est une créance sur l'assureur. Cet écran
    la regroupe par assurance et par mois pour que la clinique parte réclamer
    son dû avec le détail patient par patient.
    """
    from django.db.models.functions import TruncMonth

    factures, periode_label, mois_selectionne = _factures_prises_en_charge(request)

    # Mois proposés dans le sélecteur : ceux qui ont au moins une facture.
    mois_options = []
    for r in (Facture.objects.exclude(date_creation__isnull=True)
              .annotate(mo=TruncMonth('date_creation'))
              .values('mo').distinct().order_by('-mo')):
        d = r['mo']
        if d:
            mois_options.append({'value': f'{d.year}-{d.month:02d}',
                                 'label': f'{MOIS_FR[d.month]} {d.year}'})

    # Regroupement par assurance. Les montants viennent des méthodes du modèle
    # (mêmes arrondis que la facture affichée au patient) : pas de calcul
    # parallèle en SQL qui pourrait diverger d'un franc.
    groupes = {}
    for f in factures:
        g = groupes.setdefault(f.assurance_id, {
            'assurance': f.assurance, 'factures': [],
            'total_facture': Decimal('0'), 'a_reclamer': Decimal('0'),
            'part_patient': Decimal('0'),
            # Montants par stade de recouvrement, pour les boutons d'action
            'montant_a_reclamer': Decimal('0'), 'montant_reclame': Decimal('0'),
            'montant_rembourse': Decimal('0'),
            'nb_a_reclamer': 0, 'nb_reclame': 0, 'nb_rembourse': 0,
        })
        part = f.part_assurance()
        g['factures'].append(f)
        g['total_facture'] += f.montant_total
        g['a_reclamer'] += part
        g['part_patient'] += f.part_patient()
        if f.statut_assurance == 'rembourse':
            g['montant_rembourse'] += part; g['nb_rembourse'] += 1
        elif f.statut_assurance == 'reclame':
            g['montant_reclame'] += part;   g['nb_reclame'] += 1
        else:
            g['montant_a_reclamer'] += part; g['nb_a_reclamer'] += 1

    groupes = sorted(groupes.values(), key=lambda g: g['a_reclamer'], reverse=True)

    total_facture = sum((g['total_facture'] for g in groupes), Decimal('0'))
    totaux = {
        cle: sum((g[cle] for g in groupes), Decimal('0'))
        for cle in ('a_reclamer', 'montant_a_reclamer', 'montant_reclame', 'montant_rembourse')
    }
    nb_patients = len({f.patient_id for f in factures})

    return render(request, 'facturation/creances_assurances.html', {
        'groupes':            groupes,
        'total_a_reclamer':   totaux['a_reclamer'],
        'montant_a_reclamer': totaux['montant_a_reclamer'],
        'montant_reclame':    totaux['montant_reclame'],
        'montant_rembourse':  totaux['montant_rembourse'],
        'total_facture':      total_facture,
        'nb_factures':        len(factures),
        'nb_patients':        nb_patients,
        'periode_label':      periode_label,
        'mois_selectionne':   mois_selectionne,
        'mois_options':       mois_options,
        'statuts':            Facture.STATUT_ASSURANCE_CHOICES,
        'statut_selectionne': (request.GET.get('statut') or '').strip(),
        # Filtres courants, pour revenir sur le même écran après un marquage
        'retour_qs':          urlencode({k: v for k, v in (
                                  ('mois', mois_selectionne),
                                  ('statut', (request.GET.get('statut') or '').strip()),
                              ) if v}),
    })


@permission_required('facture.change', 'rapport.view')
def creances_marquer(request):
    """Fait avancer le recouvrement : réclamé, remboursé, ou retour en arrière.

    Deux portées possibles :
      • `facture=<id>`   → une seule facture ;
      • `assurance=<id>` → tout le dossier de cet assureur sur la période
        affichée, ce qui correspond au geste réel : on envoie une demande
        groupée par assureur et par mois, puis on encaisse en une fois.
    """
    if request.method != 'POST':
        return redirect('facturation:creances')

    action = (request.POST.get('action') or '').strip()
    libelles = dict(Facture.STATUT_ASSURANCE_CHOICES)
    retour = f"{reverse('facturation:creances')}?{request.POST.get('retour', '')}"

    if action not in libelles:
        messages.error(request, "Action de recouvrement inconnue.")
        return redirect(retour)

    facture_id = (request.POST.get('facture') or '').strip()
    if facture_id:
        cibles = Facture.objects.filter(pk=facture_id, assurance__isnull=False)
    else:
        # Portée « dossier » : on rejoue exactement le filtre de l'écran, mais
        # sans le filtre de statut — sinon marquer « réclamé » ne toucherait que
        # ce qui est déjà visible et laisserait des factures en arrière.
        cibles, _, _ = _factures_prises_en_charge(request, avec_filtre_statut=False)
        assurance_id = (request.POST.get('assurance') or '').strip()
        if not assurance_id:
            messages.error(request, "Aucune facture ni assurance indiquée.")
            return redirect(retour)
        cibles = cibles.filter(assurance_id=assurance_id)
        # On ne fait avancer que ce qui est au stade precedent : re-cliquer sur
        # « réclamé » ne doit pas faire reculer un dossier déjà remboursé.
        if action == 'reclame':
            cibles = cibles.filter(statut_assurance='a_reclamer')
        elif action == 'rembourse':
            cibles = cibles.filter(statut_assurance__in=['a_reclamer', 'reclame'])

    cibles = list(cibles)
    if not cibles:
        messages.info(request, "Aucune facture à mettre à jour pour cette action.")
        return redirect(retour)

    montant = Decimal('0')
    for f in cibles:
        f.marquer_assurance(action)
        montant += f.part_assurance()

    messages.success(
        request,
        f"{len(cibles)} facture{'s' if len(cibles) > 1 else ''} — "
        f"{libelles[action].lower()} — {_fmt(montant)} FCFA.")
    return redirect(retour)


@permission_required('facture.view', 'rapport.view')
def creances_export(request):
    """Exporte le détail à réclamer, prêt à être envoyé à l'assureur.

    ?assurance=<id> limite l'export à un seul assureur : c'est le fichier que
    la clinique joint à sa demande de remboursement.
    """
    from django.utils.text import slugify
    from .exports import csv_response

    factures, periode_label, _ = _factures_prises_en_charge(request)

    assurance_id = (request.GET.get('assurance') or '').strip()
    nom = 'toutes-assurances'
    if assurance_id:
        factures = factures.filter(assurance_id=assurance_id)
        premiere = factures.first()
        if premiere:
            # slugify : sans accent ni « % », sinon le nom de fichier casse
            # l'en-tête HTTP et n'est pas enregistrable sous Windows.
            nom = slugify(premiere.assurance.nom) or 'assurance'

    headers = ['Assurance', 'Taux (%)', 'Facture', 'Patient', 'Numero assure',
               'Service', 'Date', 'Montant total', 'A reclamer', 'Part patient',
               'Recouvrement', 'Reclame le', 'Rembourse le']
    rows = [[
        f.assurance.nom,
        f'{f.taux_prise_en_charge:.0f}',
        f'FAC-{f.pk:04d}',
        f'{f.patient.nom} {f.patient.prenom}',
        f.patient.numero_assure or '',
        f.service_libelle(),
        f.date_creation.strftime('%d/%m/%Y') if f.date_creation else '',
        int(f.montant_total), int(f.part_assurance()), int(f.part_patient()),
        f.get_statut_assurance_display(),
        f.date_reclamation.strftime('%d/%m/%Y') if f.date_reclamation else '',
        f.date_remboursement.strftime('%d/%m/%Y') if f.date_remboursement else '',
    ] for f in factures]

    return csv_response(f'creances_{nom}_{slugify(periode_label)}.csv', headers, rows)


@permission_required('facture.view')
def factures_export(request):
    """Exporte la liste des factures (filtres de recherche appliqués) en CSV."""
    from .exports import csv_response
    qs = Facture.objects.select_related('patient', 'assurance').prefetch_related('paiements').order_by('-id')
    statut = request.GET.get('statut', '')
    q = request.GET.get('q', '').strip()
    if statut:
        qs = qs.filter(statut=statut)
    if q:
        qs = qs.filter(termes_q(q, 'patient__nom', 'patient__prenom'))

    headers = ['Facture', 'Patient', 'Date', 'Montant total', 'Part assurance',
               'Part patient', 'Payé', 'Statut']
    rows = [[
        f'FAC-{f.pk:04d}',
        f'{f.patient.nom} {f.patient.prenom}',
        f.date_creation.strftime('%d/%m/%Y') if f.date_creation else '',
        int(f.montant_total), int(f.part_assurance()), int(f.part_patient()),
        int(f.montant_paye()), f.get_statut_display(),
    ] for f in qs]
    return csv_response('factures.csv', headers, rows)


@role_required('admin')
def paiements_export(request):
    """Exporte le journal de caisse (paiements) en CSV."""
    from .exports import csv_response
    qs = Paiement.objects.select_related('facture', 'facture__patient').order_by('-date')
    headers = ['Date', 'Facture', 'Patient', 'Montant', 'Mode de paiement']
    rows = [[
        p.date.strftime('%d/%m/%Y %H:%M'),
        f'FAC-{p.facture_id:04d}',
        f'{p.facture.patient.nom} {p.facture.patient.prenom}',
        int(p.montant), p.get_mode_paiement_display(),
    ] for p in qs]
    return csv_response('journal_caisse.csv', headers, rows)


# ── Tarifs ───────────────────────────────────────────────────────

@permission_required('tarif.view')
def tarif_liste(request):
    tarifs = Tarif.objects.all().order_by('type_service', 'nom')
    return render(request, 'facturation/tarifs.html', {
        'tarifs':          tarifs,
        'nb_consultation': tarifs.filter(type_service='consultation').count(),
        'nb_examen':       tarifs.filter(type_service='examen').count(),
        'nb_hospit':       tarifs.filter(type_service='hospitalisation').count(),
    })


def _specialite_from_post(request):
    """Spécialité/type choisi : valeur de la liste, ou texte libre si « Autre »."""
    spec = (request.POST.get('specialite') or '').strip()
    if spec == '__autre__':
        spec = (request.POST.get('specialite_autre') or '').strip()
    return spec or None


@permission_required('tarif.add', 'tarif.manage')
def tarif_ajouter(request):
    if request.method == 'POST':
        try:
            Tarif.objects.create(
                nom=request.POST['nom'],
                type_service=request.POST['type_service'],
                specialite=_specialite_from_post(request),
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


@permission_required('tarif.manage')
def tarif_modifier(request, pk):
    tarif = get_object_or_404(Tarif, pk=pk)
    if request.method == 'POST':
        try:
            tarif.nom          = request.POST['nom']
            tarif.type_service = request.POST['type_service']
            tarif.specialite   = _specialite_from_post(request)
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


@permission_required('tarif.manage')
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