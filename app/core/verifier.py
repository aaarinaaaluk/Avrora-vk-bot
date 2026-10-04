from pydantic import BaseModel


class ClaimRequest(BaseModel):
    claim: str


class VerificationResult(BaseModel):
    claim: str
    status: str
    confidence: str
    explanation: str


def verify_claim(claim: str) -> VerificationResult:
    return VerificationResult(
        claim=claim,
        status="INSUFFICIENT",
        confidence="LOW",
        explanation="Для проверки необходимо сопоставить утверждение с одобренными медицинскими источниками."
    )
