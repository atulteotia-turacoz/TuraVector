"""Finance analytics and reports for Turacoz Financial Managers (always limited to the workspaces they handle).

Terms used throughout:
* billed      – invoices Turacoz has approved and sent to the client (pending_client, awaiting_payment, paid);
                dated by the invoice date.
* received    – paid invoices, dated by the payment date.
* outstanding – billed and not yet paid.
* draft       – generated, still with Turacoz (pending_turacoz). Cancelled invoices are left out.
Dates are India time.
"""
from __future__ import annotations

import datetime
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenancy import unfiltered
from app.core.utils import iso
from app.models import Invoice, InvoiceEvent
from app.models.billing import INVOICE_STATUSES
from app.services import billing

BILLED = ("pending_client", "awaiting_payment", "paid")
OUTSTANDING = ("pending_client", "awaiting_payment")
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)
AGEING = (("0–7 days", 0, 7), ("8–30 days", 8, 30), ("31–60 days", 31, 60), ("Over 60 days", 61, None))


def local_date(dt: datetime.datetime | None) -> datetime.date | None:
    return (dt + IST_OFFSET).date() if dt else None


def _f(v) -> float:
    return float(v or 0)


def _round(v: float) -> float:
    return round(v + 0.0, 2)


def invoices_in_scope(db: Session, scope: set[int] | None, organisation: int | None = None) -> list[Invoice]:
    with unfiltered(db):
        stmt = select(Invoice)
        if scope is not None:
            stmt = stmt.where(Invoice.organisation_id.in_(scope or {-1}))
        if organisation:
            stmt = stmt.where(Invoice.organisation_id == organisation)
        return list(db.execute(stmt.order_by(Invoice.created_at)).scalars())


def _month_key(d: datetime.date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _months(n: int, today: datetime.date) -> list[str]:
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def _days_between(events: list[InvoiceEvent], start_actions: set[str], end_action: str) -> list[float]:
    """Days from the first `start` event to each following `end` event (per invoice)."""
    out, start = [], None
    for e in events:
        if e.action in start_actions and start is None:
            start = e.created_at
        elif e.action == end_action and start is not None:
            out.append((e.created_at - start).total_seconds() / 86400)
            start = None
    return out


def analytics(db: Session, scope: set[int] | None, months: int = 12) -> dict:
    today = datetime.datetime.now(billing.IST).date()
    invs = invoices_in_scope(db, scope)
    keys = _months(months, today)
    trend = {k: {"month": k, "billed": 0.0, "received": 0.0, "invoices": 0} for k in keys}
    by_org: dict[int, dict] = {}
    by_service: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "quantity": 0.0, "lines": 0})
    ageing = [{"label": label, "amount": 0.0, "count": 0} for label, _, _ in AGEING]
    status = {k: {"count": 0, "amount": 0.0} for k in INVOICE_STATUSES}
    tax = {"cgst": 0.0, "sgst": 0.0, "igst": 0.0, "taxable": 0.0}
    approve_days, client_days, pay_days = [], [], []
    billed_total = received_total = 0.0
    for inv in invs:
        total = _f(inv.total)
        status[inv.status]["count"] += 1
        status[inv.status]["amount"] += total
        if inv.status not in BILLED:
            continue
        billed_total += total
        k = _month_key(local_date(inv.created_at))
        if k in trend:
            trend[k]["billed"] += total
            trend[k]["invoices"] += 1
        o = by_org.setdefault(inv.organisation_id, {"id": inv.organisation_id, "name": inv.organisation.name if inv.organisation else "",
                                                    "billed": 0.0, "received": 0.0, "outstanding": 0.0, "invoices": 0})
        o["billed"] += total
        o["invoices"] += 1
        for line in inv.lines:
            name = line.description.split(" · ")[0]
            by_service[name]["amount"] += _f(line.amount)
            by_service[name]["quantity"] += _f(line.quantity)
            by_service[name]["lines"] += 1
        tax["cgst"] += _f(inv.cgst)
        tax["sgst"] += _f(inv.sgst)
        tax["igst"] += _f(inv.igst)
        tax["taxable"] += _f(inv.subtotal)
        if inv.status == "paid":
            received_total += total
            o["received"] += total
            pk = _month_key(local_date(inv.paid_at)) if inv.paid_at else None
            if pk in trend:
                trend[pk]["received"] += total
        else:
            o["outstanding"] += total
            age = (today - local_date(inv.turacoz_approved_at or inv.created_at)).days
            for bucket, (_, lo, hi) in zip(ageing, AGEING):
                if age >= lo and (hi is None or age <= hi):
                    bucket["amount"] += total
                    bucket["count"] += 1
                    break
        ev = list(inv.events)
        approve_days += _days_between(ev, {"created", "client_query"}, "turacoz_approved")
        client_days += _days_between(ev, {"turacoz_approved"}, "client_approved")
        pay_days += _days_between(ev, {"client_approved"}, "paid")

    def avg(xs):
        return round(sum(xs) / len(xs), 1) if xs else None

    orgs = sorted(by_org.values(), key=lambda r: -r["billed"])
    services = sorted(({"name": k, **v} for k, v in by_service.items()), key=lambda r: -r["amount"])
    return {
        "trend": [{**v, "billed": _round(v["billed"]), "received": _round(v["received"])} for v in trend.values()],
        "by_organisation": [{**r, **{k: _round(r[k]) for k in ("billed", "received", "outstanding")}} for r in orgs[:10]],
        "by_service": [{**r, "amount": _round(r["amount"])} for r in services[:10]],
        "ageing": [{**b, "amount": _round(b["amount"])} for b in ageing],
        "status": {k: {"label": INVOICE_STATUSES[k], "count": v["count"], "amount": _round(v["amount"])} for k, v in status.items()},
        "tax": {k: _round(v) for k, v in tax.items()},
        "cycle_days": {"turacoz_approval": avg(approve_days), "client_approval": avg(client_days), "payment": avg(pay_days)},
        "totals": {"billed": _round(billed_total), "received": _round(received_total),
                   "collection_rate": round(received_total / billed_total * 100) if billed_total else None},
    }


