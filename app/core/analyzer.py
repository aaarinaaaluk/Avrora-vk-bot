from enum import Enum

from pydantic import BaseModel

from app.classifier.claim_type import (
    ClaimType,
    classify_claim_type,
)
from app.classifier.intent import (
    IntentType,
    classify_intent,
    is_risky_treatment_question,
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
        if is_risky_treatment_question(text):
            safety_message = (
                "Не отменяйте и не меняйте назначенные лекарства самостоятельно, даже если "
                "изменили питание. Обсудите любые изменения лечения с лечащим врачом. "
                "Если состояние резко ухудшилось или возникла тяжёлая реакция на лекарство, "
                "обратитесь за срочной медицинской помощью. Сервис не назначает и не отменяет лечение."
            )
        else:
            safety_message = (
                "Этот вопрос касается вашего здоровья или здоровья другого конкретного человека. "
                "Подходящий рацион и лечение зависят от индивидуальных обстоятельств. "
                "Обсудите выбор диеты с квалифицированным медицинским специалистом. "
                "Сервис не ставит диагнозы и не назначает лечение."
            )
        sources = []

    elif intent_result.intent == IntentType.GENERAL_QUESTION:
        if any(tag != ClaimType.UNCLEAR for tag in claim_result.tags):
            route = AnalysisRoute.EVIDENCE_SEARCH
            source_types = [
                tag.value
                for tag in claim_result.tags
                if tag != ClaimType.UNCLEAR
            ]
            sources = find_sources_by_claim_types(source_types)
        else:
            route = AnalysisRoute.GENERAL_INFORMATION
            sources = []

    elif intent_result.intent == IntentType.UNCLEAR:
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
