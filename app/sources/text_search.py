import re

from pydantic import BaseModel

from app.sources.pdf_reader import PDFDocument


class SearchResult(BaseModel):
    page_number: int
    text: str
    matched_terms: list[str]
    score: int


def extract_snippet(text: str, terms: set[str], window: int = 220) -> str:
    """Возвращает короткий фрагмент вокруг найденного слова."""
    if not text.strip():
        return ""

    words = list(re.finditer(r"\w+", text))
    matching_positions = [
        match.start()
        for match in words
        if match.group(0).lower() in terms
    ]

    if not matching_positions:
        return text[:window].strip()

    position = matching_positions[0]
    start = max(0, position - window // 2)
    end = min(len(text), position + window // 2)

    # Сдвигаем начало до границы слова.
    if start > 0:
        while start < len(text) and text[start].isalnum():
            start += 1
        while start < len(text) and not text[start].isalnum():
            start += 1

    # Сдвигаем конец до границы слова.
    if end < len(text):
        while end > start and text[end - 1].isalnum():
            end -= 1

    snippet = text[start:end].strip()

    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet += "…"

    return snippet


def search_document(
    document: PDFDocument,
    query: str,
    limit: int = 5,
) -> list[SearchResult]:
    """Ищет совпадения по словам и возвращает фрагменты с номерами страниц."""
    if limit < 1:
        raise ValueError("limit должен быть не меньше 1")

    terms = {
        word.lower()
        for word in re.findall(r"\w+", query.lower())
        if len(word) > 2
    }

    if not terms:
        return []

    results = []

    for page in document.pages:
        page_words = {
            word.lower()
            for word in re.findall(r"\w+", page.text.lower())
        }
        matched = sorted(terms.intersection(page_words))

        if matched:
            results.append(
                SearchResult(
                    page_number=page.page_number,
                    text=extract_snippet(page.text, set(matched)),
                    matched_terms=matched,
                    score=len(matched),
                )
            )

    results.sort(key=lambda item: (-item.score, item.page_number))
    return results[:limit]
