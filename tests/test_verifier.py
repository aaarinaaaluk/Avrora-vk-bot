from app.core.verifier import (
    ClaimRequest,
    ConfidenceLevel,
    VerificationStatus,
    verify_claim,
)


def test_verify_claim_without_evidence_returns_insufficient():
    result = verify_claim("Витамин C лечит простуду")

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert result.evidence == []


def test_verify_claim_preserves_original_claim():
    claim = "Витамин C лечит простуду"

    result = verify_claim(claim)

    assert result.claim == claim


def test_claim_request_rejects_empty_claim():
    from pydantic import ValidationError

    import pytest

    with pytest.raises(ValidationError):
        ClaimRequest(claim="")


def test_claim_request_rejects_claim_over_2000_characters():
    from pydantic import ValidationError

    import pytest

    with pytest.raises(ValidationError):
        ClaimRequest(claim="а" * 2001)

def test_verify_claim_does_not_invent_evidence():
    result = verify_claim(
        "Витамин C гарантированно предотвращает простуду"
    )

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert result.evidence == []
    assert "недостаточно" in result.explanation.lower()

def test_verify_claim_preserves_search_results_without_confirming_claim():
    from app.sources.text_search import SearchResult

    search_result = SearchResult(
        document_title="Клинические рекомендации",
        source_url="https://example.org/guideline.pdf",
        page_number=12,
        text="Фрагмент найден по совпадению слов.",
        matched_terms=["витамин", "простуда"],
        score=2,
    )

    result = verify_claim(
        "Витамин C предотвращает простуду",
        search_results=[search_result],
    )

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert len(result.evidence) == 1
    assert result.evidence[0].source_url == (
        "https://example.org/guideline.pdf"
    )
    assert result.evidence[0].source_name == "Клинические рекомендации"
    assert "странице 12" in result.evidence[0].evidence_summary
    assert result.evidence[0].limitations


def test_verifier_uses_model_only_with_real_evidence_and_known_evidence_ids():
    from app.sources.text_search import SearchResult

    class FakeLLM:
        def generate(self, prompt):
            assert "Разрешённые доказательные фрагменты" in prompt
            return (
                '{"status":"SUPPORTED","confidence":"HIGH",'
                '"explanation":"Фрагмент поддерживает утверждение.",'
                '"assessments":[{"evidence_id":"local:1","relevant":true,'
                '"supports_claim":true,"summary":"поддерживает",'
                '"limitations":[]}]}'
            )

    source = SearchResult(
        document_title="Клинические рекомендации",
        source_url="https://cr.minzdrav.gov.ru/example",
        page_number=5,
        text="В документе содержится релевантная рекомендация.",
        matched_terms=["документ", "рекомендация"],
        score=2,
    )
    result = verify_claim(
        "Проверяемое утверждение",
        search_results=[source],
        llm_client=FakeLLM(),
    )

    assert result.status == VerificationStatus.SUPPORTED
    assert result.confidence == ConfidenceLevel.MEDIUM  # один фрагмент: не HIGH
    assert result.evidence[0].supports_claim is True
    assert result.evidence[0].source_url == source.source_url


def test_verifier_rejects_model_verdict_with_unknown_source_id():
    from app.sources.text_search import SearchResult

    class FakeLLM:
        def generate(self, prompt):
            return (
                '{"status":"SUPPORTED","confidence":"HIGH",'
                '"explanation":"якобы подтверждено",'
                '"assessments":[{"evidence_id":"invented-source",'
                '"supports_claim":true,"summary":"фальшивый источник",'
                '"limitations":[]}]}'
            )

    source = SearchResult(
        document_title="Исходный документ",
        source_url="https://example.org/source",
        page_number=1,
        text="Текст фрагмента.",
        matched_terms=["фрагмент", "текст"],
        score=2,
    )
    result = verify_claim("Утверждение", search_results=[source], llm_client=FakeLLM())

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert result.evidence[0].supports_claim is None

def test_parse_model_json_accepts_trailing_text():
    from app.core.verifier import _parse_model_json

    raw = (
        '{"status":"INSUFFICIENT","confidence":"LOW",'
        '"explanation":"Недостаточно данных","assessments":[]} '
        'Пояснение после JSON'
    )
    result = _parse_model_json(raw)
    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW


def test_parse_model_json_rejects_multiple_verdicts():
    import pytest
    from app.core.verifier import _parse_model_json

    raw = (
        '{"status":"INSUFFICIENT","confidence":"LOW",'
        '"explanation":"Недостаточно данных","assessments":[]} '
        '{"status":"SUPPORTED","confidence":"HIGH",'
        '"explanation":"Подтверждено","assessments":[]}'
    )
    with pytest.raises(ValueError, match="несколько JSON-объектов"):
        _parse_model_json(raw)

