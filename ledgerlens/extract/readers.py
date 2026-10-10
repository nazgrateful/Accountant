"""Turn uploaded files into plain text plus any tables they contain."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

SUPPORTED_EXTENSIONS = {".pdf", ".csv", ".xlsx", ".xls", ".txt"}


class UnsupportedFileError(ValueError):
    pass


@dataclass
class RawDocument:
    filename: str
    text: str = ""
    tables: list[pd.DataFrame] = field(default_factory=list)
    pages: int = 1
    warnings: list[str] = field(default_factory=list)

    @property
    def is_tabular(self) -> bool:
        """True for spreadsheet-style inputs where the table *is* the document."""
        return Path(self.filename).suffix.lower() in {".csv", ".xlsx", ".xls"}


def read_document(filename: str, data: bytes) -> RawDocument:
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedFileError(
            f"Unsupported file type '{ext or filename}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    if ext == ".pdf":
        return _read_pdf(filename, data)
    if ext == ".csv":
        return _read_csv(filename, data)
    if ext in {".xlsx", ".xls"}:
        return _read_excel(filename, data)
    return RawDocument(filename=filename, text=_decode(data))


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _read_pdf(filename: str, data: bytes) -> RawDocument:
    import pdfplumber

    doc = RawDocument(filename=filename)
    texts = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            doc.pages = len(pdf.pages)
            for page in pdf.pages:
                texts.append(page.extract_text(layout=False) or "")
                for table in page.extract_tables() or []:
                    df = _table_to_frame(table)
                    if df is not None:
                        doc.tables.append(df)
    except Exception as exc:  # pdfplumber raises a variety of parser errors
        raise UnsupportedFileError(f"Could not read PDF: {exc}") from exc
    doc.text = "\n".join(texts)
    if not doc.text.strip():
        doc.warnings.append(
            "No text layer found in this PDF. It is probably a scanned image; "
            "run it through OCR first and re-upload."
        )
    return doc


def _table_to_frame(rows: list[list]) -> pd.DataFrame | None:
    rows = [[(c or "").strip() for c in r] for r in rows if r and any(c for c in r)]
    if len(rows) < 2:
        return None
    header, body = rows[0], rows[1:]
    if len(set(header)) != len(header) or not all(header):
        header = [h or f"col{i}" for i, h in enumerate(header)]
        header = [f"{h}_{i}" if header.count(h) > 1 else h for i, h in enumerate(header)]
    body = [r + [""] * (len(header) - len(r)) for r in body]
    return pd.DataFrame([r[: len(header)] for r in body], columns=header)


def _read_csv(filename: str, data: bytes) -> RawDocument:
    text = _decode(data)
    try:
        df = pd.read_csv(io.StringIO(text), sep=None, engine="python", dtype=str)
    except Exception as exc:
        raise UnsupportedFileError(f"Could not parse CSV: {exc}") from exc
    df = df.dropna(how="all")
    return RawDocument(filename=filename, text=text, tables=[df])


def _read_excel(filename: str, data: bytes) -> RawDocument:
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str)
    except Exception as exc:
        raise UnsupportedFileError(f"Could not read spreadsheet: {exc}") from exc
    doc = RawDocument(filename=filename)
    parts = []
    for name, df in sheets.items():
        df = df.dropna(how="all")
        if df.empty:
            continue
        doc.tables.append(df)
        parts.append(f"# Sheet: {name}\n{df.to_csv(index=False)}")
    doc.text = "\n".join(parts)
    doc.pages = len(sheets)
    return doc
