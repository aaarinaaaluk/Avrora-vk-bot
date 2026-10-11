"""Поиск аннотаций PubMed через официальный NCBI E-utilities API."""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from app.config import NCBI_API_KEY, NCBI_EMAIL
from app.sources.evidence import EvidenceRecord

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
USER_AGENT = "AVRORA-medical-fact-checker/1.0 (evidence retrieval)"


def _get_text(url: str, timeout: int = 8) -> str:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/xml"}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def search_pubmed(query: str, limit: int = 3) -> list[EvidenceRecord]:
    """Возвращает заголовки и аннотации из PubMed; сбой сети не ломает бота."""
    query = query.strip()[:500]
    if not query or limit < 1:
        return []

    params: dict[str, str] = {
        "db": "pubmed",
        "term": query,
        "retmax": str(min(limit, 5)),
        "retmode": "json",
        "sort": "relevance",
    }
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    if NCBI_EMAIL:
        params["email"] = NCBI_EMAIL
    search_url = f"{BASE_URL}/esearch.fcgi?{urllib.parse.urlencode(params)}"

    try:
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
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, ET.ParseError, KeyError):
        return []

    records: list[EvidenceRecord] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = (article.findtext(".//PMID") or "").strip()
        title = " ".join("".join(article.find(".//ArticleTitle").itertext()).split()) if article.find(".//ArticleTitle") is not None else "Без названия"
        abstract_parts: list[str] = []
        for part in article.findall(".//Abstract/AbstractText"):
            text = " ".join("".join(part.itertext()).split())
            label = part.attrib.get("Label")
            if text:
                abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(abstract_parts).strip()
        if not pmid or not (title or abstract):
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
    return records[:limit]
