
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

def test_build_evidence_context_warns_about_keyword_matches():
    result = SearchResult(
        document_title="Клинические рекомендации",
        source_url="https://example.org/guideline.pdf",
        page_number=1,
        text="Текст для проверки.",
        matched_terms=["проверки"],
        score=1,
    )

    context = build_evidence_context([result])

    assert "совпадению слов" in context
    assert "не считаются подтверждёнными доказательствами" in context
    assert "Учитывай контекст и ограничения источника" in context

def test_evidence_assessment_defaults_to_uncertain():
    from app.core.llm import EvidenceAssessment

    assessment = EvidenceAssessment()

    assert assessment.relevant is False
    assert assessment.supports_claim is None
    assert assessment.limitations == []
    assert assessment.source_url is None
    assert assessment.page_number is None
    assert "Недостаточно данных" in assessment.explanation
