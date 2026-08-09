# -*- coding: utf-8 -*-
"""
Exporte la base Django (SQLite) vers un fichier SQL importable dans MySQL 8.

    python export_mysql.py            -> genere clinique_db.sql

Le fichier produit cree la base `clinique_db`, toutes les tables, les cles
etrangeres et toutes les donnees. A relancer apres chaque changement de
donnees, puis reimporter dans MySQL.

Points importants :
  - collation utf8mb4_bin (sensible a la casse) : sans elle, les comptes
    aicha / Aicha / AICHA entrent en collision sur auth_user.username ;
  - toutes les cles primaires et etrangeres sont en bigint, pour que les
    contraintes FK correspondent ;
  - les FK sont creees sans ON DELETE : c'est Django qui gere on_delete.
"""

import os
import sqlite3
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SQLITE = os.path.join(BASE, "clinique", "db.sqlite3")
SORTIE = os.path.join(BASE, "clinique_db.sql")
NOM_BASE = "clinique_db"


def est_auto_increment(type_sqlite, est_pk):
    """Vrai si la cle primaire est l'entier auto-incremente de SQLite.

    Attention : certaines tables ont une cle primaire textuelle
    (django_session.session_key en varchar(40)) : elles ne doivent surtout
    pas devenir AUTO_INCREMENT, sinon toutes les cles valent 0.
    """
    return est_pk and (type_sqlite or "").lower().strip() in ("integer", "bigint")


def type_mysql(nom_col, type_sqlite, est_pk, est_fk):
    """Traduit un type SQLite en type MySQL."""
    t = (type_sqlite or "").lower().strip()
    if est_auto_increment(type_sqlite, est_pk):
        return "bigint NOT NULL AUTO_INCREMENT"
    if est_fk or t in ("bigint", "integer unsigned"):
        return "bigint"
    if t == "integer":
        return "int"
    if t == "smallint unsigned":
        return "smallint"
    if t == "bool":
        return "tinyint(1)"
    if t == "datetime":
        return "datetime(6)"
    if t == "date":
        return "date"
    if t == "time":
        return "time(6)"
    if t == "decimal":
        return "decimal(12,2)"
    if t == "text":
        return "longtext"
    if t.startswith("varchar"):
        return t
    return "longtext"


def echapper(valeur):
    """Transforme une valeur Python en litteral SQL."""
    if valeur is None:
        return "NULL"
    if isinstance(valeur, (int,)):
        return str(valeur)
    if isinstance(valeur, float):
        return repr(valeur)
    if isinstance(valeur, bytes):
        return "0x" + valeur.hex() if valeur else "''"
    texte = str(valeur)
    texte = (texte.replace("\\", "\\\\").replace("'", "\\'")
                  .replace("\r", "\\r").replace("\n", "\\n")
                  .replace("\x00", ""))
    return "'" + texte + "'"


