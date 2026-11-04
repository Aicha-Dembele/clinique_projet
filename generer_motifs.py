"""Génère les dessins médicaux de l'interface (fichiers SVG, tracés pour Nevroglie).

    python generer_motifs.py

Écrit dans clinique/consultation/static/consultation/img/motifs/ :
  - icone_<nom>.svg     : un dessin seul, colorié par la feuille de style (classe .dessin) ;
  - tuile_<service>.svg : petits dessins éparpillés, répétés en fond de page ;
  - bandeau_<service>.svg : dessins plus grands, à droite de l'en-tête des pages ;
  - coin_<service>.svg  : un seul dessin, en filigrane dans le coin des cartes.

Les tuiles, bandeaux et coins portent leur couleur et leur transparence : un bleu moyen
qui reste visible en thème jour comme en thème nuit. Pour changer de dessins, modifier
ICONES ou SERVICES puis relancer ce script. Le hasard est à graine fixe : le résultat
est le même à chaque génération.
"""
import random
from pathlib import Path

SORTIE = Path(__file__).parent / 'clinique/consultation/static/consultation/img/motifs'

# Chaque dessin tient dans un carré de 64 × 64, en trait uniquement.
ICONES = {
    'stethoscope': '<path d="M16 6h-3v14a13 13 0 0 0 26 0V6h-3"/><path d="M26 33v9a11 11 0 0 0 22 0v-7"/><circle cx="48" cy="29" r="6"/>',
    'seringue': '<g transform="rotate(-45 32 32)"><path d="M2 32h10"/><rect x="12" y="25" width="30" height="14" rx="2"/><path d="M42 21v22M42 32h12M54 24v16"/><path d="M19 25v6M26 25v6M33 25v6"/></g>',
    'thermometre': '<g transform="rotate(35 32 32)"><path d="M26 42V11a6 6 0 0 1 12 0v31a11 11 0 1 1-12 0z"/><circle cx="32" cy="51" r="4.5"/><path d="M32 46.5V24"/><path d="M38 14h-4M38 21h-4M38 28h-4"/></g>',
    'gelule': '<g transform="rotate(-40 32 32)"><rect x="6" y="20" width="52" height="24" rx="12"/><path d="M32 20v24"/><path d="M14 27c2-2 4-2.5 8-2.5"/></g>',
    'comprime': '<circle cx="32" cy="32" r="22"/><path d="M16.5 47.5l31-31"/>',
    'flacon': '<rect x="22" y="5" width="20" height="9" rx="2"/><path d="M25 14v5c-7 3-11 8-11 15v19a6 6 0 0 0 6 6h24a6 6 0 0 0 6-6V34c0-7-4-12-11-15v-5"/><path d="M14 35h36M14 51h36"/><path d="M32 38v10M27 43h10"/>',
    'mortier': '<path d="M9 28h46c0 13-8 22-23 22S9 41 9 28z"/><path d="M24 50l-2 8h20l-2-8"/><path d="M36 28L50 7a4 4 0 0 1 7 4L43 28"/>',
    'ecg': '<path d="M3 34h13l5-16 9 30 7-22 4 8h20"/>',
    'coeur': '<path d="M32 56S7 41 7 23a13 13 0 0 1 25-5 13 13 0 0 1 25 5c0 18-25 33-25 33z"/><path d="M14 31h10l4-8 6 15 4-7h12"/>',
    'croix': '<path d="M25 8h14a2 2 0 0 1 2 2v13h13a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H41v13a2 2 0 0 1-2 2H25a2 2 0 0 1-2-2V41H10a2 2 0 0 1-2-2V25a2 2 0 0 1 2-2h13V10a2 2 0 0 1 2-2z"/>',
    'pansement': '<g transform="rotate(-45 32 32)"><rect x="4" y="20" width="56" height="24" rx="12"/><rect x="22" y="20" width="20" height="24"/><path d="M28 27h.01M36 27h.01M28 37h.01M36 37h.01M32 32h.01"/></g>',
    'microscope': '<path d="M12 57h40"/><path d="M40 57c8-6 11-21 1-32"/><path d="M16 46h24"/><g transform="rotate(25 30 22)"><rect x="24" y="8" width="12" height="24" rx="2"/><path d="M27 8V4h6v4M28 32v5h4v-5"/></g>',
    'tube': '<g transform="rotate(30 32 32)"><path d="M22 6h20M25 6v42a7 7 0 0 0 14 0V6"/><path d="M25 30h14"/><path d="M29 38h.01M34 43h.01"/></g>',
    'goutte': '<path d="M32 6s18 20 18 33a18 18 0 0 1-36 0C14 26 32 6 32 6z"/><path d="M23 40a9 9 0 0 0 8 8"/>',
    'lit': '<path d="M5 14v38M5 44h54M59 52V34a6 6 0 0 0-6-6H27v16"/><circle cx="15" cy="32" r="5"/>',
    'perfusion': '<path d="M36 6v50M26 58h20"/><path d="M22 10h20"/><rect x="12" y="10" width="16" height="22" rx="4"/><path d="M20 32v6c0 7-8 6-8 14v6"/><path d="M12 18h16"/>',
    'fauteuil': '<circle cx="21" cy="9" r="4"/><path d="M21 17v16h16l8 16h6"/><path d="M21 24h13"/><path d="M15 27a15 15 0 1 0 20 20"/>',
    'dossier': '<rect x="11" y="10" width="42" height="49" rx="5"/><rect x="23" y="5" width="18" height="10" rx="3"/><path d="M32 23v12M26 29h12"/><path d="M21 43h22M21 50h14"/>',
    'calendrier': '<rect x="8" y="12" width="48" height="45" rx="6"/><path d="M8 25h48M20 6v12M44 6v12"/><path d="M32 32v14M25 39h14"/>',
    'horloge': '<circle cx="32" cy="32" r="25"/><path d="M32 16v16l11 7"/>',
    'recu': '<path d="M13 6h38v52l-6.3-4-6.4 4-6.3-4-6.3 4-6.4-4L13 58z"/><path d="M23 18h18M23 27h18M23 36h10"/>',
    'bouclier': '<path d="M32 5l22 8v17c0 14-9 24-22 29-13-5-22-15-22-29V13z"/><path d="M32 20v18M23 29h18"/>',
    'plaquette': '<rect x="11" y="6" width="42" height="52" rx="6"/><circle cx="23" cy="19" r="5"/><circle cx="41" cy="19" r="5"/><circle cx="23" cy="32" r="5"/><circle cx="41" cy="32" r="5"/><circle cx="23" cy="45" r="5"/><circle cx="41" cy="45" r="5"/>',
    'sacoche': '<rect x="6" y="20" width="52" height="36" rx="6"/><path d="M22 20v-6a5 5 0 0 1 5-5h10a5 5 0 0 1 5 5v6"/><path d="M32 29v18M23 38h18"/>',
    'cerveau': '<path d="M30 9a9 9 0 0 0-9 7 9 9 0 0 0-7 14 9 9 0 0 0 4 14 9 9 0 0 0 12 8z"/><path d="M34 9a9 9 0 0 1 9 7 9 9 0 0 1 7 14 9 9 0 0 1-4 14 9 9 0 0 1-12 8z"/><path d="M22 24c3 0 5 2 5 5M42 24c-3 0-5 2-5 5M20 38c3-2 6-1 7 2M44 38c-3-2-6-1-7 2"/>',
    'ampoule': '<g transform="rotate(30 32 32)"><path d="M25 26v-7l4-5V6h6v8l4 5v7"/><path d="M22 26h20v28a4 4 0 0 1-4 4H26a4 4 0 0 1-4-4z"/><path d="M22 38h20"/></g>',
    'poche': '<path d="M16 8h32a3 3 0 0 1 3 3v29a11 11 0 0 1-11 11H24a11 11 0 0 1-11-11V11a3 3 0 0 1 3-3z"/><path d="M32 51v9"/><path d="M13 22h8M13 31h8M13 40h8"/>',
    'sachet': '<rect x="13" y="8" width="38" height="48" rx="3"/><path d="M13 16h38M13 48h38"/><path d="M32 25v14M25 32h14"/>',
    'bande': '<circle cx="22" cy="34" r="16"/><circle cx="22" cy="34" r="6"/><path d="M22 18h32v32H22"/><path d="M40 18v32"/>',
    'aerosol': '<rect x="19" y="21" width="26" height="37" rx="4"/><path d="M25 21v-7h14v7"/><path d="M32 14V8h7"/><path d="M45 8h.01M51 4h.01M51 12h.01"/><path d="M19 33h26"/>',
}

