from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path

from flask import jsonify, request

import aquagold_secret_bootstrap  # noqa: F401,E402

MODULE_PATH = Path(__file__).resolve().parent / "aqua-bale-standalone" / "app.py"
SPEC = spec_from_file_location("aqua_bale_standalone_app", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load standalone Aqua Bale application")
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

_ORIGINAL_SETTINGS = MODULE._settings


def _settings_with_single_history_fallback():
    settings = _ORIGINAL_SETTINGS()
    if settings.get("allowed_chat_ids"):
        return settings
    try:
        with MODULE.get_db() as db, db.cursor() as cur:
            cur.execute("select distinct chat_id::text as chat_id from bale_jobs where chat_id is not null order by chat_id limit 2")
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

@app.before_request
def _block_standalone_webhook_activation():
    if request.path == "/api/mini/bale/activate":
        return jsonify({"error": "انتقال وب‌هوک ربات غیرفعال است؛ ربات روی AquaGold اصلی باقی می‌ماند."}), 410
    return None

BALE_MINIAPP_DIRECT_URL = os.getenv("AQUA_BALE_DIRECT_LINK") or "https://ble.ir/aqua_goldbot?startapp"


def _group_miniapp_markup():
    return {"inline_keyboard": [[{"text": "💧 باز کردن AquaGold", "url": BALE_MINIAPP_DIRECT_URL}]]}


@app.post("/api/mini/bale/send-button")
@MODULE.auth_required
def send_bale_miniapp_button():
    settings = MODULE._settings()
    if not settings.get("bot_token"):
        return jsonify({"error": "توکن ربات بله پیدا نشد"}), 400
    chats = settings.get("allowed_chat_ids") or []
    if not chats:
        return jsonify({"error": "گروه مجاز پیدا نشد"}), 400
    sent = 0
    for chat_id in chats:
        result = MODULE._send_chat(
            settings,
            chat_id,
            "💧 AquaGold را داخل خود بله باز کن 👇",
            reply_markup=_group_miniapp_markup(),
        )
        if isinstance(result, dict) and result.get("ok", True):
            sent += 1
    return jsonify({"ok": sent > 0, "button_sent": sent, "webhook_changed": False})


# The standalone day API originally returned only finalized services and
# cancellations. The production AquaGold inbox stores fresh Bale work as
# bale_jobs(status='new'/'review'), so include those rows in the same day view.
_ORIGINAL_MINI_DAY = app.view_functions.get("mini_day")


def _mini_day_with_pending():
    if _ORIGINAL_MINI_DAY is None:
        return jsonify({"error": "نمای روز در دسترس نیست"}), 500

    original_response = app.make_response(_ORIGINAL_MINI_DAY())
    if original_response.status_code != 200:
        return original_response

    payload = original_response.get_json(silent=True) or {}
    day = MODULE._parse_day(request.args.get("date"))
    start, end = MODULE._day_bounds(day)

    with MODULE.get_db() as db, db.cursor() as cur:
        cur.execute(
            """select b.id,
                      coalesce(nullif(trim(concat_ws(' ',c.first_name,c.last_name)),''),
                               nullif(trim(b.customer_name),''),'بدون نام') customer_name,
                      coalesce((select p.phone from customer_phones p
                                where p.customer_id=c.id
                                order by p.is_primary desc,p.id limit 1),b.phone,'') phone,
                      coalesce(c.address,b.address) address,
                      coalesce(b.job_type,'سرویس') job_type,
                      b.status::text status,
                      b.received_at,
                      null::timestamptz completed_at,
                      null::timestamptz cancelled_at,
                      null::text cancel_reason,
                      b.customer_id,
                      b.service_visit_id,
                      0::bigint received_amount,
                      0::bigint company_share_amount
               from bale_jobs b
               left join customers_v2 c on c.id=b.customer_id
               where b.status in ('new','review')
                 and b.received_at >= %s and b.received_at < %s
               order by b.received_at""",
            (start, end),
        )
        pending = [MODULE._row(row) for row in cur.fetchall()]

    jobs = list(payload.get("jobs") or [])
    jobs.extend(pending)
    jobs.sort(key=lambda item: str(item.get("received_at") or ""))
    payload["jobs"] = jobs

    summary = dict(payload.get("summary") or {})
    summary["new"] = sum(item.get("status") == "new" for item in jobs)
    summary["review"] = sum(item.get("status") == "review" for item in jobs)
    summary["total"] = len(jobs)
    payload["summary"] = summary
    return jsonify(payload)


if _ORIGINAL_MINI_DAY is not None:
    app.view_functions["mini_day"] = _mini_day_with_pending
