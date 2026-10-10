"""Pull individual transactions out of statement tables or statement text."""

from __future__ import annotations

import re

import pandas as pd

from .parsing import DATE_RE, find_amounts, parse_amount, parse_date

_COLS = {
    "date": ["transaction date", "posting date", "post date", "value date", "date", "posted"],
    "description": ["description", "details", "narrative", "memo", "payee", "merchant",
                    "particulars", "transaction", "reference", "name"],
    "amount": ["amount", "value", "net amount", "transaction amount"],
    "debit": ["debit", "withdrawal", "withdrawals", "money out", "paid out", "dr", "outflow", "spent"],
    "credit": ["credit", "deposit", "deposits", "money in", "paid in", "cr", "inflow", "received"],
    "balance": ["balance", "running balance", "closing balance"],
    "category": ["category", "type", "account"],
}


def _match_columns(columns) -> dict[str, str]:
    norm = {c: re.sub(r"[^a-z ]", " ", str(c).lower()).strip() for c in columns}
    norm = {c: re.sub(r"\s+", " ", n) for c, n in norm.items()}
    found: dict[str, str] = {}
    used = set()
    for role in ("date", "debit", "credit", "balance", "amount", "description", "category"):
        for alias in _COLS[role]:
            hit = next((c for c, n in norm.items() if c not in used and n == alias), None)
            hit = hit or next(
                (c for c, n in norm.items() if c not in used and re.search(rf"\b{re.escape(alias)}\b", n)),
                None,
            )
            if hit is not None:
                found[role] = hit
                used.add(hit)
                break
    return found


def is_transaction_table(df: pd.DataFrame) -> bool:
    cols = _match_columns(df.columns)
    return "date" in cols and ("amount" in cols or "debit" in cols or "credit" in cols)


def transactions_from_table(df: pd.DataFrame, day_first: bool = False) -> list[dict]:
    cols = _match_columns(df.columns)
    if not ("date" in cols and ({"amount", "debit", "credit"} & cols.keys())):
        return []
    out = []
    for _, row in df.iterrows():
        d = parse_date(row.get(cols["date"]), day_first)
        if not d:
            continue
        if "amount" in cols:
            amount = parse_amount(row.get(cols["amount"]))
        else:
            debit = parse_amount(row.get(cols["debit"])) if "debit" in cols else None
            credit = parse_amount(row.get(cols["credit"])) if "credit" in cols else None
            if debit is None and credit is None:
                amount = None
            else:
                amount = (abs(credit) if credit else 0.0) - (abs(debit) if debit else 0.0)
        if amount is None:
            continue
        desc = row.get(cols["description"]) if "description" in cols else ""
        desc = "" if pd.isna(desc) else str(desc).strip()
        balance = parse_amount(row.get(cols["balance"])) if "balance" in cols else None
        category = row.get(cols["category"]) if "category" in cols else None
        out.append({
            "date": d.isoformat(),
            "description": desc,
            "amount": round(amount, 2),
            "balance": balance,
            "source_category": None if category is None or pd.isna(category) else str(category),
        })
    return out


_DEBIT_HINT = re.compile(
    r"\b(withdrawal|debit|purchase|payment to|pos|atm|fee|charge|transfer to|direct debit|dd|card)\b",
    re.IGNORECASE,
)
_CREDIT_HINT = re.compile(r"\b(deposit|credit|salary|payroll|refund|interest paid|transfer from|received)\b", re.IGNORECASE)
_BALANCE_LINE = re.compile(r"\b(opening|closing|beginning|ending|previous|new)\s+balance\b", re.IGNORECASE)


def transactions_from_text(text: str, day_first: bool = False) -> list[dict]:
    """Parse statement lines of the form ``DATE  DESCRIPTION  AMOUNT  [BALANCE]``.

    When a running balance is present, the sign of each transaction is inferred
    from how the balance moved, which is more reliable than keyword guessing.
    """
    out = []
    prev_balance = None
    for line in text.splitlines():
        line = line.strip()
        if _BALANCE_LINE.search(line):
            amounts = find_amounts(line)
            if amounts:
                prev_balance = amounts[-1]
            continue
        m = DATE_RE.match(line)
        if not m:
            continue
        d = parse_date(m.group(1), day_first)
        if not d:
            continue
        rest = line[m.end():].strip()
        amounts = find_amounts(rest)
        if not amounts:
            continue
        # Description is everything before the first amount.
        first_num = re.search(r"[-($€£]?\s?\d[\d,]*[.,]\d{2}", rest)
        desc = rest[: first_num.start()].strip(" -|") if first_num else rest

        balance = None
        sign_known = False
        if len(amounts) >= 2:
            amount, balance = amounts[-2], amounts[-1]
            if prev_balance is not None:
                delta = round(balance - prev_balance, 2)
                if abs(abs(delta) - abs(amount)) < 0.011:
                    amount, sign_known = delta, True
        else:
            amount = amounts[0]
        if amount > 0 and not sign_known:
            if _DEBIT_HINT.search(desc) and not _CREDIT_HINT.search(desc):
                amount = -amount
        if balance is not None:
            prev_balance = balance
        out.append({
            "date": d.isoformat(),
            "description": desc,
            "amount": round(amount, 2),
            "balance": balance,
            "source_category": None,
        })
    return out
