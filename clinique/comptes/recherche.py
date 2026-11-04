"""Aide à la recherche texte des listes (patients, RDV, consultations…)."""
import re
import unicodedata

from django.db.models import CharField, Q, TextField, Transform, Value
from django.db.models.functions import Concat, Lower, Replace

#: Lettres accentuées ramenées à leur lettre simple, côté base de données.
#: Les majuscules sont listées aussi : sous SQLite, LOWER() ne connaît que
#: l'ASCII et laisse « É » tel quel.
ACCENTS = {
    'a': 'àâäáÀÂÄÁ', 'c': 'çÇ', 'e': 'éèêëÉÈÊË', 'i': 'îïíÎÏÍ',
    'o': 'ôöóÔÖÓ', 'u': 'ùûüúÙÛÜÚ', 'y': 'ÿŸ',
}

#: Caractères qui séparent deux mots : « Jean-Pierre », « N'Diaye »,
#: « awa.traore@… », « +223 70… ». Ils sont tous ramenés à une espace.
SEPARATEURS = "-'.@/+(),"


class Mots(Transform):
    """Le texte d'un champ, prêt à être cherché mot par mot.

    En SQL : minuscules, sans accents, séparateurs remplacés par des espaces,
    et une espace ajoutée devant. Chercher « ' kei' » dedans revient alors à
    chercher un mot qui COMMENCE par « kei », où qu'il soit dans le champ.

    Pourquoi en SQL et pas avec __icontains : la base MySQL de la clinique
    est en collation utf8mb4_bin (voir local_settings), qui distingue les
    majuscules — « kante » ne trouvait pas « Kante ».
    """
    lookup_name = 'mots'

    def as_sql(self, compiler, connection):
        texte = Lower(self.lhs)
        for lettre, variantes in ACCENTS.items():
            for variante in variantes:
                texte = Replace(texte, Value(variante), Value(lettre))
        for separateur in SEPARATEURS:
            texte = Replace(texte, Value(separateur), Value(' '))
        return compiler.compile(Concat(Value(' '), texte, output_field=CharField()))


CharField.register_lookup(Mots)
TextField.register_lookup(Mots)
# `champ__lower=…` : comparaison sans tenir compte des majuscules qui marche
# AUSSI sur MySQL en utf8mb4_bin — contrairement à __iexact / __istartswith,
# que cette collation rend sensibles à la casse sans prévenir.
CharField.register_lookup(Lower)
TextField.register_lookup(Lower)


def normaliser(texte):
    """Le même traitement que Mots, en Python, pour ce que l'utilisateur a tapé."""
    texte = unicodedata.normalize('NFKD', texte or '')
    texte = ''.join(c for c in texte if not unicodedata.combining(c)).lower()
    for separateur in SEPARATEURS:
        texte = texte.replace(separateur, ' ')
    return texte


def termes_q(q, *champs, numero=None, champ_numero='pk'):
    """Construit un filtre de recherche multi-mots.

    Chaque mot de `q` doit être le DÉBUT d'un mot d'au moins un des `champs` ;
    les mots sont ensuite combinés en ET. Ainsi :
      - « Oumar Kante » et « kante oumar » trouvent le patient Kante Oumar,
        même si aucun champ ne contient la chaîne complète ;
      - « K », « Ke », « Kei »… le trouvent au fur et à mesure de la frappe ;
      - majuscules et accents ne comptent pas (« kanté » = « KANTE »).

    `numero` : le préfixe affiché dans la liste (« FAC », « ORD »…). Taper
    « FAC-0012 », « fac12 » ou « 12 » trouve alors aussi l'élément n° 12
    (`champ_numero`, la clé primaire par défaut).

    Exemple :
        qs.filter(termes_q(q, 'nom', 'prenom', 'telephone', numero='P'))

    Renvoie un Q() vide si `q` est vide (donc aucun filtrage).
    """
    filtre = Q()
    for mot in normaliser(q).split():
        sous = Q()
        for champ in champs:
            sous |= Q(**{f'{champ}__mots__contains': ' ' + mot})
        filtre &= sous
    if numero and filtre:
        trouve = re.fullmatch(rf'\s*(?:{re.escape(numero)})?[\s-]*0*(\d+)\s*', q, re.IGNORECASE)
        if trouve:
            filtre |= Q(**{champ_numero: int(trouve.group(1))})
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
