"""Key-field extraction for invoices and receipts."""

from __future__ import annotations

import re

from .parsing import detect_currency, find_amounts, find_dates, parse_date

_LABEL_SKIP = re.compile(
    r"\b(invoice|receipt|bill\s*to|ship\s*to|date|page|tax\s*invoice|statement|tel|phone|fax|"
    r"email|www\.|http|abn|vat\s*(?:no|reg)|po\s*box)\b",
    re.IGNORECASE,
)

_INVOICE_NO = re.compile(
    r"\b(?:invoice|inv|receipt|bill)\s*(?:no\.?|number|num|#|id)?\s*[:#.]?\s*"
    r"(?P<num>[A-Z0-9][A-Z0-9\-/]*\d[A-Z0-9\-/]*)",
    re.IGNORECASE,
)
_PO_NO = re.compile(r"\b(?:p\.?o\.?|purchase\s*order)\s*(?:no\.?|number|#)?\s*[:#]?\s*(?P<num>[A-Z0-9\-]+\d)", re.IGNORECASE)
_TAX_ID = re.compile(r"\b(?:vat|gst|abn|ein|tax\s*id|tin)\s*(?:no\.?|number|#|reg\.?)?\s*[:#]?\s*(?P<id>[A-Z]{0,2}[\d][\d \-]{5,}\d)", re.IGNORECASE)
_TERMS = re.compile(r"\b(net\s*\d{1,3}|due\s+on\s+receipt|due\s+upon\s+receipt|\d{1,3}\s*days)\b", re.IGNORECASE)
_RATE = re.compile(r"(\d{1,2}(?:\.\d{1,3})?)\s*%")

# Label patterns ordered by priority (first match wins per field).
_TOTAL_LABELS = [
    r"grand\s*total", r"total\s*amount\s*due", r"amount\s*due", r"balance\s*due",
    r"total\s*due", r"invoice\s*total", r"total\s*\(?(?:incl|inc)", r"(?<!sub)(?<!sub\s)\btotal\b",
]
_SUBTOTAL_LABELS = [r"sub\s*-?\s*total", r"net\s*amount", r"total\s*\(?(?:excl|ex)\b", r"amount\s*before\s*tax"]
_TAX_LABELS = [r"\b(?:sales\s*)?tax\b", r"\bvat\b", r"\bgst\b", r"\bhst\b", r"\bpst\b"]
_DISCOUNT_LABELS = [r"\bdiscount\b"]
_SHIPPING_LABELS = [r"\bshipping\b", r"\bfreight\b", r"\bdelivery\b"]


def _labelled_amount(lines: list[str], patterns: list[str], exclude: str | None = None) -> float | None:
    for pattern in patterns:
        rx = re.compile(pattern, re.IGNORECASE)
        # Totals usually appear at the bottom, so scan from the end.
        for line in reversed(lines):
            if not rx.search(line):
                continue
            if exclude and re.search(exclude, line, re.IGNORECASE):
                continue
            amounts = find_amounts(rx.split(line, maxsplit=1)[-1]) or find_amounts(line)
            if amounts:
                return round(amounts[-1], 2)
    return None


def _labelled_date(lines: list[str], label: str, day_first: bool) -> str | None:
    rx = re.compile(label, re.IGNORECASE)
    for i, line in enumerate(lines):
        if rx.search(line):
            tail = rx.split(line, maxsplit=1)[-1]
            dates = find_dates(tail, day_first) or (find_dates(lines[i + 1], day_first) if i + 1 < len(lines) else [])
            if dates:
                return dates[0].isoformat()
    return None


def _vendor(lines: list[str]) -> str | None:
    for line in lines[:8]:
        clean = line.strip(" :-|")
        if len(clean) < 3 or _LABEL_SKIP.search(clean):
            continue
        if find_amounts(clean) or find_dates(clean):
            continue
        if re.fullmatch(r"[\d\s\-/#.,]+", clean):
            continue
        return clean[:120]
    return None


def _customer(lines: list[str]) -> str | None:
    for i, line in enumerate(lines):
        m = re.search(r"\bbill(?:ed)?\s*to\s*:?\s*(.*)", line, re.IGNORECASE)
        if m:
            inline = m.group(1).strip()
            if inline:
                return inline[:120]
            if i + 1 < len(lines):
                return lines[i + 1].strip()[:120] or None
    return None


_ITEM_RE = re.compile(
    r"^(?P<desc>[A-Za-z][^\d$€£]*?(?:\s\S*\d\S*)*?)\s+"
    r"(?P<qty>\d+(?:\.\d+)?)\s+(?:x\s+)?"
    r"(?P<price>[$€£]?\s?[\d,]+\.\d{2})\s+"
    r"(?P<amount>[$€£]?\s?[\d,]+\.\d{2})\s*$"
)
_SUMMARY_WORDS = re.compile(r"total|tax|vat|gst|discount|shipping|balance|due|paid|change", re.IGNORECASE)


