"""Flask web application for LedgerLens."""

from __future__ import annotations

import io
import os
from pathlib import Path

from flask import (
    Flask, Response, abort, flash, jsonify, redirect, render_template, request, send_file, url_for,
)

from . import db as store
from .analysis import UNCATEGORISED, categorise, find_anomalies, summarise
from .export import invoices_csv, transactions_csv, workbook
from .extract import DOC_TYPES, SUPPORTED_EXTENSIONS, UnsupportedFileError, process_document, validate_fields

EDITABLE_FIELDS = [
    ("vendor", "Vendor", "text"), ("customer", "Customer", "text"),
    ("document_number", "Document #", "text"), ("po_number", "PO #", "text"),
    ("issue_date", "Issue date", "date"), ("due_date", "Due date", "date"),
    ("payment_terms", "Terms", "text"), ("currency", "Currency", "text"), ("tax_id", "Tax ID", "text"),
    ("subtotal", "Subtotal", "number"), ("tax_rate", "Tax rate %", "number"), ("tax", "Tax", "number"),
    ("discount", "Discount", "number"), ("shipping", "Shipping", "number"), ("total", "Total", "number"),
]
STATUSES = ["new", "reviewed", "approved", "paid"]


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("LEDGERLENS_SECRET", "dev-only-change-me"),
        DATABASE=os.environ.get("LEDGERLENS_DB", str(Path(app.instance_path) / "ledgerlens.db")),
        DAY_FIRST=os.environ.get("LEDGERLENS_DAY_FIRST", "0") == "1",
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    )
    if config:
        app.config.update(config)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        store.init_db(store.get_db())
    app.teardown_appcontext(store.close_db)

    @app.template_filter("money")
    def money(value):
        if value is None or value == "":
            return "—"
        return f"{value:,.2f}" if value >= 0 else f"({abs(value):,.2f})"

    @app.context_processor
    def globals_():
        return {"DOC_TYPES": DOC_TYPES, "STATUSES": STATUSES}

    def _analysis(db, **filters):
        txns = store.list_transactions(db, **filters)
        docs = store.list_documents(db)
        return txns, docs, summarise(txns), find_anomalies(txns, docs)

    def _ingest(db, filename: str, data: bytes) -> tuple[int, object]:
        result = process_document(filename, data, day_first=app.config["DAY_FIRST"])
        rules = store.rule_tuples(db)
        for t in result.transactions:
            t["category"] = categorise(t["description"], t["amount"], rules)
        doc_id = store.insert_document(db, result, data)
        store.insert_transactions(db, doc_id, result.transactions)
        db.commit()
        return doc_id, result

    # --- pages ---------------------------------------------------------------

    @app.get("/")
    def dashboard():
        db = store.get_db()
        txns, docs, summary, anomalies = _analysis(db)
        open_invoices = [
            d for d in docs if d["doc_type"] == "invoice" and d["status"] != "paid" and d["fields"].get("total")
        ]
        payable = sum(d["fields"]["total"] for d in open_invoices)
        max_month = max([max(m["in"], m["out"]) for m in summary["months"]] or [0]) or 1
        max_cat = max([v for _, v in summary["expenses_by_category"]] or [0]) or 1
        return render_template(
            "dashboard.html", summary=summary, docs=docs[:6], anomalies=anomalies[:6],
            anomaly_count=len(anomalies), doc_count=len(docs), open_invoices=len(open_invoices),
            payable=payable, max_month=max_month, max_cat=max_cat,
        )

    @app.route("/upload", methods=["GET", "POST"])
    def upload():
        if request.method == "GET":
            return render_template("upload.html", extensions=sorted(SUPPORTED_EXTENSIONS))
        files = [f for f in request.files.getlist("files") if f and f.filename]
        if not files:
            flash("Choose at least one file to upload.", "error")
            return redirect(url_for("upload"))
        db = store.get_db()
        last_id = None
        for f in files:
            try:
                last_id, result = _ingest(db, f.filename, f.read())
            except UnsupportedFileError as exc:
                flash(f"{f.filename}: {exc}", "error")
                continue
            summary = f"{f.filename}: detected {DOC_TYPES[result.doc_type].lower()}"
            if result.transactions:
                summary += f", {len(result.transactions)} transactions extracted"
            if result.fields.get("total") is not None:
                summary += f", total {result.fields['total']:,.2f}"
            flash(summary + ".", "success")
            for w in result.warnings:
                flash(f"{f.filename}: {w}", "warning")
        if len(files) == 1 and last_id:
            return redirect(url_for("document_detail", doc_id=last_id))
        return redirect(url_for("documents"))

    @app.get("/documents")
    def documents():
        docs = store.list_documents(store.get_db())
        doc_type = request.args.get("type")
        if doc_type:
            docs = [d for d in docs if d["doc_type"] == doc_type]
        return render_template("documents.html", docs=docs, doc_type=doc_type)

    @app.get("/documents/<int:doc_id>")
    def document_detail(doc_id):
        db = store.get_db()
        doc = store.get_document(db, doc_id) or abort(404)
        txns = store.list_transactions(db, document_id=doc_id)
        summary = summarise(txns) if txns else None
        return render_template(
            "document.html", doc=doc, txns=txns, summary=summary, editable=EDITABLE_FIELDS,
            categories=store.categories_in_use(db),
        )

    @app.post("/documents/<int:doc_id>/fields")
    def update_fields(doc_id):
        db = store.get_db()
        doc = store.get_document(db, doc_id) or abort(404)
        fields = dict(doc["fields"])
        for key, _, kind in EDITABLE_FIELDS:
            raw = request.form.get(key, "").strip()
            if kind == "number":
                try:
                    fields[key] = round(float(raw.replace(",", "")), 2) if raw else None
                except ValueError:
                    flash(f"'{raw}' is not a valid number for {key}.", "error")
                    return redirect(url_for("document_detail", doc_id=doc_id))
            else:
                fields[key] = raw or None
        doc_type = request.form.get("doc_type", doc["doc_type"])
        store.update_document(db, doc_id, fields=fields, checks=validate_fields(fields),
                              doc_type=doc_type if doc_type in DOC_TYPES else doc["doc_type"],
                              status="reviewed" if doc["status"] == "new" else doc["status"])
        db.commit()
        flash("Fields saved and checks re-run.", "success")
        return redirect(url_for("document_detail", doc_id=doc_id))

    @app.post("/documents/<int:doc_id>/status")
    def update_status(doc_id):
        status = request.form.get("status")
        if status not in STATUSES:
            abort(400)
        db = store.get_db()
        store.get_document(db, doc_id) or abort(404)
        store.update_document(db, doc_id, status=status)
        db.commit()
        return redirect(request.referrer or url_for("document_detail", doc_id=doc_id))

    @app.post("/documents/<int:doc_id>/delete")
    def delete_document(doc_id):
        db = store.get_db()
        store.delete_document(db, doc_id)
        db.commit()
        flash("Document deleted.", "success")
        return redirect(url_for("documents"))

    @app.get("/documents/<int:doc_id>/file")
    def document_file(doc_id):
        found = store.get_document_content(store.get_db(), doc_id) or abort(404)
        filename, content = found
        return send_file(io.BytesIO(content), download_name=filename, as_attachment=True)

    @app.get("/transactions")
    def transactions():
        db = store.get_db()
        filters = {
            "category": request.args.get("category") or None,
            "search": request.args.get("q") or None,
            "start": request.args.get("start") or None,
            "end": request.args.get("end") or None,
            "document_id": request.args.get("document", type=int),
        }
        txns = store.list_transactions(db, **filters)
        return render_template(
            "transactions.html", txns=txns, summary=summarise(txns), filters=filters,
            categories=store.categories_in_use(db), docs=store.list_documents(db),
        )

    @app.post("/transactions/<int:txn_id>/category")
    def set_category(txn_id):
        category = request.form.get("category", "").strip() or UNCATEGORISED
        db = store.get_db()
        store.set_transaction_category(db, txn_id, category)
        db.commit()
        if request.accept_mimetypes.best == "application/json":
            return jsonify(ok=True, category=category)
        return redirect(request.referrer or url_for("transactions"))

    @app.get("/review")
    def review():
        db = store.get_db()
        _, _, _, anomalies = _analysis(db)
        return render_template("review.html", anomalies=anomalies)

    @app.route("/rules", methods=["GET", "POST"])
    def rules():
        db = store.get_db()
        if request.method == "POST":
            pattern = request.form.get("pattern", "").strip()
            category = request.form.get("category", "").strip()
            if pattern and category:
                db.execute("INSERT INTO rules (pattern, category, priority) VALUES (?, ?, ?)",
                           (pattern, category, request.form.get("priority", type=int) or 5))
                db.commit()
                flash(f"Rule added: '{pattern}' → {category}. Click “Re-apply rules” to update existing transactions.", "success")
            else:
                flash("Both a pattern and a category are required.", "error")
            return redirect(url_for("rules"))
        return render_template("rules.html", rules=store.list_rules(db))

    @app.post("/rules/<int:rule_id>/delete")
    def delete_rule(rule_id):
        db = store.get_db()
        db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        db.commit()
        return redirect(url_for("rules"))

    @app.post("/rules/apply")
    def apply_rules():
        db = store.get_db()
        rules_ = store.rule_tuples(db)
        rows = db.execute("SELECT id, description, amount FROM transactions WHERE category_locked = 0").fetchall()
        db.executemany("UPDATE transactions SET category = ? WHERE id = ?",
                       [(categorise(r["description"], r["amount"], rules_), r["id"]) for r in rows])
        db.commit()
        flash(f"Re-categorised {len(rows)} transactions (manual overrides kept).", "success")
        return redirect(url_for("rules"))

    # --- exports -------------------------------------------------------------

    @app.get("/export/transactions.csv")
    def export_transactions():
        txns = store.list_transactions(store.get_db())
        return Response(transactions_csv(txns), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=transactions.csv"})

    @app.get("/export/invoices.csv")
    def export_invoices():
        docs = store.list_documents(store.get_db())
        return Response(invoices_csv(docs), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=invoices.csv"})

    @app.get("/export/report.xlsx")
    def export_report():
        txns, docs, summary, anomalies = _analysis(store.get_db())
        return send_file(
            io.BytesIO(workbook(txns, docs, summary, anomalies)), as_attachment=True,
            download_name="ledgerlens-report.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # --- JSON API --------------------------------------------------------------

    @app.post("/api/extract")
    def api_extract():
        """Extract without storing — handy for scripting and integrations."""
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify(error="Send a file in the 'file' form field."), 400
        try:
            r = process_document(f.filename, f.read(), day_first=app.config["DAY_FIRST"])
        except UnsupportedFileError as exc:
            return jsonify(error=str(exc)), 415
        rules_ = store.rule_tuples(store.get_db())
        for t in r.transactions:
            t["category"] = categorise(t["description"], t["amount"], rules_)
        return jsonify(
            filename=r.filename, doc_type=r.doc_type, confidence=r.confidence, pages=r.pages,
            fields=r.fields, checks=r.checks, transactions=r.transactions, warnings=r.warnings,
            summary=summarise(r.transactions) if r.transactions else None,
        )

    @app.post("/api/documents")
    def api_upload():
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify(error="Send a file in the 'file' form field."), 400
        try:
            doc_id, _ = _ingest(store.get_db(), f.filename, f.read())
        except UnsupportedFileError as exc:
            return jsonify(error=str(exc)), 415
        return jsonify(store.get_document(store.get_db(), doc_id)), 201

    @app.get("/api/documents")
    def api_documents():
        docs = store.list_documents(store.get_db())
        for d in docs:
            d.pop("text", None)
        return jsonify(docs)

    @app.get("/api/transactions")
    def api_transactions():
        return jsonify(store.list_transactions(store.get_db()))

    @app.get("/api/summary")
    def api_summary():
        _, _, summary, anomalies = _analysis(store.get_db())
        return jsonify(summary=summary, anomalies=anomalies)

    @app.errorhandler(413)
    def too_large(_):
        flash("File too large (25 MB limit).", "error")
        return redirect(url_for("upload"))

    return app
