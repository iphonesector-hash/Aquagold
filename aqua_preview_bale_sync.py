"""Preview-only, read-only mirror of live Bale inbox rows from the main database.

The Preview database stays isolated for all edits. When AQUAGOLD_MAIN_DATABASE_URL
is configured in the Preview environment, only new/review Bale inbox rows are
read from main and copied into Preview with customer/service foreign keys cleared.
No write is ever issued against the main connection.
"""
from __future__ import annotations

import os
from functools import wraps

import psycopg
from psycopg.rows import dict_row

import app_v3
from aquagold_validation import ValidationError


def _is_preview():
    return (os.getenv("VERCEL_ENV") or os.getenv("AQUAGOLD_ENV") or "").lower() == "preview"


def _main_url():
    value = os.getenv("AQUAGOLD_MAIN_DATABASE_URL", "").strip()
    return value if value.startswith(("postgres://", "postgresql://")) else ""


def _sync_live_bale_inbox():
    main_url = _main_url()
    if not (_is_preview() and main_url):
        return 0
    try:
        with psycopg.connect(
            main_url,
            row_factory=dict_row,
            connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=5000",
        ) as source, source.cursor() as src:
            src.execute(
                """
                select id,bale_update_id,chat_id,chat_title,message_id,sender_id,sender_name,
                       raw_text,customer_name,phone,address,job_type,status,received_amount,
                       cancel_reason,parsed,received_at,completed_at,cancelled_at,updated_at
                from bale_jobs
                where status in ('new','review')
                order by received_at desc
                limit 300
                """
            )
            rows = src.fetchall()
        if not rows:
            return 0
        inserted = 0
        with app_v3.get_db() as db, db.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    insert into bale_jobs(
                      id,bale_update_id,chat_id,chat_title,message_id,sender_id,sender_name,
                      raw_text,customer_name,phone,address,job_type,customer_id,service_visit_id,
                      status,received_amount,cancel_reason,parsed,received_at,completed_at,cancelled_at,updated_at
                    ) values(
                      %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,null,null,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    on conflict do nothing
                    returning id
                    """,
                    (
                        row["id"], row.get("bale_update_id"), row["chat_id"], row.get("chat_title"),
                        row["message_id"], row.get("sender_id"), row.get("sender_name"), row["raw_text"],
                        row.get("customer_name"), row.get("phone"), row.get("address"), row.get("job_type"),
                        row["status"], row.get("received_amount"), row.get("cancel_reason"),
                        app_v3.Jsonb(row.get("parsed") or {}), row["received_at"], row.get("completed_at"),
                        row.get("cancelled_at"), row.get("updated_at") or row["received_at"],
                    ),
                )
                if cur.fetchone():
                    inserted += 1
        return inserted
    except Exception as exc:
        app_v3.logger.warning("preview_bale_sync_failed detail=%s", str(exc)[:300])
        return 0


@app_v3.roles_required("technician")
def preview_bale_jobs_list():
    _sync_live_bale_inbox()
    status = (app_v3.request.args.get("status") or "new").strip()
    if status not in {"new", "completed", "cancelled", "review", "all"}:
        raise ValidationError("وضعیت کار معتبر نیست")
    with app_v3.get_db() as db, db.cursor() as cur:
        if status == "all":
            cur.execute("select * from bale_jobs order by received_at desc limit 300")
        else:
            cur.execute("select * from bale_jobs where status=%s order by received_at desc limit 300", (status,))
        rows = [app_v3.row_json(row) for row in cur.fetchall()]
    return app_v3.jsonify(rows)


@app_v3.roles_required("technician")
def preview_bale_jobs_counts():
    _sync_live_bale_inbox()
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select status,count(*)::int count from bale_jobs group by status")
        counts = {row["status"]: row["count"] for row in cur.fetchall()}
    return app_v3.jsonify({
        "new": counts.get("new", 0), "review": counts.get("review", 0),
        "completed": counts.get("completed", 0), "cancelled": counts.get("cancelled", 0),
    })


if _is_preview():
    # bale_bridge has already registered these endpoints before this module loads.
    app_v3.app.view_functions["bale_jobs_list"] = preview_bale_jobs_list
    app_v3.app.view_functions["bale_jobs_counts"] = preview_bale_jobs_counts