def main():
    if not os.path.exists(SQLITE):
        sys.exit("Base SQLite introuvable : %s" % SQLITE)

    cx = sqlite3.connect(SQLITE)
    cx.text_factory = str
    cur = cx.cursor()

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    out = []
    w = out.append

    w("-- Base de donnees de l'application de gestion de clinique")
    w("-- Genere le %s a partir de %s" % (
        datetime.now().strftime("%d/%m/%Y %H:%M"), os.path.basename(SQLITE)))
    w("-- Cible : MySQL 8.0 -- import : mysql -u root -p < clinique_db.sql")
    w("")
    w("SET NAMES utf8mb4;")
    w("SET FOREIGN_KEY_CHECKS = 0;")
    w("SET SQL_MODE = 'NO_AUTO_VALUE_ON_ZERO';")
    w("")
    w("DROP DATABASE IF EXISTS `%s`;" % NOM_BASE)
    w("CREATE DATABASE `%s` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;" % NOM_BASE)
    w("USE `%s`;" % NOM_BASE)
    w("")

    total_lignes = 0
    total_fk = 0

    # ------------------------------------------------------------- structure
    for table in tables:
        colonnes = list(cur.execute('PRAGMA table_info("%s")' % table))
        fks = list(cur.execute('PRAGMA foreign_key_list("%s")' % table))
        index = list(cur.execute('PRAGMA index_list("%s")' % table))

        cols_fk = {f[3] for f in fks}
        morceaux = []

        for _, nom, type_col, non_nul, defaut, pk in colonnes:
            auto = est_auto_increment(type_col, pk == 1)
            sql_type = type_mysql(nom, type_col, pk == 1, nom in cols_fk)
            ligne = "  `%s` %s" % (nom, sql_type)
            if not auto:
                ligne += " NOT NULL" if (non_nul or pk == 1) else " NULL"
            morceaux.append(ligne)

        pk_cols = [c[1] for c in colonnes if c[5] == 1]
        if pk_cols:
            morceaux.append("  PRIMARY KEY (%s)" %
                            ", ".join("`%s`" % c for c in pk_cols))

        # contraintes d'unicite
        for _, nom_idx, unique, origine, partiel in index:
            if not unique:
                continue
            cols_idx = [r[2] for r in cur.execute('PRAGMA index_info("%s")' % nom_idx)]
            if not cols_idx or cols_idx == pk_cols:
                continue
            morceaux.append("  UNIQUE KEY `%s` (%s)" % (
                nom_idx[:60], ", ".join("`%s`" % c for c in cols_idx)))

        # index simples sur les colonnes de cle etrangere (necessaires aux FK)
        for col in sorted(cols_fk):
            morceaux.append("  KEY `idx_%s_%s` (`%s`)" % (table[:25], col[:25], col))

        w("DROP TABLE IF EXISTS `%s`;" % table)
        w("CREATE TABLE `%s` (" % table)
        w(",\n".join(morceaux))
        w(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;")
        w("")

    # ---------------------------------------------------------------- donnees
    for table in tables:
        colonnes = [c[1] for c in cur.execute('PRAGMA table_info("%s")' % table)]
        lignes = list(cur.execute('SELECT %s FROM "%s"' % (
            ", ".join('"%s"' % c for c in colonnes), table)))
        if not lignes:
            continue
        total_lignes += len(lignes)
        w("-- %s : %d ligne(s)" % (table, len(lignes)))
        entete = "INSERT INTO `%s` (%s) VALUES" % (
            table, ", ".join("`%s`" % c for c in colonnes))
        paquet = 100
        for debut in range(0, len(lignes), paquet):
            bloc = lignes[debut:debut + paquet]
            valeurs = ",\n".join(
                "(" + ", ".join(echapper(v) for v in ligne) + ")" for ligne in bloc)
            w(entete)
            w(valeurs + ";")
        w("")

    # ------------------------------------------------------- cles etrangeres
    w("-- Cles etrangeres")
    for table in tables:
        for i, (_id, _seq, cible, col_source, col_cible, *_r) in enumerate(
                cur.execute('PRAGMA foreign_key_list("%s")' % table)):
            total_fk += 1
            nom = ("fk_%s_%s_%d" % (table, col_source, i))[:60]
            w("ALTER TABLE `%s` ADD CONSTRAINT `%s` "
              "FOREIGN KEY (`%s`) REFERENCES `%s` (`%s`);"
              % (table, nom, col_source, cible, col_cible or "id"))
    w("")
    w("SET FOREIGN_KEY_CHECKS = 1;")
    w("")

    with open(SORTIE, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out))

    cx.close()
    print("Fichier genere : %s" % SORTIE)
    print("  %d tables, %d lignes de donnees, %d cles etrangeres"
          % (len(tables), total_lignes, total_fk))
    print("  Taille : %.0f Ko" % (os.path.getsize(SORTIE) / 1024.0))


if __name__ == "__main__":
    main()