def _line_items(lines: list[str]) -> list[dict]:
    items = []
    for line in lines:
        line = line.strip()
        if _SUMMARY_WORDS.search(line):
            continue
        m = _ITEM_RE.match(line)
        if not m:
            continue
        qty = float(m.group("qty"))
        price = find_amounts(m.group("price"))[0]
        amount = find_amounts(m.group("amount"))[0]
        items.append({
            "description": m.group("desc").strip(),
            "quantity": qty,
            "unit_price": price,
            "amount": amount,
            "math_ok": abs(qty * price - amount) < 0.011,
        })
    return items


def extract_fields(text: str, day_first: bool = False) -> dict:
    lines = [ln for ln in (l.strip() for l in text.splitlines()) if ln]
    fields: dict = {}

    m = _INVOICE_NO.search(text)
    fields["document_number"] = m.group("num") if m else None
    m = _PO_NO.search(text)
    fields["po_number"] = m.group("num") if m else None
    m = _TAX_ID.search(text)
    fields["tax_id"] = m.group("id").strip() if m else None
    m = _TERMS.search(text)
    fields["payment_terms"] = m.group(1) if m else None

    fields["vendor"] = _vendor(lines)
    fields["customer"] = _customer(lines)
    fields["currency"] = detect_currency(text)

    fields["issue_date"] = (
        _labelled_date(lines, r"(?:invoice|issue|receipt|bill)\s*date|\bdated?\b(?!\s*due)", day_first)
    )
    fields["due_date"] = _labelled_date(lines, r"due\s*date|payment\s*due|due\s*by", day_first)
    if not fields["issue_date"]:
        dates = find_dates(text, day_first)
        fields["issue_date"] = dates[0].isoformat() if dates else None

    fields["subtotal"] = _labelled_amount(lines, _SUBTOTAL_LABELS)
    fields["tax"] = _labelled_amount(lines, _TAX_LABELS, exclude=r"total|tax\s*id|vat\s*(?:no|reg)|gst\s*(?:no|reg)|abn")
    fields["discount"] = _labelled_amount(lines, _DISCOUNT_LABELS)
    fields["shipping"] = _labelled_amount(lines, _SHIPPING_LABELS)
    fields["total"] = _labelled_amount(lines, _TOTAL_LABELS, exclude=r"sub\s*-?\s*total")

    tax_rate = None
    for line in lines:
        if re.search(r"tax|vat|gst|hst", line, re.IGNORECASE) and (r := _RATE.search(line)):
            tax_rate = float(r.group(1))
            break
    fields["tax_rate"] = tax_rate
    fields["line_items"] = _line_items(lines)
    return fields


def validate_fields(fields: dict) -> list[dict]:
    """Arithmetic and completeness checks an accountant would do by eye."""
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "status": "pass" if ok else "fail", "detail": detail})

    def warn(name, detail):
        checks.append({"check": name, "status": "warn", "detail": detail})

    sub, tax, total = fields.get("subtotal"), fields.get("tax"), fields.get("total")
    disc = abs(fields.get("discount") or 0)
    ship = fields.get("shipping") or 0
    items = fields.get("line_items") or []

    if total is None:
        warn("Total found", "No total amount could be located.")
    if sub is not None and total is not None:
        expected = round(sub + (tax or 0) + ship - disc, 2)
        add("Subtotal + tax = total", abs(expected - total) < 0.02,
            f"{sub:,.2f} + {tax or 0:,.2f} tax" + (f" + {ship:,.2f} shipping" if ship else "")
            + (f" − {disc:,.2f} discount" if disc else "") + f" = {expected:,.2f}; document says {total:,.2f}")
    if sub is not None and tax is not None and fields.get("tax_rate"):
        # Tax may be charged on the subtotal before or after discount.
        bases = [sub - disc, sub] if disc else [sub]
        base = min(bases, key=lambda b: abs(round(b * fields["tax_rate"] / 100, 2) - tax))
        expected_tax = round(base * fields["tax_rate"] / 100, 2)
        add("Tax rate applied correctly", abs(expected_tax - tax) < 0.02,
            f"{fields['tax_rate']}% of {base:,.2f} = {expected_tax:,.2f}; document says {tax:,.2f}")
    if items:
        bad = [i["description"] for i in items if not i["math_ok"]]
        add("Line items: qty × price = amount", not bad,
            "All lines reconcile." if not bad else f"Mismatch on: {', '.join(bad)}")
        target = sub if sub is not None else total
        if target is not None:
            s = round(sum(i["amount"] for i in items), 2)
            add("Line items sum to subtotal", abs(s - target) < 0.02,
                f"Items sum to {s:,.2f}; {'subtotal' if sub is not None else 'total'} is {target:,.2f}")
    if fields.get("issue_date") and fields.get("due_date"):
        d1, d2 = parse_date(fields["issue_date"]), parse_date(fields["due_date"])
        if d1 and d2:
            add("Due date after issue date", d2 >= d1, f"Issued {d1}, due {d2} ({(d2 - d1).days} days)")
    if not fields.get("document_number"):
        warn("Document number found", "No invoice/receipt number detected.")
    if not fields.get("vendor"):
        warn("Vendor found", "Could not identify the issuing vendor.")
    return checks