# ---------------------------------------------------------------------------------------------- reports
def _period_filter(invs: list[Invoice], start: datetime.date, end: datetime.date) -> list[Invoice]:
    return [i for i in invs if start <= local_date(i.created_at) <= end]


def report(db: Session, scope: set[int] | None, start: datetime.date, end: datetime.date,
           organisation: int | None = None, status: str = "", client: bool = False) -> dict:
    """Every finance report for invoices dated in [start, end] (payments: paid in that period).
    `client`: the university's own view — invoices still with Turacoz are left out, and spending is
    broken down by member instead of by client."""
    everything = invoices_in_scope(db, scope, organisation)
    if client:
        everything = [i for i in everything if i.status != "pending_turacoz"]
    invs = [i for i in _period_filter(everything, start, end) if not status or i.status == status]
    today = datetime.datetime.now(billing.IST).date()

    register = [{
        "id": i.id, "number": i.number, "date": iso(local_date(i.created_at)), "organisation": i.organisation.name,
        "gstin": (i.buyer or {}).get("gstin", ""), "place": ", ".join(x for x in ((i.buyer or {}).get("state"), (i.buyer or {}).get("country")) if x),
        "cycle": i.cycle, "status": i.status, "status_label": INVOICE_STATUSES[i.status], "tax_mode": i.tax_mode,
        "subtotal": _f(i.subtotal), "cgst": _f(i.cgst), "sgst": _f(i.sgst), "igst": _f(i.igst), "total": _f(i.total),
        "paid_on": iso(local_date(i.paid_at)), "payment_ref": i.payment_id,
    } for i in invs]

    # GST: billed invoices only (cancelled and drafts are not tax invoices yet), by tax type and rate
    gst: dict[tuple, dict] = {}
    for i in invs:
        if i.status not in BILLED:
            continue
        b2b = bool((i.buyer or {}).get("gstin"))
        for line in i.lines:
            # an overseas line without tax is a zero-rated export, whatever the service's usual rate
            rate = 0.0 if i.tax_mode == "overseas" and not line.tax_overseas else float(line.tax_percent)
            key = (i.tax_mode, rate, "B2B" if b2b else ("Export" if i.tax_mode == "overseas" else "B2C"))
            g = gst.setdefault(key, {"tax_mode": key[0], "rate": key[1], "category": key[2], "invoices": set(), "taxable": 0.0,
                                     "cgst": 0.0, "sgst": 0.0, "igst": 0.0})
            g["invoices"].add(i.id)
            g["taxable"] += _f(line.amount)
            g["cgst"] += _f(line.cgst)
            g["sgst"] += _f(line.sgst)
            g["igst"] += _f(line.igst)
    gst_rows = [{**{k: v for k, v in g.items() if k != "invoices"}, "invoices": len(g["invoices"]),
                 "total_tax": _round(g["cgst"] + g["sgst"] + g["igst"]),
                 **{k: _round(g[k]) for k in ("taxable", "cgst", "sgst", "igst")}} for g in gst.values()]
    gst_rows.sort(key=lambda r: (r["category"], r["tax_mode"], r["rate"]))

    by_org: dict[str, dict] = {}
    by_service: dict[str, dict] = {}
    for i in invs:
        if i.status not in BILLED:
            continue
        o = by_org.setdefault(i.organisation.name, {"organisation": i.organisation.name, "invoices": 0, "subtotal": 0.0, "tax": 0.0,
                                                    "total": 0.0, "paid": 0.0, "outstanding": 0.0})
        o["invoices"] += 1
        o["subtotal"] += _f(i.subtotal)
        o["tax"] += _f(i.cgst) + _f(i.sgst) + _f(i.igst)
        o["total"] += _f(i.total)
        o["paid" if i.status == "paid" else "outstanding"] += _f(i.total)
        for line in i.lines:
            name = line.description.split(" · ")[0]
            s = by_service.setdefault(name, {"service": name, "sac_code": line.sac_code, "lines": 0, "quantity": 0.0, "amount": 0.0})
            s["lines"] += 1
            s["quantity"] += _f(line.quantity)
            s["amount"] += _f(line.amount)

    # Outstanding is as of today, for every billed invoice up to the period end (not just those dated inside it)
    outstanding = []
    for i in everything:
        if i.status not in OUTSTANDING or local_date(i.created_at) > end:
            continue
        sent = local_date(i.turacoz_approved_at or i.created_at)
        age = (today - sent).days
        outstanding.append({"id": i.id, "number": i.number, "organisation": i.organisation.name, "date": iso(local_date(i.created_at)),
                            "status_label": INVOICE_STATUSES[i.status], "total": _f(i.total), "days": age,
                            "bucket": next(lbl for lbl, lo, hi in AGEING if age >= lo and (hi is None or age <= hi)),
                            "reminders_sent": i.reminders_sent})
    outstanding.sort(key=lambda r: -r["days"])

    by_member: dict[str, dict] = {}
    if client:
        for i in invs:
            if i.status not in BILLED:
                continue
            owners = {it.id: r.user for r in i.requests for it in r.items}
            for line in i.lines:
                u = owners.get(line.request_item_id)
                name = billing.name_of(u) if u else "—"
                m = by_member.setdefault(name, {"member": name, "email": u.email if u else "", "requests": set(), "services": 0, "amount": 0.0, "tax": 0.0})
                m["requests"].add(i.id)
                m["services"] += 1
                m["amount"] += _f(line.amount)
                m["tax"] += _f(line.cgst) + _f(line.sgst) + _f(line.igst)

    payments = [{"number": i.number, "organisation": i.organisation.name, "paid_on": iso(local_date(i.paid_at)), "amount": _f(i.total),
                 "reference": i.payment_id, "gateway": i.gateway or "Recorded manually"}
                for i in everything if i.status == "paid" and i.paid_at and start <= local_date(i.paid_at) <= end]
    payments.sort(key=lambda r: r["paid_on"] or "")

    billed = [r for r in register if r["status"] in BILLED]
    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "summary": {
            "invoices": len(billed), "subtotal": _round(sum(r["subtotal"] for r in billed)),
            "tax": _round(sum(r["cgst"] + r["sgst"] + r["igst"] for r in billed)), "total": _round(sum(r["total"] for r in billed)),
            "received": _round(sum(p["amount"] for p in payments)),
            "outstanding": _round(sum(r["total"] for r in outstanding)),
            "drafts": sum(1 for r in register if r["status"] == "pending_turacoz"),
            "cancelled": sum(1 for r in register if r["status"] == "rejected"),
        },
        "register": register, "gst": gst_rows,
        **({"by_member": sorted(({**{k: v for k, v in m.items() if k != "requests"}, "invoices": len(m["requests"]),
                                  "amount": _round(m["amount"]), "tax": _round(m["tax"]), "total": _round(m["amount"] + m["tax"])}
                                 for m in by_member.values()), key=lambda r: -r["total"])} if client else {}),
        "by_organisation": sorted(({**o, **{k: _round(o[k]) for k in ("subtotal", "tax", "total", "paid", "outstanding")}}
                                   for o in by_org.values()), key=lambda r: -r["total"]),
        "by_service": sorted(({**s, "amount": _round(s["amount"]), "quantity": _round(s["quantity"])} for s in by_service.values()),
                             key=lambda r: -r["amount"]),
        "outstanding": outstanding, "payments": payments,
    }


