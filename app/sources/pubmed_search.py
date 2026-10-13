"""Поиск и первичная фильтрация аннотаций PubMed через NCBI E-utilities."""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from app.config import NCBI_API_KEY, NCBI_EMAIL
from app.sources.evidence import EvidenceRecord

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
USER_AGENT = "AVRORA-medical-fact-checker/1.0 (evidence retrieval)"
logger = logging.getLogger(__name__)


_STOP_WORDS = {
    "the", "and", "for", "from", "with", "that", "this", "into",
    "are", "was", "were", "been", "being", "has", "have", "had",
    "but", "about", "after", "before", "than", "then",
    "one", "once", "time", "test", "message", "response", "respond",
    "reply", "please", "check", "claim", "statement", "avrora",
    "его", "это", "как", "для", "или", "при", "что", "этот",
}

# Эти слова часто встречаются в самых разных медицинских статьях и сами по
# себе не являются доказательством тематической релевантности публикации.
_TOPIC_GENERIC_TERMS = {
    "who", "study", "studies", "review", "systematic", "meta", "analysis",
    "research", "article", "publication", "human", "humans", "adult", "adults",
    "patient", "patients", "population", "risk", "effect", "effects", "impact",
    "association", "associated", "health", "disease", "diseases", "disorder",
    "disorders", "treatment", "therapy", "diet", "dietary", "nutrition", "intake",
    "outcome", "outcomes", "benefit", "benefits", "clinical", "trial", "trials",
    "use", "using", "long", "term", "evidence", "result", "results",
    "риск", "заболевание", "заболевания", "болезнь", "болезни", "исследование",
    "исследования", "эффект", "эффекты", "польза", "здоровье", "пациенты",
    "люди", "человек", "лечение", "диета", "питание", "рацион", "влияние",
    "результат", "результаты", "взрослые", "риск", "связь",
}


@dataclass(frozen=True)
class PubMedSearchOutcome:
    """Результат поиска с отличием пустой выдачи от технического сбоя."""

    records: list[EvidenceRecord]
    status: str  # ok | no_results | unavailable | invalid_query
    attempts: int = 0
    failed_attempts: int = 0


def _meaningful_terms(text: str) -> set[str]:
    """Выделяет содержательные слова для предварительной проверки релевантности."""
    tokens = re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
    return {
        token
        for token in tokens
        if (len(token) >= 3 or token.isdigit()) and token not in _STOP_WORDS
    }


def _topic_terms(text: str) -> set[str]:
    """Выделяет предметные термины, убирая широкие слова о здоровье и исследованиях."""
    terms = _meaningful_terms(text)
    topic_terms = {
        term for term in terms
        if term not in _TOPIC_GENERIC_TERMS
        and not (term.isdigit() and len(term) == 4 and term.startswith(("19", "20")))
    }
    # Оставляем совместимость с короткими/синтетическими запросами: для
    # реальных утверждений предпочтительны два предметных термина, но тесты
    # и короткие поиски не должны превращаться в техническую ошибку.
    return topic_terms or terms


# Keep below NCBI's published rate limits even when several requests arrive
# close together. The lock is process-wide; for multi-worker deployments, set
# one worker or use a shared limiter if strict global pacing is required.
_RATE_LIMIT_LOCK = threading.Lock()
_LAST_REQUEST_STARTED = 0.0
_MIN_REQUEST_INTERVAL_WITH_KEY = 0.15  # ~6.7 requests/second
_MIN_REQUEST_INTERVAL_WITHOUT_KEY = 0.40  # ~2.5 requests/second
_RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}
_MAX_HTTP_ATTEMPTS = 3


def _wait_for_request_slot() -> None:
    """Pace E-utilities calls below NCBI's per-key/IP request limit."""
    global _LAST_REQUEST_STARTED
    interval = (
        _MIN_REQUEST_INTERVAL_WITH_KEY
        if NCBI_API_KEY
        else _MIN_REQUEST_INTERVAL_WITHOUT_KEY
    )
    with _RATE_LIMIT_LOCK:
        now = time.monotonic()
        delay = _LAST_REQUEST_STARTED + interval - now
        if delay > 0:
            time.sleep(delay)
        _LAST_REQUEST_STARTED = time.monotonic()


def _retry_delay(exc: urllib.error.HTTPError, attempt: int) -> float:
    """Return a bounded Retry-After delay or exponential fallback."""
    retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            return min(15.0, max(0.0, float(retry_after)))
        except (TypeError, ValueError):
            pass
    return min(8.0, 2.0 ** attempt)


