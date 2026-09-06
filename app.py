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
