import pytest

from radar.telegram import build_endpoint, send


def test_endpoint_embeds_the_token():
    assert build_endpoint("abc123").endswith("/botabc123/sendMessage")
    assert build_endpoint("abc123").startswith("https://")


def test_send_posts_text_and_chat_id():
    calls = []

    def fake_post(url, json):
        calls.append((url, json))
        return {"ok": True}

    assert send("mensagem", token="t", chat_id="42", post=fake_post) is True
    assert calls[0][1]["chat_id"] == "42"
    assert calls[0][1]["text"] == "mensagem"


def test_empty_text_is_not_sent():
    """Silencio e resultado valido; nao mandar mensagem vazia."""
    calls = []
    assert send("", token="t", chat_id="42", post=lambda u, json: calls.append(1)) is False
    assert calls == []


def test_whitespace_only_text_is_not_sent():
    calls = []
    assert send("   \n ", token="t", chat_id="42",
                post=lambda u, json: calls.append(1)) is False
    assert calls == []


def test_missing_credentials_raise_rather_than_fail_silently():
    with pytest.raises(ValueError, match="token"):
        send("oi", token="", chat_id="42", post=lambda u, json: None)
    with pytest.raises(ValueError, match="chat_id"):
        send("oi", token="t", chat_id="", post=lambda u, json: None)


def test_transport_failure_returns_false_without_raising():
    def failing_post(url, json):
        raise RuntimeError("timeout")

    assert send("oi", token="t", chat_id="42", post=failing_post) is False
