from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

# Reuse AquaGold's existing stable secret derivation. This keeps encrypted
# Bale settings readable without requiring a separate AQUAGOLD_SECRET_KEY
# when the production project already derives it from its database settings.
import aquagold_secret_bootstrap  # noqa: F401,E402

MODULE_PATH = Path(__file__).resolve().parent / "aqua-bale-standalone" / "app.py"
SPEC = spec_from_file_location("aqua_bale_standalone_app", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load standalone Aqua Bale application")
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

# Safe allowlist recovery for the standalone runtime only:
# if AquaGold has never explicitly stored allowed_chat_ids but all historical
# Bale jobs came from exactly one chat, use that one historical group. If there
# are zero or multiple chats, remain fail-closed.
_ORIGINAL_SETTINGS = MODULE._settings


def _settings_with_single_history_fallback():
    settings = _ORIGINAL_SETTINGS()
    if settings.get("allowed_chat_ids"):
        return settings
    try:
        with MODULE.get_db() as db, db.cursor() as cur:
            cur.execute(
                "select distinct chat_id::text as chat_id from bale_jobs "
                "where chat_id is not null order by chat_id limit 2"
            )
            rows = cur.fetchall()
        candidates = [str(row.get("chat_id")) for row in rows if row.get("chat_id") is not None]
        if len(candidates) == 1:
            settings["allowed_chat_ids"] = candidates
            settings["allowed_chat_ids_source"] = "single_historical_group"
    except Exception:
        pass
    return settings


MODULE._settings = _settings_with_single_history_fallback
app = MODULE.app

# Temporary non-sensitive preview diagnostic. Removed after verification.
@app.get("/__aqua_bale_data_probe")
def _aqua_bale_data_probe():
    today = MODULE._tehran_today()
    start_today, end_today = MODULE._day_bounds(today)
    start_prev, _ = MODULE._day_bounds(today - MODULE.timedelta(days=1))
    with MODULE.get_db() as db, db.cursor() as cur:
        cur.execute("select count(*)::int n from customers_v2 where not archived")
        customers = cur.fetchone()["n"]
        cur.execute("select count(*)::int n from service_visits")
        visits = cur.fetchone()["n"]
        cur.execute("select count(*)::int n from service_visits where coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s", (start_today, end_today))
        today_visits = cur.fetchone()["n"]
        cur.execute("select count(*)::int n from service_visits where coalesce(visited_at,created_at)>=%s and coalesce(visited_at,created_at)<%s", (start_prev, start_today))
        previous_day_visits = cur.fetchone()["n"]
        cur.execute("select max(coalesce(visited_at,created_at)) latest from service_visits")
        latest = cur.fetchone()["latest"]
    return MODULE.jsonify({
        "connected": True,
        "has_customers": customers > 0,
        "has_service_history": visits > 0,
        "today_has_services": today_visits > 0,
        "previous_day_has_services": previous_day_visits > 0,
        "latest_service_at": latest.isoformat() if latest else None,
    })
