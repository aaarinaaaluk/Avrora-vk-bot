from pathlib import Path

from pypdf import PdfReader
from pydantic import BaseModel


class PDFPage(BaseModel):
    """Текст одной страницы PDF с указанием её номера."""

    page_number: int
    text: str


class PDFDocument(BaseModel):
    """Извлечённый текст PDF-документа."""

    title: str
    source_url: str
    page_count: int
    pages: list[PDFPage]


def extract_pdf_text(
    pdf_path: str | Path,
    source_url: str,
    title: str = "Неизвестный документ",
) -> PDFDocument:
    """Извлекает текст PDF, сохраняя название и номера страниц."""
    path = Path(pdf_path)

    if not path.is_file():
        raise FileNotFoundError(f"PDF-файл не найден: {path}")

    reader = PdfReader(str(path))

    pages = [
        PDFPage(
            page_number=page_number,
            text=page.extract_text() or "",
        )
        for page_number, page in enumerate(reader.pages, start=1)
    ]

    return PDFDocument(
        title=title,
        source_url=source_url,
        page_count=len(pages),
        pages=pages,
    )
    