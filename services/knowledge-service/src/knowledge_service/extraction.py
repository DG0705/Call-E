"""Deterministic text extraction for customer knowledge file formats.

Each extractor turns raw upload bytes into plain readable text that flows
into the existing normalize → chunk → embed → store pipeline. Extraction is
pure and deterministic: the same bytes always produce the same text. Nothing
here executes document macros or embedded code — only static content is read.
"""

from __future__ import annotations

import csv
import html as html_module
import io
import json
import zipfile
from html.parser import HTMLParser
from typing import Any
from xml.etree import ElementTree


class ExtractionError(Exception):
    """Raised when upload bytes cannot be extracted as text."""


class ExtractedText:
    """Plain-text extraction result with identifying metadata."""

    def __init__(
        self,
        *,
        text: str,
        title: str,
        source_type: str,
        table_rows: list[str] | None = None,
    ) -> None:
        self.text = text
        self.title = title
        self.source_type = source_type
        # For tabular sources (spreadsheets, CSV): each entry is one
        # self-contained data row prefixed with its header, so retrieval can
        # rank individual facts instead of one diluted table blob.
        self.table_rows = table_rows


SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".json": "application/json",
}

_EXTENSION_BY_MIME: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/csv": ".csv",
    "application/csv": ".csv",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/html": ".html",
    "application/json": ".json",
}


def extension_for(filename: str, mime_type: str | None = None) -> str | None:
    """Resolve the extraction extension from filename, falling back to MIME."""
    lowered = filename.lower()
    for extension in SUPPORTED_EXTENSIONS:
        if lowered.endswith(extension):
            return extension
    if mime_type:
        base = mime_type.split(";")[0].strip().lower()
        return _EXTENSION_BY_MIME.get(base)
    return None


def is_supported(filename: str, mime_type: str | None = None) -> bool:
    """Report whether upload bytes can be extracted as text."""
    return extension_for(filename, mime_type) is not None


def extract_text(
    data: bytes, *, filename: str, mime_type: str | None = None
) -> ExtractedText:
    """Extract readable text from upload bytes by file extension."""
    extension = extension_for(filename, mime_type)
    if extension is None:
        raise ExtractionError(f"Unsupported file type for '{filename}'.")
    try:
        if extension == ".pdf":
            return _extract_pdf(data, filename)
        if extension == ".docx":
            return _extract_docx(data, filename)
        if extension == ".xlsx":
            return _extract_xlsx(data, filename)
        if extension == ".csv":
            return _extract_csv(data, filename)
        if extension in (".txt", ".md", ".markdown"):
            return _extract_textual(data, filename, extension)
        if extension in (".html", ".htm"):
            return _extract_html(data, filename)
        if extension == ".json":
            return _extract_json(data, filename)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError(f"Could not extract text from '{filename}'.") from exc
    raise ExtractionError(f"Unsupported file type for '{filename}'.")


def _decode(data: bytes, filename: str) -> str:
    for encoding in ("utf-8", "utf-8-sig", "windows-1252", "latin-1"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, ValueError):
            continue
    raise ExtractionError(f"Could not decode text from '{filename}'.")


def _extract_textual(data: bytes, filename: str, extension: str) -> ExtractedText:
    text = _decode(data, filename)
    source_type = "markdown" if extension in (".md", ".markdown") else "text"
    return ExtractedText(text=text, title=filename, source_type=source_type)


def _extract_pdf(data: bytes, filename: str) -> ExtractedText:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(f"Could not parse PDF '{filename}'.") from exc
    pages: list[str] = []
    for number, page in enumerate(reader.pages, start=1):
        try:
            content = page.extract_text() or ""
        except Exception:
            content = ""
        content = content.strip()
        if content:
            pages.append(f"--- Page {number} ---\n{content}")
    if not pages:
        raise ExtractionError(f"No readable text found in PDF '{filename}'.")
    return ExtractedText(text="\n\n".join(pages), title=filename, source_type="text")


_DOCX_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_paragraph_text(paragraph: ElementTree.Element) -> str:
    return "".join(
        node.text or "" for node in paragraph.iter(f"{_DOCX_NAMESPACE}t")
    ).strip()


def _docx_table_text(table: ElementTree.Element) -> str:
    rows: list[str] = []
    for row in table.iter(f"{_DOCX_NAMESPACE}tr"):
        cells = [
            _docx_paragraph_text(cell) for cell in row.findall(f"{_DOCX_NAMESPACE}tc")
        ]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _extract_docx(data: bytes, filename: str) -> ExtractedText:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    except Exception as exc:
        raise ExtractionError(f"Could not parse DOCX '{filename}'.") from exc
    body = root.find(f"{_DOCX_NAMESPACE}body")
    blocks: list[str] = []
    if body is not None:
        for child in body:
            if child.tag == f"{_DOCX_NAMESPACE}p":
                paragraph = _docx_paragraph_text(child)
                if paragraph:
                    blocks.append(paragraph)
            elif child.tag == f"{_DOCX_NAMESPACE}tbl":
                table = _docx_table_text(child)
                if table:
                    blocks.append(table)
    text = "\n\n".join(blocks).strip()
    if not text:
        raise ExtractionError(f"No readable text found in DOCX '{filename}'.")
    return ExtractedText(text=text, title=filename, source_type="text")


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml_bytes = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    root = ElementTree.fromstring(xml_bytes)
    return [
        "".join(node.text or "" for node in item.iter(f"{namespace}t"))
        for item in root.iter(f"{namespace}si")
    ]


