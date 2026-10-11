import json
import time

import pytest

from app.core.llm import GigaChatClient


class FakeResponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.data


def test_gigachat_uses_oauth_and_reuses_access_token(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=30, context=None):
        calls.append(request)
        if request.full_url.endswith("/api/v2/oauth"):
            return FakeResponse({
                "access_token": "temporary-token",
                "expires_at": int((time.time() + 1800) * 1000),
            })
        return FakeResponse({
            "choices": [{"message": {"content": "ответ модели"}}],
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 1,
                "total_tokens": 3,
            },
        })

    monkeypatch.setattr("app.core.llm.urllib.request.urlopen", fake_urlopen)
    client = GigaChatClient(auth_key="encoded-auth-key")

    assert client.generate("первый запрос") == "ответ модели"
    assert client.generate("второй запрос") == "ответ модели"

    oauth_calls = [call for call in calls if call.full_url.endswith("/api/v2/oauth")]
    completion_calls = [call for call in calls if call.full_url.endswith("/v1/chat/completions")]
    assert len(oauth_calls) == 1
    assert len(completion_calls) == 2
    assert oauth_calls[0].get_header("Authorization") == "Basic encoded-auth-key"
    assert completion_calls[0].get_header("Authorization") == "Bearer temporary-token"
    assert json.loads(completion_calls[0].data.decode("utf-8"))["model"] == "GigaChat"
    assert oauth_calls[0].get_header("Rquid")
    assert client.usage_snapshot() == {
        "calls": 2,
        "prompt_tokens": 4,
        "completion_tokens": 2,
        "total_tokens": 6,
    }


def test_gigachat_can_build_authorization_key_from_client_credentials():
    import base64

    client = GigaChatClient(client_id="client", client_secret="secret")
    expected = base64.b64encode(b"client:secret").decode("ascii")
    assert client.is_configured
    assert client.auth_key == expected


def test_gigachat_requires_credentials():
    client = GigaChatClient()
    assert not client.is_configured
    with pytest.raises(RuntimeError, match="GIGACHAT_AUTH_KEY"):
        client.generate("test")