def _get_text(url: str, timeout: int = 8) -> str:
    """Fetch NCBI content with pacing and bounded retries for transient failures."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/xml"}
    request = urllib.request.Request(url, headers=headers)

    for attempt in range(_MAX_HTTP_ATTEMPTS):
        _wait_for_request_slot()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE_HTTP_CODES or attempt + 1 >= _MAX_HTTP_ATTEMPTS:
                raise
            delay = _retry_delay(exc, attempt)
            logger.warning(
                "NCBI E-utilities returned HTTP %s; retrying request (%d/%d) after %.1fs",
                exc.code, attempt + 1, _MAX_HTTP_ATTEMPTS - 1, delay,
            )
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt + 1 >= _MAX_HTTP_ATTEMPTS:
                raise
            delay = min(4.0, 2.0 ** attempt)
            logger.warning(
                "NCBI E-utilities request failed (%s); retrying request (%d/%d) after %.1fs",
                type(exc).__name__, attempt + 1, _MAX_HTTP_ATTEMPTS - 1, delay,
            )
            time.sleep(delay)

    raise RuntimeError("NCBI E-utilities request failed after retries")


_QUERY_ACTION_TERMS = {
    "reduce", "reduces", "reduced", "reducing", "lower", "lowers",
    "lowered", "decrease", "decreases", "decreased", "decreasing",
    "increase", "increases", "increased", "increasing", "risk",
    "prevent", "prevents", "prevented", "prevention", "effect", "effects",
    "impact", "benefit", "benefits", "associated", "association",
    "relationship", "relationships", "improve", "improves", "improved",
    "improvement", "significant", "significantly", "may", "might",
    "can", "could", "show", "shows", "shown", "demonstrate",
    "demonstrates", "demonstrated", "suggest", "suggests", "suggested",
    "the", "and", "for", "from", "with", "that", "this", "into",
    "are", "was", "were", "been", "being", "has", "have", "had",
    "but", "about", "after", "before", "than", "then", "of", "on",
}


def _query_variants(query: str) -> list[str]:
    """Подготавливает широкие варианты запроса, не меняя их смысловые якоря."""
    primary = re.sub(r"\s+", " ", query).strip().strip('"\'`')
    variants: list[str] = []
    if primary:
        variants.append(primary)

    tokens = re.findall(r"[^\W_]+", primary, flags=re.UNICODE)
    compact_tokens = [
        token for token in tokens
        if token.casefold() not in _QUERY_ACTION_TERMS
        and token.casefold() not in _STOP_WORDS
    ]
    compact = " ".join(compact_tokens).strip()
    if len(_meaningful_terms(compact)) >= 2 and compact.casefold() != primary.casefold():
        variants.append(compact)

    if len(compact_tokens) > 4:
        short = " ".join(compact_tokens[:4])
        if len(_meaningful_terms(short)) >= 2 and all(
            short.casefold() != existing.casefold() for existing in variants
        ):
            variants.append(short)

    return variants[:3]


def _fetch_pubmed_articles(query: str, limit: int) -> list[ET.Element]:
    """Выполняет одну пару ESearch/EFetch. Сетевые ошибки обрабатывает вызывающий код."""
    params: dict[str, str] = {
        "db": "pubmed",
        "term": query,
        "retmax": str(min(max(limit * 4, 10), 20)),
        "retmode": "json",
        "sort": "relevance",
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    if NCBI_EMAIL:
        params["email"] = NCBI_EMAIL
    search_url = f"{BASE_URL}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    search_data = json.loads(_get_text(search_url))
    ids = search_data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []

    fetch_params = {"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}
    if NCBI_API_KEY:
        fetch_params["api_key"] = NCBI_API_KEY
    fetch_url = f"{BASE_URL}/efetch.fcgi?{urllib.parse.urlencode(fetch_params)}"
    root = ET.fromstring(_get_text(fetch_url))
    return root.findall(".//PubmedArticle")


def search_pubmed_with_status(query: str, limit: int = 3) -> PubMedSearchOutcome:
    """Ищет PubMed и различает пустую выдачу от неудавшегося обращения к API."""
    query = query.strip()[:500]
    if not query or limit < 1:
        return PubMedSearchOutcome(records=[], status="invalid_query")

    variants = _query_variants(query)
    if not variants:
        return PubMedSearchOutcome(records=[], status="invalid_query")

    # Сначала сохраняем лучший результат для каждого PMID. Источники с
    # совпадением только по общим словам (risk/disease/health/diet/WHO) отсекаются.
    scored_records: dict[str, tuple[int, EvidenceRecord]] = {}
    successful_attempts = 0
    failed_attempts = 0
    rate_limited = False

    for attempt, search_query in enumerate(variants, start=1):
        query_terms = _topic_terms(search_query)
        generic_fallback_query = query_terms.issubset(_TOPIC_GENERIC_TERMS)
        try:
            articles = _fetch_pubmed_articles(search_query, limit)
            successful_attempts += 1
        except urllib.error.HTTPError as exc:
            failed_attempts += 1
            logger.warning(
                "PubMed search attempt %d failed (HTTP %s)", attempt, exc.code
            )
            if exc.code == 429:
                # The HTTP layer already made bounded retries. Do not immediately
                # hammer E-utilities with compact/short variants after a rate limit.
                rate_limited = True
                logger.warning("Stopping PubMed query variants after HTTP 429")
                break
            continue
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, ET.ParseError, KeyError, TypeError) as exc:
            failed_attempts += 1
            logger.warning(
                "PubMed search attempt %d failed (%s)", attempt, type(exc).__name__
            )
            continue
        except Exception as exc:
            failed_attempts += 1
            logger.warning(
                "PubMed search attempt %d failed unexpectedly (%s)",
                attempt,
                type(exc).__name__,
            )
            continue

        accepted_this_attempt = 0
        for article in articles:
            pmid = (article.findtext(".//PMID") or "").strip()
            article_node = article.find(".//Article")
            title_node = article_node.find(".//ArticleTitle") if article_node is not None else None
            title = (
                " ".join("".join(title_node.itertext()).split())
                if title_node is not None else "Без названия"
            )
            abstract_parts: list[str] = []
            for part in article.findall(".//Abstract/AbstractText"):
                text = " ".join("".join(part.itertext()).split())
                label = part.attrib.get("Label")
                if text:
                    abstract_parts.append(f"{label}: {text}" if label else text)
            abstract = " ".join(abstract_parts).strip()
            if not pmid or not (title or abstract):
                continue

            if generic_fallback_query:
                title_terms = _meaningful_terms(title)
                article_terms = _meaningful_terms(f"{title} {abstract}")
            else:
                title_terms = _topic_terms(title)
                article_terms = _topic_terms(f"{title} {abstract}")
            overlap = query_terms.intersection(article_terms)
            minimum_overlap = min(2, len(query_terms))
            if len(overlap) < minimum_overlap:
                continue

            # Предпочитаем результаты, где предметные термины есть уже в названии.
            # Это особенно важно для утверждений с конкретным исходом/болезнью.
            score = 3 * len(query_terms.intersection(title_terms)) + len(overlap)
            date_node = article.find(".//PubDate")
            published_at = " ".join(date_node.itertext()).strip() if date_node is not None else None
            excerpt = f"Заголовок: {title}\nАннотация: {abstract or 'Аннотация не представлена.'}"
            record = EvidenceRecord(
                evidence_id=f"pubmed:{pmid}",
                source_id="pubmed",
                source_name=f"PubMed: {title}",
                source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                excerpt=excerpt[:5000],
                source_type="научная публикация / аннотация",
                published_at=published_at or None,
                limitations=[
                    "Часто доступна только аннотация, а не полный текст статьи.",
                    "Поиск не заменяет оценку дизайна исследования, систематических ошибок и совокупности доказательств.",
                ],
            )
            existing = scored_records.get(pmid)
            if existing is None or score > existing[0]:
                scored_records[pmid] = (score, record)
            accepted_this_attempt += 1

        logger.info(
            "PubMed attempt %d completed: article_candidates=%d accepted=%d",
            attempt,
            len(articles),
            accepted_this_attempt,
        )
        if len(scored_records) >= limit:
            break

    ranked_records = [pair[1] for pair in sorted(
        scored_records.values(), key=lambda pair: (-pair[0], pair[1].source_name)
    )]
    if ranked_records:
        status = "ok"
        logger.info("PubMed retrieval completed with %d relevant abstracts", len(ranked_records))
        logger.info(
            "PubMed selected evidence IDs: %s",
            [record.evidence_id for record in ranked_records[:limit]],
        )
    elif rate_limited or not successful_attempts:
        status = "unavailable"
        logger.warning(
            "PubMed retrieval unavailable: rate_limited=%s failed_attempts=%d",
            rate_limited, failed_attempts,
        )
    elif successful_attempts:
        status = "no_results"
        logger.info("PubMed search completed successfully but found no relevant abstracts")
    else:
        status = "unavailable"
        logger.warning(
            "PubMed retrieval unavailable: all %d search attempts failed", failed_attempts
        )
    return PubMedSearchOutcome(
        records=ranked_records[:limit],
        status=status,
        attempts=successful_attempts + failed_attempts,
        failed_attempts=failed_attempts,
    )


def search_pubmed(query: str, limit: int = 3) -> list[EvidenceRecord]:
    """Обратносуместимая обёртка: возвращает только записи PubMed."""
    return search_pubmed_with_status(query, limit=limit).records
