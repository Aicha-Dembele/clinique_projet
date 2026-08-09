"""Bascule la base de l'application de SQLite vers MySQL, puis verifie le transfert.

Le fichier db.sqlite3 n'est jamais modifie ni supprime : on le lit, c'est tout.
En cas de probleme, commenter le bloc DATABASES de clinique/clinique/local_settings.py
suffit a repartir sur SQLite.

Prerequis : le mot de passe root doit etre renseigne dans local_settings.py
(MYSQL_PASSWORD) ou dans la variable d'environnement MYSQL_PASSWORD.

Usage :  venv\\Scripts\\python.exe migrer_vers_mysql.py
"""
import json
import os
import sqlite3
import subprocess
import sys

# la console Windows est en cp1252 et refuse les accents et les fleches
for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

RACINE = os.path.dirname(os.path.abspath(__file__))
PROJET = os.path.join(RACINE, "clinique")
SQLITE = os.path.join(PROJET, "db.sqlite3")
DUMP = os.path.join(RACINE, "donnees_avant_mysql.json")
PY = sys.executable

# la collation binaire est sensible a la casse : indispensable ici, voir local_settings
COLLATION = "utf8mb4_bin"


def etape(n, titre):
    print(f"\n[{n}] {titre}")
    print("-" * (len(titre) + 6))


def config_base():
    sys.path.insert(0, PROJET)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "clinique.settings")
    import django

    django.setup()
    from django.conf import settings

    return settings.DATABASES["default"]


def creer_base(cfg, recreer=False):
    """CREATE DATABASE avec la bonne collation. Le mot de passe vient des reglages,
    il n'a pas a transiter par la ligne de commande.

    Avec recreer=True on repart de zero, pour que le schema soit bien celui que
    Django genere lui-meme et non celui d'un ancien import SQL.
    """
    import MySQLdb

    if not cfg.get("PASSWORD"):
        sys.exit(
            "Le mot de passe MySQL est vide.\n"
            "Renseigne MYSQL_PASSWORD dans clinique/clinique/local_settings.py, "
            "puis relance."
        )
    cnx = MySQLdb.connect(
        host=cfg["HOST"], port=int(cfg["PORT"]),
        user=cfg["USER"], passwd=cfg["PASSWORD"],
    )
    cur = cnx.cursor()
    if recreer:
        cur.execute(f"DROP DATABASE IF EXISTS `{cfg['NAME']}`")
        print("    ancienne base supprimee (les donnees viennent de SQLite, rien n'est perdu)")
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS `{cfg['NAME']}` "
        f"CHARACTER SET utf8mb4 COLLATE {COLLATION}"
    )
    cur.execute(
        "SELECT default_character_set_name, default_collation_name "
        "FROM information_schema.SCHEMATA WHERE schema_name=%s",
        (cfg["NAME"],),
    )
    jeu, col = cur.fetchone()
    cnx.close()
    print(f"    base « {cfg['NAME']} » prete — {jeu} / {col}")
    if col != COLLATION:
        sys.exit(
            f"    collation {col} au lieu de {COLLATION} : les comptes AICHA/Aicha/aicha "
            "entreraient en conflit. Supprime la base et relance."
        )


def manage(*args):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run(
        [PY, os.path.join(PROJET, "manage.py"), *args],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )
    if r.returncode:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:], file=sys.stderr)
        sys.exit(f"    echec de « manage.py {' '.join(args)} »")
    return r.stdout


