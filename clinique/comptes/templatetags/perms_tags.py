from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def has_perm(context, code):
    """Verifie si l'utilisateur connecte possede la permission `code`."""
    codes = context.get('user_permissions') or set()
    return code in codes
