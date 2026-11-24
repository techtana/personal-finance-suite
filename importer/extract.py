"""Turn a dropped file into a Document: tables, text and/or page images.

Pure file handling, no AI. CSV/TSV, Excel, OFX/QFX, JSON, PDF (text layer or
scanned pages), plain text and photos.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime


class UnsupportedFile(Exception):
    """The file can't be read; the message is shown to the user."""


@dataclass
class Document:
    kind: str                     # csv | xlsx | ofx | pdf | text | image | json
    filename: str
    tables: list = field(default_factory=list)   # [[row cells as str]]
    text: str = ""
    images: list = field(default_factory=list)   # JPEG bytes, downscaled
    ofx: dict | None = None
    meta: dict = field(default_factory=dict)


EXT_KIND = {
    ".csv": "csv", ".tsv": "csv", ".xlsx": "xlsx", ".xlsm": "xlsx",
    ".ofx": "ofx", ".qfx": "ofx", ".qbo": "ofx", ".json": "json", ".pdf": "pdf",
    ".txt": "text", ".text": "text", ".md": "text", ".eml": "text", ".html": "text", ".htm": "text",
    ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image", ".gif": "image",
    ".bmp": "image", ".tif": "image", ".tiff": "image", ".heic": "image", ".heif": "image",
}
ACCEPTED_EXTENSIONS = sorted(EXT_KIND) + [".xls"]
MAX_IMAGE_SIDE = 1600
MAX_PDF_IMAGE_PAGES = 5


def kind_for(filename: str, data: bytes) -> str:
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".xls":
        raise UnsupportedFile("Old Excel .xls files can't be read. Save it as .xlsx or .csv and drop it again.")
    if ext in EXT_KIND:
        return EXT_KIND[ext]
    head = data[:2048]
    if head.startswith(b"%PDF"):
        return "pdf"
    if b"OFXHEADER" in head or b"<OFX>" in head.upper():
        return "ofx"
    if head[:3] == b"\xff\xd8\xff" or head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if head[:2] == b"PK":
        return "xlsx"
    return "text"


def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return data.decode("latin-1", errors="replace")


def load_document(data: bytes, filename: str) -> Document:
    kind = kind_for(filename, data)
    if kind == "csv":
        return Document("csv", filename, tables=[read_delimited(decode_text(data))])
    if kind == "xlsx":
        return read_xlsx(data, filename)
    if kind == "ofx":
        text = decode_text(data)
        return Document("ofx", filename, ofx=parse_ofx(text), text=text)
    if kind == "json":
        return read_json(decode_text(data), filename)
    if kind == "pdf":
        return read_pdf(data, filename)
    if kind == "image":
        return Document("image", filename, images=[prepare_image(data, filename)])
    text = decode_text(data)
    if kind == "text" and "<html" in text[:2000].lower():
        text = html_to_text(text)
    table = read_delimited(text)
    if looks_tabular(text, table):
        return Document("csv", filename, tables=[table], text=text)
    return Document("text", filename, text=text)


# ── delimited text ─────────────────────────────────────────────────────────────

def read_delimited(text: str) -> list[list[str]]:
    """Rows of a CSV/TSV, choosing the delimiter that gives the most consistent rows."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    sample = "\n".join(lines[:60])
    best, best_score = ",", -1
    for delim in (",", ";", "\t", "|"):
        try:
            rows = list(csv.reader(io.StringIO(sample), delimiter=delim))
        except csv.Error:
            continue
        counts = Counter(len(r) for r in rows if len(r) >= 2)
        if not counts:
            continue
        width, n = counts.most_common(1)[0]
        score = n * min(width, 8)
        if score > best_score:
            best, best_score = delim, score
    try:
        rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=best))
    except csv.Error as e:
        raise UnsupportedFile(f"The file looks like CSV but couldn't be read: {e}")
    return [[c.strip() for c in r] for r in rows]


def looks_tabular(text: str, table: list[list[str]]) -> bool:
    """A .txt that is really a CSV export."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 4:
        return False
    counts = Counter(len(r) for r in table if len(r) >= 3)
    if not counts:
        return False
    width, n = counts.most_common(1)[0]
    return width >= 3 and n >= 4 and n >= 0.7 * len(lines)


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", html)
    html = re.sub(r"(?i)</t[dh]>", "  ", html)
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())


# ── Excel ──────────────────────────────────────────────────────────────────────

def _cell_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat() if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else repr(round(v, 6))
    return str(v).strip()


def read_xlsx(data: bytes, filename: str) -> Document:
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover
        raise UnsupportedFile("Excel support needs openpyxl (pip install -r requirements.txt).")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        raise UnsupportedFile(f"The Excel file couldn't be opened: {e}")
    tables = []
    for ws in wb.worksheets:
        rows = [[_cell_str(c) for c in row] for row in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(c for c in r)]
        if rows:
            width = max(len(r) for r in rows)
            while width and all(len(r) < width or not r[width - 1] for r in rows):
                width -= 1
            tables.append([r[:width] for r in rows])
    wb.close()
    if not tables:
        raise UnsupportedFile("The Excel file has no data.")
    tables.sort(key=lambda t: -sum(1 for r in t if sum(1 for c in r if c) >= 3))
    return Document("xlsx", filename, tables=tables)