# Les dessins de chaque service. L'ordre compte : les premiers sont les plus visibles.
SERVICES = {
    'soins':       ['stethoscope', 'cerveau', 'seringue', 'coeur', 'thermometre', 'sacoche', 'pansement', 'ecg', 'croix'],
    'pharmacie':   ['mortier', 'gelule', 'flacon', 'plaquette', 'comprime', 'ampoule', 'seringue', 'goutte', 'croix'],
    'labo':        ['microscope', 'tube', 'goutte', 'flacon', 'seringue', 'ecg', 'cerveau', 'croix'],
    'hospit':      ['lit', 'perfusion', 'fauteuil', 'coeur', 'thermometre', 'ecg', 'pansement', 'croix'],
    'rdv':         ['calendrier', 'stethoscope', 'horloge', 'dossier', 'coeur', 'sacoche', 'croix'],
    'dossier':     ['dossier', 'stethoscope', 'coeur', 'cerveau', 'thermometre', 'ecg', 'croix'],
    'ordonnance':  ['dossier', 'gelule', 'plaquette', 'flacon', 'stethoscope', 'comprime', 'seringue', 'pansement'],
    'facturation': ['recu', 'bouclier', 'dossier', 'calendrier', 'coeur', 'croix'],
    'personnel':   ['sacoche', 'stethoscope', 'bouclier', 'dossier', 'coeur', 'croix'],
}

