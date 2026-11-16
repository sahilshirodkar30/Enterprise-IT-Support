import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

SUPPORTED = {".pdf", ".txt", ".md", ".docx"}
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
MAX_EMPTY_PDF_RATIO = 0.5


@dataclass(frozen=True)
class Block:
    text: str
    section: str | None = None
    page: int | None = None


def read_blocks(path: Path) -> list[Block]:
    ext = path.suffix.lower()
    if ext == ".md":
        return _read_markdown(path)
    if ext == ".txt":
        return _read_text(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext == ".pdf":
        return _read_pdf(path)
    raise ValueError(f"unsupported file type: {ext}")


def _normalise(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_text(path: Path) -> list[Block]:
    text = _normalise(path.read_text(encoding="utf-8-sig")).strip()
    return [Block(text)] if text else []


def _read_markdown(path: Path) -> list[Block]:
    text = _normalise(path.read_text(encoding="utf-8-sig"))
    blocks: list[Block] = []
    section: str | None = None
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            blocks.append(Block(body, section))
        buf.clear()

    for line in text.split("\n"):
        m = HEADING_RE.match(line)
        if m:
            flush()
            section = m.group(1).strip()
        else:
            buf.append(line)
    flush()
    return blocks


def _iter_docx(doc: Document):
    """Yield paragraphs and tables in document order."""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _is_heading(p: Paragraph) -> bool:
    name = (p.style.name if p.style else "") or ""
    return name.lower().startswith(("heading", "title"))


def _table_rows(table: Table) -> list[str]:
    rows = []
    for row in table.rows:
        cells, prev = [], None
        for cell in row.cells:
            if cell._tc is prev:  # merged cells repeat the same element
                continue
            prev = cell._tc
            text = " ".join(cell.text.split())
            if text:
                cells.append(text)
        if cells:
            rows.append(" | ".join(cells))
    return rows


def _read_docx(path: Path) -> list[Block]:
    doc = Document(str(path))
    blocks: list[Block] = []
    section: str | None = None
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            blocks.append(Block(body, section))
        buf.clear()

    for item in _iter_docx(doc):
        if isinstance(item, Table):
            buf.extend(_table_rows(item))
            continue
        text = " ".join(item.text.split())
        if not text:
            continue
        if _is_heading(item):
            flush()
            section = text
        else:
            buf.append(text)
    flush()
    return blocks


def _read_pdf(path: Path) -> list[Block]:
    reader = PdfReader(str(path))
    total = len(reader.pages)
    blocks: list[Block] = []
    empty = 0

    for n, page in enumerate(reader.pages, 1):
        text = _normalise((page.extract_text() or "").strip())
        if text:
            blocks.append(Block(text, page=n))
        else:
            empty += 1

    if total == 0 or not blocks:
        raise ValueError("no extractable text; the PDF may be scanned and need OCR")
    if empty / total > MAX_EMPTY_PDF_RATIO:
        raise ValueError(f"{empty} of {total} pages had no text; OCR needed")
    return blocks