# ── JSON ───────────────────────────────────────────────────────────────────────

def read_json(text: str, filename: str) -> Document:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise UnsupportedFile(f"The JSON file isn't valid: {e}")
    records = None
    if isinstance(data, list) and data and all(isinstance(x, dict) for x in data):
        records = data
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                records = v
                break
    if not records:
        return Document("text", filename, text=json.dumps(data, indent=1)[:20000])
    headers = []
    for r in records:
        for k in r:
            if k not in headers and not isinstance(r[k], (dict, list)):
                headers.append(k)
    rows = [headers] + [[_cell_str(r.get(h)) for h in headers] for r in records]
    return Document("json", filename, tables=[rows])


# ── OFX / QFX ──────────────────────────────────────────────────────────────────

def _ofx_tag(block: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, re.I)
    return m.group(1).strip() if m else None


def _ofx_date(v: str | None) -> str | None:
    if not v:
        return None
    m = re.match(r"(\d{4})(\d{2})(\d{2})", v)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def parse_ofx(text: str) -> dict:
    """Transactions, closing balance and account id from OFX 1 (SGML) or OFX 2 (XML)."""
    from importer.parsing import parse_amount

    txns = []
    for block in re.findall(r"(?is)<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|</BANKTRANLIST>)", text):
        amount = parse_amount(_ofx_tag(block, "TRNAMT"), decimal_comma=False)
        name = _ofx_tag(block, "NAME") or ""
        memo = _ofx_tag(block, "MEMO") or ""
        txns.append({
            "date": _ofx_date(_ofx_tag(block, "DTPOSTED")),
            "amount": amount,
            "name": name,
            "memo": memo,
            "fitid": _ofx_tag(block, "FITID"),
            "trntype": (_ofx_tag(block, "TRNTYPE") or "").upper(),
            "checknum": _ofx_tag(block, "CHECKNUM"),
        })
    if not txns:
        raise UnsupportedFile("No transactions were found in this OFX/QFX file.")
    bal_block = re.search(r"(?is)<LEDGERBAL>(.*?)(?:</LEDGERBAL>|<AVAILBAL>|</STMTRS>|</CCSTMTRS>)", text)
    balance = None
    if bal_block:
        amt = parse_amount(_ofx_tag(bal_block.group(1), "BALAMT"), decimal_comma=False)
        if amt is not None:
            balance = {"amount": amt, "date": _ofx_date(_ofx_tag(bal_block.group(1), "DTASOF"))}
    return {
        "transactions": txns,
        "balance": balance,
        "account_id": _ofx_tag(text, "ACCTID"),
        "account_type": (_ofx_tag(text, "ACCTTYPE") or ("CREDITCARD" if re.search(r"(?i)<CCACCTFROM>", text) else "")).upper(),
        "org": _ofx_tag(text, "ORG"),
        "currency": _ofx_tag(text, "CURDEF"),
        "period": {"start": _ofx_date(_ofx_tag(text, "DTSTART")), "end": _ofx_date(_ofx_tag(text, "DTEND"))},
    }


# ── PDF ────────────────────────────────────────────────────────────────────────

def read_pdf(data: bytes, filename: str) -> Document:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        raise UnsupportedFile("PDF support needs pypdf (pip install -r requirements.txt).")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise UnsupportedFile("This PDF is password protected. Save an unprotected copy and drop that.")
    except UnsupportedFile:
        raise
    except Exception as e:
        raise UnsupportedFile(f"The PDF couldn't be opened: {e}")
    pages = []
    for page in reader.pages:
        try:
            txt = page.extract_text(extraction_mode="layout")
        except Exception:
            txt = page.extract_text() or ""
        pages.append("\n".join(ln.rstrip() for ln in (txt or "").splitlines() if ln.strip()))
    text = "\n\n".join(p for p in pages if p)
    if len(re.sub(r"\s", "", text)) >= 40:
        return Document("pdf", filename, text=text, meta={"pages": len(reader.pages)})
    images = []
    for page in reader.pages[:MAX_PDF_IMAGE_PAGES]:
        try:
            for img in page.images:
                images.append(prepare_image(img.data, img.name))
                break  # one scan per page
        except Exception:
            continue
    if not images:
        raise UnsupportedFile("This PDF has no text and no scanned pages that can be read.")
    return Document("pdf", filename, images=images, meta={"pages": len(reader.pages), "scanned": True})


# ── images ─────────────────────────────────────────────────────────────────────

def prepare_image(data: bytes, filename: str = "") -> bytes:
    """Upright, RGB, at most 1600 px on the long side, as JPEG."""
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover
        raise UnsupportedFile("Photo support needs Pillow (pip install -r requirements.txt).")
    if filename.lower().endswith((".heic", ".heif")):
        try:
            import pillow_heif  # type: ignore

            pillow_heif.register_heif_opener()
        except ImportError:
            raise UnsupportedFile("HEIC photos can't be read yet. Export the photo as JPEG and drop that.")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        out = io.BytesIO()
        img.convert("RGB").save(out, "JPEG", quality=88)
        return out.getvalue()
    except UnsupportedFile:
        raise
    except Exception as e:
        raise UnsupportedFile(f"The image couldn't be opened: {e}")
