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
        role = request.user.profil.role.code
    except Exception:
        if request.user.is_superuser:
            role = 'admin'

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

        # Nouveaux patients enregistrés ce mois-ci (chiffre réel, pas décoratif)
        nouveaux_patients_mois = Patient.objects.filter(
            date_creation__date__gte=debut_mois
        ).count()

        # Répartition des modes de paiement (sur tout l'historique)
        total_paiements = Paiement.objects.aggregate(t=Sum('montant'))['t'] or 0
        if total_paiements > 0:
            def _pct(mode):
                m = Paiement.objects.filter(mode_paiement=mode).aggregate(t=Sum('montant'))['t'] or 0
                return round(float(m) * 100 / float(total_paiements))
            pct_especes = _pct('cash')
            pct_orange  = _pct('orange_money')
            pct_carte   = _pct('carte')
        else:
            pct_especes = pct_orange = pct_carte = 0

        # ── Statistiques d'évolution sur les 6 derniers mois ──────────
        from django.db.models.functions import TruncMonth
        from django.db.models import Count
        from consultation.models import Consultation

        mois_list = []
        yy, mm = aujourd_hui.year, aujourd_hui.month
        for i in range(5, -1, -1):
            m2, y2 = mm - i, yy
            while m2 <= 0:
                m2 += 12
                y2 -= 1
            mois_list.append((y2, m2))

        NOMS = ['', 'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin',
                'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']
        stats_labels = [f'{NOMS[m2]} {y2}' for (y2, m2) in mois_list]

        rev_par_mois = {}
        for r in (Paiement.objects.annotate(mo=TruncMonth('date'))
                  .values('mo').annotate(t=Sum('montant'))):
            if r['mo']:
                rev_par_mois[(r['mo'].year, r['mo'].month)] = int(r['t'] or 0)
        stats_revenus = [rev_par_mois.get(k, 0) for k in mois_list]

        cons_par_mois = {}
        for r in (Consultation.objects.annotate(mo=TruncMonth('date'))
                  .values('mo').annotate(c=Count('id'))):
            if r['mo']:
                cons_par_mois[(r['mo'].year, r['mo'].month)] = r['c']
        stats_consultations = [cons_par_mois.get(k, 0) for k in mois_list]

        # ── Tendance du CA : mois courant vs mois précédent ──────────
        rev_courant = stats_revenus[-1]
        rev_precedent = stats_revenus[-2]
        if rev_precedent:
            tendance_pct = round((rev_courant - rev_precedent) / rev_precedent * 100)
            tendance_dir = 'up' if tendance_pct > 0 else ('down' if tendance_pct < 0 else 'flat')
        else:
            # Pas de référence le mois précédent : pas de % comparable.
            tendance_pct = None
            tendance_dir = None

        # ── Revenus par service (facturé, MOIS COURANT) ──────────────
        # Chaque LigneFacture porte un type_service ; on ne garde que les lignes
        # dont la facture a été créée ce mois-ci (même période que les recettes).
        # Agrégation en une requête, sans N+1, quel que soit le nombre de factures.
        from facturation.models import LigneFacture
        from django.db.models import F, DecimalField
        _dec = DecimalField(max_digits=16, decimal_places=2)
        rev_map = {
            r['type_service']: (r['total'] or 0)
            for r in (LigneFacture.objects
                      .filter(facture__date_creation__date__gte=debut_mois)
                      .values('type_service')
                      .annotate(total=Sum(F('prix_unitaire') * F('quantite'),
                                          output_field=_dec)))
        }
        rev_consultation    = rev_map.get('consultation', 0)
        rev_examen          = rev_map.get('examen', 0)
        rev_hospitalisation = rev_map.get('hospitalisation', 0)
        rev_pharmacie       = rev_map.get('medicament', 0)   # médicaments dispensés
        rev_global          = sum(rev_map.values()) or 0

        MOIS_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                   'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        mois_courant_label = f"{MOIS_FR[aujourd_hui.month]} {aujourd_hui.year}"

        # ── Recettes du mois passé (mois précédent complet) ──────────
        mp_y, mp_m = mois_list[-2]
        recettes_mois_precedent = rev_precedent            # = stats_revenus[-2]
        mois_precedent_label = f"{MOIS_FR[mp_m]} {mp_y}"

        ctx = {
            **base_ctx,
            'total_patients':    Patient.objects.count(),
            'nouveaux_patients_mois': nouveaux_patients_mois,
            'rdv_termines':      Rendez_vous.objects.filter(date__date=aujourd_hui, statut='termine').count(),
            'total_hospitalises': Hospitalisation.objects.filter(date_sortie__isnull=True).count(),
            'rdv_aujourd_hui':   Rendez_vous.objects.filter(date__date=aujourd_hui).order_by('date')[:8],
            'patients_recents':  Patient.objects.order_by('-date_creation')[:6],
            'recettes_mois':     recettes_mois,
            'recettes_mois_precedent': recettes_mois_precedent,
            'mois_precedent_label':    mois_precedent_label,
            'pct_especes':       pct_especes,
            'pct_orange':        pct_orange,
            'pct_carte':         pct_carte,
            'stats_labels':         stats_labels,
            'stats_revenus':        stats_revenus,
            'stats_consultations':  stats_consultations,
            'tendance_pct':         tendance_pct,
            'tendance_dir':         tendance_dir,
            # Revenus par service (facturé, mois courant)
            'rev_consultation':     rev_consultation,
            'rev_hospitalisation':  rev_hospitalisation,
            'rev_examen':           rev_examen,
            'rev_pharmacie':        rev_pharmacie,
            'rev_global':           rev_global,
            'mois_courant_label':   mois_courant_label,
        }
        return render(request, 'admin/dashboard.html', ctx)

    # ── MÉDECIN ────────────────────────────────────────────────────
    elif role == 'medecin':
        import datetime
        from django.db.models import Q, Count
        from django.db.models.functions import TruncDate
        from consultation.models import Consultation, Ordonnance
        try:
            medecin = request.user.profil.medecin
        except Exception:
            medecin = None

        mes_rdv = Rendez_vous.objects.filter(
            date__date=aujourd_hui, medecin=medecin
        ).order_by('date') if medecin else Rendez_vous.objects.none()

        tous_mes_rdv = Rendez_vous.objects.filter(medecin=medecin) if medecin else Rendez_vous.objects.none()
        mes_consult_qs = Consultation.objects.filter(rendez_vous__medecin=medecin) if medecin else Consultation.objects.none()

        # Patients suivis par ce médecin (lien de soin : RDV, hospitalisation ou examen)
        mes_patients = Patient.objects.filter(
            Q(rendez_vous__medecin=medecin) |
            Q(hospitalisation__medecin=medecin) |
            Q(examenmedical__medecin=medecin)
        ).distinct().count() if medecin else 0

        # Courbe d'activité : consultations des 7 derniers jours
        JOURS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
        par_jour = {
            r['j']: r['n'] for r in
            mes_consult_qs.filter(date__date__gte=aujourd_hui - datetime.timedelta(days=6))
            .values(j=TruncDate('date')).annotate(n=Count('id'))
        }
        activite_labels, activite_valeurs = [], []
        for i in range(6, -1, -1):
            j = aujourd_hui - datetime.timedelta(days=i)
            activite_labels.append(f'{JOURS[j.weekday()]} {j.day:02d}')
            activite_valeurs.append(par_jour.get(j, 0))

        ctx = {
            **base_ctx,
            'mes_rdv_count':         mes_rdv.count(),
            'rdv_termines':          mes_rdv.filter(statut='termine').count(),
            'mes_rdv_aujourd_hui':   mes_rdv[:8],
            'mes_patients':          mes_patients,
            'mes_consultations':     mes_consult_qs.count(),
            'mes_ordonnances':       Ordonnance.objects.filter(consultation__rendez_vous__medecin=medecin).count() if medecin else 0,
            'mes_hospitalises':      Hospitalisation.objects.filter(medecin=medecin, date_sortie__isnull=True).count() if medecin else 0,
            'mes_hospitalises_list': Hospitalisation.objects.filter(medecin=medecin, date_sortie__isnull=True)[:5] if medecin else [],
            'activite_labels':       activite_labels,
            'activite_valeurs':      activite_valeurs,
            # Donut : répartition de tous mes rendez-vous par statut
            'rdv_programmes':        tous_mes_rdv.filter(statut='programme').count(),
            'rdv_termines_total':    tous_mes_rdv.filter(statut='termine').count(),
            'rdv_annules':           tous_mes_rdv.filter(statut='annule').count(),
        }
        return render(request, 'medecin/dashboard.html', ctx)

    # ── LABORANTIN ─────────────────────────────────────────────────
    elif role == 'laborantin':
        from consultation.models import ResultatExamen
        try:
            laborantin = request.user.profil.laborantin
        except Exception:
            laborantin = None
        examens_qs = ExamenMedical.objects.all()
        ctx = {
            **base_ctx,
            'examens_liste':       examens_qs.filter(statut__in=['en_attente','en_cours']).order_by('id')[:10],
            'examens_en_cours':    examens_qs.filter(statut='en_cours').count(),
            'examens_termines':    examens_qs.filter(statut='termine').count(),
            'total_examens_mois':  examens_qs.count(),
            'derniers_resultats':  ResultatExamen.objects.order_by('-date_examen')[:4],
        }
        return render(request, 'laborantin/dashboard.html', ctx)

    # ── INFIRMIER ──────────────────────────────────────────────────
    elif role == 'infirmier':
        from consultation.models import Traitement
        hospit = Hospitalisation.objects.filter(date_sortie__isnull=True)
        traitements_qs = Traitement.objects.all()
        ctx = {
            **base_ctx,
            'total_hospitalises':   hospit.count(),
            'traitements_actifs':   traitements_qs.filter(statut__in=['prescrit', 'en_cours']).count(),
            'traitements_termines': traitements_qs.filter(statut='termine').count(),
            'sejours_longs':        hospit.filter(nombre_jours__gt=5).count(),
            'hospitalisations':     hospit[:10],
            'traitements':          traitements_qs.order_by('-date_creation')[:10],
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
            'rdv_honores':      rdvs.filter(statut='termine').count(),
            'rdv_annules':      rdvs.filter(statut='annule').count(),
        }
        return render(request, 'receptionniste/dashboard.html', ctx)

    # ── PHARMACIEN ─────────────────────────────────────────────────
    elif role == 'pharmacien':
        from pharmacie.models import Medicament, MouvementStock
        from django.db.models import F, DecimalField
        from django.db.models.functions import Coalesce

        actifs    = Medicament.objects.filter(actif=True)
        en_alerte = [m for m in actifs if m.est_en_alerte()]
        rupture   = [m for m in actifs if m.est_rupture()]
        valeur = actifs.aggregate(
            v=Coalesce(Sum(F('prix_unitaire') * F('quantite_stock'),
                           output_field=DecimalField(max_digits=14, decimal_places=2)), 0,
                       output_field=DecimalField(max_digits=14, decimal_places=2))
        )['v']
        ctx = {
            **base_ctx,
            'nb_medicaments':     actifs.count(),
            'nb_alerte':          len(en_alerte),
            'nb_rupture':         len(rupture),
            'valeur_stock':       valeur,
            'medic_a_reapprovisionner': (rupture + en_alerte)[:10],
            'mouvements_recents': MouvementStock.objects.select_related('medicament').order_by('-date')[:8],
        }
        return render(request, 'pharmacien/dashboard.html', ctx)

    # Fallback → admin
    return redirect('dashboard')
