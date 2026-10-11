"""Поиск уже проверенных утверждений через Google Fact Check Tools API."""

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request

from app.config import GOOGLE_FACT_CHECK_API_KEY
from app.sources.evidence import EvidenceRecord

ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


def search_fact_checks(claim: str, limit: int = 3) -> list[EvidenceRecord]:
    """Возвращает найденные ClaimReview; индекс не считается абсолютной истиной."""
    claim = claim.strip()[:500]
    if not claim or not GOOGLE_FACT_CHECK_API_KEY or limit < 1:
        return []

    params = {
        "query": claim,
        "languageCode": "ru",
        "pageSize": str(min(limit, 5)),
        "key": GOOGLE_FACT_CHECK_API_KEY,
    }
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "AVRORA-medical-fact-checker/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return []

    records: list[EvidenceRecord] = []
    for claim_item in data.get("claims", []):
        claim_text = str(claim_item.get("text", "")).strip()
        for review in claim_item.get("claimReview", []):
            review_url = str(review.get("url", "")).strip()
            if not review_url.startswith("https://"):
                continue
            publisher = review.get("publisher") or {}
            publisher_name = publisher.get("name") or publisher.get("site") or "Издатель не указан"
            title = review.get("title") or "Проверка факта"
            rating = review.get("textualRating") or "Оценка не указана"
            reviewed_at = review.get("reviewDate") or None
            payload = "|".join([review_url, claim_text, rating])
            item_id = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
            excerpt = (
                f"Проверяемое утверждение в индексе: {claim_text or 'не указано'}\n"
                f"Заголовок проверки: {title}\n"
                f"Оценка автора проверки: {rating}\n"
                f"Издатель: {publisher_name}\n"
                f"Дата проверки: {reviewed_at or 'не указана'}\n"
                f"Ссылка на публикацию проверки: {review_url}"
            )
            records.append(
                EvidenceRecord(
                    evidence_id=f"factcheck:{item_id}",
                    source_id="google_fact_check_tools",
                    source_name=f"Google Fact Check Tools — {publisher_name}: {title}",
                    source_url=review_url,
                    excerpt=excerpt,
                    source_type="индекс ранее проверенных утверждений",
                    published_at=reviewed_at,
                    limitations=[
                        "API показывает только найденные ранее проверки; отсутствие результата не доказывает истинность утверждения.",
                        "Оценка принадлежит конкретному издателю и требует прочитать оригинальную публикацию и проверить контекст.",
                    ],
                )
            )
            if len(records) >= limit:
                return records
    return records
