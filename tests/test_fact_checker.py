from app.core import fact_checker
from app.sources.evidence import EvidenceRecord
from app.sources.pubmed_search import PubMedSearchOutcome


class BrokenLLM:
    def generate(self, prompt):
        raise RuntimeError("simulated timeout")


def test_pubmed_query_uses_topic_fallback_when_gigachat_translation_times_out():
    query, translation_failed = fact_checker._build_pubmed_query(
        "Ограничение калорий без недоедания замедляет маркеры биологического старения человека.",
        BrokenLLM(),
    )

    assert "caloric restriction" in query
    assert "biological aging" in query
    assert translation_failed is False


def test_pubmed_query_rejects_unrelated_gigachat_translation():
    class WrongTopicLLM:
        def generate(self, prompt):
            return "WHO classification penile and scrotal cancers"

    query, translation_failed = fact_checker._build_pubmed_query(
        "ВОЗ рекомендует получать не менее 25% суточной энергии из свободных сахаров.",
        WrongTopicLLM(),
    )

    assert "free sugars" in query
    assert "penile" not in query
    assert translation_failed is False


def test_official_who_claim_skips_pubmed_and_unneeded_translation(monkeypatch):
    who_record = EvidenceRecord(
        evidence_id="who:healthy-diet",
        source_id="who",
        source_name="Здоровое питание",
        source_url="https://www.who.int/ru/news-room/fact-sheets/detail/healthy-diet",
        excerpt="Свободные сахара должны составлять менее 10% суточной энергии.",
        source_type="official WHO page",
    )

    monkeypatch.setattr(fact_checker, "search_documents", lambda *args, **kwargs: [])
    monkeypatch.setattr(fact_checker, "search_who_pages", lambda *args, **kwargs: [who_record])
    monkeypatch.setattr(fact_checker, "search_fact_checks", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        fact_checker,
        "search_pubmed_with_status",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("PubMed should be skipped")),
    )

    class MustNotTranslate:
        def generate(self, prompt):
            raise AssertionError("An official WHO source already answered the WHO claim")

    local, external, failures = fact_checker._collect_evidence_with_status(
        "ВОЗ рекомендует ограничивать свободные сахара.", MustNotTranslate()
    )

    assert local == []
    assert [item.evidence_id for item in external] == ["who:healthy-diet"]
    assert failures == []


def test_pubmed_unavailable_is_reported_as_retrieval_failure(monkeypatch):
    monkeypatch.setattr(fact_checker, "search_documents", lambda *args, **kwargs: [])
    monkeypatch.setattr(fact_checker, "search_who_pages", lambda *args, **kwargs: [])
    monkeypatch.setattr(fact_checker, "search_fact_checks", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        fact_checker,
        "search_pubmed_with_status",
        lambda *args, **kwargs: PubMedSearchOutcome([], "unavailable", 3, 3),
    )

    local, external, failures = fact_checker._collect_evidence_with_status(
        "Ограничение калорий замедляет биологическое старение.", None
    )

    assert local == []
    assert external == []
    assert "PubMed" in failures
