"""Exports CSV (ouvrables directement dans Excel).

Le séparateur « ; » et le BOM UTF-8 garantissent un affichage correct des
accents et des colonnes dans Excel en environnement francophone.
"""
import csv

from django.http import HttpResponse


def csv_response(filename, headers, rows):
    """Construit une réponse HTTP CSV téléchargeable.

    - `headers` : liste des titres de colonnes.
    - `rows` : itérable de listes (une par ligne).
    """
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('﻿')  # BOM : Excel reconnaît l'UTF-8 (accents)
    writer = csv.writer(response, delimiter=';')  # ; = séparateur Excel FR
    writer.writerow(headers)
    writer.writerows(rows)
    return response