# ---------------------------------------------------------------------------------------------- exports
SHEETS = {
    "register": ("Invoice register", ["Invoice", "Date", "Client", "GSTIN", "Place", "Status", "Taxable", "CGST", "SGST", "IGST", "Total", "Paid on", "Payment ref"],
                 lambda r: [r["number"], r["date"], r["organisation"], r["gstin"], r["place"], r["status_label"], r["subtotal"], r["cgst"],
                            r["sgst"], r["igst"], r["total"], r["paid_on"] or "", r["payment_ref"]]),
    "gst": ("GST summary", ["Category", "Supply", "Rate %", "Invoices", "Taxable value", "CGST", "SGST", "IGST", "Total tax"],
            lambda r: [r["category"], {"intra": "Intra-state", "inter": "Inter-state", "overseas": "Overseas"}[r["tax_mode"]], r["rate"],
                       r["invoices"], r["taxable"], r["cgst"], r["sgst"], r["igst"], r["total_tax"]]),
    "by_organisation": ("By client", ["Client", "Invoices", "Taxable", "Tax", "Total", "Paid", "Outstanding"],
                        lambda r: [r["organisation"], r["invoices"], r["subtotal"], r["tax"], r["total"], r["paid"], r["outstanding"]]),
    "by_member": ("By member", ["Member", "Email", "Invoices", "Services", "Taxable", "GST", "Total"],
                  lambda r: [r["member"], r["email"], r["invoices"], r["services"], r["amount"], r["tax"], r["total"]]),
    "by_service": ("By service", ["Service", "SAC", "Lines", "Quantity", "Amount"],
                   lambda r: [r["service"], r["sac_code"], r["lines"], r["quantity"], r["amount"]]),
    "outstanding": ("Outstanding", ["Invoice", "Client", "Date", "Status", "Amount", "Days", "Ageing", "Reminders"],
                    lambda r: [r["number"], r["organisation"], r["date"], r["status_label"], r["total"], r["days"], r["bucket"], r["reminders_sent"]]),
    "payments": ("Payments", ["Invoice", "Client", "Paid on", "Amount", "Reference", "Through"],
                 lambda r: [r["number"], r["organisation"], r["paid_on"], r["amount"], r["reference"], r["gateway"]]),
}


