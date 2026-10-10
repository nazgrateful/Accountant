"""Extraction pipeline: raw file bytes -> structured financial data."""

from __future__ import annotations

from dataclasses import dataclass, field

from .classify import DOC_TYPES, classify
from .fields import extract_fields, validate_fields
from .readers import SUPPORTED_EXTENSIONS, UnsupportedFileError, read_document
from .transactions import is_transaction_table, transactions_from_table, transactions_from_text

__all__ = [
    "DOC_TYPES", "SUPPORTED_EXTENSIONS", "UnsupportedFileError", "ExtractionResult",
    "process_document", "validate_fields",
]


@dataclass
class ExtractionResult:
    filename: str
    doc_type: str
    confidence: float
    text: str
    pages: int
    fields: dict = field(default_factory=dict)
    checks: list[dict] = field(default_factory=list)
    transactions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def process_document(filename: str, data: bytes, day_first: bool = False) -> ExtractionResult:
    raw = read_document(filename, data)

    txn_tables = [t for t in raw.tables if is_transaction_table(t)]
    doc_type, confidence = classify(raw.text, bool(txn_tables), raw.is_tabular)

    result = ExtractionResult(
        filename=filename, doc_type=doc_type, confidence=confidence,
        text=raw.text, pages=raw.pages, warnings=list(raw.warnings),
    )

    if doc_type in ("invoice", "receipt"):
        result.fields = extract_fields(raw.text, day_first)
        result.checks = validate_fields(result.fields)
    elif doc_type in ("bank_statement", "ledger", "unknown"):
        for table in txn_tables:
            result.transactions.extend(transactions_from_table(table, day_first))
        if not result.transactions and not raw.is_tabular:
            result.transactions = transactions_from_text(raw.text, day_first)
        if doc_type == "unknown" and result.transactions:
            result.doc_type, result.confidence = "bank_statement", 0.5
        if doc_type == "unknown" and not result.transactions:
            # Fall back to treating it as an invoice-like document if it has a total.
            fields = extract_fields(raw.text, day_first)
            if fields.get("total") is not None:
                result.fields = fields
                result.checks = validate_fields(fields)

    if result.doc_type in ("bank_statement", "ledger") and not result.transactions:
        result.warnings.append("Looked like a statement but no transaction rows were recognised.")
    return result