def test_verifier_does_not_retain_unsupported_model_explanation():
    from app.sources.text_search import SearchResult

    class FakeLLM:
        def generate(self, prompt):
            return (
                '{"status":"SUPPORTED","confidence":"HIGH",'
                '"explanation":"Утверждение подтверждается источниками.",'
                '"assessments":[]}'
            )

    source = SearchResult(
        document_title="Клинические рекомендации",
        source_url="https://example.org/guideline.pdf",
        page_number=3,
        text="Фрагмент найден, но его связь с утверждением не установлена.",
        matched_terms=["утверждение", "источники"],
        score=2,
    )

    result = verify_claim(
        "Проверяемое медицинское утверждение",
        search_results=[source],
        llm_client=FakeLLM(),
    )

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert "недостаточно данных" in result.explanation.lower()
    assert "утверждение подтверждается источниками" not in result.explanation.lower()
    assert len(result.evidence) == 1
    assert result.evidence[0].supports_claim is None



def test_who_sugar_threshold_contradiction_is_not_marked_supported():
    from app.sources.evidence import EvidenceRecord

    class MustNotCallLLM:
        def generate(self, prompt):
            raise AssertionError("The deterministic contradiction guard should run first")

    evidence = EvidenceRecord(
        evidence_id="who:sugars",
        source_id="who",
        source_name="Здоровое питание",
        source_url="https://www.who.int/ru/news-room/fact-sheets/detail/healthy-diet",
        excerpt=(
            "Свободные сахара должны составлять менее 10% общей суточной энергии. "
            "Сокращение потребления сахаров снижает риски для здоровья."
        ),
        source_type="официальная русскоязычная информационная страница ВОЗ",
    )
    result = verify_claim(
        "ВОЗ рекомендует получать не менее 25% суточной энергии из свободных сахаров.",
        external_evidence=[evidence],
        llm_client=MustNotCallLLM(),
    )
    assert result.status == VerificationStatus.CONTRADICTED
    assert result.confidence == ConfidenceLevel.HIGH
    assert result.evidence[0].supports_claim is False


def test_who_numeric_contradiction_only_returns_directly_relevant_who_sources():
    from app.sources.evidence import EvidenceRecord

    who = EvidenceRecord(
        evidence_id="who:sugars",
        source_id="who",
        source_name="Здоровое питание",
        source_url="https://www.who.int/ru/news-room/fact-sheets/detail/healthy-diet",
        excerpt="Свободные сахара должны составлять менее 10% общей суточной энергии.",
        source_type="official WHO page",
    )
    irrelevant_pubmed = EvidenceRecord(
        evidence_id="pubmed:cancer",
        source_id="pubmed",
        source_name="PubMed: WHO classification of penile cancer",
        source_url="https://pubmed.ncbi.nlm.nih.gov/36221864/",
        excerpt="This article discusses classification of penile and scrotal cancers.",
        source_type="scientific article",
    )

    class MustNotCallLLM:
        def generate(self, prompt):
            raise AssertionError("The deterministic contradiction guard should run first")

    result = verify_claim(
        "ВОЗ рекомендует получать не менее 25% суточной энергии из свободных сахаров.",
        external_evidence=[who, irrelevant_pubmed],
        llm_client=MustNotCallLLM(),
    )

    assert result.status == VerificationStatus.CONTRADICTED
    assert [item.source_id for item in result.evidence] == ["who"]


def test_verifier_prompt_requires_support_for_all_parts_of_compound_claim():
    from app.core.verifier import _make_prompt
    from app.sources.evidence import EvidenceRecord

    record = EvidenceRecord(
        evidence_id="pubmed:123",
        source_id="pubmed",
        source_name="A relevant study",
        source_url="https://pubmed.ncbi.nlm.nih.gov/123/",
        excerpt="Study excerpt",
        source_type="scientific article",
    )
    prompt = _make_prompt("Claim part A and claim part B", [record.model_dump()])
    assert "каждую существенную часть" in prompt
    assert "неизбежно" in prompt


def test_verify_claim_reports_retrieval_failure_instead_of_claiming_no_evidence():
    result = verify_claim(
        "Ограничение калорий замедляет биологическое старение человека.",
        retrieval_warnings=["PubMed", "перевод поискового запроса PubMed"],
    )

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert "поиск не удалось полностью завершить" in result.explanation.lower()
    assert "не означает" in result.explanation.lower()