TRAIT = 'fill="none" stroke="{}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"'
COULEUR = '#3f8ed8'     # bleu moyen : lisible sur le fond clair comme sur le fond sombre
OPACITE_TUILE = .24
OPACITE_COIN = .32


def icone(nom):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" {TRAIT.format("#000")}>{ICONES[nom]}</svg>\n'


def placer(nom, x, y, taille, rotation, opacite):
    """Un dessin centré en (x, y). Le trait garde la même épaisseur quelle que soit la taille."""
    e = taille / 64
    return (f'<g transform="translate({x:.1f} {y:.1f}) rotate({rotation:.0f}) scale({e:.3f}) translate(-32 -32)"'
            f' stroke-width="{1.8 / e:.2f}" opacity="{opacite:.2f}">{ICONES[nom]}</g>')


def fichier(largeur, hauteur, morceaux):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largeur} {hauteur}" width="{largeur}" '
            f'height="{hauteur}" {TRAIT.format(COULEUR)}>{"".join(morceaux)}</svg>\n')


def tuile(noms, graine):
    """Grille en quinconce de petits dessins : aucun ne dépasse, donc les raccords ne se voient pas."""
    hasard = random.Random(graine)
    pas, cases, marge = 118, 4, 36
    cote = pas * cases
    morceaux = []
    for rang in range(cases):
        for col in range(cases):
            decalage = -pas / 4 if rang % 2 else pas / 4
            x = min(max(col * pas + pas / 2 + decalage + hasard.uniform(-7, 7), marge), cote - marge)
            y = rang * pas + pas / 2 + hasard.uniform(-10, 10)
            nom = noms[(rang * 3 + col) % len(noms)]    # jamais deux fois le même dessin côte à côte
            morceaux.append(placer(nom, x, y, hasard.uniform(44, 56), hasard.uniform(-22, 22), OPACITE_TUILE))
    return fichier(cote, cote, morceaux)


def bandeau(noms, graine):
    """Dessins plus grands, de plus en plus nets vers la droite."""
    hasard = random.Random(graine)
    largeur, hauteur = 760, 170
    ordre = list(noms[:7])
    morceaux = []
    for i, nom in enumerate(ordre):
        t = i / max(1, len(ordre) - 1)              # 0 = le plus à droite
        x = largeur - 62 - t * 620
        y = hauteur / 2 + (22 if i % 2 else -18) + hasard.uniform(-6, 6)
        morceaux.append(placer(nom, x, y, 104 - 46 * t, hasard.uniform(-14, 14), .95 - .6 * t))
    return fichier(largeur, hauteur, morceaux)


def coin(noms):
    return fichier(64, 64, [placer(noms[0], 32, 32, 58, -10, OPACITE_COIN)])


def main():
    SORTIE.mkdir(parents=True, exist_ok=True)
    for nom in ICONES:
        (SORTIE / f'icone_{nom}.svg').write_text(icone(nom), encoding='utf-8')
    for i, (service, noms) in enumerate(SERVICES.items()):
        (SORTIE / f'tuile_{service}.svg').write_text(tuile(noms, 2026 + i), encoding='utf-8')
        (SORTIE / f'bandeau_{service}.svg').write_text(bandeau(noms, 7 + i), encoding='utf-8')
        (SORTIE / f'coin_{service}.svg').write_text(coin(noms), encoding='utf-8')
    print(f'{len(ICONES)} dessins, {len(SERVICES)} services → {SORTIE}')


if __name__ == '__main__':
    main()
