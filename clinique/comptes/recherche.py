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


def nouveau_en_tete(request, qs):
    """Fait remonter en tête de liste l'élément qui vient d'être ajouté.

    Les vues d'ajout redirigent vers la liste avec `?new=<pk>` ; ici cet
    élément est placé en premier (le reste garde l'ordre du queryset,
    normalement alphabétique) et son pk est renvoyé pour que le template
    surligne la ligne (classe CSS `row-new`).

    Renvoie (liste, new_pk).
    """
    new_pk = request.GET.get('new', '')
    new_pk = int(new_pk) if new_pk.isdigit() else None
    items = list(qs)
    if new_pk is not None:
        items.sort(key=lambda o: o.pk != new_pk)  # tri stable : le nouveau d'abord
    return items, new_pk
