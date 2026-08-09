"""Execute chaque requete de requetes_soutenance.sql et affiche son resultat.

Sert a garantir qu'aucune requete presentee au jury ne plante ou ne renvoie
un tableau vide le jour J.
"""
import os
import re
import sys

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(RACINE, "clinique"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "clinique.settings")

import django  # noqa: E402

django.setup()
from django.db import connection  # noqa: E402


def decouper(chemin):
    """Rend une liste de (etiquette, commentaire, sql)."""
    texte = open(chemin, encoding="utf-8").read()
    blocs = []
    courant, titre = [], None
    for ligne in texte.splitlines():
        m = re.match(r"^-- ([A-H]\d)\. (.+)", ligne)
        if m:
            if titre and courant:
                blocs.append((*titre, "\n".join(courant).strip()))
            titre, courant = (m.group(1), m.group(2)), []
        elif titre is not None and not ligne.startswith("-- ---"):
            if not ligne.lstrip().startswith("--"):
                courant.append(ligne)
    if titre and courant:
        blocs.append((*titre, "\n".join(courant).strip()))
    return [(e, c, s.rstrip(";").strip()) for e, c, s in blocs if s.strip()]


def main():
    requetes = decouper(os.path.join(RACINE, "requetes_soutenance.sql"))
    print(f"{len(requetes)} requetes a verifier\n")
    echecs, vides = [], []
    for etiquette, commentaire, sql in requetes:
        try:
            with connection.cursor() as cur:
                cur.execute(sql)
                colonnes = [d[0] for d in cur.description] if cur.description else []
                lignes = cur.fetchall() if colonnes else []
        except Exception as e:
            echecs.append((etiquette, str(e).split("\n")[0][:130]))
            print(f"[{etiquette}] ECHEC — {commentaire}")
            print(f"        {str(e).split(chr(10))[0][:130]}\n")
            continue
        if not lignes:
            vides.append(etiquette)
        marque = "vide" if not lignes else f"{len(lignes)} ligne(s)"
        print(f"[{etiquette}] {commentaire}  →  {marque}")
        if lignes:
            larges = [
                max(len(str(c)), max((len(str(l[i])) for l in lignes[:5]), default=0))
                for i, c in enumerate(colonnes)
            ]
            larges = [min(w, 26) for w in larges]
            print("        " + " | ".join(
                str(c)[:26].ljust(w) for c, w in zip(colonnes, larges)))
            for l in lignes[:4]:
                print("        " + " | ".join(
                    str(v)[:26].ljust(w) for v, w in zip(l, larges)))
            if len(lignes) > 4:
                print(f"        … {len(lignes)-4} ligne(s) de plus")
        print()

    print("=" * 62)
    print(f"{len(requetes)-len(echecs)}/{len(requetes)} requetes s'executent sans erreur")
    if echecs:
        print("ECHECS :", ", ".join(e for e, _ in echecs))
    if vides:
        print("Resultat vide (a eviter devant le jury) :", ", ".join(vides))


if __name__ == "__main__":
    main()
