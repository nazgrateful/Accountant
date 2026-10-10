from ledgerlens.analysis import DEFAULT_RULES, categorise, find_anomalies, normalise_payee, summarise


def t(id, date, desc, amount, **kw):
    return {"id": id, "document_id": 1, "date": date, "description": desc, "amount": amount,
            "balance": kw.get("balance"), "category": kw.get("category")}


def test_categorise_defaults():
    assert categorise("AWS AMAZON WEB SERVICES", -10, DEFAULT_RULES) == "Software & Subscriptions"
    assert categorise("RENT - MARKET ST", -10, DEFAULT_RULES) == "Rent & Lease"
    assert categorise("CURRENT ACCOUNT XYZ", -10, DEFAULT_RULES) == "Uncategorised"  # 'rent' inside a word
    assert categorise("STARBUCKS COFFEE", -10, DEFAULT_RULES) == "Meals & Entertainment"
    assert categorise("SOMETHING", 10, DEFAULT_RULES) == "Other Income"


def test_summarise():
    txns = [t(1, "2024-01-01", "A", 100, category="Revenue"), t(2, "2024-01-05", "B", -40, category="Rent"),
            t(3, "2024-02-01", "C", -10, category="Fees")]
    s = summarise(txns)
    assert (s["inflow"], s["outflow"], s["net"]) == (100, 50, 50)
    assert s["expenses_by_category"] == [("Rent", 40), ("Fees", 10)]
    assert [m["month"] for m in s["months"]] == ["2024-01", "2024-02"]
    assert s["avg_monthly_burn"] == 25


def test_normalise_payee():
    assert normalise_payee("POS PURCHASE STARBUCKS #1182 4421") == "Starbucks"


def test_duplicate_detection():
    a = find_anomalies([t(1, "2024-03-14", "ADOBE", -89.99, category="X"),
                        t(2, "2024-03-15", "ADOBE", -89.99, category="X"),
                        t(3, "2024-04-15", "ADOBE", -89.99, category="X")])
    dups = [x for x in a if x["kind"] == "Possible duplicate payment"]
    assert [d["transaction_id"] for d in dups] == [2]


def test_outlier_round_number_and_weekend():
    txns = [t(i, f"2024-03-0{i}", f"Vendor {i}", -100 - i, category="Ops") for i in range(1, 7)]
    txns.append(t(9, "2024-03-09", "BIG VENDOR", -5000, category="Ops"))  # Saturday
    kinds = {x["kind"] for x in find_anomalies(txns) if x.get("transaction_id") == 9}
    assert {"Unusually large amount", "Round-number payment", "Weekend expense"} <= kinds


def test_balance_break():
    txns = [t(1, "2024-01-01", "A", -10, balance=90, category="X"),
            t(2, "2024-01-02", "B", -10, balance=75, category="X")]
    assert any(x["kind"] == "Balance does not reconcile" for x in find_anomalies(txns))


def test_duplicate_invoice_numbers():
    docs = [{"id": i, "filename": f"f{i}.pdf", "doc_type": "invoice", "status": "paid", "checks": [],
             "fields": {"vendor": "Acme", "document_number": "INV-1"}} for i in (1, 2)]
    assert any(x["kind"] == "Duplicate invoice number" for x in find_anomalies([], docs))
