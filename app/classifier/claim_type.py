
from enum import Enum

from pydantic import BaseModel


class ClaimType(str, Enum):
    COMPARATIVE = "COMPARATIVE"
    CAUSAL = "CAUSAL"
    EFFECTIVENESS = "EFFECTIVENESS"
    SAFETY = "SAFETY"
    QUANTITATIVE = "QUANTITATIVE"
    GENERAL = "GENERAL"
    UNCLEAR = "UNCLEAR"


class ClaimTypeResult(BaseModel):
    text: str
    claim_type: ClaimType
    tags: list[ClaimType]
    explanation: str


def classify_claim_type(text: str) -> ClaimTypeResult:
    normalized = text.lower().strip()

    if not normalized:
        return ClaimTypeResult(
            text=text,
            claim_type=ClaimType.UNCLEAR,
            tags=[ClaimType.UNCLEAR],
            explanation="Не удалось определить тип: текст пустой."
        )

    detected = []

    comparative_markers = (
        "эффективнее", "лучше, чем", "хуже, чем",
        "по сравнению с", "в отличие от", "превосходит",
        "не уступает", "сравнение", "более эффективн",
        "менее эффективн"
    )

    safety_markers = (
        "опасен", "опасна", "опасно", "побочн",
        "осложнен", "осложнён", "вред", "противопоказан",
        "вызывает осложнения", "безопас"
    )

    effectiveness_markers = (
        "эффективен", "эффективна", "эффективно",
        "эффективнее", "помогает похудеть", "снижает вес",
        "улучшает", "уменьшает симптомы",
        "способствует снижению"
    )

    causal_markers = (
        "приводит к", "ведёт к", "ведет к",
        "вызывает", "повышает риск",
        "снижает риск", "из-за", "в результате"
    )

    quantitative_markers = (
        "процентов", "%", "кг за", "раза в",
        "в два раза", "на 5 кг", "на 10 кг"
    )

    if any(marker in normalized for marker in comparative_markers):
        detected.append(ClaimType.COMPARATIVE)

    if any(marker in normalized for marker in safety_markers):
        detected.append(ClaimType.SAFETY)

    if any(marker in normalized for marker in effectiveness_markers):
        detected.append(ClaimType.EFFECTIVENESS)

    if any(marker in normalized for marker in causal_markers):
        detected.append(ClaimType.CAUSAL)

    if any(marker in normalized for marker in quantitative_markers):
        detected.append(ClaimType.QUANTITATIVE)

    if not detected:
        if normalized.endswith("?"):
            return ClaimTypeResult(
                text=text,
                claim_type=ClaimType.UNCLEAR,
                tags=[ClaimType.UNCLEAR],
                explanation=(
                    "Вопрос сам по себе не определяет тип "
                    "проверяемого утверждения."
                )
            )

        detected.append(ClaimType.GENERAL)

    primary_type = detected[0]

    return ClaimTypeResult(
        text=text,
        claim_type=primary_type,
        tags=detected,
        explanation="Определены смысловые признаки текста по ключевым словам."
    )