def test_irrelevant_source_cannot_support_or_contradict_claim_even_if_model_marks_true():
    from app.sources.evidence import EvidenceRecord

    class FakeLLM:
        def generate(self, prompt):
            return (
                '{"status":"SUPPORTED","confidence":"HIGH",'
                '"explanation":"Подтверждено.","assessments":['
                '{"evidence_id":"pubmed:glaucoma","relevant":false,'
                '"supports_claim":true,"summary":"Другая болезнь.","limitations":[]}]}'
            )

    unrelated = EvidenceRecord(
        evidence_id="pubmed:glaucoma",
        source_id="pubmed",
        source_name="PubMed: MIND diet and glaucoma",
        source_url="https://pubmed.ncbi.nlm.nih.gov/36123555/",
        excerpt="This study examines open-angle glaucoma, not cognitive decline.",
        source_type="scientific article / abstract",
    )
    result = verify_claim(
        "Диета MIND замедляет когнитивный спад на 7,5 лет.",
        external_evidence=[unrelated],
        llm_client=FakeLLM(),
    )

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert len(result.evidence) == 1
    assert result.evidence[0].relevant is False
    assert result.evidence[0].supports_claim is None
    assert "ни один не был подтверждён" in result.explanation.lower()


def test_relevant_but_inconclusive_source_is_distinguished_from_irrelevant_source():
    from app.sources.evidence import EvidenceRecord

    class FakeLLM:
        def generate(self, prompt):
            return (
                '{"status":"INSUFFICIENT","confidence":"LOW",'
                '"explanation":"Данные ограничены.","assessments":['
                '{"evidence_id":"pubmed:aging","relevant":true,'
                '"supports_claim":null,"summary":"Тема совпадает, но прямого вывода нет.","limitations":[]},'
                '{"evidence_id":"pubmed:glaucoma","relevant":false,'
                '"supports_claim":null,"summary":"Другой исход.","limitations":[]}]} '
            )

    relevant = EvidenceRecord(
        evidence_id="pubmed:aging",
        source_id="pubmed",
        source_name="PubMed: Caloric restriction and aging biomarkers",
        source_url="https://pubmed.ncbi.nlm.nih.gov/11111111/",
        excerpt="This study measured biomarkers during caloric restriction.",
        source_type="scientific article / abstract",
    )
    unrelated = EvidenceRecord(
        evidence_id="pubmed:glaucoma",
        source_id="pubmed",
        source_name="PubMed: MIND diet and glaucoma",
        source_url="https://pubmed.ncbi.nlm.nih.gov/22222222/",
        excerpt="This study measured glaucoma risk.",
        source_type="scientific article / abstract",
    )
    result = verify_claim(
        "Ограничение калорий замедляет маркеры биологического старения человека.",
        external_evidence=[relevant, unrelated],
        llm_client=FakeLLM(),
    )

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert [item.relevant for item in result.evidence] == [True, False]
    assert all(item.supports_claim is None for item in result.evidence)
    assert "источники по теме" in result.explanation.lower()


def test_verifier_prompt_requires_separate_relevance_assessment():
    from app.core.verifier import _make_prompt
    from app.sources.evidence import EvidenceRecord

    record = EvidenceRecord(
        evidence_id="pubmed:123",
        source_id="pubmed",
        source_name="A relevant study",
        source_url="https://pubmed.ncbi.nlm.nih.gov/123/",
        excerpt="Study excerpt",
        source_type="scientific article",
    )
    prompt = _make_prompt("Claim", [record.model_dump()])

    assert '"relevant":true' in prompt
    assert "релевантность каждого источника" in prompt
    assert "отсутствие поддержки не равно противоречию" in prompt


def test_missing_relevance_flag_cannot_make_candidate_support_claim():
    from app.sources.evidence import EvidenceRecord

    class FakeLLM:
        def generate(self, prompt):
            # Simulate a model that ignores the new relevance field.
            return (
                '{"status":"SUPPORTED","confidence":"HIGH",'
                '"explanation":"Подтверждено.","assessments":['
                '{"evidence_id":"pubmed:unknown-context",'
                '"supports_claim":true,"summary":"Совпали ключевые слова.","limitations":[]}]}'
            )

    candidate = EvidenceRecord(
        evidence_id="pubmed:unknown-context",
        source_id="pubmed",
        source_name="PubMed: generic diet paper",
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        excerpt="Generic article mentioning diet and health.",
        source_type="scientific article / abstract",
    )
    result = verify_claim(
        "Точный медицинский тезис с конкретным исходом.",
        external_evidence=[candidate],
        llm_client=FakeLLM(),
    )

    assert result.status == VerificationStatus.INSUFFICIENT
    assert result.confidence == ConfidenceLevel.LOW
    assert result.evidence[0].relevant is False
    assert result.evidence[0].supports_claim is None
