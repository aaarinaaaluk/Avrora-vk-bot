from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.sources.pdf_reader import extract_pdf_text


def create_test_pdf(page_count: int = 2) -> bytes:
    writer = PdfWriter()

    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)

    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_extract_pdf_text_preserves_page_numbers(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(create_test_pdf(2))

    document = extract_pdf_text(
        pdf_path,
        "https://example.org/sample.pdf",
    )

    assert document.page_count == 2
    assert [page.page_number for page in document.pages] == [1, 2]
    assert document.source_url == "https://example.org/sample.pdf"


def test_extract_pdf_text_raises_for_missing_file(tmp_path):
    missing_path = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError):
        extract_pdf_text(missing_path, "https://example.org/missing.pdf")
