"""Оркестрация поиска разрешённых источников и оценки GigaChat."""

import logging
import re

from app.core.llm import create_llm_client
from app.core.verifier import VerificationResult, verify_claim
from app.sources.document_search import search_documents
from app.sources.evidence import EvidenceRecord
from app.sources.factcheck_search import search_fact_checks
from app.sources.pubmed_search import search_pubmed
from app.sources.who_search import search_who_pages


def _pubmed_query_from_claim(claim: str, llm_client) -> str:
    """Преобразует русское утверждение в короткий поисковый запрос на английском.

    Перевод нужен только для поиска. Если GigaChat не ответил, исходное
    утверждение возвращается как резервный вариант; search_pubmed затем
    пробует несколько упрощённых вариантов запроса. Содержимое утверждения
    не записывается в логи.
    """
    if llm_client is None:
        logging.getLogger(__name__).warning(
            "GigaChat is not configured; PubMed will receive the original-language claim"
        )
        return claim
    prompt = (
        "Преобразуй медицинское утверждение ниже в короткий поисковый запрос "
        "на английском языке для PubMed. Сохрани ключевые медицинские понятия, "
        "не добавляй фактов и не оценивай утверждение. Верни только запрос, "
        "не более 12 слов. Не добавляй кавычки, пояснения или метки.\n\nУтверждение: "
        + claim[:1000]
    )
    logger = logging.getLogger(__name__)
    try:
        query = llm_client.generate(prompt).strip().strip('"\'`')
        query = re.sub(r"\s+", " ", query)
        # Reject an obviously untranslated output so it does not silently become
        # an ineffective PubMed query. The source search will still degrade safely.
        contains_latin = bool(re.search(r"[A-Za-z]", query))
        if query and len(query) <= 250 and "\n" not in query and contains_latin:
            return query
        logger.warning("GigaChat returned an unusable PubMed search translation")
    except Exception as exc:
        logger.warning("PubMed query translation failed (%s)", type(exc).__name__)
    return claim


def collect_evidence(claim: str, llm_client=None) -> tuple[list, list[EvidenceRecord]]:
    """Ищет локальные клинические рекомендации, PubMed и опционально Fact Check."""
    logger = logging.getLogger(__name__)
    local_results = []
    try:
        local_results = [
            result
            for result in search_documents(claim, limit=5)
            if len(result.matched_terms) >= 2
        ]
    except (OSError, ValueError) as exc:
        logger.warning("Local document search failed (%s)", type(exc).__name__)
        local_results = []

    translated_query = _pubmed_query_from_claim(claim, llm_client)
    external: list[EvidenceRecord] = []
    who_count = pubmed_count = fact_check_count = 0
    try:
        who_results = search_who_pages(claim, limit=2)
        who_count = len(who_results)
        external.extend(who_results)
    except Exception as exc:
        logger.warning("WHO search failed (%s)", type(exc).__name__)
    try:
        pubmed_results = search_pubmed(translated_query, limit=3)
        pubmed_count = len(pubmed_results)
        external.extend(pubmed_results)
    except Exception as exc:
        logger.warning("PubMed retrieval failed (%s)", type(exc).__name__)
    try:
        fact_check_results = search_fact_checks(claim, limit=3)
        fact_check_count = len(fact_check_results)
        external.extend(fact_check_results)
    except Exception as exc:
        logger.warning("Fact Check search failed (%s)", type(exc).__name__)

    # Убираем повторы URL и ограничиваем размер перед передачей модели.
    seen_urls = {item.source_url for item in local_results if item.source_url}
    deduplicated: list[EvidenceRecord] = []
    for item in external:
        if item.source_url in seen_urls:
            continue
        seen_urls.add(item.source_url)
        deduplicated.append(item)

    logger.info(
        "Evidence retrieval complete: local=%d WHO=%d PubMed=%d fact_check=%d external_unique=%d",
        len(local_results),
        who_count,
        pubmed_count,
        fact_check_count,
        len(deduplicated),
    )
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
