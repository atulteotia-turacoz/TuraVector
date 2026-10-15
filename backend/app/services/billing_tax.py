"""GST on Turacoz invoices.

* Client in India, same state as Turacoz  → intra-state: CGST + SGST, half the rate each.
* Client in India, another state          → inter-state: IGST at the full rate.
* Client outside India                    → overseas: IGST at the rate only for services marked
  "tax applies to overseas clients", otherwise no tax.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
INDIA = {"india", "in", "bharat"}


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _norm(v: str | None) -> str:
    return " ".join((v or "").lower().replace("&", "and").split())


def in_india(country: str | None) -> bool:
    return _norm(country) in INDIA


def tax_mode(seller_state: str, seller_state_code: str, buyer_state: str, buyer_state_code: str,
             buyer_country: str) -> str:
    if not in_india(buyer_country):
        return "overseas"
    if seller_state_code and buyer_state_code:
        same = seller_state_code.strip().lstrip("0") == buyer_state_code.strip().lstrip("0")
    else:
        same = _norm(seller_state) == _norm(buyer_state)
    return "intra" if same else "inter"


def line_tax(amount, tax_percent, tax_overseas: bool, mode: str) -> tuple[Decimal, Decimal, Decimal]:
    """(cgst, sgst, igst) for one line."""
    amount, rate = money(amount), Decimal(str(tax_percent or 0))
    if mode == "intra":
        half = money(amount * rate / 200)
        return half, half, Decimal("0.00")
    if mode == "overseas" and not tax_overseas:
        return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")
    return Decimal("0.00"), Decimal("0.00"), money(amount * rate / 100)


MODE_LABELS = {"intra": "Intra-state (CGST + SGST)", "inter": "Inter-state (IGST)", "overseas": "Overseas client"}

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_thousand(n: int) -> str:
    words = []
    if n >= 100:
        words += [_ONES[n // 100], "Hundred"]
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10])
        n %= 10
    if n:
        words.append(_ONES[n])
    return " ".join(words)


def _indian(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for size, name in ((10**7, "Crore"), (10**5, "Lakh"), (1000, "Thousand")):
        if n >= size:
            parts.append(f"{_indian(n // size) if n // size >= 100 and size == 10**7 else _below_thousand(n // size)} {name}")
            n %= size
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def amount_in_words(value) -> str:
    """e.g. 11800.50 → 'Rupees Eleven Thousand Eight Hundred and Fifty Paise Only'."""
    v = money(value)
    rupees, paise = int(v), int((v - int(v)) * 100)
    text = f"Rupees {_indian(rupees)}"
    if paise:
        text += f" and {_below_thousand(paise)} Paise"
    return text + " Only"
