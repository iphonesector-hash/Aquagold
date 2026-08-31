import aqua_ai


def test_live_price_query_forces_web_search_and_retries_compound_mini(monkeypatch):
    calls = []

    def fake_post(url, payload, headers, timeout=45):
        calls.append(payload)
        if payload["model"] == "groq/compound":
            raise RuntimeError("سرویس هوش مصنوعی پاسخ نداد (404): source not found")
        return {"choices": [{"message": {"content": "قیمت لحظه‌ای با منبع معتبر"}}]}

    monkeypatch.setattr(aqua_ai, "_post_json", fake_post)
    answer = aqua_ai._groq_answer(
        {"groq_api_key": "test", "brain_model": "llama-3.1-8b-instant"},
        "قیمت دلار امروز چنده؟",
        [],
        {},
    )

    assert answer == "قیمت لحظه‌ای با منبع معتبر"
    assert [call["model"] for call in calls] == ["groq/compound", "groq/compound-mini"]
    assert all(call["compound_custom"]["tools"]["enabled_tools"] == ["web_search"] for call in calls)


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
