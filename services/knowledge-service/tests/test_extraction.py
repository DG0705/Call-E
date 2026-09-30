"""Deterministic tests for knowledge file extraction (all formats)."""

import io
import zipfile

import pytest

from knowledge_service.extraction import (
    ExtractionError,
    extract_text,
    extension_for,
    is_supported,
)


def make_pdf_bytes(lines: list[str]) -> bytes:
    """Build a minimal valid single-page PDF with selectable text lines."""
    content_lines = "".join(
        f"BT /F1 12 Tf 10 {200 - index * 20} Td ({line}) Tj ET\n"
        for index, line in enumerate(lines)
    )
    content = content_lines.encode("latin-1")
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 250] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode("latin-1") + body + b"\nendobj\n")
    xref_at = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF".encode("latin-1")
    )
    return output.getvalue()


def make_docx_bytes() -> bytes:
    from docx import Document

    document = Document()
    document.add_heading("Price List", level=1)
    document.add_paragraph("DEW 28 costs 7300 INR.")
    table = document.add_table(rows=2, cols=3)
    for row, values in enumerate([["Product", "Size", "Price"], ["DEW", "28", "7300"]]):
        for column, value in enumerate(values):
            table.cell(row, column).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    products = workbook.active
    products.title = "Products"
    products.append(["Product", "Size", "Price", "Material"])
    products.append(["DEW", 21, 4200, "FRP"])
    products.append(["DEW", 28, 7300, "FRP"])
    notes = workbook.create_sheet("Notes")
    notes.append(["made to order"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_extension_resolution_prefers_filename_then_mime() -> None:
    assert extension_for("catalog.PDF") == ".pdf"
    assert extension_for("no-extension", "text/csv") == ".csv"
    assert extension_for("unknown.xyz", "application/octet-stream") is None
    assert is_supported("prices.xlsx") is True
    assert is_supported("archive.zip") is False


def test_txt_extraction_is_verbatim() -> None:
    extracted = extract_text(b"  Hello\r\nworld  ", filename="note.txt")

    assert extracted.text == "  Hello\r\nworld  "
    assert extracted.title == "note.txt"
    assert extracted.source_type == "text"


def test_markdown_extraction_marks_source_type() -> None:
    extracted = extract_text(b"# Title\n\nSome *text*.", filename="doc.md")

    assert "Title" in extracted.text
    assert extracted.source_type == "markdown"


def test_pdf_extraction_is_page_aware() -> None:
    extracted = extract_text(
        make_pdf_bytes(["DEW 28 price 7300", "made to order"]),
        filename="catalog.pdf",
    )

    assert "--- Page 1 ---" in extracted.text
    assert "DEW 28 price 7300" in extracted.text
    assert "made to order" in extracted.text


def test_pdf_without_text_is_rejected() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"%PDF-1.4 not a real pdf", filename="broken.pdf")


def test_docx_extraction_reads_paragraphs_and_tables() -> None:
    extracted = extract_text(make_docx_bytes(), filename="prices.docx")

    assert "Price List" in extracted.text
    assert "DEW 28 costs 7300 INR." in extracted.text
    assert "Product | Size | Price" in extracted.text
    assert "DEW | 28 | 7300" in extracted.text


def test_docx_rejects_non_zip_bytes() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"not a docx", filename="broken.docx")


def test_xlsx_extraction_renders_sheets_headers_rows() -> None:
    extracted = extract_text(make_xlsx_bytes(), filename="prices.xlsx")

    assert "Sheet: Products" in extracted.text
    assert "Product | Size | Price | Material" in extracted.text
    assert "DEW | 28 | 7300 | FRP" in extracted.text
    assert "Sheet: Notes" in extracted.text
    assert "made to order" in extracted.text
    assert extracted.table_rows is not None
    assert any(
        "DEW | 28 | 7300 | FRP" in row and "Price" in row
        for row in extracted.table_rows
    )


def test_csv_extraction_exposes_header_prefixed_rows() -> None:
    extracted = extract_text(
        b"Product,Size,Price\nDEW,28,7300\n", filename="prices.csv"
    )

    assert extracted.table_rows == ["Product | Size | Price\nDEW | 28 | 7300"]


def test_xlsx_rejects_non_zip_bytes() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"not a workbook", filename="broken.xlsx")


def test_csv_extraction_renders_pipe_rows() -> None:
    extracted = extract_text(
        b"Product,Size,Price\nDEW,28,7300\n", filename="prices.csv"
    )

    assert "Product | Size | Price" in extracted.text
    assert "DEW | 28 | 7300" in extracted.text


def test_html_extraction_drops_noise() -> None:
    markup = (
        b"<html><head><title>Kaari Planters</title><style>.x{}</style></head>"
        b"<body><nav>Home Shop</nav><script>evil()</script>"
        b"<h1>DEW 28</h1><p>Price 7300 INR.</p></body></html>"
    )
    extracted = extract_text(markup, filename="page.html")

    assert "DEW 28" in extracted.text
    assert "Price 7300 INR." in extracted.text
    assert "evil()" not in extracted.text
    assert "Home Shop" not in extracted.text
    assert extracted.source_type == "html"


def test_json_extraction_preserves_key_value_relationships() -> None:
    payload = b'{"products": [{"name": "DEW 28", "price": 7300}], "made_to_order": true}'

    extracted = extract_text(payload, filename="catalog.json")

    assert "DEW 28" in extracted.text
    assert "7300" in extracted.text
    assert "price" in extracted.text
    assert "made_to_order" in extracted.text


def test_json_rejects_malformed_payload() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"{not json", filename="broken.json")


def test_unsupported_type_is_rejected() -> None:
    with pytest.raises(ExtractionError):
        extract_text(b"\x00\x01\x02", filename="archive.zip")


def test_extraction_is_deterministic() -> None:
    data = make_xlsx_bytes()

    assert (
        extract_text(data, filename="a.xlsx").text
        == extract_text(data, filename="b.xlsx").text
    )


def test_docx_is_treated_as_static_content() -> None:
    """Macros or active content must never affect extraction output."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>Static text only</w:t></w:r></w:p></w:body></w:document>",
        )
    extracted = extract_text(buffer.getvalue(), filename="macro.docm".replace("docm", "docx"))

    assert extracted.text == "Static text only"
