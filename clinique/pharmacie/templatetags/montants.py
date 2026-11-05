from django import template

register = template.Library()


@register.filter
def espaces(montant):
    """Un montant lisible, avec une espace entre les milliers : 1 250 000."""
    try:
        return f'{round(montant):,}'.replace(',', ' ')
    except (TypeError, ValueError):
        return '0'
