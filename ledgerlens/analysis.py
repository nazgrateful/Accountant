"""Categorisation, summaries and anomaly detection over extracted data."""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date

DEFAULT_RULES: list[tuple[str, str]] = [
    # (keyword or regex, category) — first match wins, checked in priority order.
    (r"payroll|salary|wages", "Payroll"),
    (r"\brent\b|\blease\b", "Rent & Lease"),
    (r"electric|water|gas bill|utility|utilities|power|energy", "Utilities"),
    (r"comcast|verizon|at&t|vodafone|t-mobile|internet|telecom|phone", "Telecom & Internet"),
    (r"legal|attorney|lawyer|accounting|consult", "Professional Services"),
    (r"aws|amazon web services|google cloud|azure|github|slack|\bzoom\b|adobe|microsoft|dropbox|software|saas", "Software & Subscriptions"),
    (r"uber|lyft|airline|delta|united|american airlines|hotel|marriott|hilton|airbnb|travel|taxi", "Travel"),
    (r"restaurant|cafe|coffee|starbucks|doordash|grubhub|meal|lunch|dinner", "Meals & Entertainment"),
    (r"staples|office depot|office supplies|stationery", "Office Supplies"),
    (r"insurance", "Insurance"),
    (r"\birs\b|hmrc|tax payment|vat payment|sales tax", "Taxes"),
    (r"\bfees?\b|service charge|interest charged|overdraft", "Bank Fees & Interest"),
    (r"advert|facebook ads|google ads|marketing|linkedin", "Marketing"),
    (r"fuel|shell|chevron|exxon|bp |gas station", "Vehicle & Fuel"),
    (r"refund|reversal", "Refunds"),
    (r"transfer|payment thank you|autopay", "Transfers"),
    (r"deposit|invoice payment|customer payment|stripe payout|paypal transfer|square payout|sales", "Revenue"),
    (r"interest", "Interest Income"),
]

UNCATEGORISED = "Uncategorised"


def categorise(description: str, amount: float, rules: list[tuple[str, str]]) -> str:
    text = (description or "").lower()
    for pattern, category in rules:
        try:
            if re.search(pattern, text, re.IGNORECASE):
                return category
        except re.error:
            if pattern.lower() in text:
                return category
    return "Other Income" if amount > 0 else UNCATEGORISED


def summarise(transactions: list[dict]) -> dict:
    inflow = sum(t["amount"] for t in transactions if t["amount"] > 0)
    outflow = -sum(t["amount"] for t in transactions if t["amount"] < 0)

    by_category: dict[str, float] = defaultdict(float)
    by_month: dict[str, dict[str, float]] = defaultdict(lambda: {"in": 0.0, "out": 0.0})
    by_payee: dict[str, float] = defaultdict(float)
    for t in transactions:
        by_category[t.get("category") or UNCATEGORISED] += t["amount"]
        month = t["date"][:7]
        key = "in" if t["amount"] > 0 else "out"
        by_month[month][key] += abs(t["amount"])
        if t["amount"] < 0:
            by_payee[normalise_payee(t["description"])] += -t["amount"]

    expenses = sorted(
        ((c, -v) for c, v in by_category.items() if v < 0), key=lambda x: x[1], reverse=True
    )
    income = sorted(((c, v) for c, v in by_category.items() if v > 0), key=lambda x: x[1], reverse=True)
    months = [
        {"month": m, "in": round(v["in"], 2), "out": round(v["out"], 2), "net": round(v["in"] - v["out"], 2)}
        for m, v in sorted(by_month.items())
    ]
    dates = sorted(t["date"] for t in transactions)
    return {
        "count": len(transactions),
        "inflow": round(inflow, 2),
        "outflow": round(outflow, 2),
        "net": round(inflow - outflow, 2),
        "period_start": dates[0] if dates else None,
        "period_end": dates[-1] if dates else None,
        "expenses_by_category": [(c, round(v, 2)) for c, v in expenses],
        "income_by_category": [(c, round(v, 2)) for c, v in income],
        "months": months,
        "top_payees": sorted(((p, round(v, 2)) for p, v in by_payee.items()), key=lambda x: x[1], reverse=True)[:10],
        "avg_monthly_burn": round(outflow / len(months), 2) if months else 0.0,
    }


