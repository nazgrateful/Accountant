"""Generate realistic sample documents in ./samples for demos and tests.

Usage: python scripts/make_samples.py
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples"


def _pdf(path: Path, lines: list[tuple[float, str]], font_size=10):
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 750
    for indent, text in lines:
        if y < 60:
            c.showPage()
            y = 750
        c.setFont("Helvetica", font_size)
        c.drawString(50 + indent, y, text)
        y -= 16
    c.save()


def invoice():
    _pdf(OUT / "invoice_brightworks_INV-2024-0117.pdf", [
        (0, "Brightworks Design Studio LLC"),
        (0, "450 Market Street, Suite 12, San Francisco, CA 94105"),
        (0, "Tax ID: 94-3217765"),
        (0, ""),
        (300, "INVOICE"),
        (300, "Invoice Number: INV-2024-0117"),
        (300, "Invoice Date: 03/04/2024"),
        (300, "Due Date: 04/03/2024"),
        (300, "Payment Terms: Net 30"),
        (300, "PO #: PO-88231"),
        (0, "Bill To: Harbor & Pine Accounting Group"),
        (0, ""),
        (0, "Description                         Qty     Unit Price      Amount"),
        (0, "Brand identity redesign               1      $4,500.00   $4,500.00"),
        (0, "Website landing pages                 6        $650.00   $3,900.00"),
        (0, "Stock photography licences           12         $45.00     $540.00"),
        (0, "Print-ready business cards            2        $120.00     $240.00"),
        (0, ""),
        (300, "Subtotal: $9,180.00"),
        (300, "Sales Tax (8.625%): $791.78"),
        (300, "Total Amount Due: $9,971.78"),
        (0, ""),
        (0, "Please remit payment to account 0045-221-889. Thank you for your business."),
    ])


def invoice_with_error():
    # Same vendor; the tax line does not add up to the stated total.
    _pdf(OUT / "invoice_northwind_NW-5521.pdf", [
        (0, "Northwind Office Supplies Inc."),
        (0, "12 Commerce Way, Austin, TX 78701"),
        (300, "INVOICE"),
        (300, "Invoice No: NW-5521"),
        (300, "Date: March 18, 2024"),
        (300, "Due Date: April 17, 2024"),
        (0, "Bill To: Harbor & Pine Accounting Group"),
        (0, ""),
        (0, "Item                                Qty     Price        Amount"),
        (0, "Ergonomic office chair               4     289.00       1,156.00"),
        (0, "Standing desk frame                  2     415.00         830.00"),
        (0, "Printer paper (case)                10      38.50         385.00"),
        (0, ""),
        (300, "Subtotal: 2,371.00"),
        (300, "Tax 8.25%: 195.61"),
        (300, "Shipping: 75.00"),
        (300, "Total Due: 2,661.61"),
    ])


def receipt():
    _pdf(OUT / "receipt_bluebottle.pdf", [
        (0, "Corner Bistro & Coffee"),
        (0, "88 Elm Street, Portland, OR"),
        (0, "Store #0231   Register 2   Cashier: Dana"),
        (0, "Receipt #: R-77812"),
        (0, "Date: 2024-03-12 12:41"),
        (0, ""),
        (0, "Club sandwich           2   14.50   29.00"),
        (0, "Latte                   3    5.25   15.75"),
        (0, "Sparkling water         2    3.00    6.00"),
        (0, ""),
        (0, "Subtotal                        50.75"),
        (0, "Tax                              0.00"),
        (0, "Total                           50.75"),
        (0, "VISA ****4421                   50.75"),
        (0, "Thank you for visiting!"),
    ])


def bank_statement():
    rows = [
        ("03/01/2024", "Opening Balance", None, 18250.00),
        ("03/01/2024", "RENT - MARKET ST PROPERTIES", -4200.00, None),
        ("03/02/2024", "STRIPE PAYOUT", 6340.55, None),
        ("03/04/2024", "AWS AMAZON WEB SERVICES", -612.40, None),
        ("03/05/2024", "PAYROLL GUSTO", -9800.00, None),
        ("03/06/2024", "COMCAST BUSINESS INTERNET", -189.99, None),
        ("03/08/2024", "UBER TRIP 8823", -42.18, None),
        ("03/08/2024", "UBER TRIP 8851", -38.90, None),
        ("03/11/2024", "CUSTOMER PAYMENT ACME CORP", 12500.00, None),
        ("03/12/2024", "CORNER BISTRO & COFFEE", -50.75, None),
        ("03/14/2024", "ADOBE CREATIVE CLOUD", -89.99, None),
        ("03/15/2024", "ADOBE CREATIVE CLOUD", -89.99, None),
        ("03/16/2024", "STAPLES OFFICE SUPPLIES", -312.47, None),
        ("03/18/2024", "TRANSFER TO SAVINGS", -5000.00, None),
        ("03/20/2024", "PG&E ELECTRIC UTILITY", -421.36, None),
        ("03/22/2024", "GOOGLE ADS MARKETING", -1250.00, None),
        ("03/25/2024", "STRIPE PAYOUT", 4870.10, None),
        ("03/28/2024", "MONTHLY SERVICE FEE", -25.00, None),
        ("03/30/2024", "ZEPHYR HOLDINGS LTD", -3000.00, None),
    ]
    lines = [
        (0, "First Coastal Bank"),
        (0, "Business Checking Statement"),
        (0, "Account Number: ****7781     Statement Period: 03/01/2024 - 03/31/2024"),
        (0, "Harbor & Pine Accounting Group"),
        (0, ""),
        (0, "Date         Description                                 Amount        Balance"),
    ]
    balance = rows[0][3]
    lines.append((0, f"03/01/2024   Opening Balance                                            {balance:,.2f}"))
    for d, desc, amt, _ in rows[1:]:
        balance = round(balance + amt, 2)
        # Bank prints unsigned amounts; sign is implied by the balance movement.
        lines.append((0, f"{d}   {desc:<42} {abs(amt):>12,.2f}   {balance:>12,.2f}"))
    lines.append((0, f"03/31/2024   Closing Balance                                            {balance:,.2f}"))
    _pdf(OUT / "bank_statement_march_2024.pdf", lines, font_size=9)


def ledger_csv():
    (OUT / "card_transactions_q1_2024.csv").write_text(
        "Transaction Date,Description,Debit,Credit,Category\n"
        "01/03/2024,DELTA AIRLINES SFO-JFK,612.30,,\n"
        "01/04/2024,MARRIOTT NEW YORK,845.00,,\n"
        "01/05/2024,STARBUCKS #1182,6.45,,\n"
        "01/09/2024,GITHUB INC,44.00,,\n"
        "01/12/2024,SLACK TECHNOLOGIES,87.50,,\n"
        "01/15/2024,PAYMENT THANK YOU,,1595.25,\n"
        "01/20/2024,STAPLES 0442,58.12,,\n"
        "01/27/2024,DOORDASH LUNCH TEAM,186.40,,\n"
        "02/03/2024,LINKEDIN ADS,500.00,,\n"
        "02/09/2024,GITHUB INC,44.00,,\n"
        "02/12/2024,SLACK TECHNOLOGIES,87.50,,\n"
        "02/14/2024,SHELL OIL 5512,62.18,,\n"
        "02/15/2024,PAYMENT THANK YOU,,832.90,\n"
        "02/24/2024,LEGAL ZOOM ATTORNEY,2500.00,,\n"
        "03/02/2024,UNITED AIRLINES ORD,488.20,,\n"
        "03/09/2024,GITHUB INC,44.00,,\n"
        "03/12/2024,SLACK TECHNOLOGIES,87.50,,\n"
        "03/15/2024,PAYMENT THANK YOU,,3234.30,\n"
        "03/21/2024,MYSTERY VENDOR 99,140.00,,\n"
    )


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    invoice()
    invoice_with_error()
    receipt()
    bank_statement()
    ledger_csv()
    print(f"Samples written to {OUT}")
