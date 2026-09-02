import aqua_ai
import aqua_live_search_hotfix  # noqa: F401


def test_live_price_query_uses_fast_compound_mini_first(monkeypatch):
    calls = []

    def fake_post(url, payload, headers, timeout=45):
        calls.append((payload, headers, timeout))
        return {"choices": [{"message": {"content": "قیمت لحظه‌ای با منبع معتبر"}}]}

    monkeypatch.setattr(aqua_ai, "_post_json", fake_post)
    answer = aqua_ai._groq_answer(
        {"groq_api_key": "test", "brain_model": "llama-3.1-8b-instant"},
        "قیمت دلار امروز چنده؟",
        [],
        {},
    )

    assert answer == "قیمت لحظه‌ای با منبع معتبر"
    assert [call[0]["model"] for call in calls] == ["groq/compound-mini"]
    assert calls[0][0]["compound_custom"] == {"tools": {"enabled_tools": ["web_search"]}}
    assert calls[0][1]["Groq-Model-Version"] == "2025-07-23"
    assert calls[0][2] <= 10
    assert len(calls[0][0]["messages"][0]["content"]) < 700


def test_live_price_query_falls_back_to_compound(monkeypatch):
    calls = []

    def fake_post(url, payload, headers, timeout=45):
        calls.append(payload)
        if payload["model"] == "groq/compound-mini":
            raise RuntimeError("temporary mini failure")
        return {"choices": [{"message": {"content": "پاسخ جایگزین وب"}}]}

    monkeypatch.setattr(aqua_ai, "_post_json", fake_post)
    answer = aqua_ai._groq_answer(
        {"groq_api_key": "test", "brain_model": "llama-3.1-8b-instant"},
        "قیمت طلا الان چنده؟",
        [],
        {},
    )

    assert answer == "پاسخ جایگزین وب"
    assert [call["model"] for call in calls] == ["groq/compound-mini", "groq/compound"]
    assert all(call["compound_custom"] == {"tools": {"enabled_tools": ["web_search"]}} for call in calls)


def test_non_live_chat_keeps_configured_model(monkeypatch):
    calls = []

    def fake_post(url, payload, headers, timeout=45):
        calls.append(payload)
        return {"choices": [{"message": {"content": "سلام پیمان"}}]}

    monkeypatch.setattr(aqua_ai, "_post_json", fake_post)
    answer = aqua_ai._groq_answer(
        {"groq_api_key": "test", "brain_model": "llama-3.1-8b-instant"},
        "سلام آریا",
        [],
        {},
    )

    assert answer == "سلام پیمان"
    assert calls[0]["model"] == "llama-3.1-8b-instant"
    assert "compound_custom" not in calls[0]
