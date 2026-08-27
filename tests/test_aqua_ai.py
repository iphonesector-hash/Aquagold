import aqua_ai


def test_aqua_secret_round_trip_and_public_mask():
    value = "gsk_test_abcdefghijklmnopqrstuvwxyz"
    encrypted = aqua_ai._encrypt(value)
    assert encrypted != value
    assert aqua_ai._decrypt(encrypted) == value
    public = aqua_ai._public_settings({**aqua_ai.DEFAULTS, "groq_api_key": value, "elevenlabs_api_key": ""})
    assert public["groq_api_key_configured"] is True
    assert public["groq_api_key_mask"] == "••••wxyz"
    assert "groq_api_key" not in public


def test_aqua_understands_guarded_customer_creation():
    draft = aqua_ai._customer_draft("مشتری علی رضایی با شماره 09121234567 آدرس تهران ونک ثبت کن")
    assert draft == {
        "first_name": "علی",
        "last_name": "رضایی",
        "phones": ["09121234567"],
        "address": "تهران ونک",
        "map_label": "علی رضایی",
    }


def test_aqua_extracts_map_customer_query():
    assert aqua_ai._map_query("مشتری رضایی را روی نقشه برام پیدا کن") == "رضایی"


def test_farangi_routes_are_removed_and_aqua_routes_register():
    rules = {rule.rule for rule in aqua_ai.app_v3.app.url_map.iter_rules()}
    assert "/api/aqua-ai/chat" in rules
    assert "/api/aqua-ai/transcribe" in rules
    assert "/api/aqua-ai/speak" in rules
    assert not any("farangis" in rule for rule in rules)
