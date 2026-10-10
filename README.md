# LedgerLens

**Financial document data extraction & analysis for accountants.**

Upload invoices, receipts, bank statements and transaction exports. LedgerLens pulls out the
figures, checks the arithmetic, categorises the spend, flags what needs a second look, and
exports clean data to CSV or a formatted Excel workbook.

## Features

| Area | What it does |
|---|---|
| **Ingest** | PDF (text-based), CSV (any delimiter), Excel (`.xlsx`/`.xls`, all sheets), plain text. Drag-and-drop with multiple files at once. The original file is stored so you can download it later. |
| **Classify** | Detects whether a document is an invoice, receipt, bank statement or transaction ledger, with a confidence score. You can override the type. |
| **Invoice & receipt fields** | Vendor, customer, invoice / receipt number, PO number, tax ID, payment terms, issue & due dates, currency, subtotal, tax rate, tax, discount, shipping, total and line items. |
| **Validation** | Subtotal + tax + shipping − discount = total; tax rate × base = tax; qty × unit price = line amount; line items sum to subtotal; due date after issue date; missing number/vendor warnings. Edit any field and the checks re-run. |
| **Statements & ledgers** | Extracts date, description, amount and running balance. Signs (debit/credit) are inferred from balance movements, separate Debit/Credit columns, or keywords. Column names are auto-detected (`Posting Date`, `Narrative`, `Money Out`, …). US and European number formats, `(1,234.56)`, `CR`/`DR`. |
| **Categorisation** | Editable regex rule set (Payroll, Rent, Software, Travel, …). Override any transaction's category inline; manual overrides are kept when rules are re-applied. |
| **Analysis** | Money in/out, net cash flow, monthly trend, average monthly outflow, spend by category, top payees, unpaid invoice total. Filter by date, category, document or text. |
| **Review queue** | Possible duplicate payments, statistical outliers per category (robust z-score), large round-number payments, weekend expenses, uncategorised spend, running-balance breaks, failed invoice arithmetic, duplicate invoice numbers and past-due invoices. |
| **Export** | Transactions CSV, invoices CSV, and an Excel report with Summary, Transactions, Expenses/Income by Category, Monthly Cash Flow, Top Payees, Invoices & Receipts and Review Flags sheets. |
| **JSON API** | `POST /api/extract` (extract without saving), `POST /api/documents`, `GET /api/documents`, `GET /api/transactions`, `GET /api/summary`. |

## Quick start

```bash
pip install -r requirements.txt
python run.py            # http://127.0.0.1:5000
```

Try it with the bundled samples in `samples/` (an invoice, an invoice with a deliberate arithmetic
error, a receipt, a bank statement with a duplicate charge, and a credit-card CSV export).

### Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `LEDGERLENS_DB` | `instance/ledgerlens.db` | SQLite database path |
| `LEDGERLENS_DAY_FIRST` | `0` | Set to `1` to read `05/01/2024` as 5 January (UK/EU/AU) |
| `LEDGERLENS_SECRET` | dev value | Flask secret key — set this for any shared deployment |

### API example

```bash
curl -F file=@samples/invoice_brightworks_INV-2024-0117.pdf http://127.0.0.1:5000/api/extract
```

## Development

```bash
pip install -r requirements-dev.txt
python scripts/make_samples.py   # regenerate sample documents
pytest
```

Project layout:

```
ledgerlens/
  extract/
    readers.py        file -> text + tables (pdfplumber, pandas)
    classify.py       document type detection
    parsing.py        amount / date / currency parsing
    fields.py         invoice & receipt field extraction + validation checks
    transactions.py   statement & ledger transaction extraction
  analysis.py         categorisation rules, summaries, anomaly detection
  export.py           CSV and Excel report generation
  db.py               SQLite storage
  app.py              Flask routes (UI + JSON API)
  templates/, static/
```

## Limitations

- Scanned PDFs with no text layer need OCR first (e.g. `ocrmypdf in.pdf out.pdf`); LedgerLens warns when it sees one.
- Extraction is rule-based, so unusual layouts may need a field corrected by hand — the edit form and re-run checks are there for that.
- Designed as a single-user local tool: there is no login. Put it behind authentication before exposing it on a network.