def installer_fuseaux(cfg, tz_app):
    """Charge dans MySQL les fuseaux horaires dont Django a besoin.

    MySQL sous Windows est livre SANS ses tables de fuseaux : `CONVERT_TZ` renvoie
    alors NULL, et Django leve « Database returned an invalid datetime value » des
    qu'il regroupe par date — le tableau de bord, typiquement. Django n'emet
    CONVERT_TZ que si le fuseau demande differe de celui de la connexion
    (operations.py), et il demande settings.TIME_ZONE : il faut donc que MySQL
    connaisse « UTC » et ce fuseau-la.

    On ne traite que les fuseaux a decalage constant, ce qui est le cas ici :
    Africa/Bamako vaut UTC+00:00 depuis 1960 et n'a jamais d'heure d'ete. Une
    seule regle suffit, sans aucune transition a declarer.
    """
    import datetime
    from zoneinfo import ZoneInfo

    import MySQLdb

    zone = ZoneInfo(tz_app)
    decalages = {
        datetime.datetime(an, mois, 15, 12, tzinfo=zone).utcoffset()
        for an in range(1970, 2051, 5) for mois in (1, 7)
    }
    if len(decalages) != 1:
        sys.exit(
            f"    {tz_app} change de decalage dans l'annee (heure d'ete) : il faut "
            "charger les vraies tables de fuseaux de MySQL, ce script ne sait pas le faire."
        )
    secondes = int(next(iter(decalages)).total_seconds())

    cnx = MySQLdb.connect(
        host=cfg["HOST"], port=int(cfg["PORT"]), user=cfg["USER"],
        passwd=cfg["PASSWORD"], db="mysql",
    )
    cur = cnx.cursor()
    poses = []
    for nom, offset, abrev in (("UTC", 0, "UTC"), (tz_app, secondes, "GMT")):
        cur.execute("select Time_zone_id from time_zone_name where Name=%s", (nom,))
        if cur.fetchone():
            continue
        cur.execute("insert into time_zone (Use_leap_seconds) values ('N')")
        tzid = cur.lastrowid
        cur.execute(
            "insert into time_zone_name (Name, Time_zone_id) values (%s,%s)", (nom, tzid)
        )
        cur.execute(
            "insert into time_zone_transition_type "
            "(Time_zone_id, Transition_type_id, Offset, Is_DST, Abbreviation) "
            "values (%s,0,%s,0,%s)",
            (tzid, offset, abrev),
        )
        poses.append(nom)
    cnx.commit()
    cur.execute("flush tables")
    cnx.close()

    # on verifie sur une connexion neuve : le cache des fuseaux est par connexion
    cnx = MySQLdb.connect(
        host=cfg["HOST"], port=int(cfg["PORT"]), user=cfg["USER"],
        passwd=cfg["PASSWORD"], db=cfg["NAME"],
    )
    cur = cnx.cursor()
    cur.execute("select CONVERT_TZ('2026-01-01 12:00:00','UTC',%s)", (tz_app,))
    essai = cur.fetchone()[0]
    cnx.close()
    if essai is None:
        sys.exit(f"    CONVERT_TZ vers {tz_app} renvoie toujours NULL")
    return poses, essai


# Tables gerees par le framework : elles different legitimement de SQLite
# (recreees par migrate) et ne doivent surtout pas etre alignees.
CADRE = {
    "django_session", "django_migrations", "django_content_type", "auth_permission",
}


def pk_de(src, table):
    """Nom de la colonne cle primaire d'une table SQLite."""
    for col in src.execute(f"PRAGMA table_info(`{table}`)"):
        if col[5]:  # pk
            return col[1]
    return None


def colonnes_de(src, table):
    return [c[1] for c in src.execute(f"PRAGMA table_info(`{table}`)")]


def cles_de_liaison(cols):
    """Table de liaison auto-generee par Django : id + exactement deux colonnes *_id.

    Ses `id` sont reattribues a l'import (dumpdata serialise les relations
    plusieurs-a-plusieurs comme une liste dans l'objet parent, pas comme des
    lignes). Il faut donc les comparer sur le couple de cles etrangeres.
    """
    fk = [c for c in cols if c.endswith("_id")]
    if len(cols) == 3 and "id" in cols and len(fk) == 2:
        return fk
    return None


def aligner(cfg):
    """Supprime dans MySQL les lignes absentes de SQLite.

    Certaines migrations sont des « seeds » : elles reinserent des donnees de
    reference (ici 6 assurances) que l'utilisatrice avait supprimees. Sans cette
    etape, MySQL contient des lignes fantomes qui reapparaitraient dans l'appli.
    """
    import MySQLdb

    src = sqlite3.connect(SQLITE)
    tables = sorted(
        r[0] for r in src.execute(
            "select name from sqlite_master where type='table' "
            "and name not like 'sqlite_%'"
        )
    )
    cnx = MySQLdb.connect(
        host=cfg["HOST"], port=int(cfg["PORT"]), user=cfg["USER"],
        passwd=cfg["PASSWORD"], db=cfg["NAME"],
    )
    cur = cnx.cursor()
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    retires = []
    for t in tables:
        if t in CADRE:
            continue
        cols = colonnes_de(src, t)
        liaison = cles_de_liaison(cols)
        pk = pk_de(src, t)
        if liaison:
            a, b = liaison
            gardees = {tuple(r) for r in src.execute(f"select `{a}`,`{b}` from `{t}`")}
            try:
                cur.execute(f"select `id`,`{a}`,`{b}` from `{t}`")
            except Exception:
                continue
            en_trop = [r[0] for r in cur.fetchall() if (r[1], r[2]) not in gardees]
            colonne_suppr = "id"
        else:
            if not pk:
                continue
            gardees = {r[0] for r in src.execute(f"select `{pk}` from `{t}`")}
            try:
                cur.execute(f"select `{pk}` from `{t}`")
            except Exception:
                continue
            en_trop = [r[0] for r in cur.fetchall() if r[0] not in gardees]
            colonne_suppr = pk
        if en_trop:
            marques = ",".join(["%s"] * len(en_trop))
            cur.execute(
                f"delete from `{t}` where `{colonne_suppr}` in ({marques})", en_trop
            )
            retires.append((t, len(en_trop)))
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    cnx.commit()
    cnx.close()
    return retires