def normalise_payee(description: str) -> str:
    s = (description or "").upper()
    s = re.sub(r"\b(POS|DEBIT|CARD|PURCHASE|ACH|DD|ONLINE|PAYMENT TO|PAYMENT|REF|TXN)\b", " ", s)
    s = re.sub(r"[#*]\S*|\d{3,}|\b\d+\b", " ", s)
    s = re.sub(r"[^A-Z& ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.title() or "(blank)"


def find_anomalies(transactions: list[dict], documents: list[dict] | None = None) -> list[dict]:
    """Flag items an accountant would want to review.

    Each anomaly: {kind, severity, message, transaction_id?, document_id?}.
    """
    findings: list[dict] = []

    # 1. Possible duplicate payments: same amount & payee within 3 days.
    seen: dict[tuple, list[dict]] = defaultdict(list)
    for t in sorted(transactions, key=lambda x: x["date"]):
        if t["amount"] >= 0:
            continue
        key = (round(t["amount"], 2), normalise_payee(t["description"]))
        for prior in seen[key]:
            gap = abs((date.fromisoformat(t["date"]) - date.fromisoformat(prior["date"])).days)
            if gap <= 3:
                findings.append({
                    "kind": "Possible duplicate payment", "severity": "high",
                    "transaction_id": t.get("id"), "document_id": t.get("document_id"),
                    "message": f"{t['description']} for {abs(t['amount']):,.2f} on {t['date']} "
                               f"matches a payment on {prior['date']}.",
                })
                break
        seen[key].append(t)

    # 2. Statistical outliers within each expense category (robust z-score via MAD).
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for t in transactions:
        if t["amount"] < 0:
            by_cat[t.get("category") or UNCATEGORISED].append(t)
    for cat, items in by_cat.items():
        if len(items) < 5:
            continue
        values = [abs(t["amount"]) for t in items]
        med = statistics.median(values)
        mad = statistics.median(abs(v - med) for v in values) or (med * 0.1) or 1
        for t in items:
            score = 0.6745 * (abs(t["amount"]) - med) / mad
            if score > 3.5:
                findings.append({
                    "kind": "Unusually large amount", "severity": "medium",
                    "transaction_id": t.get("id"), "document_id": t.get("document_id"),
                    "message": f"{t['description']} ({abs(t['amount']):,.2f}) is far above the typical "
                               f"{cat} amount of {med:,.2f}.",
                })

    # 3. Large round-number payments (common in fraud / estimates that never got trued-up).
    for t in transactions:
        a = abs(t["amount"])
        if t["amount"] < 0 and a >= 1000 and a % 500 == 0:
            findings.append({
                "kind": "Round-number payment", "severity": "low",
                "transaction_id": t.get("id"), "document_id": t.get("document_id"),
                "message": f"{t['description']} on {t['date']} is exactly {a:,.2f}.",
            })

    # 4. Weekend transactions for business expenses.
    for t in transactions:
        if t["amount"] < 0 and date.fromisoformat(t["date"]).weekday() >= 5 and abs(t["amount"]) >= 250:
            findings.append({
                "kind": "Weekend expense", "severity": "low",
                "transaction_id": t.get("id"), "document_id": t.get("document_id"),
                "message": f"{t['description']} ({abs(t['amount']):,.2f}) posted on a "
                           f"{date.fromisoformat(t['date']).strftime('%A')}.",
            })

    # 5. Uncategorised spend.
    for t in transactions:
        if t["amount"] < 0 and (t.get("category") or UNCATEGORISED) == UNCATEGORISED:
            findings.append({
                "kind": "Uncategorised expense", "severity": "low",
                "transaction_id": t.get("id"), "document_id": t.get("document_id"),
                "message": f"{t['description']} ({abs(t['amount']):,.2f}) on {t['date']} needs a category.",
            })

    # 6. Running-balance breaks within a single statement.
    by_doc: dict = defaultdict(list)
    for t in transactions:
        if t.get("balance") is not None:
            by_doc[t.get("document_id")].append(t)
    for doc_id, items in by_doc.items():
        items.sort(key=lambda x: x.get("id") or 0)
        for prev, cur in zip(items, items[1:]):
            if abs(round(prev["balance"] + cur["amount"], 2) - cur["balance"]) > 0.011:
                findings.append({
                    "kind": "Balance does not reconcile", "severity": "high",
                    "transaction_id": cur.get("id"), "document_id": doc_id,
                    "message": f"After '{cur['description']}' on {cur['date']} the balance should be "
                               f"{prev['balance'] + cur['amount']:,.2f} but the statement shows {cur['balance']:,.2f}.",
                })

    # 7. Document-level issues: failed arithmetic checks and duplicate invoice numbers.
    if documents:
        numbers: dict[tuple, list[dict]] = defaultdict(list)
        for d in documents:
            f = d.get("fields") or {}
            for c in d.get("checks") or []:
                if c["status"] == "fail":
                    findings.append({
                        "kind": f"Document check failed: {c['check']}", "severity": "medium",
                        "document_id": d["id"], "message": f"{d['filename']}: {c['detail']}",
                    })
            if f.get("document_number"):
                numbers[((f.get("vendor") or "").lower(), f["document_number"])].append(d)
            if f.get("due_date") and d["doc_type"] == "invoice":
                try:
                    if date.fromisoformat(f["due_date"]) < date.today() and d.get("status") != "paid":
                        findings.append({
                            "kind": "Invoice past due", "severity": "medium", "document_id": d["id"],
                            "message": f"{d['filename']}: {f.get('vendor') or 'Invoice'} "
                                       f"#{f.get('document_number') or '?'} was due {f['due_date']}.",
                        })
                except ValueError:
                    pass
        for (vendor, num), docs in numbers.items():
            if len(docs) > 1:
                findings.append({
                    "kind": "Duplicate invoice number", "severity": "high", "document_id": docs[-1]["id"],
                    "message": f"Invoice #{num} from {vendor or 'unknown vendor'} appears in "
                               f"{len(docs)} uploads: {', '.join(d['filename'] for d in docs)}.",
                })

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order[f["severity"]])
    return findings
