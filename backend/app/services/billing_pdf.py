"""Tax invoice PDF (reportlab), from an invoice payload (`billing.invoice_detail`)."""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#1f1f1f")
MUTED = colors.HexColor("#6b6b6b")
RULE = colors.HexColor("#d9d4cc")
ACCENT = colors.HexColor("#9b2c2c")


def _amt(v) -> str:
    return f"{float(v or 0):,.2f}"


def _esc(s) -> str:
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def invoice_pdf(d: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=f"Invoice {d['number']}")
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9, leading=12, textColor=INK)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10, textColor=MUTED)
    right = ParagraphStyle("r", parent=body, alignment=TA_RIGHT)
    h1 = ParagraphStyle("h1", parent=body, fontSize=16, leading=20, textColor=ACCENT, fontName="Helvetica-Bold")
    bold = ParagraphStyle("bd", parent=body, fontName="Helvetica-Bold")
    s, b = d["seller"], d["buyer"]
    story = []

    def party(title: str, p: dict, name_key: str) -> list:
        lines = [f"<b>{_esc(p.get(name_key))}</b>"]
        if p.get("address"):
            lines.append(_esc(p["address"]))
        place = ", ".join(x for x in (p.get("state"), p.get("country")) if x)
        if place:
            lines.append(_esc(place) + (f" (State code {_esc(p['state_code'])})" if p.get("state_code") else ""))
        if p.get("gstin"):
            lines.append(f"GSTIN: {_esc(p['gstin'])}")
        if p.get("pan"):
            lines.append(f"PAN: {_esc(p['pan'])}")
        return [Paragraph(title.upper(), small), Paragraph("<br/>".join(lines), body)]

    head = Table([[Paragraph("TAX INVOICE", h1),
                   Paragraph(f"<b>Invoice no.</b> {_esc(d['number'])}<br/><b>Date</b> {_esc((d['created_at'] or '')[:10])}"
                             + (f"<br/><b>Period</b> {_esc(d['period_start'])} to {_esc(d['period_end'])}" if d.get('period_start') else "")
                             + f"<br/><b>Status</b> {_esc(d['status_label'])}", right)]],
                 colWidths=[95 * mm, 83 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [head, Spacer(1, 6 * mm)]
    parties = Table([[party("From", s, "company_name"), party("Bill to", b, "name")]], colWidths=[89 * mm, 89 * mm])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                                 ("INNERGRID", (0, 0), (-1, -1), 0.5, RULE), ("PADDING", (0, 0), (-1, -1), 6)]))
    story += [parties, Spacer(1, 3 * mm), Paragraph(f"Tax: {_esc(d['tax_mode_label'])}", small), Spacer(1, 3 * mm)]

    intra = d["tax_mode"] == "intra"
    header = ["#", "Description", "SAC", "Qty", "Rate", "Amount", "Tax %"] + (["CGST", "SGST"] if intra else ["IGST"])
    rows = [header]
    for i, line in enumerate(d["lines"], start=1):
        unit = line["unit_label"].replace("Per ", "") if line["unit_label"] and line["unit_label"] != "Fixed" else ""
        qty = f"{line['quantity']:g}" + (f" {unit}{'' if line['quantity'] == 1 else 's'}" if unit else "")
        rows.append([str(i), Paragraph(_esc(line["description"]), body), line["sac_code"], qty, _amt(line["rate"]),
                     _amt(line["amount"]), f"{line['tax_percent']:g}%"]
                    + ([_amt(line["cgst"]), _amt(line["sgst"])] if intra else [_amt(line["igst"])]))
    widths = ([8, 52, 15, 16, 18, 20, 12, 18, 19] if intra else [8, 62, 16, 18, 20, 22, 12, 20])
    widths = [w * mm for w in widths]  # 178 mm either way
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
    ]))
    story += [t, Spacer(1, 4 * mm)]

    totals = [["Subtotal", _amt(d["subtotal"])]]
    if intra:
        totals += [["CGST", _amt(d["cgst"])], ["SGST", _amt(d["sgst"])]]
    else:
        totals += [["IGST", _amt(d["igst"])]]
    totals += [["Total (INR)", _amt(d["total"])]]
    tt = Table(totals, colWidths=[40 * mm, 35 * mm], hAlign="RIGHT")
    tt.setStyle(TableStyle([("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                            ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 10), ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK)]))
    story += [tt, Spacer(1, 2 * mm), Paragraph(f"<b>Amount in words:</b> {_esc(d['amount_in_words'])}", body)]
    if d.get("payment_id"):
        story += [Spacer(1, 2 * mm), Paragraph(f"Paid on {_esc((d.get('paid_at') or '')[:10])} · reference {_esc(d['payment_id'])}", bold)]
    if s.get("bank_details"):
        story += [Spacer(1, 5 * mm), Paragraph("BANK DETAILS", small), Paragraph(_esc(s["bank_details"]), body)]
    if s.get("terms"):
        story += [Spacer(1, 4 * mm), Paragraph("TERMS", small), Paragraph(_esc(s["terms"]), body)]
    story += [Spacer(1, 8 * mm), Paragraph("This is a computer-generated invoice.", small)]
    doc.build(story)
    return buf.getvalue()
