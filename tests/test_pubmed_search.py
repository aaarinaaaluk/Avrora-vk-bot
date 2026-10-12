import json
import urllib.error

from app.sources import pubmed_search


PUBMED_XML = """
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>123456</PMID>
      <Article>
        <ArticleTitle>Vitamin D and bone health</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Vitamin D supports bone health.</AbstractText>
        </Abstract>
        <Journal>
          <JournalIssue>
            <PubDate><Year>2024</Year><Month>Jan</Month></PubDate>
          </JournalIssue>
        </Journal>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def test_search_pubmed_parses_article(monkeypatch):
    def fake_get_text(url: str, timeout: int = 8) -> str:
        if "esearch.fcgi" in url:
            return json.dumps({"esearchresult": {"idlist": ["123456"]}})
        if "efetch.fcgi" in url:
            return PUBMED_XML
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(pubmed_search, "_get_text", fake_get_text)

    results = pubmed_search.search_pubmed("vitamin D bone health", limit=3)

    assert len(results) == 1
    result = results[0]
    assert result.evidence_id == "pubmed:123456"
    assert result.source_id == "pubmed"
    assert result.source_name == "PubMed: Vitamin D and bone health"
    assert result.source_url == "https://pubmed.ncbi.nlm.nih.gov/123456/"
    assert "Vitamin D supports bone health." in result.excerpt
    assert "BACKGROUND:" in result.excerpt
    assert result.published_at == "2024 Jan"
    assert result.limitations


def test_search_pubmed_keeps_title_when_abstract_is_missing(monkeypatch):
    xml_without_abstract = """
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>789</PMID>
          <Article>
            <ArticleTitle>Study without abstract</ArticleTitle>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>
    """

    def fake_get_text(url: str, timeout: int = 8) -> str:
        if "esearch.fcgi" in url:
            return json.dumps({"esearchresult": {"idlist": ["789"]}})
        return xml_without_abstract

    monkeypatch.setattr(pubmed_search, "_get_text", fake_get_text)
    results = pubmed_search.search_pubmed("study", limit=1)

    assert len(results) == 1
    assert "Study without abstract" in results[0].excerpt
    assert "Аннотация не представлена." in results[0].excerpt


def test_search_pubmed_returns_empty_when_no_ids_found(monkeypatch):
    calls = []

    def fake_get_text(url: str, timeout: int = 8) -> str:
        calls.append(url)
        return json.dumps({"esearchresult": {"idlist": []}})

    monkeypatch.setattr(pubmed_search, "_get_text", fake_get_text)

    assert pubmed_search.search_pubmed("no matching article") == []
    assert len(calls) == 1


def test_search_pubmed_handles_network_error(monkeypatch):
    def fake_get_text(url: str, timeout: int = 8) -> str:
        raise urllib.error.URLError("network unavailable")

    monkeypatch.setattr(pubmed_search, "_get_text", fake_get_text)

    assert pubmed_search.search_pubmed("diabetes treatment") == []


def test_search_pubmed_skips_request_for_empty_query_or_invalid_limit(monkeypatch):
    def unexpected_request(*args, **kwargs):
        raise AssertionError("PubMed should not be called for invalid input")

    monkeypatch.setattr(pubmed_search, "_get_text", unexpected_request)

    assert pubmed_search.search_pubmed("   ") == []
    assert pubmed_search.search_pubmed("diabetes", limit=0) == []


def test_search_pubmed_filters_irrelevant_articles(monkeypatch):
    xml = """
    <PubmedArticleSet>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>123456</PMID>
          <Article>
            <ArticleTitle>Vitamin D deficiency and bone health</ArticleTitle>
            <Abstract>
              <AbstractText>Vitamin D deficiency can affect bone health.</AbstractText>
            </Abstract>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
      <PubmedArticle>
        <MedlineCitation>
          <PMID>789</PMID>
          <Article>
            <ArticleTitle>Obesity treatment in children</ArticleTitle>
            <Abstract>
              <AbstractText>A test estimates weight-related risk.</AbstractText>
            </Abstract>
          </Article>
        </MedlineCitation>
      </PubmedArticle>
    </PubmedArticleSet>
    """

    def fake_get_text(url: str, timeout: int = 8) -> str:
        if "esearch.fcgi" in url:
            return json.dumps({"esearchresult": {"idlist": ["123456", "789"]}})
        return xml

    monkeypatch.setattr(pubmed_search, "_get_text", fake_get_text)

    results = pubmed_search.search_pubmed(
        "vitamin D deficiency bone health",
        limit=3,
    )

    assert [result.evidence_id for result in results] == ["pubmed:123456"]


def test_meaningful_terms_preserves_negation():
    terms = pubmed_search._meaningful_terms("treatment does not reduce risk")
    assert "not" in terms
