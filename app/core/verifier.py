```python
from enum import Enum

from pydantic import BaseModel, Field


class ClaimRequest(BaseModel):
    claim: str = Field(min_length=1, max_length=2000)


class VerificationStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EvidenceItem(BaseModel):
    source_id: str
    source_name: str
    source_url: str
    evidence_summary: str
    limitations: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    claim: str
    status: VerificationStatus
    confidence: ConfidenceLevel
    explanation: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


def verify_claim(claim: str) -> VerificationResult:
    return VerificationResult(
        claim=claim,
        status=VerificationStatus.INSUFFICIENT,
        confidence=ConfidenceLevel.LOW,
        explanation=(
            "Пока недостаточно проверенных доказательств для вывода. "
            "Необходимо найти подходящие источники и оценить их содержание."
        ),
        evidence=[],
    )
```
