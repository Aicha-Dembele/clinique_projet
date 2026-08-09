from .decorators import get_role


def _user_permissions(request):
    """Retourne l'ensemble des codes de permission de l'utilisateur connecte."""
    user = request.user
    if not user.is_authenticated:
        return set()
    # L'administrateur est soumis à sa liste de permissions comme les autres rôles.
    # Il garde toutefois TOUJOURS l'accès à « Rôles & Permissions » (protégée par
    # admin_required, basé sur le rôle et non sur une permission), donc il peut
    # toujours se re-donner des droits — impossible de se verrouiller.
    try:
        return set(user.profil.role.permissions.values_list('code', flat=True))
    except Exception:
        return set()


class _PermLookup:
    """Permet 'perms.patient_view' dans les templates (point au lieu de .)."""
    def __init__(self, codes):
        self._codes = codes

    def __contains__(self, code):
        return code in self._codes

    def __getitem__(self, code):
        return code.replace('_', '.') in self._codes or code in self._codes

    def __getattr__(self, name):
        return name.replace('_', '.') in self._codes


def _stock_alertes(role):
    """Nombre de médicaments actifs en rupture ou sous le seuil d'alerte.
    Calculé seulement pour les rôles ayant accès à la pharmacie (badge du menu)."""
    if role not in ('admin', 'receptionniste', 'pharmacien'):
        return 0
    try:
        from django.db.models import F
        from pharmacie.models import Medicament
        return Medicament.objects.filter(
            actif=True, quantite_stock__lte=F('seuil_alerte')
        ).count()
    except Exception:
        return 0


def _resultats_non_lus(request, role):
    """Nombre de résultats d'examens transmis au médecin connecté et pas encore
    lus par lui (badge du menu). Un résultat est marqué lu quand le médecin
    ouvre son détail ; une retransmission le repasse en non lu."""
    if role != 'medecin':
        return 0
    try:
        from consultation.models import ResultatExamen
        medecin = getattr(request.user.profil, 'medecin', None)
        if not medecin:
            return 0
        return ResultatExamen.objects.filter(
            examen__medecin=medecin, transmis=True, lu_par_medecin=False).count()
    except Exception:
        return 0


def _examens_a_faire(request, role):
    """Nombre d'examens adressés au laborantin connecté et pas encore réalisés
    (badge du menu « Examens médicaux »). Un examen est « à faire » tant qu'aucun
    résultat n'y est rattaché."""
    if role != 'laborantin':
        return 0
    try:
        from consultation.models import ExamenMedical
        labo = getattr(request.user.profil, 'laborantin', None)
        if not labo:
            return 0
        return ExamenMedical.objects.filter(
            laborantin=labo, resultats__isnull=True).distinct().count()
    except Exception:
        return 0


def _notifications(request):
    """(nombre_non_lues, 8 dernières) pour la cloche de la barre du haut."""
    if not request.user.is_authenticated:
        return 0, []
    try:
        from .models import Notification
        qs = Notification.objects.filter(user=request.user)
        return qs.filter(lu=False).count(), list(qs[:8])
    except Exception:
        return 0, []


def role_context(request):
    role = get_role(request.user) if request.user.is_authenticated else None
    codes = _user_permissions(request)
    notif_count, notif_list = _notifications(request)
    return {
        'user_role': role,
        'is_admin': role == 'admin',
        'is_medecin': role == 'medecin',
        'is_laborantin': role == 'laborantin',
        'is_infirmier': role == 'infirmier',
        'is_receptionniste': role == 'receptionniste',
        'is_pharmacien': role == 'pharmacien',
        'user_permissions': codes,
        'perms': _PermLookup(codes),
        'stock_alertes': _stock_alertes(role),
        'resultats_non_lus': _resultats_non_lus(request, role),
        'examens_a_faire': _examens_a_faire(request, role),
        'notifications_non_lues': notif_count,
        'notifications_recentes': notif_list,
    }
