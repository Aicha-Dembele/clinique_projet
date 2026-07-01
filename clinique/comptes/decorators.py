from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages


def get_role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return 'admin'
    try:
        return user.profil.role.code
    except Exception:
        return None


def role_required(*roles):
    """Decorator: only allow users whose profile role is in the given list. Admin always allowed."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            role = get_role(request.user)
            if role == 'admin' or role in roles:
                return view_func(request, *args, **kwargs)
            messages.error(request, "Vous n'avez pas l'autorisation d'acceder a cette page.")
            return redirect('dashboard')
        return _wrapped
    return decorator


def permission_required(*codes):
    """Autorise l'accès si l'utilisateur possède AU MOINS UNE des permissions données.

    Contrairement à `role_required` (liste de rôles figée dans le code), ce contrôle
    s'appuie sur les permissions du rôle — modifiables depuis l'écran « Rôles &
    permissions ». Cocher une permission donne donc réellement accès à la page.
    L'administrateur (rôle admin ou superuser) est toujours autorisé.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            try:
                if any(user.profil.has_permission(c) for c in codes):
                    return view_func(request, *args, **kwargs)
            except Exception:
                pass
            messages.error(request, "Vous n'avez pas l'autorisation d'acceder a cette page.")
            return redirect('dashboard')
        return _wrapped
    return decorator


def admin_required(view_func):
    return role_required('admin')(view_func)


def medecin_required(view_func):
    return role_required('medecin')(view_func)


def laborantin_required(view_func):
    return role_required('laborantin')(view_func)


def infirmier_required(view_func):
    return role_required('infirmier')(view_func)


def receptionniste_required(view_func):
    return role_required('receptionniste')(view_func)


def pharmacien_required(view_func):
    return role_required('pharmacien')(view_func)
