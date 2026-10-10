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
   