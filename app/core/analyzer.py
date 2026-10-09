
from pydantic import BaseModel

from app.classifier.claim_type import (
    ClaimType,
    classify_claim_type,
)
from app.classifier.intent import (
    IntentType,
    classify_intent,
)
from app.core.source_catalog import find_sources_by_claim_types


class AnalysisResult(BaseModel):
    text: str
    intent: IntentType
    intent_explanation: str
    claim_type: ClaimType
    claim_tags: list[ClaimType]
    claim_type_explanation: str
    candidate_sources: list[dict]


def analyze_query(text: str) -> AnalysisResult:
    """Выполняет предварительный анализ запроса без медицинского вердикта."""
    intent_result = classify_intent(text)
    claim_result = classify_claim_type(text)

    # Личные медицинские запросы не направляем в обычный подбор источников.
    if intent_result.intent == IntentType.PERSONAL_MEDICAL:
        sources = []
    else:
        source_types = [
            tag.value
            for tag in claim_result.tags
            if tag != ClaimType.UNCLEAR
        ]
        sources = find_sources_by_claim_types(source_types)

    return AnalysisResult(
        text=text,
        intent=intent_result.intent,
        intent_explanation=intent_result.explanation,
        claim_type=claim_result.claim_type,
        claim_tags=claim_result.tags,
        claim_type_explanation=claim_result.explanation,
        candidate_sources=sources,
    )
