"""Web Push for new Bale jobs and client UI injection."""
from __future__ import annotations

import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import jsonify, request
from pywebpush import WebPushException, webpush

import app_v3
import bale_bridge

ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
SUBJECT = "https://aquagold-db.vercel.app"
_SCHEMA_READY = False


def _b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _key():
    raw = hashlib.sha256((str(app_v3.app.secret_key) + "|aquagold-push-v1").encode()).digest()
    return ec.derive_private_key((int.from_bytes(raw, "big") % (ORDER - 1)) + 1, ec.SECP256R1())


def _public():
    return _b64(
        _key().public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    )


def _private():
    return _b64(
        _key().private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def _schema():
    """Ensure the fallback Push schema once per warm serverless instance."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """create table if not exists push_subscriptions(
              id uuid primary key default gen_random_uuid(),
              user_id bigint not null references users(id) on delete cascade,
              endpoint text not null unique,
              p256dh text not null,
              auth text not null,
              user_agent text,
              active boolean not null default true,
              created_at timestamptz not null default now(),
              updated_at timestamptz not null default now(),
              last_success_at timestamptz,
              last_error text
            )"""
        )
        cur.execute(
            "create index if not exists push_subscriptions_active_idx "
            "on push_subscriptions(active) where active=true"
        )
        cur.execute(
            "create index if not exists push_subscriptions_user_idx "
            "on push_subscriptions(user_id,updated_at desc)"
        )
    _SCHEMA_READY = True


def send_push(title, body, url="/?open=bale-jobs", tag="aquagold-work"):
    _schema()
    payload = json.dumps(
        {"title": title, "body": body, "url": url, "tag": tag},
        ensure_ascii=False,
    )
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            "select id,endpoint,p256dh,auth from push_subscriptions where active=true"
        )
        rows = [dict(row) for row in cur.fetchall()]

    sent = 0
    failed = 0
    for row in rows:
        try:
            webpush(
                subscription_info={
                    "endpoint": row["endpoint"],
                    "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
                },
                data=payload,
                vapid_private_key=_private(),
                vapid_claims={"sub": SUBJECT},
                timeout=6,
            )
            sent += 1
            with app_v3.get_db() as db, db.cursor() as cur:
                cur.execute(
                    "update push_subscriptions set last_success_at=now(),last_error=null,updated_at=now() where id=%s",
                    (row["id"],),
                )
        except WebPushException as exc:
            failed += 1
            status = getattr(getattr(exc, "response", None), "status_code", None)
            with app_v3.get_db() as db, db.cursor() as cur:
                if status in {404, 410}:
                    cur.execute(
                        "update push_subscriptions set active=false,last_error=%s,updated_at=now() where id=%s",
                        (f"expired:{status}", row["id"]),
                    )
                else:
                    cur.execute(
                        "update push_subscriptions set last_error=%s,updated_at=now() where id=%s",
                        (str(exc)[:500], row["id"]),
                    )
        except Exception as exc:
            failed += 1
            app_v3.logger.warning("push_failed: %s", exc)
    return {"sent": sent, "failed": failed}


@app_v3.app.get("/api/push/public-key")
@app_v3.roles_required("technician")
def push_public_key():
    return jsonify({"public_key": _public()})


@app_v3.app.get("/api/push/status")
@app_v3.roles_required("technician")
def push_status():
    _schema()
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            "select count(*)::int n from push_subscriptions where active=true and user_id=%s",
            (request.current_user["user_id"],),
        )
        count = int((cur.fetchone() or {}).get("n") or 0)
    return jsonify({"supported": True, "active": count > 0, "subscriptions": count})


@app_v3.app.post("/api/push/subscribe")
@app_v3.roles_required("technician")
def push_subscribe():
    _schema()
    data = request.get_json(silent=True) or {}
    keys = data.get("keys") or {}
    endpoint = str(data.get("endpoint") or "").strip()
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()
    if not endpoint.startswith("https://") or not p256dh or not auth:
        return jsonify({"error": "اشتراک Push معتبر نیست"}), 400

    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            """insert into push_subscriptions(user_id,endpoint,p256dh,auth,user_agent,active,updated_at)
               values(%s,%s,%s,%s,%s,true,now())
               on conflict(endpoint) do update set
                 user_id=excluded.user_id,
                 p256dh=excluded.p256dh,
                 auth=excluded.auth,
                 user_agent=excluded.user_agent,
                 active=true,
                 last_error=null,
                 updated_at=now()
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
    return jsonify({"ok": True, "id": str(row["id"])})


@app_v3.app.delete("/api/push/subscribe")
@app_v3.roles_required("technician")
def push_unsubscribe():
    _schema()
    endpoint = str((request.get_json(silent=True) or {}).get("endpoint") or "").strip()
    with app_v3.get_db() as db, db.cursor() as cur:
        if endpoint:
            cur.execute(
                "update push_subscriptions set active=false,updated_at=now() where user_id=%s and endpoint=%s",
                (request.current_user["user_id"], endpoint),
            )
        else:
            cur.execute(
                "update push_subscriptions set active=false,updated_at=now() where user_id=%s",
                (request.current_user["user_id"],),
            )
    return jsonify({"ok": True})


_original_webhook = app_v3.app.view_functions.get("bale_webhook")


def _webhook(secret):
    response = app_v3.app.make_response(_original_webhook(secret))
    try:
        result = response.get_json(silent=True) if response.is_json else {}
        update = request.get_json(silent=True) or {}
        message, text, *_ = bale_bridge._message_payload(update)
        if result.get("registered") and result.get("job_id") and message and text:
            parsed = bale_bridge._extract_job(text) or {}
            send_push(
                "کار جدید AquaGold",
                f"{parsed.get('customer_name') or 'کار جدید'} • {parsed.get('job_type') or 'سرویس'}",
                tag=f"bale-{result['job_id']}",
            )
    except Exception as exc:
        app_v3.logger.warning("bale_push_hook_failed: %s", exc)
    return response


if _original_webhook:
    app_v3.app.view_functions["bale_webhook"] = _webhook


PWA_SAFE_STYLE = """<style id=\"aqua-pwa-safe-area\">
.aq-float{display:none!important}
@media(max-width:1023px){
  .topbar{padding-top:calc(8px + env(safe-area-inset-top,0px))!important}
}
@media(display-mode:standalone) and (max-width:1023px){
  html,body{min-height:100dvh}
  .topbar{padding-top:calc(12px + env(safe-area-inset-top,0px))!important}
}
</style>"""
POLISH_SCRIPT = '<script src="/aqua-system-polish.js?v=20260831-3"></script>'


@app_v3.app.after_request
def _inject(response):
    try:
        if request.path in {"/", "/index.html"} and response.mimetype == "text/html":
            response.direct_passthrough = False
            body = response.get_data(as_text=True)
            insert = ""
            if 'id="aqua-pwa-safe-area"' not in body:
                insert += PWA_SAFE_STYLE
            if "/aqua-system-polish.js" not in body:
                insert += POLISH_SCRIPT
            if insert:
                pos = body.lower().find("</head>")
                if pos >= 0:
                    body = body[:pos] + insert + body[pos:]
                    response.set_data(body)
                    response.headers["Content-Length"] = str(len(response.get_data()))
            response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("push_ui_inject_failed: %s", exc)
    return response
