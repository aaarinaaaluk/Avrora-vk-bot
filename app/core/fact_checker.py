"""Оркестрация поиска разрешённых источников и оценки GigaChat."""

import logging
import re

from app.core.llm import create_llm_client
from app.core.verifier import VerificationResult, verify_claim
from app.sources.document_search import search_documents
from app.sources.evidence import EvidenceRecord
from app.sources.factcheck_search import search_fact_checks
from app.sources.pubmed_search import search_pubmed


def _pubmed_query_from_claim(claim: str, llm_client) -> str:
    """Преобразует русское утверждение в поисковую фразу на английском.

    Это вспомогательный поисковый запрос, а не оценка истинности. Если модель
    недоступна или вернула слишком большой ответ, используется исходный текст.
    """
    if llm_client is None:
        return claim
    prompt = (
        "Преобразуй медицинское утверждение ниже в короткий поисковый запрос "
        "на английском языке для PubMed. Сохрани ключевые медицинские понятия, "
        "не добавляй фактов и не оценивай утверждение. Верни только запрос, "
        "не более 12 слов.\n\nУтверждение: " + claim[:1000]
    )
    try:
        query = llm_client.generate(prompt).strip().strip('"\'`')
        query = re.sub(r"\s+", " ", query)
        if query and len(query) <= 250 and "\n" not in query:
            return query
    except Exception:
        pass
    return claim


def collect_evidence(claim: str, llm_client=None) -> tuple[list, list[EvidenceRecord]]:
    """Ищет локальные клинические рекомендации, PubMed и опционально Fact Check."""
    local_results = []
    try:
        local_results = [
            result
            for result in search_documents(claim, limit=5)
            if len(result.matched_terms) >= 2
        ]
    except (OSError, ValueError):
        local_results = []

    translated_query = _pubmed_query_from_claim(claim, llm_client)
    external: list[EvidenceRecord] = []
    try:
        external.extend(search_pubmed(translated_query, limit=3))
    except Exception:
        pass
    try:
        external.extend(search_fact_checks(claim, limit=3))
    except Exception:
        pass

    # Убираем повторы URL и ограничиваем размер перед передачей модели.
    seen_urls = {item.source_url for item in local_results if item.source_url}
    deduplicated: list[EvidenceRecord] = []
    for item in external:
        if item.source_url in seen_urls:
            continue
        seen_urls.add(item.source_url)
        deduplicated.append(item)
    return local_results[:3], deduplicated[:6]


def check_claim(claim: str) -> VerificationResult:
    """Полная проверка: сбор источников, оценка модели, безопасный fallback."""
    client = create_llm_client()
    local_results, external_results = collect_evidence(claim, llm_client=client)
    result = verify_claim(
        claim,
        search_results=local_results,
        external_evidence=external_results,
        llm_client=client,
    )

    if client is not None:
        usage = client.usage_snapshot()
        if usage["calls"] > 0:
            logging.getLogger(__name__).info(
                "GigaChat usage: calls=%d prompt_tokens=%d "
                "completion_tokens=%d total_tokens=%d",
                usage["calls"],
                usage["prompt_tokens"],
                usage["completion_tokens"],
                usage["total_tokens"],
            )

    return result
