from app.core.verifier import (
    ClaimRequest,
    ConfidenceLevel,
    VerificationStatus,
    verify_claim,
)


def test_verify_claim_without_evidence_returns_insufficient():
    result = verify_claim("Витамин C лечит простуду")

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert result.evidence == []


def test_verify_claim_preserves_original_claim():
    claim = "Витамин C лечит простуду"

    result = verify_claim(claim)

    assert result.claim == claim


def test_claim_request_rejects_empty_claim():
    from pydantic import ValidationError

    import pytest

    with pytest.raises(ValidationError):
        ClaimRequest(claim="")


def test_claim_request_rejects_claim_over_2000_characters():
    from pydantic import ValidationError

    import pytest

    with pytest.raises(ValidationError):
        ClaimRequest(claim="а" * 2001)

def test_verify_claim_does_not_invent_evidence():
    result = verify_claim(
        "Витамин C гарантированно предотвращает простуду"
    )

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert result.evidence == []
    assert "недостаточно" in result.explanation.lower()

def test_verify_claim_preserves_search_results_without_confirming_claim():
    from app.sources.text_search import SearchResult

    search_result = SearchResult(
        document_title="Клинические рекомендации",
        source_url="https://example.org/guideline.pdf",
        page_number=12,
        text="Фрагмент найден по совпадению слов.",
        matched_terms=["витамин", "простуда"],
        score=2,
    )

    result = verify_claim(
        "Витамин C предотвращает простуду",
        search_results=[search_result],
    )

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert len(result.evidence) == 1
    assert result.evidence[0].source_url == (
        "https://example.org/guideline.pdf"
    )
    assert result.evidence[0].source_name == "Клинические рекомендации"
    assert "странице 12" in result.evidence[0].evidence_summary
    assert result.evidence[0].limitations


def test_verifier_uses_model_only_with_real_evidence_and_known_evidence_ids():
    from app.sources.text_search import SearchResult

    class FakeLLM:
        def generate(self, prompt):
            assert "Разрешённые доказательные фрагменты" in prompt
            return (
                '{"status":"SUPPORTED","confidence":"HIGH",'
                '"explanation":"Фрагмент поддерживает утверждение.",'
                '"assessments":[{"evidence_id":"local:1",'
                '"supports_claim":true,"summary":"поддерживает",'
                '"limitations":[]}]}'
            )

    source = SearchResult(
        document_title="Клинические рекомендации",
        source_url="https://cr.minzdrav.gov.ru/example",
        page_number=5,
        text="В документе содержится релевантная рекомендация.",
        matched_terms=["документ", "рекомендация"],
        score=2,
    )
    result = verify_claim(
        "Проверяемое утверждение",
        search_results=[source],
        llm_client=FakeLLM(),
    )

    assert result.status == VerificationStatus.SUPPORTED
    assert result.confidence == ConfidenceLevel.MEDIUM  # один фрагмент: не HIGH
    assert result.evidence[0].supports_claim is True
    assert result.evidence[0].source_url == source.source_url


def test_verifier_rejects_model_verdict_with_unknown_source_id():
    from app.sources.text_search import SearchResult

    class FakeLLM:
        def generate(self, prompt):
            return (
                '{"status":"SUPPORTED","confidence":"HIGH",'
                '"explanation":"якобы подтверждено",'
                '"assessments":[{"evidence_id":"invented-source",'
                '"supports_claim":true,"summary":"фальшивый источник",'
                '"limitations":[]}]}'
            )

    source = SearchResult(
        document_title="Исходный документ",
        source_url="https://example.org/source",
        page_number=1,
        text="Текст фрагмента.",
        matched_terms=["фрагмент", "текст"],
        score=2,
    )
    result = verify_claim("Утверждение", search_results=[source], llm_client=FakeLLM())

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert result.evidence[0].supports_claim is None

def test_parse_model_json_accepts_trailing_text():
    from app.core.verifier import _parse_model_json

    raw = (
        '{"status":"INSUFFICIENT","confidence":"LOW",'
        '"explanation":"Недостаточно данных","assessments":[]} '
        'Пояснение после JSON'
    )
    result = _parse_model_json(raw)
    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW


def test_parse_model_json_rejects_multiple_verdicts():
    import pytest
    from app.core.verifier import _parse_model_json

    raw = (
        '{"status":"INSUFFICIENT","confidence":"LOW",'
        '"explanation":"Недостаточно данных","assessments":[]} '
        '{"status":"SUPPORTED","confidence":"HIGH",'
        '"explanation":"Подтверждено","assessments":[]}'
    )
    with pytest.raises(ValueError, match="несколько JSON-объектов"):
        _parse_model_json(raw)
