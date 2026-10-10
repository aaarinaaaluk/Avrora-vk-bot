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
        