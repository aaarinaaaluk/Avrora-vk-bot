
from app.core.llm import MockLLMClient


def test_mock_llm_returns_test_response():
    client = MockLLMClient()

    result = client.generate("Проверь медицинское утверждение")

    assert "тестовый ответ" in result
    assert "не является медицинским доказательством" in result


def test_mock_llm_does_not_depend_on_prompt():
    client = MockLLMClient()

    first_result = client.generate("Первый запрос")
    second_result = client.generate("Совершенно другой запрос")

    assert first_result == second_result

from app.core.llm import build_evidence_context
from app.sources.text_search import SearchResult


def test_build_evidence_context_preserves_source_details():
    result = SearchResult(
        document_title="Клинические рекомендации",
        source_url="https://example.org/guideline.pdf",
        page_number=12,
        text="Фрагмент медицинского документа.",
        matched_terms=["документ"],
        score=1,
    )

    context = build_evidence_context([result])

    assert "Клинические рекомендации" in context
    assert "https://example.org/guideline.pdf" in context
    assert "Страница: 12" in context
    assert "Фрагмент медицинского документа." in context


def test_build_evidence_context_handles_empty_results():
    context = build_evidence_context([])

    assert "не найдены" in context
