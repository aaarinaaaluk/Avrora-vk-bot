from enum import Enum

from pydantic import BaseModel, Field

from app.sources.text_search import SearchResult


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

def verify_claim(
    claim: str,
    search_results: list[SearchResult] | None = None,
) -> VerificationResult:
    evidence = [
        EvidenceItem(
            source_id=result.source_url,
            source_name=result.document_title,
            source_url=result.source_url,
            evidence_summary=(
                f"Найден фрагмент на странице {result.page_number}. "
                f"Совпавшие слова: {', '.join(result.matched_terms)}. "
                f"Текст: {result.text}"
            ),
            limitations=[
                "Фрагмент найден по совпадению слов.",
                "Содержание ещё не оценено на предмет подтверждения утверждения.",
            ],
        )
        for result in (search_results or [])
    ]

    return VerificationResult(
        claim=claim,
        status=VerificationStatus.INSUFFICIENT,
        confidence=ConfidenceLevel.LOW,
        explanation=(
            "Найдены фрагменты источников, но их содержание ещё не оценено. "
            "Совпадение слов не подтверждает медицинское утверждение. "
            "Для вывода необходимо проверить контекст и качество доказательств."
            if evidence
            else
            "Пока недостаточно проверенных доказательств для вывода. "
            "Необходимо найти подходящие источники и оценить их содержание."
        ),
        evidence=evidence,
    )
    