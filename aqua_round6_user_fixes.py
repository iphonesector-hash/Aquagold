"""Round 6 branch-only fixes requested by the user.

Scope:
- persist Smart Intake payment method instead of dropping it;
- compute a six-month next-service date from each completed visit;
- expose reliable payment breakdown and customer due-date endpoints;
- send a once-per-due-date Web Push reminder from a dedicated daily cron.

This module is imported only on the isolated QA branch. Production/main stays untouched.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import jsonify, request

import app_v3
import aqua_push_runtime
import bale_reports

TEHRAN = ZoneInfo("Asia/Tehran")
PAYMENT_VALUES = {"cash", "transfer", "card"}


def _payment_key(value):
    method = str(value or "").strip().lower().replace("\u200c", " ")
    if method == "cash" or "نقد" in method:
        return "cash"
    if method == "transfer" or re.search(r"کارت\s*به\s*کارت|card.?to.?card", method):
        return "transfer"
    if method in {"card", "pos"} or re.search(r"کارت\s*خوان|کارتخوان|card.?reader", method):
        return "card"
    return None


def _fix_visit_after_write(visit_id, *, payment_method=None, force_completed=False):
    if not visit_id:
        return
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select status from service_visits where id=%s::uuid", (str(visit_id),))
        row = cur.fetchone()
        if not row:
            return
        status = str(row.get("status") or "")
        if force_completed and status not in {"cancelled", "scheduled"}:
            status = "completed"
        method = _payment_key(payment_method)
        if status == "completed":
            cur.execute(
                """update service_visits
                   set payment_method=coalesce(%s,payment_method),
                       status='completed',
                       next_service_at=coalesce(visited_at,created_at) + interval '6 months',
                       updated_at=now()
                   where id=%s::uuid""",
                (method, str(visit_id)),
            )
        elif status in {"cancelled", "scheduled"}:
            cur.execute(
                """update service_visits
                   set payment_method=coalesce(%s,payment_method),
                       next_service_at=null,
                       updated_at=now()
                   where id=%s::uuid""",
                (method, str(visit_id)),
            )
        elif method:
            cur.execute(
                "update service_visits set payment_method=%s,updated_at=now() where id=%s::uuid",
                (method, str(visit_id)),
            )


_original_smart_register = app_v3.app.view_functions.get("smart_register")


def _smart_register_round6():
    data = request.get_json(silent=True) or {}
    parsed = data.get("parsed") if isinstance(data.get("parsed"), dict) else {}
    method = _payment_key(parsed.get("payment_method") or data.get("payment_method"))
    response = app_v3.app.make_response(_original_smart_register())
    if response.status_code < 300 and response.is_json:
        payload = response.get_json(silent=True) or {}
        _fix_visit_after_write(payload.get("visit_id"), payment_method=method, force_completed=True)
    return response


if _original_smart_register is not None:
    app_v3.app.view_functions["smart_register"] = _smart_register_round6


_original_job_create = app_v3.app.view_functions.get("job_create")


def _job_create_round6():
    data = request.get_json(silent=True) or {}
    response = app_v3.app.make_response(_original_job_create())
    if response.status_code < 300 and response.is_json:
        payload = response.get_json(silent=True) or {}
        status = str(data.get("status") or "completed")
        _fix_visit_after_write(
            payload.get("id"),
            payment_method=data.get("payment_method"),
            force_completed=(status == "completed"),
        )
    return response


if _original_job_create is not None:
    app_v3.app.view_functions["job_create"] = _job_create_round6


_original_job_update = app_v3.app.view_functions.get("job_update")


def _job_update_round6(jid):
    data = request.get_json(silent=True) or {}
    response = app_v3.app.make_response(_original_job_update(jid))
    if response.status_code < 300:
        _fix_visit_after_write(jid, payment_method=data.get("payment_method"), force_completed=False)
    return response


if _original_job_update is not None:
    app_v3.app.view_functions["job_update"] = _job_update_round6


@app_v3.app.get("/api/reports/payment-methods-v2")
@app_v3.token_required
def aqua_round6_payment_methods():
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            r"""
            with normalized as (
              select received_amount,
                     case
                       when lower(coalesce(payment_method,''))='cash' or coalesce(payment_method,'') ilike '%نقد%' then 'cash'
                       when lower(coalesce(payment_method,''))='transfer'
                            or replace(coalesce(payment_method,''), '‌', ' ') ~* 'کارت[[:space:]]*به[[:space:]]*کارت|card.?to.?card' then 'transfer'
                       when lower(coalesce(payment_method,'')) in ('card','pos')
                            or replace(coalesce(payment_method,''), '‌', ' ') ~* 'کارت[[:space:]]*خوان|کارتخوان|card.?reader' then 'card'
                       when replace(coalesce(raw_chat_input,''), '‌', ' ') ~* 'کارت[[:space:]]*به[[:space:]]*کارت' then 'transfer'
                       when replace(coalesce(raw_chat_input,''), '‌', ' ') ~* 'کارت[[:space:]]*خوان|کارتخوان|(^|[^[:alpha:]])pos([^[:alpha:]]|$)' then 'card'
                       when coalesce(raw_chat_input,'') ~* 'نقد' then 'cash'
                       else 'unclassified'
                     end method
              from service_visits
              where status not in ('cancelled','scheduled')
            )
            select method,count(*)::int services,coalesce(sum(received_amount),0)::bigint amount
            from normalized group by method order by amount desc
            """
        )
        rows = [dict(row) for row in cur.fetchall()]
    totals = {"cash": 0, "transfer": 0, "card": 0, "unclassified": 0}
    counts = {"cash": 0, "transfer": 0, "card": 0, "unclassified": 0}
    for row in rows:
        key = str(row.get("method") or "unclassified")
        if key not in totals:
            key = "unclassified"
        totals[key] += int(row.get("amount") or 0)
        counts[key] += int(row.get("services") or 0)
    return jsonify({"totals": totals, "counts": counts})


def _customer_due_rows(*, days=None):
    where = ""
    params = []
    if days is not None:
        where = "and due.next_service_at <= now() + (%s * interval '1 day')"
        params.append(int(days))
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute(
            f"""
            select c.id customer_id,c.first_name,c.last_name,c.address,
                   (select phone from customer_phones p where p.customer_id=c.id order by p.is_primary desc,p.id limit 1) phone,
                   due.service_visit_id,due.last_service_at,due.next_service_at,due.service_type,
                   case when due.next_service_at is not null and due.next_service_at<=now() then true else false end due_now
            from customers_v2 c
            left join lateral (
              select v.id service_visit_id,
                     coalesce(v.visited_at,v.created_at) last_service_at,
                     coalesce(v.next_service_at,coalesce(v.visited_at,v.created_at)+interval '6 months') next_service_at,
                     v.service_type
              from service_visits v
              where v.customer_id=c.id and v.status not in ('cancelled','scheduled')
              order by coalesce(v.visited_at,v.created_at) desc,v.created_at desc
              limit 1
            ) due on true
            where c.archived=false {where}
            order by due.next_service_at nulls last,c.last_name,c.first_name
            """,
            tuple(params),
        )
        rows = [app_v3.row_json(row) for row in cur.fetchall()]
    for row in rows:
        row["customer_id"] = str(row["customer_id"])
        if row.get("service_visit_id") is not None:
            row["service_visit_id"] = str(row["service_visit_id"])
    return rows


@app_v3.app.get("/api/customer-service-due")
@app_v3.token_required
def aqua_round6_customer_service_due():
    return jsonify(_customer_due_rows())


@app_v3.app.get("/api/reminders-v2")
@app_v3.token_required
def aqua_round6_reminders():
    days = max(1, min(app_v3.as_int(request.args.get("days"), 30), 365))
    rows = [row for row in _customer_due_rows(days=days) if row.get("next_service_at")]
    out = []
    for row in rows:
        key = row["customer_id"]
        out.append({
            "id": row.get("service_visit_id") or f"due-{key}",
            "customer_id": key,
            "next_service_at": row.get("next_service_at"),
            "service_type": row.get("service_type") or "سرویس دوره‌ای",
            "name": " ".join(x for x in [str(row.get("first_name") or "").strip(), str(row.get("last_name") or "").strip()] if x).strip(),
            "phone": row.get("phone"),
            "address": row.get("address"),
            "due_now": bool(row.get("due_now")),
        })
    return jsonify(out)


def _ensure_due_push_log(cur):
    cur.execute(
        """create table if not exists service_due_push_log(
               customer_id uuid not null references customers_v2(id) on delete cascade,
               due_on date not null,
               service_visit_id uuid references service_visits(id) on delete set null,
               sent_at timestamptz not null default now(),
               primary key(customer_id,due_on)
           )"""
    )


def _unsent_due_rows():
    with app_v3.get_db() as db, db.cursor() as cur:
        _ensure_due_push_log(cur)
        cur.execute(
            """
            with latest as (
              select distinct on (v.customer_id)
                     v.customer_id,v.id service_visit_id,
                     coalesce(v.next_service_at,coalesce(v.visited_at,v.created_at)+interval '6 months') next_service_at
              from service_visits v
              where v.status not in ('cancelled','scheduled')
              order by v.customer_id,coalesce(v.visited_at,v.created_at) desc,v.created_at desc
            )
            select l.customer_id,l.service_visit_id,l.next_service_at,
                   (l.next_service_at at time zone 'Asia/Tehran')::date due_on,
                   coalesce(nullif(trim(c.last_name),''),nullif(trim(c.first_name),''),'بدون نام') customer_name
            from latest l
            join customers_v2 c on c.id=l.customer_id and c.archived=false
            left join service_due_push_log sent
              on sent.customer_id=l.customer_id
             and sent.due_on=(l.next_service_at at time zone 'Asia/Tehran')::date
            where l.next_service_at<=now() and sent.customer_id is null
            order by l.next_service_at
            limit 200
            """
        )
        return [dict(row) for row in cur.fetchall()]


def _mark_due_push_sent(rows):
    if not rows:
        return
    with app_v3.get_db() as db, db.cursor() as cur:
        _ensure_due_push_log(cur)
        for row in rows:
            cur.execute(
                """insert into service_due_push_log(customer_id,due_on,service_visit_id,sent_at)
                   values(%s,%s,%s,now()) on conflict(customer_id,due_on) do nothing""",
                (row["customer_id"], row["due_on"], row.get("service_visit_id")),
            )


@app_v3.app.get("/api/cron/service-reminders")
@app_v3.limiter.exempt
def aqua_round6_service_reminder_cron():
    if not bale_reports._cron_authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    rows = _unsent_due_rows()
    if not rows:
        return jsonify({"ok": True, "due": 0, "sent": 0})
    names = [str(row.get("customer_name") or "بدون نام") for row in rows[:3]]
    suffix = "" if len(rows) <= 3 else f" و {len(rows)-3} مشتری دیگر"
    body = f"موعد سرویس ۶ ماهه {len(rows)} مشتری رسیده: " + "، ".join(names) + suffix
    result = aqua_push_runtime.send_push(
        "⏰ موعد سرویس AquaGold",
        body,
        url="/?open=reminders",
        tag=f"service-due-{datetime.now(TEHRAN).date().isoformat()}",
    )
    if int(result.get("sent") or 0) > 0:
        _mark_due_push_sent(rows)
    return jsonify({"ok": True, "due": len(rows), **result})
