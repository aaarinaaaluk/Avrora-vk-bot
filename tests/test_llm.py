
from app.core.llm import MockLLMClient


def test_mock_llm_returns_test_response():
    client = MockLLMClient()

    result = client.generate("Проверь медицинское утверждение")

    assert "тестовый ответ" in result
    assert "не является медицинским доказательством" in result


def test_mock_llm_does_not_depend_on_prompt():
    client = MockLLMClient()

    first_result = client.generate("Первый запрос")
    second_result = client.generate("Совершенно другой запрос")

    assert first_result == second_result
