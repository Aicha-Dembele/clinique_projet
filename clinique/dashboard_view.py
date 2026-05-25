from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from patients.models import Patient


@login_required
def dashboard(request):
    """
    Redirige vers le bon dashboard selon le rôle de l'utilisateur.
    Si aucun profil n'est défini → dashboard admin par défaut.
    """
    role = 'admin'  # défaut
    try:
        role = request.user.profil.role
    except Exception:
        pass

    aujourd_hui = timezone.now().date()

    # Imports ici pour éviter les imports circulaires
    from consultation.models import Rendez_vous, Hospitalisation, ExamenMedical
    from facturation.models import Facture, Paiement
    from django.db.models import Sum

    # Contexte commun (utilisé dans la sidebar / notifs pour tous les rôles)
    base_ctx = {
        'rdv_count':            Rendez_vous.objects.filter(date__date=aujourd_hui).count(),
        'examens_attente_count': ExamenMedical.objects.filter(statut='en_attente').count(),
        'factures_impayees':    Facture.objects.filter(statut='non payé').count(),
    }

    # ── ADMIN ──────────────────────────────────────────────────────
    if role == 'admin':
        # Recettes du mois courant (paiements)
        debut_mois = aujourd_hui.replace(day=1)
        recettes_mois = Paiement.objects.filter(
            date__date__gte=debut_mois
        ).aggregate(total=Sum('montant'))['total'] or 0

        # Répartition des modes de paiement (sur tout l'historique)
        total_paiements = Paiement.objects.aggregate(t=Sum('montant'))['t'] or 0
        if total_paiements > 0:
            def _pct(mode):
                m = Paiement.objects.filter(mode_paiement=mode).aggregate(t=Sum('montant'))['t'] or 0
                return round(float(m) * 100 / float(total_paiements))
            pct_especes = _pct('cash')
            pct_orange  = _pct('orange_money')
            pct_moov    = _pct('moov_money')
            pct_carte   = _pct('carte')
        else:
            pct_especes = pct_orange = pct_moov = pct_carte = 0

        ctx = {
            **base_ctx,
            'total_patients':    Patient.objects.count(),
            'rdv_termines':      Rendez_vous.objects.filter(date__date=aujourd_hui, statut='termine').count(),
            'total_hospitalises': Hospitalisation.objects.filter(date_sortie__isnull=True).count(),
            'rdv_aujourd_hui':   Rendez_vous.objects.filter(date__date=aujourd_hui).order_by('date')[:8],
            'patients_recents':  Patient.objects.order_by('-date_creation')[:6],
            'recettes_mois':     recettes_mois,
            'pct_especes':       pct_especes,
            'pct_orange':        pct_orange,
            'pct_moov':          pct_moov,
            'pct_carte':         pct_carte,
        }
        return render(request, 'admin/dashboard.html', ctx)

    # ── MÉDECIN ────────────────────────────────────────────────────
    elif role == 'medecin':
        from consultation.models import Consultation
        try:
            medecin = request.user.profil.medecin
        except Exception:
            medecin = None

        mes_rdv = Rendez_vous.objects.filter(
            date__date=aujourd_hui, medecin=medecin
        ).order_by('date') if medecin else Rendez_vous.objects.none()

        ctx = {
            **base_ctx,
            'mes_rdv_count':         mes_rdv.count(),
            'rdv_termines':          mes_rdv.filter(statut='termine').count(),
            'mes_rdv_aujourd_hui':   mes_rdv[:8],
            'mes_consultations':     Consultation.objects.filter(rendez_vous__medecin=medecin).count() if medecin else 0,
            'mes_consultations_list': Consultation.objects.filter(rendez_vous__medecin=medecin).order_by('-date')[:5] if medecin else [],
            'mes_hospitalises':      Hospitalisation.objects.filter(medecin=medecin, date_sortie__isnull=True).count() if medecin else 0,
            'mes_hospitalises_list': Hospitalisation.objects.filter(medecin=medecin, date_sortie__isnull=True)[:5] if medecin else [],
        }
        return render(request, 'medecin/dashboard.html', ctx)

    # ── LABORANTIN ─────────────────────────────────────────────────
    elif role == 'laborantin':
        ctx = {
            **base_ctx,
            'examens_liste':       ExamenMedical.objects.filter(statut__in=['en_attente','en_cours']).order_by('id')[:10],
            'examens_en_cours':    ExamenMedical.objects.filter(statut='en_cours').count(),
            'examens_termines':    ExamenMedical.objects.filter(statut='termine').count(),
            'total_examens_mois':  ExamenMedical.objects.count(),
            'derniers_resultats':  ExamenMedical.objects.filter(statut='termine').order_by('-id')[:4],
        }
        return render(request, 'laborantin/dashboard.html', ctx)

    # ── INFIRMIER ──────────────────────────────────────────────────
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

    # ── RÉCEPTIONNISTE ─────────────────────────────────────────────
    elif role == 'receptionniste':
        rdvs = Rendez_vous.objects.filter(date__date=aujourd_hui).order_by('date')
        ctx = {
            **base_ctx,
            'rdv_aujourd_hui':  rdvs[:10],
            'rdv_restants':     rdvs.filter(statut='programme').count(),
            'nouveaux_patients': Patient.objects.filter(date_creation__date=aujourd_hui).count(),
            'rdv_annules':      rdvs.filter(statut='annule').count(),
        }
        return render(request, 'receptionniste/dashboard.html', ctx)

    # Fallback → admin
    return redirect('dashboard')
