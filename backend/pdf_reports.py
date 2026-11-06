import io
from datetime import datetime, timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle

NAVY = colors.HexColor("#0B111E")
BLUE = colors.HexColor("#0284C7")
GOLD = colors.HexColor("#B7791F")

FOOTER = "VaultBridge Escrow demo environment — not a real financial, regulatory or blockchain record"


def _decorate(canvas, doc):
    canvas.saveState()
    w, h = A4
    canvas.setFont("Helvetica-Bold", 110)
    canvas.setFillColor(colors.Color(0.5, 0.55, 0.65, alpha=0.07))
    canvas.translate(w / 2, h / 2)
    canvas.rotate(40)
    canvas.drawCentredString(0, 0, "DEMO")
    canvas.restoreState()
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 22 * mm, w, 22 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(18 * mm, h - 12 * mm, "VAULTBRIDGE ESCROW")
    canvas.setFont("Helvetica", 8)
    canvas.drawString(18 * mm, h - 17 * mm, "Digital asset escrow")
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(w / 2, 10 * mm, FOOTER)
    canvas.setFillColor(colors.grey)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(w - 18 * mm, 5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_report(title: str, reference: str, sections: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=32 * mm, bottomMargin=20 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm, title=title)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=NAVY, fontSize=17, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading3"], textColor=BLUE, fontSize=11, spaceBefore=10, spaceAfter=4)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, leading=11, textColor=colors.HexColor("#334155"))
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=8.5, leading=11)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story = [
        Paragraph(title, h1),
        Paragraph(f"Deal reference: <b>{reference}</b> &nbsp;|&nbsp; Generated: {stamp}", small),
    ]
    for heading, rows in sections:
        story.append(Paragraph(heading, h2))
        data = [[Paragraph(f"<b>{k}</b>", cell), Paragraph(str(v), cell)] for k, v in rows]
        t = Table(data, colWidths=[60 * mm, 114 * mm])
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
    doc.build(story, onFirstPage=_decorate, onLaterPages=_decorate)
    return buf.getvalue()
