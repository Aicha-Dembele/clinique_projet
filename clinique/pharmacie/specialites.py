"""Spécialités médicales : référentiel partagé + normalisation du texte libre.

Les médecins saisissent leur spécialité en texte libre (CharField). Cette
normalisation permet de la rattacher à un code stable, utilisé pour filtrer
les médicaments proposés à la prescription dans le formulaire d'ordonnance.
"""
import unicodedata

# (code, libellé) — référentiel des spécialités gérées par le catalogue
SPECIALITES = [
    ('generaliste', 'Médecine générale'),
    ('gynecologie', 'Gynécologie'),
    ('cardiologie', 'Cardiologie'),
    ('neurologie',  'Neurologie'),
]

SPECIALITES_DICT = dict(SPECIALITES)

# Mots-clés (texte normalisé) → code, pour rattacher une spécialité saisie librement
_INDICES = [
    ('gyneco',  'gynecologie'),
    ('obstetr', 'gynecologie'),
    ('cardio',  'cardiologie'),
    ('neuro',   'neurologie'),
    ('general', 'generaliste'),
]


def sans_accents(texte):
    """Minuscule, sans accents ni espaces superflus — pour comparaisons robustes."""
    if not texte:
        return ''
    nfkd = unicodedata.normalize('NFKD', str(texte))
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def code_specialite(texte):
    """Convertit une spécialité en texte libre vers un code connu, ou None."""
    t = sans_accents(texte)
    if not t:
        return None
    for code, _ in SPECIALITES:        # correspondance exacte d'un code
        if t == code:
            return code
    for cle, code in _INDICES:         # correspondance par mot-clé
        if cle in t:
            return code
    return None
