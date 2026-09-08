"""Compatibility layer for AquaGold Web Push subscription schemas.

Production has an older ``push_subscriptions`` table that stores the browser
subscription as JSONB, while newer databases use separate endpoint/key columns.
Keep both layouts working without mutating the production schema.
"""
from __future__ import annotations

import json

from flask import jsonify, request

import app_v3
import aqua_push_runtime


def _layout_from_columns(columns):
    columns = set(columns or ())
    if {"endpoint", "p256dh", "auth"}.issubset(columns):
        return "modern"
    if "subscription" in columns:
        return "legacy"
    raise RuntimeError("push_subscriptions schema is unsupported")


def _layout(cur):
    cur.execute(
        "select column_name from information_schema.columns "
        "where table_schema='public' and table_name='push_subscriptions'"
    )
    return _layout_from_columns(row["column_name"] for row in cur.fetchall())


def _subscription_from_row(row, layout):
    row = dict(row or {})
    if layout == "modern":
        return {
            "id": row.get("id"),
            "endpoint": str(row.get("endpoint") or "").strip(),
            "p256dh": str(row.get("p256dh") or "").strip(),
            "auth": str(row.get("auth") or "").strip(),
        }

    raw = row.get("subscription") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    keys = raw.get("keys") or {}
    if not isinstance(keys, dict):
        keys = {}
    return {
        "id": row.get("id"),
        "endpoint": str(raw.get("endpoint") or "").strip(),
        "p256dh": str(keys.get("p256dh") or "").strip(),
        "auth": str(keys.get("auth") or "").strip(),
    }


def _load_subscriptions(user_id=None):
    aqua_push_runtime._schema()
    with app_v3.get_db() as db, db.cursor() as cur:
        layout = _layout(cur)
        if layout == "modern":
            if user_id is None:
                cur.execute(
                    "select id,endpoint,p256dh,auth from push_subscriptions where active=true"
                )
            else:
                cur.execute(
                    "select id,endpoint,p256dh,auth from push_subscriptions "
                    "where active=true and user_id=%s",
                    (user_id,),
                )
        else:
            if user_id is None:
                cur.execute(
                    "select id,subscription from push_subscriptions where active=true"
                )
            else:
                cur.execute(
                    "select id,subscription from push_subscriptions "
                    "where active=true and user_id=%s",
                    (str(user_id),),
                )
        rows = [_subscription_from_row(row, layout) for row in cur.fetchall()]
    return layout, [row for row in rows if row["endpoint"] and row["p256dh"] and row["auth"]]


def _record_success(layout, subscription_id):
    with app_v3.get_db() as db, db.cursor() as cur:
        if layout == "modern":
            cur.execute(
                "update push_subscriptions set last_success_at=now(),last_error=null,updated_at=now() "
                "where id=%s",
                (subscription_id,),
            )
        else:
            cur.execute(
                "update push_subscriptions set updated_at=now() where id=%s",
                (subscription_id,),
            )


def _record_failure(layout, subscription_id, exc):
    status = getattr(getattr(exc, "response", None), "status_code", None)
    with app_v3.get_db() as db, db.cursor() as cur:
        if layout == "modern":
            if status in {404, 410}:
                cur.execute(
                    "update push_subscriptions set active=false,last_error=%s,updated_at=now() where id=%s",
                    (f"expired:{status}", subscription_id),
                )
            else:
                cur.execute(
                    "update push_subscriptions set last_error=%s,updated_at=now() where id=%s",
                    (str(exc)[:500], subscription_id),
                )
        elif status in {404, 410}:
            cur.execute(
                "update push_subscriptions set active=false,updated_at=now() where id=%s",
                (subscription_id,),
            )
        else:
            cur.execute(
                "update push_subscriptions set updated_at=now() where id=%s",
                (subscription_id,),
            )


def send_push(title, body, url="/?open=bale-jobs", tag="aquagold-work", *, user_id=None, timeout=6):
    payload = json.dumps(
        {"title": title, "body": body, "url": url, "tag": tag},
        ensure_ascii=False,
    )
    layout, rows = _load_subscriptions(user_id=user_id)
    sent = failed = 0
    for sub in rows:
        try:
            aqua_push_runtime.webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=payload,
                vapid_private_key=aqua_push_runtime._private(),
                vapid_claims={"sub": aqua_push_runtime.SUBJECT},
                timeout=timeout,
            )
            sent += 1
            _record_success(layout, sub["id"])
        except aqua_push_runtime.WebPushException as exc:
            failed += 1
            _record_failure(layout, sub["id"], exc)
        except Exception as exc:
            failed += 1
            app_v3.logger.warning("push_failed: %s", exc)
    return {"subscriptions": len(rows), "sent": sent, "failed": failed}


