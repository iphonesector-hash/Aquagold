"""Branch-only targeted repairs requested on 2026-09-02.

Scope is intentionally narrow:
- fast, bounded live web search for market-price questions;
- real CRM mutation for unambiguous Aqua commands that correct a service amount;
- PATCH support for existing expenses;
- tiny HTML/UI hooks for edit buttons/modals and dashboard company-share amount.

No auth, navigation, splash, layout, theme or global styling is changed.
"""
from __future__ import annotations

import re
import time
from decimal import Decimal

from flask import jsonify, request

import app_v3
import aqua_ai
from aquagold_validation import (
    ValidationError,
    choice as valid_choice,
    integer as valid_integer,
    text as valid_text,
)


# ---------------------------------------------------------------------------
# 1) Fast live web search for prices/current information
# ---------------------------------------------------------------------------
_PREVIOUS_GROQ_ANSWER = aqua_ai._groq_answer
_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _is_weather_query(text):
    value = re.sub(r"\s+", " ", str(text or "").replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک")).strip()
    marks = (
        "آب و هوا", "آب‌وهوا", "اب و هوا", "هواشناسی", "وضعیت هوا",
        "دمای هوا", "آب و هوای", "هوای امروز",
    )
    return any(mark in value for mark in marks) or bool(re.search(r"هوای\s+\S+", value))


def _live_search_answer(settings, text):
    key = str((settings or {}).get("groq_api_key") or "").strip()
    if not key:
        raise RuntimeError("کلید Groq تنظیم نشده است؛ از تنظیمات هوش آکوا آن را بررسی کن.")

    # Compound latest uses the heavier advanced-search path. Price lookups only
    # need the basic search path, so use the stable 2025-07-23 version with a
    # deliberately tiny request to avoid the 413 seen in the current preview.
    endpoint = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Groq-Model-Version": "2025-07-23",
    }
    user_text = re.sub(r"\s+", " ", str(text or "")).strip()[:320]
    weather = _is_weather_query(text)
    if weather:
        compact_prompt = (
            "با web_search آب‌وهوای فعلی را پیدا کن و کوتاه به فارسی جواب بده. "
            "شهر، دما، وضعیت آسمان و زمان گزارش را روشن بنویس؛ حدس نزن. درخواست: "
            + user_text
        )
        attempts = (("groq/compound-mini", 18), ("groq/compound", 20))
    else:
        compact_prompt = (
            "با web_search اطلاعات لحظه‌ای این درخواست را پیدا کن و کوتاه به فارسی جواب بده. "
            "برای قیمت بازار ایران نوع دارایی، واحد تومان و زمان تقریبی را روشن بنویس؛ حدس نزن. درخواست: "
            + user_text
        )
        attempts = (("groq/compound-mini", 9), ("groq/compound", 10))
    messages = [{"role": "user", "content": compact_prompt}]
    last_error = None
    for model, timeout in attempts:
        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "compound_custom": {"tools": {"enabled_tools": ["web_search"]}},
            }
            data = aqua_ai._post_json(endpoint, payload, headers, timeout=timeout)
            answer = str(data["choices"][0]["message"].get("content") or "").strip()
            if answer:
                return answer
            raise RuntimeError("live search returned an empty answer")
        except (RuntimeError, KeyError, IndexError, TypeError) as exc:
            last_error = exc
            app_v3.logger.warning(
                "aqua_targeted_live_search_failed model=%s detail=%s",
                model,
                str(exc)[:300],
            )
    raise RuntimeError("جست‌وجوی زنده آریا پاسخ نداد؛ اتصال Groq یا Web Search را بررسی کن.") from last_error


def _targeted_groq_answer(settings, text, history, context):
    live = aqua_ai._needs_live_web_search(text) or _is_weather_query(text)
    if not live:
        return _PREVIOUS_GROQ_ANSWER(settings, text, history, context)
    started = time.monotonic()
    try:
        return _live_search_answer(settings, text)
    except RuntimeError:
        if _is_weather_query(text):
            return "الان نتونستم آب‌وهوای زنده را از وب بگیرم؛ چند لحظه بعد دوباره بپرس. هیچ حدسی نزدم."
        raise
    finally:
        app_v3.logger.info(
            "aqua_targeted_live_answer_ms=%d",
            int((time.monotonic() - started) * 1000),
        )


