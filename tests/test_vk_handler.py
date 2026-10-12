import asyncio

import pytest
from fastapi import BackgroundTasks

import app.vk.handler as handler


class FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


@pytest.fixture(autouse=True)
def reset_event_cache(monkeypatch):
    monkeypatch.setattr(handler, "VK_SECRET", "")
    with handler._event_lock:
        handler._seen_events.clear()
    yield
    with handler._event_lock:
        handler._seen_events.clear()


def make_event(event_id, text="Проверочное медицинское утверждение"):
    return {
        "type": "message_new",
        "event_id": event_id,
        "object": {
            "message": {
                "text": text,
                "peer_id": 2000000001,
            }
        },
    }


def test_duplicate_vk_event_schedules_only_one_reply(monkeypatch):
    processed = []
    sent = []

    monkeypatch.setattr(
        handler, "build_reply",
        lambda text: processed.append(text) or "Ответ AVRORA",
    )
    monkeypatch.setattr(
        handler, "send_vk_message",
        lambda peer_id, message, **kwargs: sent.append((peer_id, message)),
    )

    async def scenario():
        first_tasks = BackgroundTasks()
        first_response = await handler.vk_callback(
            FakeRequest(make_event("event-123")), first_tasks
        )

        # Обработчик вернул HTTP-ответ, но долгая работа ещё не запускалась.
        assert first_response.body == b"ok"
        assert processed == []
        assert len(first_tasks.tasks) == 1
        await first_tasks()

        duplicate_tasks = BackgroundTasks()
        duplicate_response = await handler.vk_callback(
            FakeRequest(make_event("event-123")), duplicate_tasks
        )
        assert duplicate_response.body == b"ok"
        assert len(duplicate_tasks.tasks) == 0
        await duplicate_tasks()

        # Новое событие с тем же текстом не должно блокироваться.
        new_tasks = BackgroundTasks()
        new_response = await handler.vk_callback(
            FakeRequest(make_event("event-124")), new_tasks
        )
        assert new_response.body == b"ok"
        assert len(new_tasks.tasks) == 1
        await new_tasks()

    asyncio.run(scenario())

    assert len(processed) == 2
    assert len(sent) == 2
    assert all(item[1] == "Ответ AVRORA" for item in sent)


def test_invalid_secret_is_rejected(monkeypatch):
    monkeypatch.setattr(handler, "VK_SECRET", "expected-secret")

    async def scenario():
        tasks = BackgroundTasks()
        response = await handler.vk_callback(
            FakeRequest({
                "type": "message_new",
                "event_id": "event-secret-test",
                "secret": "wrong-secret",
                "object": {
                    "message": {
                        "text": "Тест",
                        "peer_id": 2000000001,
                    }
                },
            }),
            tasks,
        )
        assert response.status_code == 403
        assert len(tasks.tasks) == 0

    asyncio.run(scenario())

def test_event_random_id_is_stable():
    first = handler._event_random_id("vk-event-123", 2000000001)
    second = handler._event_random_id("vk-event-123", 2000000001)
    other_event = handler._event_random_id("vk-event-124", 2000000001)

    assert first == second
    assert first > 0
    assert first != other_event


def test_send_vk_message_retries_timeout_with_same_random_id(monkeypatch):
    import json
    from urllib.parse import parse_qs

    monkeypatch.setattr(handler, "VK_GROUP_TOKEN", "test-token")
    attempts = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"response": 123}).encode("utf-8")

    def fake_urlopen(request, timeout):
        params = parse_qs(request.data.decode("utf-8"))
        attempts.append((int(params["random_id"][0]), timeout))

        if len(attempts) == 1:
            raise TimeoutError("simulated response timeout")
        return FakeResponse()

    monkeypatch.setattr(handler.urllib.request, "urlopen", fake_urlopen)

    handler.send_vk_message(
        2000000001,
        "Тест отправки",
        random_id=123456789,
    )

    assert attempts == [(123456789, 30), (123456789, 30)]
