"""Génération PDF côté serveur pour ordonnances, résultats d'examens et dossiers médicaux."""
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)

CLINIQUE_NOM = "Clinique Nevroglie"
ACCENT = colors.HexColor("#0088aa")
LOGO_STATIC = "consultation/img/logo_clinique.jpg"


def _logo_flowable(taille_mm=22):
    try:
        from django.contrib.staticfiles import finders
        path = finders.find(LOGO_STATIC)
        if not path:
            return None
        from reportlab.platypus import Image
        return Image(path, width=taille_mm * mm, height=taille_mm * mm)
    except Exception:
        return None


def _entete_clinique(elements, styles, sous_titre):
    h_clinic = ParagraphStyle('clinic', parent=styles['Title'],
                              fontSize=18, textColor=ACCENT, spaceAfter=2, alignment=0)
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
    elements.append(Spacer(1, 6 * mm))
    elements.append(HRFlowable(width="100%", thickness=2, color=ACCENT))
    elements.append(Spacer(1, 5 * mm))


def _build_pdf(titre_fichier, sous_titre, build_fn):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
        title=titre_fichier,
    )
    styles = getSampleStyleSheet()
    elements = []
    _entete_clinique(elements, styles, sous_titre)
    build_fn(elements, styles)
    now = timezone.localtime(timezone.now()).strftime("%d/%m/%Y à %H:%M")
    elements.append(Spacer(1, 10 * mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d6e3e8")))
    elements.append(Spacer(1, 3 * mm))
    foot = ParagraphStyle('foot', parent=styles['Normal'],
                          fontSize=8, textColor=colors.grey, alignment=1)
    elements.append(Paragraph(
        f"{CLINIQUE_NOM} — Poly Clinique · Neurologie  |  Document généré le {now}",
        foot))
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def _lbl(styles, texte):
    s = ParagraphStyle('lbl', parent=styles['Normal'], fontSize=8,
                       textColor=colors.grey, spaceBefore=0)
    return Paragraph(f"<b>{texte}</b>", s)


def _val(styles, texte):
    s = ParagraphStyle('val', parent=styles['Normal'], fontSize=10,
                       textColor=colors.HexColor("#1a2530"))
    return Paragraph(str(texte) if texte else "—", s)


# ── Ordonnance ──────────────────────────────────────────────────────────────

def ordonnance_pdf_response(ordonnance):
    def _build(elements, styles):
        h1 = ParagraphStyle('h1', parent=styles['Title'],
                            fontSize=14, textColor=colors.HexColor("#1a2530"),
                            spaceAfter=4, alignment=0)
        elements.append(Paragraph("Ordonnance médicale", h1))
        num = ParagraphStyle('num', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
        elements.append(Paragraph(f"N° ORD-{ordonnance.pk:04d}", num))
        elements.append(Spacer(1, 6 * mm))

        rdv = ordonnance.consultation.rendez_vous
        info = [
            [_lbl(styles, "Patient"), _val(styles, rdv.patient),
             _lbl(styles, "Date"), _val(styles, ordonnance.date.strftime("%d/%m/%Y") if ordonnance.date else "—")],
            [_lbl(styles, "Médecin"), _val(styles, f"Dr. {rdv.medecin}"),
             _lbl(styles, "Spécialité"), _val(styles, getattr(rdv.medecin, 'specialite', '') or "Généraliste")],
        ]
        t = Table(info, colWidths=[28 * mm, 62 * mm, 28 * mm, 56 * mm])
        t.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#e3e8ee")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8 * mm))

        rx_lbl = ParagraphStyle('rxlbl', parent=styles['Normal'], fontSize=9,
                                textColor=colors.grey, spaceBefore=0)
        elements.append(Paragraph("Prescription :", rx_lbl))
        elements.append(Spacer(1, 2 * mm))

        rx_text = ParagraphStyle('rx', parent=styles['Normal'], fontSize=11,
                                 textColor=colors.HexColor("#1a2530"), leading=18,
                                 leftIndent=6, rightIndent=6)
        rx_data = [[Paragraph(
            (ordonnance.medicaments or "").replace("\n", "<br/>"),
            rx_text
        )]]
        rx_table = Table(rx_data, colWidths=[174 * mm])
        rx_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#b3d4de")),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0f8fb")),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ]))
        elements.append(rx_table)
        elements.append(Spacer(1, 18 * mm))

        sign = ParagraphStyle('sign', parent=styles['Normal'], fontSize=9,
                              textColor=colors.grey, alignment=2)
        elements.append(Paragraph("______________________________", sign))
        elements.append(Paragraph("Signature et cachet du médecin", sign))

    pdf = _build_pdf(f"ORD-{ordonnance.pk:04d}", "Ordonnance médicale", _build)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="ordonnance-ORD-{ordonnance.pk:04d}.pdf"'
    return response


# ── Résultat d'examen ────────────────────────────────────────────────────────

def resultat_pdf_response(resultat):
    def _build(elements, styles):
        h1 = ParagraphStyle('h1', parent=styles['Title'],
                            fontSize=14, textColor=colors.HexColor("#1a2530"),
                            spaceAfter=4, alignment=0)
        elements.append(Paragraph("Résultat d'examen", h1))
        elements.append(Spacer(1, 5 * mm))

        examen = resultat.examen
        date_str = timezone.localtime(resultat.date_examen).strftime("%d/%m/%Y à %H:%M") if resultat.date_examen else "—"
        rows = [
            [_lbl(styles, "Patient"), _val(styles, resultat.patient),
             _lbl(styles, "Date"), _val(styles, date_str)],
            [_lbl(styles, "Type d'examen"), _val(styles, examen.type_examen),
             _lbl(styles, "Médecin"), _val(styles, f"Dr. {resultat.medecin}" if resultat.medecin else "—")],
        ]
        if resultat.laborantin:
            rows.append([_lbl(styles, "Laborantin"), _val(styles, str(resultat.laborantin)),
                         Paragraph("", styles['Normal']), Paragraph("", styles['Normal'])])

        t = Table(rows, colWidths=[32 * mm, 58 * mm, 28 * mm, 56 * mm])
        t.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#e3e8ee")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 8 * mm))

        section = ParagraphStyle('sec', parent=styles['Normal'], fontSize=10,
                                 textColor=ACCENT, fontName='Helvetica-Bold', spaceBefore=6)
        body_style = ParagraphStyle('body', parent=styles['Normal'], fontSize=10,
                                    textColor=colors.HexColor("#1a2530"), leading=16)

        elements.append(Paragraph("Résultats :", section))
        elements.append(Spacer(1, 2 * mm))
        res_data = [[Paragraph((resultat.resultat or "").replace("\n", "<br/>"), body_style)]]
        res_table = Table(res_data, colWidths=[174 * mm])
        res_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#b3d4de")),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0f8fb")),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(res_table)

        if resultat.observations:
            elements.append(Spacer(1, 6 * mm))
            elements.append(Paragraph("Observations :", section))
            elements.append(Spacer(1, 2 * mm))
            elements.append(Paragraph(resultat.observations.replace("\n", "<br/>"), body_style))

        if resultat.transmis and resultat.date_transmission:
            elements.append(Spacer(1, 6 * mm))
            dt = timezone.localtime(resultat.date_transmission).strftime("%d/%m/%Y à %H:%M")
            transmitted = ParagraphStyle('tr', parent=styles['Normal'], fontSize=8,
                                         textColor=colors.HexColor("#059669"))
            elements.append(Paragraph(f"Résultat transmis au médecin le {dt}.", transmitted))

    pdf = _build_pdf(f"resultat-{resultat.pk}", "Résultat d'examen", _build)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="resultat-{resultat.pk}.pdf"'
    return response


# ── Dossier médical ──────────────────────────────────────────────────────────

def dossier_pdf_response(dossier):
    def _build(elements, styles):
        h1 = ParagraphStyle('h1', parent=styles['Title'],
                            fontSize=14, textColor=colors.HexColor("#1a2530"),
                            spaceAfter=2, alignment=0)
        section = ParagraphStyle('sec', parent=styles['Normal'], fontSize=10,
                                 textColor=ACCENT, fontName='Helvetica-Bold',
                                 spaceBefore=10, spaceAfter=4)
        body_style = ParagraphStyle('body', parent=styles['Normal'], fontSize=9,
                                    textColor=colors.HexColor("#1a2530"), leading=14)
        lbl_s = ParagraphStyle('lbl2', parent=styles['Normal'], fontSize=8,
                               textColor=colors.grey)

        patient = dossier.patient
        elements.append(Paragraph(f"Dossier médical — {patient}", h1))
        elements.append(Paragraph(f"Dossier #{dossier.pk} · ouvert le {dossier.date_creation.strftime('%d/%m/%Y')}", lbl_s))
        elements.append(Spacer(1, 5 * mm))

        # Infos patient
        infos = []
        if patient.date_naissance:
            infos.append([_lbl(styles, "Date de naissance"), _val(styles, patient.date_naissance.strftime("%d/%m/%Y"))])
        if patient.sexe:
            infos.append([_lbl(styles, "Sexe"), _val(styles, patient.get_sexe_display() if hasattr(patient, 'get_sexe_display') else patient.sexe)])
        if patient.telephone:
            infos.append([_lbl(styles, "Téléphone"), _val(styles, patient.telephone)])
        if patient.adresse:
            infos.append([_lbl(styles, "Adresse"), _val(styles, patient.adresse)])
        if getattr(patient, 'groupe_sanguin', None):
            infos.append([_lbl(styles, "Groupe sanguin"), _val(styles, patient.groupe_sanguin)])

        if infos:
            t = Table(infos, colWidths=[40 * mm, 134 * mm])
            t.setStyle(TableStyle([
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#e3e8ee")),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(t)

        # Consultations
        consultations = dossier.consultations.select_related(
            'rendez_vous__medecin', 'rendez_vous__patient'
        ).order_by('-date')
        if consultations.exists():
            elements.append(Paragraph(f"Consultations ({consultations.count()})", section))
            for c in consultations:
                date_str = timezone.localtime(c.date).strftime("%d/%m/%Y") if c.date else "—"
                header = [[
                    Paragraph(f"<b>{date_str}</b> — Dr. {c.rendez_vous.medecin}", body_style),
                ]]
                ht = Table(header, colWidths=[174 * mm])
                ht.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0f8fb")),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ]))
                elements.append(ht)
                rows = []
                if c.motif:
                    rows.append([_lbl(styles, "Motif"), Paragraph(c.motif, body_style)])
                if c.diagnostic:
                    rows.append([_lbl(styles, "Diagnostic"), Paragraph(c.diagnostic, body_style)])
                if c.observation:
                    rows.append([_lbl(styles, "Observations"), Paragraph(c.observation, body_style)])
                if rows:
                    dt = Table(rows, colWidths=[26 * mm, 148 * mm])
                    dt.setStyle(TableStyle([
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#e3e8ee")),
                        ('TOPPADDING', (0, 0), (-1, -1), 3),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ('LEFTPADDING', (0, 0), (0, -1), 8),
                    ]))
                    elements.append(dt)
                elements.append(Spacer(1, 3 * mm))

        # Résultats d'examens
        resultats = dossier.resultats.select_related('examen', 'medecin', 'laborantin').order_by('-date_examen')
        if resultats.exists():
            elements.append(Paragraph(f"Résultats d'examens ({resultats.count()})", section))
            for r in resultats:
                date_str = timezone.localtime(r.date_examen).strftime("%d/%m/%Y") if r.date_examen else "—"
                header = [[Paragraph(
                    f"<b>{date_str}</b> — {r.examen.type_examen}"
                    + (f" · Dr. {r.medecin}" if r.medecin else ""),
                    body_style
                )]]
                ht = Table(header, colWidths=[174 * mm])
                ht.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0f8fb")),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ]))
                elements.append(ht)
                if r.resultat:
                    elements.append(Paragraph(r.resultat, body_style))
                elements.append(Spacer(1, 3 * mm))

        # Ordonnances
        ordonnances = dossier.ordonnance.select_related(
            'consultation__rendez_vous__medecin'
        ).order_by('-date')
        if ordonnances.exists():
            elements.append(Paragraph(f"Ordonnances ({ordonnances.count()})", section))
            for ord in ordonnances:
                date_str = ord.date.strftime("%d/%m/%Y") if ord.date else "—"
                medecin = ord.consultation.rendez_vous.medecin
                header = [[Paragraph(f"<b>ORD-{ord.pk:04d}</b> · {date_str} — Dr. {medecin}", body_style)]]
                ht = Table(header, colWidths=[174 * mm])
                ht.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f0f8fb")),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ]))
                elements.append(ht)
                if ord.medicaments:
                    elements.append(Paragraph(ord.medicaments.replace("\n", "<br/>"), body_style))
                elements.append(Spacer(1, 3 * mm))

    pdf = _build_pdf(f"dossier-{dossier.pk}", "Dossier médical", _build)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="dossier-{dossier.patient.nom}-{dossier.pk}.pdf"'
    return response