aqua_ai._groq_answer = _targeted_groq_answer


# ---------------------------------------------------------------------------
# 2) Real Aqua CRM correction for service received amount
# ---------------------------------------------------------------------------
_EDIT_WORDS = (
    "درست کن",
    "اصلاح کن",
    "تغییر بده",
    "تغییرش بده",
    "ویرایش کن",
    "ویرایشش کن",
    "بکنش",
    "کنش",
)
_AMOUNT_WORDS = ("مبلغ", "پرداختی", "دریافتی", "فاکتور", "قیمت")


def _normalise_text(value):
    text = str(value or "").translate(_FA_DIGITS).replace("ي", "ی").replace("ك", "ک")
    text = text.replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip()


def _service_edit_intent(text):
    value = _normalise_text(text)
    return (
        "مشتری" in value
        and any(word in value for word in _EDIT_WORDS)
        and any(word in value for word in _AMOUNT_WORDS)
    )


def _customer_name_from_command(text):
    value = _normalise_text(text)
    patterns = (
        r"به\s+اسم\s+(.+?)(?=\s+(?:که|مربوط|رو|را|مبلغ|پرداختی|دریافتی|برای|با)\b|[،,.]|$)",
        r"مشتری\s+(.+?)(?=\s+(?:که|مربوط|رو|را|مبلغ|پرداختی|دریافتی|برای|با)\b|[،,.]|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            name = match.group(1).strip(" ،,.-")
            name = re.sub(r"^(?:به\s+اسم\s+)", "", name).strip()
            if 1 <= len(name) <= 80:
                return name
    return ""


def _amounts_from_command(text):
    value = _normalise_text(text)
    raw_values = re.findall(r"(?<!\d)(\d[\d,٬،\s]{3,}\d|\d{4,})(?!\d)", value)
    amounts = []
    for raw in raw_values:
        digits = re.sub(r"\D", "", raw)
        if not digits:
            continue
        number = int(digits)
        if number >= 1000:
            amounts.append(number)
    result = []
    for amount in amounts:
        if not result or result[-1] != amount:
            result.append(amount)
    return result


def _tehran_day_mode(text):
    value = _normalise_text(text)
    if any(marker in value for marker in ("روز قبل", "دیروز", "روز گذشته")):
        return "yesterday"
    if "امروز" in value:
        return "today"
    return "latest"


def _format_money(value):
    return f"{int(value or 0):,}".replace(",", "٬")


def _correct_service_amount(text):
    name = _customer_name_from_command(text)
    amounts = _amounts_from_command(text)
    if not name:
        return jsonify({"answer": "برای ویرایش، نام مشتری را واضح بگو؛ مثلاً «مشتری میرزایی ...». چیزی تغییر ندادم."})
    if not amounts:
        return jsonify({"answer": "مبلغ جدید را در پیام پیدا نکردم؛ چیزی تغییر ندادم."})

    new_amount = amounts[-1]
    old_amount = amounts[-2] if len(amounts) >= 2 else None
    day_mode = _tehran_day_mode(text)
    like_name = f"%{name}%"

    with app_v3.get_db() as db, db.cursor() as cur:
        where_day = ""
        params = [like_name, like_name]
        if day_mode == "yesterday":
            where_day = "and (coalesce(sv.visited_at,sv.created_at) at time zone 'Asia/Tehran')::date=(now() at time zone 'Asia/Tehran')::date-1"
        elif day_mode == "today":
            where_day = "and (coalesce(sv.visited_at,sv.created_at) at time zone 'Asia/Tehran')::date=(now() at time zone 'Asia/Tehran')::date"

        cur.execute(
            f"""
            select sv.id,sv.customer_id,sv.invoice_amount,sv.received_amount,
                   sv.company_share_percent,sv.company_share_amount,sv.status,
                   coalesce(sv.visited_at,sv.created_at) visit_date,
                   trim(concat_ws(' ',c.first_name,c.last_name)) customer_name
            from service_visits sv
            join customers_v2 c on c.id=sv.customer_id
            where c.archived=false
              and (c.normalized_name ilike %s or c.last_name ilike %s)
              and coalesce(sv.status,'')<>'cancelled'
              {where_day}
            order by coalesce(sv.visited_at,sv.created_at) desc
            limit 10
            """,
            params,
        )
        rows = list(cur.fetchall())
        if old_amount is not None:
            exact_old = [row for row in rows if int(row["received_amount"] or 0) == old_amount]
            if exact_old:
                rows = exact_old

        if not rows:
            when = " مربوط به روز قبل" if day_mode == "yesterday" else " امروز" if day_mode == "today" else ""
            return jsonify({"answer": f"سرویس مشتری «{name}»{when} پیدا نشد؛ چیزی تغییر ندادم."})
        if len(rows) > 1:
            details = "، ".join(
                f"{row['customer_name']} {_format_money(row['received_amount'])} تومان"
                for row in rows[:4]
            )
            return jsonify({
                "answer": "چند سرویس مطابق این مشخصات پیدا شد و برای جلوگیری از تغییر اشتباه چیزی را عوض نکردم. "
                f"موارد نزدیک: {details}. مبلغ قبلی یا تاریخ دقیق‌تر را بگو."
            })

        row = rows[0]
        invoice_amount = int(row["invoice_amount"] or 0)
        received_before = int(row["received_amount"] or 0)
        pct = Decimal(str(row["company_share_percent"] or 0))
        value = _normalise_text(text)
        edit_invoice = any(marker in value for marker in ("مبلغ فاکتور", "قیمت کار", "مبلغ کار", "قیمت سرویس", "مبلغ سرویس"))
        if edit_invoice:
            invoice_amount = new_amount

        company_share = int(round(Decimal(new_amount) * pct / Decimal(100)))
        balance = max(invoice_amount - new_amount, 0)
        overpayment = max(new_amount - invoice_amount, 0)
        cur.execute(
            """
            update service_visits
            set invoice_amount=%s,received_amount=%s,amount=%s,
                company_share_amount=%s,customer_balance=%s,overpayment_amount=%s,updated_at=now()
            where id=%s
            """,
            (invoice_amount, new_amount, new_amount, company_share, balance, overpayment, row["id"]),
        )
        app_v3.audit(
            cur,
            "service_visit",
            row["id"],
            "aqua_ai_update_amount",
            before={"invoice": int(row["invoice_amount"] or 0), "received": received_before, "company_share": int(row["company_share_amount"] or 0)},
            after={"invoice": invoice_amount, "received": new_amount, "company_share": company_share},
        )

    when = "روز قبل" if day_mode == "yesterday" else "امروز" if day_mode == "today" else "آخرین سرویس"
    return jsonify({
        "answer": (
            f"انجام شد؛ مبلغ دریافتی {row['customer_name']} برای {when} واقعاً در دیتابیس "
            f"از {_format_money(received_before)} به {_format_money(new_amount)} تومان تغییر کرد. "
            f"سهم شرکت هم دوباره محاسبه شد و {_format_money(company_share)} تومان است."
        ),
        "action": {"type": "open_page", "page": "services"},
    })


_ORIGINAL_AQUA_CHAT = app_v3.app.view_functions.get("aqua_chat")


@app_v3.roles_required("technician")
@app_v3.limiter.limit("30 per minute; 500 per day")
def _aqua_chat_with_real_edits():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if _service_edit_intent(text):
        try:
            return _correct_service_amount(text)
        except ValidationError as exc:
            return jsonify({"answer": str(exc)}), 400
        except Exception:
            app_v3.logger.exception("aqua_targeted_service_edit_failed")
            return jsonify({"answer": "ویرایش مبلغ انجام نشد و هیچ تغییری ثبت نکردم؛ دوباره امتحان کن."}), 500
    return _ORIGINAL_AQUA_CHAT()


if _ORIGINAL_AQUA_CHAT is not None:
    app_v3.app.view_functions["aqua_chat"] = _aqua_chat_with_real_edits


# ---------------------------------------------------------------------------
# 3) Expense edit API
# ---------------------------------------------------------------------------
@app_v3.app.patch("/api/expenses/<uuid:eid>")
@app_v3.roles_required("technician")
def aqua_expense_update(eid):
    data = request.get_json(silent=True) or {}
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select * from expenses where id=%s", (eid,))
        before = cur.fetchone()
        if not before:
            return jsonify({"error": "هزینه پیدا نشد"}), 404

        amount = valid_integer(data.get("amount", before["amount"]), "مبلغ هزینه", minimum=1)
        title = valid_text(data.get("title", before["title"]), "عنوان هزینه", required=True, max_length=250)
        category = valid_choice(
            data.get("category", before["category"]),
            "دسته هزینه",
            {"goods", "fuel", "parking", "tools", "food", "other"},
            default="other",
        )
        notes = valid_text(data.get("notes", before["notes"]), "توضیحات", max_length=4000)
        cur.execute(
            """
            update expenses
            set category=%s,title=%s,amount=%s,notes=%s,updated_at=now()
            where id=%s
            returning id,category,title,amount,expense_date,notes
            """,
            (category, title, amount, notes, eid),
        )
        updated = cur.fetchone()
        app_v3.audit(
            cur,
            "expense",
            eid,
            "update",
            before={"title": before["title"], "amount": int(before["amount"] or 0), "category": before["category"]},
            after={"title": title, "amount": amount, "category": category},
        )
    return jsonify({**app_v3.row_json(updated), "id": str(updated["id"]), "message": "هزینه ویرایش شد"})


# ---------------------------------------------------------------------------
# 4) Minimal UI hooks. Existing CSS/classes are reused; no visual redesign.
# ---------------------------------------------------------------------------
TARGETED_MODAL_HTML = r'''
<div x-show="serviceEditOpen" x-cloak class="fixed inset-0 z-[95] bg-black/60 p-4 flex items-center justify-center" @click.self="serviceEditOpen=false">
  <div class="card p-5 w-full max-w-xl max-h-[90vh] overflow-auto">
    <div class="flex justify-between items-center gap-3"><h3 class="section-title">ویرایش سرویس ثبت‌شده</h3><button type="button" class="btn glass !py-2" @click="serviceEditOpen=false">بستن</button></div>
    <div class="grid md:grid-cols-2 gap-3 mt-4">
      <input x-model="serviceEdit.service_type" class="field" placeholder="نوع سرویس">
      <select x-model="serviceEdit.status" class="field"><option value="completed">تکمیل شده</option><option value="registered">ثبت شده</option><option value="scheduled">برنامه‌ریزی شده</option><option value="revisit">نیاز به مراجعه</option><option value="partial">تسویه ناقص</option><option value="unpaid">پرداخت نشده</option></select>
      <input x-model="serviceEdit.invoice_amount" inputmode="numeric" class="field" placeholder="مبلغ فاکتور">
      <input x-model="serviceEdit.received_amount" inputmode="numeric" class="field" placeholder="مبلغ دریافت‌شده">
      <textarea x-model="serviceEdit.description" class="field md:col-span-2" placeholder="شرح کار"></textarea>
    </div>
    <button type="button" class="btn primary w-full mt-4" :disabled="serviceEditBusy" @click="saveServiceEdit()" x-text="serviceEditBusy?'در حال ذخیره…':'ذخیره ویرایش'"></button>
  </div>
</div>
<div x-show="expenseEditOpen" x-cloak class="fixed inset-0 z-[95] bg-black/60 p-4 flex items-center justify-center" @click.self="expenseEditOpen=false">
  <div class="card p-5 w-full max-w-xl max-h-[90vh] overflow-auto">
    <div class="flex justify-between items-center gap-3"><h3 class="section-title">ویرایش هزینه</h3><button type="button" class="btn glass !py-2" @click="expenseEditOpen=false">بستن</button></div>
    <div class="grid gap-3 mt-4">
      <select x-model="expenseEdit.category" class="field"><option value="goods">خرید جنس/قطعه</option><option value="fuel">بنزین/سوخت</option><option value="parking">پارکینگ</option><option value="tools">ابزار/تعمیر</option><option value="food">غذا</option><option value="other">متفرقه</option></select>
      <input x-model="expenseEdit.title" class="field" placeholder="عنوان هزینه">
      <input x-model="expenseEdit.amount" inputmode="numeric" class="field" placeholder="مبلغ">
      <textarea x-model="expenseEdit.notes" class="field" placeholder="توضیحات"></textarea>
    </div>
    <button type="button" class="btn primary w-full mt-4" :disabled="expenseEditBusy" @click="saveExpenseEdit()" x-text="expenseEditBusy?'در حال ذخیره…':'ذخیره ویرایش'"></button>
  </div>
</div>
'''


@app_v3.app.get("/aqua-targeted-fix.js")
def aqua_targeted_fix_js():
    return app_v3.send_from_directory(".", "aqua_targeted_fix.js", mimetype="application/javascript", max_age=0)


@app_v3.app.after_request
def inject_aqua_targeted_fix(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response
        response.direct_passthrough = False
        body = response.get_data(as_text=True)
        body = body.replace(
            "x-text=\"Number(financeSettings.company_share_percent||0).toLocaleString('fa-IR')+'٪'\"",
            "x-text=\"money(stats.today?.company_share)+' تومان'\"",
            1,
        )
        body = body.replace(
            "x-text=\"money(stats.today?.company_share)+' تومان امروز'\"",
            "x-text=\"'بر اساس '+Number(financeSettings.company_share_percent||0).toLocaleString('fa-IR')+'٪'\"",
            1,
        )
        service_tail = '<span x-show="j.overpayment_amount>0" class="chip inline-block mt-2 bg-emerald-500/10 text-emerald-600" x-text="\'بستانکار \'+money(j.overpayment_amount)"></span></div></article>'
        service_repl = '<span x-show="j.overpayment_amount>0" class="chip inline-block mt-2 bg-emerald-500/10 text-emerald-600" x-text="\'بستانکار \'+money(j.overpayment_amount)"></span><button type="button" @click="openServiceEdit(j)" class="btn soft !py-2 mt-2">ویرایش</button></div></article>'
        body = body.replace(service_tail, service_repl, 1)
        daily_tail = '<div class="md:text-left"><b x-text="money(j.received_amount)+\' تومان\'"></b><div class="text-xs muted" x-text="\'سهم شرکت: \'+money(j.company_share_amount)"></div></div></div></template>'
        daily_repl = '<div class="md:text-left"><b x-text="money(j.received_amount)+\' تومان\'"></b><div class="text-xs muted" x-text="\'سهم شرکت: \'+money(j.company_share_amount)"></div><button type="button" @click="openServiceEdit(j)" class="btn soft !py-2 mt-2">ویرایش</button></div></div></template>'
        body = body.replace(daily_tail, daily_repl, 1)
        expense_delete = '<button type="button" x-show="canAdmin" @click="removeExpense(e)" class="text-xs text-red-500 block mt-1">حذف</button>'
        expense_actions = '<button type="button" @click="openExpenseEdit(e)" class="text-xs text-teal-500 block mt-1">ویرایش</button>' + expense_delete
        body = body.replace(expense_delete, expense_actions, 1)
        if 'x-show="serviceEditOpen"' not in body:
            body = body.replace("</main>", TARGETED_MODAL_HTML + "</main>", 1)
        if '/aqua-targeted-fix.js?' not in body:
            body = body.replace(
                "</body>",
                '<script src="/aqua-targeted-fix.js?v=20260902-1"></script></body>',
                1,
            )
        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_targeted_fix_inject_failed detail=%s", str(exc)[:300])
    return response