def comparer(cfg):
    """Compare le nombre de lignes table par table, SQLite contre MySQL."""
    import MySQLdb

    src = sqlite3.connect(SQLITE)
    tables = sorted(
        r[0] for r in src.execute(
            "select name from sqlite_master where type='table' "
            "and name not like 'sqlite_%'"
        )
    )
    cnx = MySQLdb.connect(
        host=cfg["HOST"], port=int(cfg["PORT"]), user=cfg["USER"],
        passwd=cfg["PASSWORD"], db=cfg["NAME"],
    )
    cur = cnx.cursor()
    # tables volatiles : recreees a l'usage, leur contenu n'a pas a etre transfere
    ignorees = {"django_session", "django_migrations"}
    ecarts, total_src, total_dst = [], 0, 0
    for t in tables:
        n_src = src.execute(f"select count(*) from `{t}`").fetchone()[0]
        try:
            cur.execute(f"select count(*) from `{t}`")
            n_dst = cur.fetchone()[0]
        except Exception:
            n_dst = None
        if t not in ignorees:
            total_src += n_src
            total_dst += n_dst or 0
        if n_dst != n_src and t not in ignorees:
            ecarts.append((t, n_src, n_dst))
    cnx.close()
    return total_src, total_dst, ecarts


def main():
    if not os.path.exists(DUMP):
        sys.exit(f"export introuvable : {DUMP}")

    etape(1, "Lecture de la configuration")
    cfg = config_base()
    if "mysql" not in cfg["ENGINE"]:
        sys.exit(f"    l'application pointe encore sur {cfg['ENGINE']}")
    print(f"    cible : {cfg['USER']}@{cfg['HOST']}:{cfg['PORT']} → {cfg['NAME']}")

    recreer = "--recreer" in sys.argv
    etape(2, "Creation de la base" + (" (reconstruction complete)" if recreer else ""))
    creer_base(cfg, recreer)

    etape(3, "Fuseaux horaires de MySQL")
    from django.conf import settings as _s
    poses, essai = installer_fuseaux(cfg, _s.TIME_ZONE)
    print(f"    fuseaux charges : {', '.join(poses) if poses else 'deja presents'}")
    print(f"    CONVERT_TZ vers {_s.TIME_ZONE} -> {essai}")

    etape(4, "Creation des tables (migrate)")
    sortie = manage("migrate", "--noinput")
    lignes = [l for l in sortie.strip().splitlines() if l.strip()]
    print(f"    {len(lignes)} lignes de sortie — {lignes[-1].strip()}")

    etape(5, "Transfert des donnees (loaddata)")
    sortie = manage("loaddata", DUMP)
    print("    " + sortie.strip())

    etape(6, "Alignement sur SQLite")
    retires = aligner(cfg)
    if retires:
        for t, n in retires:
            print(f"    {n} ligne(s) recreee(s) par une migration retiree de {t}")
    else:
        print("    rien a retirer")

    etape(7, "Verification ligne par ligne")
    n_src, n_dst, ecarts = comparer(cfg)
    print(f"    SQLite : {n_src} lignes   MySQL : {n_dst} lignes")
    if ecarts:
        for t, a, b in ecarts:
            print(f"    ECART  {t} : {a} dans SQLite, {b} dans MySQL")
        sys.exit("    transfert incomplet — SQLite reste intact, rien n'est perdu")
    print("\n    Tout concorde. L'application tourne maintenant sur MySQL.")
    print("    Sauvegarde SQLite conservee : clinique/db.sqlite3")


if __name__ == "__main__":
    main()
