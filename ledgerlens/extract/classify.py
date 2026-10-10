"""Guess what kind of financial document we are looking at."""

from __future__ import annotations

import re

DOC_TYPES = {
    "invoice": "Invoice",
    "receipt": "Receipt",
    "bank_statement": "Bank statement",
    "ledger": "Transaction ledger",
    "unknown": "Unknown",
}

_SIGNALS = {
    "invoice": [
        (r"\binvoice\b", 3), (r"\bbill\s*to\b", 2), (r"\binvoice\s*(?:no|number|#)", 3),
        (r"\bdue\s*date\b", 2), (r"\bamount\s*due\b", 2), (r"\bpayment\s*terms\b", 1),
        (r"\bnet\s*\d{2}\b", 1), (r"\bremit\b", 1), (r"\bpurchase\s*order\b|\bP\.?O\.?\s*#", 1),
    ],
    "receipt": [
        (r"\breceipt\b", 3), (r"\bthank\s*you\b", 1), (r"\bchange\b", 1),
        (r"\bcash\b", 1), (r"\bvisa|mastercard|amex|debit\s*card\b", 1),
        (r"\bcashier\b|\bregister\b|\bstore\s*#", 2), (r"\bpaid\b", 1),
    ],
    "bank_statement": [
        (r"\bstatement\b", 2), (r"\b(?:opening|beginning|previous)\s*balance\b", 3),
        (r"\b(?:closing|ending|new)\s*balance\b", 3), (r"\baccount\s*(?:no|number|#)", 2),
        (r"\bwithdrawals?\b", 1), (r"\bdeposits?\b", 1), (r"\bsort\s*code|routing\b", 2),
    ],
}


def classify(text: str, has_transaction_table: bool = False, is_tabular: bool = False) -> tuple[str, float]:
    """Return (doc_type, confidence 0..1)."""
    if is_tabular:
        return ("ledger", 0.9) if has_transaction_table else ("unknown", 0.2)

    lowered = text.lower()
    scores = {
        kind: sum(w for pattern, w in signals if re.search(pattern, lowered))
        for kind, signals in _SIGNALS.items()
    }
    if has_transaction_table:
        scores["bank_statement"] += 2
    best = max(scores, key=scores.get)
    total = sum(scores.values())
    if scores[best] < 2:
        return "unknown", 0.0
    return best, round(scores[best] / total, 2) if total else 0.0