def tables(data: dict, only: str = "") -> dict[str, list[list]]:
    out = {}
    for key, (title, header, row) in SHEETS.items():
        if (only and key != only) or key not in data:
            continue
        out[title] = [header] + [row(r) for r in data[key]]
    return out


def as_pdf(data: dict, title: str) -> bytes:
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title=title)
    ss = getSampleStyleSheet()
    s = data["summary"]
    story = [Paragraph(title, ss["Title"]),
             Paragraph(f"Period {data['period']['from']} to {data['period']['to']} · {s['invoices']} invoices billed · "
                       f"total INR {s['total']:,.2f} · received INR {s['received']:,.2f} · outstanding INR {s['outstanding']:,.2f}",
                       ss["Normal"]), Spacer(1, 6 * mm)]
    for i, (name, rows) in enumerate(tables(data).items()):
        story.append(Paragraph(name, ss["Heading2"]))
        if len(rows) == 1:
            story.append(Paragraph("Nothing in this period.", ss["Normal"]))
        else:
            fmt = [[f"{c:,.2f}" if isinstance(c, float) else ("" if c is None else str(c)) for c in r] for r in rows]
            t = Table(fmt, repeatRows=1)
            t.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5), ("FONT", (0, 1), (-1, -1), "Helvetica", 7.5),
                                   ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                                   ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d9d4cc"))]))
            story.append(t)
        story.append(Spacer(1, 5 * mm))
        if i == 0 and len(rows) > 25:
            story.append(PageBreak())
    doc.build(story)
    return buf.getvalue()


def resolve_range(date_from: str, date_to: str) -> tuple[datetime.date, datetime.date]:
    today = datetime.datetime.now(billing.IST).date()
    try:
        start = datetime.date.fromisoformat(date_from) if date_from else today.replace(day=1)
        end = datetime.date.fromisoformat(date_to) if date_to else today
    except ValueError:
        raise billing.BillingError("Choose a valid From and To date.") from None
    if end < start:
        raise billing.BillingError("The To date must be on or after the From date.")
    return start, end

