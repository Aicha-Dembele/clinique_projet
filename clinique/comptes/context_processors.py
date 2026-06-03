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


def role_context(request):
    role = get_role(request.user) if request.user.is_authenticated else None
    codes = _user_permissions(request)
    return {
        'user_role': role,
        'is_admin': role == 'admin',
        'is_medecin': role == 'medecin',
        'is_laborantin': role == 'laborantin',
        'is_infirmier': role == 'infirmier',
        'is_receptionniste': role == 'receptionniste',
        'user_permissions': codes,
        'perms': _PermLookup(codes),
    }
