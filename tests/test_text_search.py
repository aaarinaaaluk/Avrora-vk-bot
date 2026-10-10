import pytest

from app.sources.pdf_reader import PDFDocument, PDFPage
from app.sources.text_search import search_document


@pytest.fixture
def sample_document():
    return PDFDocument(
        title="Тестовый документ",
        source_url="https://example.org/sample.pdf",
        page_count=3,
        pages=[
            PDFPage(
                page_number=1,
                text="Киста почки у детей. Общая информация.",
            ),
            PDFPage(
                page_number=2,
                text="Диагностика кисты почки включает обследование.",
            ),
            PDFPage(
                page_number=3,
                text="Рекомендации по наблюдению пациента.",
            ),
        ],
    )


def test_search_finds_matching_pages(sample_document):
    results = search_document(sample_document, "киста почки")

    assert [result.page_number for result in results] == [1, 2]
    assert results[0].score == 2
    assert results[0].matched_terms == ["киста", "почки"]
    assert results[0].document_title == "Тестовый документ"
    assert results[0].source_url == "https://example.org/sample.pdf"
    assert results[0].page_number == 1


def test_search_returns_empty_when_no_terms_match(sample_document):
    results = search_document(sample_document, "вакцинация")

    assert results == []


def test_search_respects_result_limit(sample_document):
    results = search_document(sample_document, "киста почки", limit=1)

    assert len(results) == 1
    assert results[0].page_number == 1


def test_search_rejects_invalid_limit(sample_document):
    with pytest.raises(ValueError):
        search_document(sample_document, "киста", limit=0)


def test_search_snippets_are_short_and_keep_word_boundaries(sample_document):
    results = search_document(sample_document, "киста почки")

    assert results
    for result in results:
        assert len(result.text) <= 230
        assert not result.text.startswith("…")
        assert not result.text.endswith("…")


def test_search_snippet_contains_matching_terms(sample_document):
    results = search_document(sample_document, "киста почки")

    assert "киста" in results[0].text.lower()
    assert "почки" in results[0].text.lower()
