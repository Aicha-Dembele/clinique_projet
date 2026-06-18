from .decorators import get_role


def _user_permissions(request):
    """Retourne l'ensemble des codes de permission de l'utilisateur connecte."""
    user = request.user
    if not user.is_authenticated:
        return set()
    role = get_role(user)
    if role == 'admin':
        from .models import Permission
        return set(Permission.objects.values_list('code', flat=True))
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
    if role not in ('admin', 'receptionniste'):
        return 0
    try:
        from django.db.models import F
        from pharmacie.models import Medicament
        return Medicament.objects.filter(
            actif=True, quantite_stock__lte=F('seuil_alerte')
        ).count()
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
        'user_permissions': codes,
        'perms': _PermLookup(codes),
        'stock_alertes': _stock_alertes(role),
        'notifications_non_lues': notif_count,
        'notifications_recentes': notif_list,
    }
