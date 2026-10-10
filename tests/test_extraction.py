from ledgerlens.extract import process_document
from ledgerlens.extract.fields import extract_fields, validate_fields
from ledgerlens.extract.transactions import transactions_from_text

import pytest

from ledgerlens.extract.readers import UnsupportedFileError


def _load(samples, name):
    return process_document(name, (samples / name).read_bytes())


def test_invoice_pdf(samples):
    r = _load(samples, "invoice_brightworks_INV-2024-0117.pdf")
    f = r.fields
    assert r.doc_type == "invoice"
    assert f["vendor"] == "Brightworks Design Studio LLC"
    assert f["customer"] == "Harbor & Pine Accounting Group"
    assert f["document_number"] == "INV-2024-0117"
    assert f["po_number"] == "PO-88231"
    assert f["issue_date"] == "2024-03-04"
    assert f["due_date"] == "2024-04-03"
    assert f["payment_terms"] == "Net 30"
    assert f["currency"] == "USD"
    assert (f["subtotal"], f["tax"], f["total"], f["tax_rate"]) == (9180.0, 791.78, 9971.78, 8.625)
    assert len(f["line_items"]) == 4
    assert all(c["status"] == "pass" for c in r.checks)


def test_invoice_with_arithmetic_error_is_flagged(samples):
    r = _load(samples, "invoice_northwind_NW-5521.pdf")
    assert r.fields["shipping"] == 75.0
    failed = [c["check"] for c in r.checks if c["status"] == "fail"]
    assert failed == ["Subtotal + tax = total"]


def test_receipt_pdf(samples):
    r = _load(samples, "receipt_bluebottle.pdf")
    assert r.doc_type == "receipt"
    assert r.fields["total"] == 50.75
    assert r.fields["document_number"] == "R-77812"
    assert r.fields["issue_date"] == "2024-03-12"


def test_bank_statement_pdf_infers_signs_from_balance(samples):
    r = _load(samples, "bank_statement_march_2024.pdf")
    assert r.doc_type == "bank_statement"
    assert len(r.transactions) == 18
    by_desc = {t["description"]: t["amount"] for t in r.transactions}
    assert by_desc["STRIPE PAYOUT"] > 0
    assert by_desc["CUSTOMER PAYMENT ACME CORP"] == 12500.0
    assert by_desc["PAYROLL GUSTO"] == -9800.0
    assert r.transactions[-1]["balance"] == 16837.62


def test_csv_with_debit_credit_columns(samples):
    r = _load(samples, "card_transactions_q1_2024.csv")
    assert r.doc_type == "ledger"
    assert len(r.transactions) == 19
    assert r.transactions[0] == {
        "date": "2024-01-03", "description": "DELTA AIRLINES SFO-JFK", "amount": -612.3,
        "balance": None, "source_category": None,
    }
    assert round(sum(t["amount"] for t in r.transactions if t["amount"] > 0), 2) == 5662.45


def test_csv_with_signed_amount_and_day_first():
    data = b"Date;Narrative;Amount;Balance\n05/01/2024;Coffee;-3,50;996,50\n06/01/2024;Salary;2.000,00;2.996,50\n"
    r = process_document("export.csv", data, day_first=True)
    assert [(t["date"], t["amount"], t["balance"]) for t in r.transactions] == [
        ("2024-01-05", -3.5, 996.5), ("2024-01-06", 2000.0, 2996.5)]


def test_xlsx(tmp_path):
    import pandas as pd
    path = tmp_path / "ledger.xlsx"
    pd.DataFrame({"Posting Date": ["2024-02-01", "2024-02-02"], "Payee": ["AWS", "Client"],
                  "Amount": [-100.0, 250.0]}).to_excel(path, index=False)
    r = process_document("ledger.xlsx", path.read_bytes())
    assert [t["amount"] for t in r.transactions] == [-100.0, 250.0]


def test_text_statement_uses_keywords_without_balance():
    txns = transactions_from_text("2024-01-02 ATM WITHDRAWAL 60.00\n2024-01-03 DEPOSIT 500.00\n")
    assert [t["amount"] for t in txns] == [-60.0, 500.0]


def test_plain_text_invoice_with_discount():
    text = """Acme Widgets Ltd
    Invoice # A-1001
    Date: 2024-06-01
    Due Date: 2024-06-15
    Subtotal: 1,000.00
    Discount: -100.00
    VAT 20%: 180.00
    Total: 1,080.00
    """
    f = extract_fields(text)
    assert (f["vendor"], f["document_number"], f["discount"], f["tax"], f["total"]) == (
        "Acme Widgets Ltd", "A-1001", -100.0, 180.0, 1080.0)
    assert all(c["status"] != "fail" for c in validate_fields(f))


def test_unsupported_file():
    with pytest.raises(UnsupportedFileError):
        process_document("photo.heic", b"...")
