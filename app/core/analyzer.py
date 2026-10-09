from enum import Enum

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


class AnalysisRoute(str, Enum):
    EVIDENCE_SEARCH = "EVIDENCE_SEARCH"
    GENERAL_INFORMATION = "GENERAL_INFORMATION"
    CLINICIAN_GUIDANCE = "CLINICIAN_GUIDANCE"


class AnalysisResult(BaseModel):
    text: str
    intent: IntentType
    intent_explanation: str
    claim_type: ClaimType
    claim_tags: list[ClaimType]
    claim_type_explanation: str
    route: AnalysisRoute
    safety_message: str | None = None
    candidate_sources: list[dict]


def analyze_query(text: str) -> AnalysisResult:
    """Классифицирует запрос и выбирает следующий шаг обработки."""
    intent_result = classify_intent(text)
    claim_result = classify_claim_type(text)

    safety_message = None

    if intent_result.intent == IntentType.PERSONAL_MEDICAL:
        route = AnalysisRoute.CLINICIAN_GUIDANCE
        safety_message = (
            "Этот вопрос касается вашего личного здоровья. "
            "Подходящий рацион зависит от индивидуальных обстоятельств. "
            "Обсудите выбор диеты с квалифицированным медицинским специалистом. "
            "Сервис не ставит диагнозы и не назначает лечение."
        )
        sources = []

    elif intent_result.intent in (
        IntentType.GENERAL_QUESTION,
        IntentType.UNCLEAR,
    ):
        route = AnalysisRoute.GENERAL_INFORMATION
        sources = []

    else:
        route = AnalysisRoute.EVIDENCE_SEARCH
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
        route=route,
        safety_message=safety_message,
        candidate_sources=sources,
    )
