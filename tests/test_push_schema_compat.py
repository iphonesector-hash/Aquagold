import aqua_push_schema_compat as compat


def test_layout_detects_legacy_and_modern_push_tables():
    assert compat._layout_from_columns({"id", "user_id", "subscription", "active"}) == "legacy"
    assert compat._layout_from_columns({"id", "user_id", "endpoint", "p256dh", "auth", "active"}) == "modern"


def test_legacy_jsonb_subscription_is_normalized():
    row = compat._subscription_from_row(
        {
            "id": 12,
            "subscription": {
                "endpoint": "https://push.example/sub",
                "keys": {"p256dh": "public-key", "auth": "auth-key"},
            },
        },
        "legacy",
    )
    assert row == {
        "id": 12,
        "endpoint": "https://push.example/sub",
        "p256dh": "public-key",
        "auth": "auth-key",
    }


def test_modern_subscription_is_normalized():
    row = compat._subscription_from_row(
        {"id": "uuid", "endpoint": "https://push.example/sub", "p256dh": "p", "auth": "a"},
        "modern",
    )
    assert row["endpoint"] == "https://push.example/sub"
    assert row["p256dh"] == "p"
    assert row["auth"] == "a"


class _FakeCursor:
    def __init__(self, columns, subscription_row):
        self.columns = columns
        self.subscription_row = subscription_row
        self.result = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        if "information_schema.columns" in sql:
            self.result = [{"column_name": column} for column in self.columns]
        elif "select id,subscription" in sql:
            self.result = [self.subscription_row]
        elif "select id,endpoint,p256dh,auth" in sql:
            self.result = [self.subscription_row]
        else:
            self.result = []

    def fetchall(self):
        return list(self.result)


class _FakeDb:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor


def test_load_subscriptions_uses_legacy_jsonb_columns(monkeypatch):
    cursor = _FakeCursor(
        {"id", "user_id", "subscription", "created_at", "updated_at", "active"},
        {
            "id": 1,
            "subscription": {
                "endpoint": "https://push.example/legacy",
                "keys": {"p256dh": "legacy-p", "auth": "legacy-a"},
            },
        },
    )
    monkeypatch.setattr(compat.aqua_push_runtime, "_schema", lambda: None)
    monkeypatch.setattr(compat.app_v3, "get_db", lambda: _FakeDb(cursor))

    layout, rows = compat._load_subscriptions(user_id=7)

    assert layout == "legacy"
    assert rows[0]["endpoint"] == "https://push.example/legacy"
    assert any("select id,subscription" in sql for sql, _ in cursor.queries)
    assert not any("select id,endpoint,p256dh,auth" in sql for sql, _ in cursor.queries)


def test_load_subscriptions_uses_modern_columns(monkeypatch):
    cursor = _FakeCursor(
        {"id", "user_id", "endpoint", "p256dh", "auth", "active"},
        {"id": "u1", "endpoint": "https://push.example/modern", "p256dh": "modern-p", "auth": "modern-a"},
    )
    monkeypatch.setattr(compat.aqua_push_runtime, "_schema", lambda: None)
    monkeypatch.setattr(compat.app_v3, "get_db", lambda: _FakeDb(cursor))

    layout, rows = compat._load_subscriptions(user_id=7)

    assert layout == "modern"
    assert rows[0]["endpoint"] == "https://push.example/modern"
    assert any("select id,endpoint,p256dh,auth" in sql for sql, _ in cursor.queries)
