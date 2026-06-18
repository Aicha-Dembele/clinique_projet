"""Génération de la facture au format PDF (côté serveur, via reportlab).

Produit un document propre et imprimable, indépendant du navigateur,
réutilisable pour l'archivage ou l'envoi par email.
"""
from io import BytesIO

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
)

CLINIQUE_NOM = "Clinique Nevroglie"
ACCENT = colors.HexColor("#0088aa")


def _fcfa(val):
    """Formate un montant en FCFA avec séparateur de milliers (espace)."""
    try:
        return f"{int(val):,}".replace(",", " ") + " FCFA"
    except (TypeError, ValueError):
        return "0 FCFA"


def facture_pdf_response(facture):
    """Construit le PDF de la facture et le renvoie dans une HttpResponse."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Facture FAC-{facture.pk:04d}",
    )

    styles = getSampleStyleSheet()
    h_clinic = ParagraphStyle('clinic', parent=styles['Title'],
                              fontSize=20, textColor=ACCENT, spaceAfter=2)
    h_sub = ParagraphStyle('sub', parent=styles['Normal'],
                           fontSize=9, textColor=colors.grey)
    normal = styles['Normal']
    right = ParagraphStyle('right', parent=normal, alignment=2)

    elements = []

    # ── En-tête ──
    elements.append(Paragraph(CLINIQUE_NOM, h_clinic))
    elements.append(Paragraph("Facture de soins", h_sub))
    elements.append(Spacer(1, 8 * mm))

    # ── Infos facture / patient ──
    p = facture.patient
    statut = dict(facture.STATUT_CHOICES).get(facture.statut, facture.statut)
    info = [
        [Paragraph("<b>Facture</b>", normal), f"FAC-{facture.pk:04d}",
         Paragraph("<b>Patient</b>", normal), f"{p.nom} {p.prenom}"],
        [Paragraph("<b>Date</b>", normal),
         facture.date_creation.strftime("%d/%m/%Y") if facture.date_creation else "—",
         Paragraph("<b>Téléphone</b>", normal), p.telephone or "—"],
        [Paragraph("<b>Statut</b>", normal), statut,
         Paragraph("<b>Assurance</b>", normal),
         facture.assurance.nom if facture.assurance_id else "Aucune"],
    ]
    t_info = Table(info, colWidths=[26 * mm, 52 * mm, 30 * mm, 56 * mm])
    t_info.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(t_info)
    elements.append(Spacer(1, 6 * mm))

    # ── Lignes ──
    data = [["Désignation", "Qté", "Prix unitaire", "Sous-total"]]
    for l in facture.lignes.all():
        data.append([l.description, str(l.quantite),
                     _fcfa(l.prix_unitaire), _fcfa(l.sous_total())])

    t = Table(data, colWidths=[88 * mm, 16 * mm, 33 * mm, 33 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), ACCENT),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f7f9")]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#d6e3e8")),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6 * mm))

    # ── Totaux ──
    totaux = [["Montant total", _fcfa(facture.montant_total)]]
    if facture.assurance_id and facture.part_assurance() > 0:
        taux = facture.taux_prise_en_charge
        totaux.append([f"Part assurance ({taux:.0f} %)", "- " + _fcfa(facture.part_assurance())])
        totaux.append(["Part patient (à régler)", _fcfa(facture.part_patient())])
    totaux.append(["Montant payé", _fcfa(facture.montant_paye())])
    totaux.append(["Reste à payer", _fcfa(facture.montant_restant())])

    t_tot = Table(totaux, colWidths=[100 * mm, 70 * mm], hAlign='RIGHT')
    t_tot.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 1, ACCENT),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, -1), (-1, -1), ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_tot)
    elements.append(Spacer(1, 14 * mm))
    elements.append(Paragraph(
        f"Document généré par {CLINIQUE_NOM} — merci de votre confiance.", h_sub))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="facture-FAC-{facture.pk:04d}.pdf"'
    return response
