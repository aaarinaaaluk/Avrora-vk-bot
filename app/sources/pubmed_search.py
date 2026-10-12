"""Поиск аннотаций PubMed через официальный NCBI E-utilities API."""

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

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


def _meaningful_terms(text: str) -> set[str]:
    """Выделяет содержательные слова для предварительной проверки релевантности."""
    tokens = re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
    return {
        token
        for token in tokens
        if (len(token) >= 3 or token.isdigit()) and token not in _STOP_WORDS
    }


def _get_text(url: str, timeout: int = 8) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/xml"}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


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
    """Подготавливает более широкие варианты запроса для повторного поиска.

    Первый запрос сохраняется без изменений. Если PubMed не находит статьи,
    второй запрос оставляет основные предметные термины, убирая слова о связи,
    эффекте и риске: они часто чрезмерно сужают автоматический поиск.
    """
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

    # Third fallback: keep the first few informative terms. This is useful when
    # a translation includes many terms and PubMed's implicit AND is too strict.
    if len(compact_tokens) > 4:
        short = " ".join(compact_tokens[:4])
        if len(_meaningful_terms(short)) >= 2 and all(
            short.casefold() != existing.casefold() for existing in variants
        ):
            variants.append(short)

    return variants[:3]


def _fetch_pubmed_articles(query: str, limit: int) -> list[ET.Element]:
    """Executes one ESearch/EFetch attempt. Network errors are handled by caller."""
    params: dict[str, str] = {
        "db": "pubmed",
        "term": query,
        # Fetch more than the final output limit so the relevance filter does not
        # accidentally discard the only useful result from the first few hits.
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

    fetch_params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
    }
    if NCBI_API_KEY:
        fetch_params["api_key"] = NCBI_API_KEY
    fetch_url = f"{BASE_URL}/efetch.fcgi?{urllib.parse.urlencode(fetch_params)}"
    root = ET.fromstring(_get_text(fetch_url))
    return root.findall(".//PubmedArticle")


def search_pubmed(query: str, limit: int = 3) -> list[EvidenceRecord]:
    """Возвращает заголовки и аннотации PubMed; сбой сети не ломает бота.

    Делает до трёх попыток: перевод модели, упрощённая фраза и короткий набор
    ключевых терминов. Ошибки журналируются без текста медицинского запроса.
    """
    query = query.strip()[:500]
    if not query or limit < 1:
        return []

    variants = _query_variants(query)
    if not variants:
        return []

    records: list[EvidenceRecord] = []
    seen_pmids: set[str] = set()
    for attempt, search_query in enumerate(variants, start=1):
        query_terms = _meaningful_terms(search_query)
        if not query_terms:
            continue
        try:
            articles = _fetch_pubmed_articles(search_query, limit)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, ET.ParseError, KeyError, TypeError) as exc:
            logger.warning(
                "PubMed search attempt %d failed (%s)",
                attempt,
                type(exc).__name__,
            )
            continue
        except Exception as exc:
            # An unexpected PubMed response should not interrupt VK message handling.
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
                if title_node is not None
                else "Без названия"
            )
            abstract_parts: list[str] = []
            for part in article.findall(".//Abstract/AbstractText"):
                text = " ".join("".join(part.itertext()).split())
                label = part.attrib.get("Label")
                if text:
                    abstract_parts.append(f"{label}: {text}" if label else text)
            abstract = " ".join(abstract_parts).strip()
            if not pmid or pmid in seen_pmids or not (title or abstract):
                continue

            article_terms = _meaningful_terms(f"{title} {abstract}")
            minimum_overlap = min(2, len(query_terms))
            if len(query_terms.intersection(article_terms)) < minimum_overlap:
                continue

            date_node = article.find(".//PubDate")
            published_at = " ".join(date_node.itertext()).strip() if date_node is not None else None
            excerpt = f"Заголовок: {title}\nАннотация: {abstract or 'Аннотация не представлена.'}"
            records.append(
                EvidenceRecord(
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
            )
            seen_pmids.add(pmid)
            accepted_this_attempt += 1
            if len(records) >= limit:
                break

        logger.info(
            "PubMed attempt %d completed: article_candidates=%d accepted=%d",
            attempt,
            len(articles),
            accepted_this_attempt,
        )
        if len(records) >= limit:
            break

    if not records:
        logger.warning("PubMed search completed without relevant article abstracts")
    return records[:limit]
