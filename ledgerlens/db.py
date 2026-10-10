"""SQLite persistence for documents, transactions and categorisation rules."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from flask import current_app, g

from .analysis import DEFAULT_RULES

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    filename     TEXT NOT NULL,
    doc_type     TEXT NOT NULL,
    confidence   REAL NOT NULL DEFAULT 0,
    uploaded_at  TEXT NOT NULL,
    pages        INTEGER NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'new',
    text         TEXT NOT NULL DEFAULT '',
    fields       TEXT NOT NULL DEFAULT '{}',
    checks       TEXT NOT NULL DEFAULT '[]',
    warnings     TEXT NOT NULL DEFAULT '[]',
    content      BLOB
);
CREATE TABLE IF NOT EXISTS transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    date             TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    amount           REAL NOT NULL,
    balance          REAL,
    category         TEXT,
    category_locked  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_txn_doc ON transactions(document_id);
CREATE INDEX IF NOT EXISTS ix_txn_date ON transactions(date);
CREATE TABLE IF NOT EXISTS rules (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern   TEXT NOT NULL,
    category  TEXT NOT NULL,
    priority  INTEGER NOT NULL DEFAULT 100
);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO rules (pattern, category, priority) VALUES (?, ?, ?)",
            [(p, c, (i + 1) * 10) for i, (p, c) in enumerate(DEFAULT_RULES)],
        )
    conn.commit()


# --- documents -----------------------------------------------------------------

def _doc_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d.pop("content", None)
    for key in ("fields", "checks", "warnings"):
        d[key] = json.loads(d[key])
    return d


def insert_document(db, result, content: bytes) -> int:
    cur = db.execute(
        "INSERT INTO documents (filename, doc_type, confidence, uploaded_at, pages, text, fields, checks, warnings, content)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            result.filename, result.doc_type, result.confidence,
            datetime.now().isoformat(timespec="seconds"), result.pages, result.text,
            json.dumps(result.fields), json.dumps(result.checks), json.dumps(result.warnings), content,
        ),
    )
    return cur.lastrowid


def list_documents(db) -> list[dict]:
    rows = db.execute(
        "SELECT d.id, d.filename, d.doc_type, d.confidence, d.uploaded_at, d.pages, d.status, d.text,"
        " d.fields, d.checks, d.warnings, COUNT(t.id) AS txn_count"
        " FROM documents d LEFT JOIN transactions t ON t.document_id = d.id"
        " GROUP BY d.id ORDER BY d.id DESC"
    ).fetchall()
    return [_doc_row(r) for r in rows]


def get_document(db, doc_id: int) -> dict | None:
    row = db.execute(
        "SELECT id, filename, doc_type, confidence, uploaded_at, pages, status, text, fields, checks, warnings"
        " FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    return _doc_row(row) if row else None


def get_document_content(db, doc_id: int) -> tuple[str, bytes] | None:
    row = db.execute("SELECT filename, content FROM documents WHERE id = ?", (doc_id,)).fetchone()
    return (row["filename"], row["content"]) if row else None


def update_document(db, doc_id: int, **values):
    for key in ("fields", "checks", "warnings"):
        if key in values:
            values[key] = json.dumps(values[key])
    cols = ", ".join(f"{k} = ?" for k in values)
    db.execute(f"UPDATE documents SET {cols} WHERE id = ?", (*values.values(), doc_id))


def delete_document(db, doc_id: int):
    db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


# --- transactions --------------------------------------------------------------

def insert_transactions(db, doc_id: int, txns: list[dict]):
    db.executemany(
        "INSERT INTO transactions (document_id, date, description, amount, balance, category)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(doc_id, t["date"], t["description"], t["amount"], t.get("balance"), t.get("category")) for t in txns],
    )


def list_transactions(db, document_id=None, category=None, search=None, start=None, end=None) -> list[dict]:
    sql = ("SELECT t.*, d.filename FROM transactions t JOIN documents d ON d.id = t.document_id WHERE 1=1")
    args: list = []
    if document_id:
        sql += " AND t.document_id = ?"
        args.append(document_id)
    if category:
        sql += " AND t.category = ?"
        args.append(category)
    if search:
        sql += " AND t.description LIKE ?"
        args.append(f"%{search}%")
    if start:
        sql += " AND t.date >= ?"
        args.append(start)
    if end:
        sql += " AND t.date <= ?"
        args.append(end)
    sql += " ORDER BY t.date, t.id"
    return [dict(r) for r in db.execute(sql, args).fetchall()]


def set_transaction_category(db, txn_id: int, category: str):
    db.execute("UPDATE transactions SET category = ?, category_locked = 1 WHERE id = ?", (category, txn_id))


def categories_in_use(db) -> list[str]:
    rows = db.execute(
        "SELECT category FROM rules UNION SELECT category FROM transactions WHERE category IS NOT NULL ORDER BY 1"
    ).fetchall()
    return [r[0] for r in rows]


# --- rules ---------------------------------------------------------------------

def list_rules(db) -> list[dict]:
    return [dict(r) for r in db.execute("SELECT * FROM rules ORDER BY priority, id").fetchall()]


def rule_tuples(db) -> list[tuple[str, str]]:
    return [(r["pattern"], r["category"]) for r in list_rules(db)]
