"""Aide à la recherche texte des listes (patients, RDV, consultations…)."""
from django.db.models import Q


def termes_q(q, *champs):
    """Construit un filtre de recherche multi-mots.

    Chaque mot de `q` doit correspondre (icontains) à au moins un des `champs` ;
    les mots sont ensuite combinés en ET. Ainsi « Diallo Mami » trouve le patient
    dont le nom est « Diallo » et le prénom « Mami », même si aucun champ ne
    contient la chaîne complète « Diallo Mami ».

    Exemple :
        qs.filter(termes_q(q, 'nom', 'prenom', 'telephone'))

    Renvoie un Q() vide si `q` est vide (donc aucun filtrage).
    """
    filtre = Q()
    for mot in (q or '').split():
        sous = Q()
        for champ in champs:
            sous |= Q(**{f'{champ}__icontains': mot})
        filtre &= sous
    return filtre
