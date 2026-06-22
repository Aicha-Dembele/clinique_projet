"""Génération de la facture au format PDF (côté serveur, via reportlab).

Produit un document propre et imprimable, indépendant du navigateur,
réutilisable pour l'archivage ou l'envoi par email.
"""
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image,
)

CLINIQUE_NOM = "Clinique Nevroglie"
ACCENT = colors.HexColor("#0088aa")
LOGO_STATIC = "consultation/img/logo_clinique.jpg"


def _logo_flowable(taille_mm=22):
    """Logo de la clinique en flowable reportlab, ou None s'il est introuvable."""
    try:
        from django.contrib.staticfiles import finders
        path = finders.find(LOGO_STATIC)
        if not path:
            return None
        return Image(path, width=taille_mm * mm, height=taille_mm * mm)
    except Exception:
        return None


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
    h_sub = ParagraphStyle('sub', parent=styles['Normal'],
                           fontSize=9, textColor=colors.grey)
    normal = styles['Normal']
    right = ParagraphStyle('right', parent=normal, alignment=2)

    elements = []

    # ── En-tête : logo + nom de la clinique ──
    _entete_clinique(elements, styles, "Facture de soins")

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


def _entete_clinique(elements, styles, sous_titre):
    """Ajoute l'en-tête (logo + nom de la clinique + sous-titre) aux éléments."""
    h_clinic = ParagraphStyle('clinic', parent=styles['Title'],
                              fontSize=20, textColor=ACCENT, spaceAfter=2,
                              alignment=0)
    h_sub = ParagraphStyle('sub', parent=styles['Normal'],
                           fontSize=9, textColor=colors.grey)
    titre_cell = [Paragraph(CLINIQUE_NOM, h_clinic), Paragraph(sous_titre, h_sub)]
    logo = _logo_flowable()
    if logo:
        entete = Table([[logo, titre_cell]], colWidths=[26 * mm, 148 * mm])
        entete.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (0, 0), 0),
            ('LEFTPADDING', (1, 0), (1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(entete)
    else:
        elements.extend(titre_cell)
    elements.append(Spacer(1, 8 * mm))


def paiement_pdf_response(paiement):
    """Construit le reçu de paiement au format PDF (avec logo) et le renvoie."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
        title=f"Reçu REC-{paiement.pk:05d}",
    )

    styles = getSampleStyleSheet()
    normal = styles['Normal']
    grey = ParagraphStyle('grey', parent=normal, fontSize=9, textColor=colors.grey)
    montant = ParagraphStyle('montant', parent=styles['Title'],
                             fontSize=24, textColor=ACCENT, alignment=0, spaceBefore=2)

    elements = []
    _entete_clinique(elements, styles, "Reçu de paiement")

    f = paiement.facture
    p = f.patient

    # ── Numéro + montant payé ──
    elements.append(Paragraph(f"N° Reçu : REC-{paiement.pk:05d}", grey))
    elements.append(Paragraph(_fcfa(paiement.montant) + " &nbsp;·&nbsp; Payé", montant))
    elements.append(Spacer(1, 6 * mm))

    # ── Détails ──
    date_str = timezone.localtime(paiement.date).strftime("%d/%m/%Y à %H:%M") if paiement.date else "—"
    rows = [
        [Paragraph("<b>Date du paiement</b>", normal), date_str],
        [Paragraph("<b>Patient</b>", normal), f"{p.nom} {p.prenom}"],
        [Paragraph("<b>Téléphone</b>", normal), p.telephone or "—"],
        [Paragraph("<b>N° de facture</b>", normal), f"FAC-{f.pk:04d}"],
        [Paragraph("<b>Montant facture</b>", normal), _fcfa(f.montant_total)],
    ]
    if f.assurance_id and f.part_assurance() > 0:
        rows.append([Paragraph(f"<b>Assurance</b> ({f.assurance.nom} — {f.taux_prise_en_charge:.0f} %)", normal),
                     "- " + _fcfa(f.part_assurance())])
        rows.append([Paragraph("<b>Reste à charge patient</b>", normal), _fcfa(f.part_patient())])
    rows.append([Paragraph("<b>Mode de paiement</b>", normal), paiement.get_mode_paiement_display()])

    service = None
    if f.consultation_id:
        service = f"Consultation Dr. {f.consultation.rendez_vous.medecin}"
    elif f.hospitalisation_id:
        service = f"Hospitalisation — Ch. {f.hospitalisation.numero_chambre}"
    if service:
        rows.append([Paragraph("<b>Service</b>", normal), service])

    t = Table(rows, colWidths=[64 * mm, 110 * mm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2eaed")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6 * mm))

    # ── Total payé ──
    t_tot = Table([["Montant payé", _fcfa(paiement.montant)]],
                  colWidths=[104 * mm, 70 * mm], hAlign='RIGHT')
    t_tot.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, -1), ACCENT),
        ('LINEABOVE', (0, 0), (-1, 0), 1, ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(t_tot)
    elements.append(Spacer(1, 14 * mm))
    elements.append(Paragraph(
        f"Ce reçu fait foi de paiement — {CLINIQUE_NOM}. Conservez-le précieusement.",
        ParagraphStyle('foot', parent=normal, fontSize=9, textColor=colors.grey, alignment=1)))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="recu-REC-{paiement.pk:05d}.pdf"'
    return response