@app_v3.roles_required("technician")
def push_status_compat():
    _, rows = _load_subscriptions(user_id=request.current_user["user_id"])
    return jsonify({"supported": True, "active": bool(rows), "subscriptions": len(rows)})


@app_v3.roles_required("technician")
def push_subscribe_compat():
    aqua_push_runtime._schema()
    data = request.get_json(silent=True) or {}
    keys = data.get("keys") or {}
    endpoint = str(data.get("endpoint") or "").strip()
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()
    if not endpoint.startswith("https://") or not p256dh or not auth:
        return jsonify({"error": "اشتراک Push معتبر نیست"}), 400

    with app_v3.get_db() as db, db.cursor() as cur:
        layout = _layout(cur)
        if layout == "modern":
            cur.execute(
                """insert into push_subscriptions(user_id,endpoint,p256dh,auth,user_agent,active,updated_at)
                values(%s,%s,%s,%s,%s,true,now())
                on conflict(endpoint) do update set
                  user_id=excluded.user_id,p256dh=excluded.p256dh,auth=excluded.auth,
                  user_agent=excluded.user_agent,active=true,last_error=null,updated_at=now()
                returning id""",
                (
                    request.current_user["user_id"],
                    endpoint[:4000],
                    p256dh[:1000],
                    auth[:1000],
                    (request.user_agent.string or "")[:500],
                ),
            )
            row = cur.fetchone()
        else:
            subscription = json.dumps(
                {
                    "endpoint": endpoint[:4000],
                    "keys": {"p256dh": p256dh[:1000], "auth": auth[:1000]},
                }
            )
            cur.execute(
                """update push_subscriptions
                set user_id=%s,subscription=%s::jsonb,active=true,updated_at=now()
                where subscription->>'endpoint'=%s returning id""",
                (str(request.current_user["user_id"]), subscription, endpoint[:4000]),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """insert into push_subscriptions(user_id,subscription,active,updated_at)
                    values(%s,%s::jsonb,true,now()) returning id""",
                    (str(request.current_user["user_id"]), subscription),
                )
                row = cur.fetchone()
    return jsonify({"ok": True, "id": str(row["id"])})


@app_v3.roles_required("technician")
def push_unsubscribe_compat():
    aqua_push_runtime._schema()
    endpoint = str((request.get_json(silent=True) or {}).get("endpoint") or "").strip()
    with app_v3.get_db() as db, db.cursor() as cur:
        layout = _layout(cur)
        if layout == "modern":
            if endpoint:
                cur.execute(
                    "update push_subscriptions set active=false,updated_at=now() "
                    "where user_id=%s and endpoint=%s",
                    (request.current_user["user_id"], endpoint),
                )
            else:
                cur.execute(
                    "update push_subscriptions set active=false,updated_at=now() where user_id=%s",
                    (request.current_user["user_id"],),
                )
        elif endpoint:
            cur.execute(
                "update push_subscriptions set active=false,updated_at=now() "
                "where user_id=%s and subscription->>'endpoint'=%s",
                (str(request.current_user["user_id"]), endpoint),
            )
        else:
            cur.execute(
                "update push_subscriptions set active=false,updated_at=now() where user_id=%s",
                (str(request.current_user["user_id"]),),
            )
    return jsonify({"ok": True})


@app_v3.roles_required("technician")
def push_test_compat():
    result = send_push(
        "AquaGold",
        "اعلان تست با موفقیت ارسال شد. اگر برنامه بسته باشد هم باید این پیام را ببینی.",
        url="/?open=dashboard",
        tag="aquagold-push-test",
        user_id=request.current_user["user_id"],
        timeout=8,
    )
    if result["subscriptions"] == 0:
        return jsonify({"error": "برای این گوشی اشتراک Push فعالی ثبت نشده؛ اول اعلان را فعال کن."}), 409
    code = 200 if result["sent"] else 502
    return jsonify({"ok": result["sent"] > 0, "sent": result["sent"], "failed": result["failed"]}), code


# The Bale wrapper resolves aqua_push_runtime.send_push at call time, so replacing
# the module function fixes automatic Bale notifications without touching intake.
aqua_push_runtime.send_push = send_push
app_v3.app.view_functions["push_status"] = push_status_compat
app_v3.app.view_functions["push_subscribe"] = push_subscribe_compat
app_v3.app.view_functions["push_unsubscribe"] = push_unsubscribe_compat
if "aqua_push_test" in app_v3.app.view_functions:
    app_v3.app.view_functions["aqua_push_test"] = push_test_compat
