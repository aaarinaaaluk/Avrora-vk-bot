
from pathlib import Path

from app.sources.pdf_reader import extract_pdf_text
from app.sources.text_search import SearchResult, search_document


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"

SOURCE_URLS = {
    "Недостаточность_витамина_D_Рахит.pdf":
        "https://cr.minzdrav.gov.ru/view-cr/1059_1",
}


def search_documents(
    query: str,
    limit: int = 5,
) -> list[SearchResult]:
    """Ищет совпадения в PDF из data/documents."""
    if limit < 1:
        raise ValueError("limit должен быть не меньше 1")

    if not DOCUMENTS_DIR.is_dir():
        return []

    results: list[SearchResult] = []

    for pdf_path in sorted(DOCUMENTS_DIR.glob("*.pdf")):
        source_url = SOURCE_URLS.get(pdf_path.name)
        # Локальные документы участвуют в проверке только если источник
        # явно зарегистрирован в allowlist выше. Неизвестный PDF пропускается.
        if not source_url:
            continue

        document = extract_pdf_text(
            pdf_path,
            source_url=source_url,
            title=pdf_path.stem.replace("_", " "),
        )

        results.extend(
            search_document(
                document,
                query,
                limit=limit,
            )
        )

    results.sort(
        key=lambda item: (-item.score, item.page_number)
    )

    return results[:limit]