_XLSX_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _xlsx_sheet_names(workbook_xml: bytes) -> list[str]:
    try:
        root = ElementTree.fromstring(workbook_xml)
    except Exception:
        return []
    return [
        element.get("name", "")
        for element in root.iter(f"{_XLSX_NAMESPACE}sheet")
    ]


def _xlsx_sheet_rows(xml_bytes: bytes, shared: list[str]) -> list[list[str]]:
    """Parse one worksheet part into its string cell grid."""
    root = ElementTree.fromstring(xml_bytes)
    grid: list[list[str]] = []
    for row in root.iter(f"{_XLSX_NAMESPACE}row"):
        cells: list[str] = []
        for cell in row.iter(f"{_XLSX_NAMESPACE}c"):
            cell_type = cell.get("t", "")
            value_node = cell.find(f"{_XLSX_NAMESPACE}v")
            value = value_node.text if value_node is not None else ""
            if cell_type == "s" and value and value.isdigit():
                index = int(value)
                value = shared[index] if index < len(shared) else ""
            elif cell_type == "inlineStr":
                inline = cell.find(f"{_XLSX_NAMESPACE}is/{_XLSX_NAMESPACE}t")
                value = inline.text if inline is not None and inline.text else ""
            cells.append((value or "").strip())
        while cells and not cells[-1]:
            cells.pop()
        if any(cells):
            grid.append(cells)
    return grid


def _extract_xlsx(data: bytes, filename: str) -> ExtractedText:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = _xlsx_sheet_names(archive.read("xl/workbook.xml"))
        shared = _xlsx_shared_strings(archive)
        sheet_files = sorted(
            name
            for name in archive.namelist()
            if name.startswith("xl/worksheets/sheet")
        )
    except Exception as exc:
        raise ExtractionError(f"Could not parse spreadsheet '{filename}'.") from exc
    sections: list[str] = []
    row_blocks: list[str] = []
    for position, sheet_file in enumerate(sheet_files):
        try:
            grid = _xlsx_sheet_rows(archive.read(sheet_file), shared)
        except Exception:
            continue
        if not grid:
            continue
        label = names[position] if position < len(names) and names[position] else sheet_file
        lines = [f"Sheet: {label}"]
        lines.extend(" | ".join(row) for row in grid)
        sections.append("\n".join(lines))
        header = " | ".join(grid[0])
        for row in grid[1:]:
            row_blocks.append(f"{label} | {header}\n" + " | ".join(row))
    text = "\n\n".join(sections).strip()
    if not text:
        raise ExtractionError(f"No readable rows found in spreadsheet '{filename}'.")
    return ExtractedText(
        text=text, title=filename, source_type="text", table_rows=row_blocks or None
    )


def _extract_csv(data: bytes, filename: str) -> ExtractedText:
    text = _decode(data, filename)
    try:
        rows = [row for row in csv.reader(io.StringIO(text)) if any(cell.strip() for cell in row)]
    except Exception as exc:
        raise ExtractionError(f"Could not parse CSV '{filename}'.") from exc
    if not rows:
        raise ExtractionError(f"No readable rows found in CSV '{filename}'.")
    lines = [" | ".join(cell.strip() for cell in row) for row in rows]
    header = lines[0]
    row_blocks = [f"{header}\n{line}" for line in lines[1:]] or None
    return ExtractedText(
        text=f"Table: {filename}\n" + "\n".join(lines),
        title=filename,
        source_type="text",
        table_rows=row_blocks,
    )


class _VisibleTextParser(HTMLParser):
    """Collect visible text while dropping scripts, styles, and navigation."""

    _SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            cleaned = data.strip()
            if cleaned:
                self.parts.append(cleaned)


def extract_html_text(markup: str) -> tuple[str, str]:
    """Return (title, visible text) from HTML markup."""
    parser = _VisibleTextParser()
    parser.feed(markup)
    text = " ".join(html_module.unescape(part) for part in parser.parts)
    title = ""
    lower = markup.lower()
    start = lower.find("<title>")
    if start >= 0:
        end = lower.find("</title>", start)
        if end > start:
            title = html_module.unescape(markup[start + 7 : end]).strip()
    return title, text


def _extract_html(data: bytes, filename: str) -> ExtractedText:
    _, text = extract_html_text(_decode(data, filename))
    if not text.strip():
        raise ExtractionError(f"No readable text found in HTML '{filename}'.")
    return ExtractedText(text=text, title=filename, source_type="html")


def _json_to_text(value: Any, *, key: str | None = None, depth: int = 0) -> list[str]:
    """Render JSON deterministically as key: value lines (depth-first)."""
    lines: list[str] = []
    prefix = f"{key}: " if key else ""
    if isinstance(value, dict):
        if key:
            lines.append(f"{key}:")
        for item_key in sorted(value):
            lines.extend(_json_to_text(value[item_key], key=str(item_key), depth=depth + 1))
    elif isinstance(value, list):
        if key:
            lines.append(f"{key}:")
        for item in value:
            lines.extend(_json_to_text(item, depth=depth + 1))
    elif value is None:
        lines.append(f"{prefix}(none)")
    elif isinstance(value, bool):
        lines.append(f"{prefix}{'yes' if value else 'no'}")
    else:
        lines.append(f"{prefix}{value}")
    return lines


def _extract_json(data: bytes, filename: str) -> ExtractedText:
    try:
        value = json.loads(_decode(data, filename))
    except Exception as exc:
        raise ExtractionError(f"Could not parse JSON '{filename}'.") from exc
    text = "\n".join(_json_to_text(value)).strip()
    if not text:
        raise ExtractionError(f"No readable content found in JSON '{filename}'.")
    return ExtractedText(text=text, title=filename, source_type="text")
