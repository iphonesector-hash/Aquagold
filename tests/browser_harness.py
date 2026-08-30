"""Local visual QA harness. It never connects to production services."""
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, static_folder=str(ROOT), static_url_path="")


@app.get("/")
def index():
    response = send_from_directory(ROOT, "index.html")
    response.set_cookie("aquagold_csrf", "browser-harness", samesite="Strict")
    return response


@app.get("/api/session")
def session():
    return jsonify({"authenticated": True, "user": {"id": "1", "username": "qa", "first_name": "QA", "role": "admin"}})


@app.route("/api/<path:path>", methods=["GET", "POST", "PATCH", "DELETE"])
def api(path):
    customer = {"id": "11111111-1111-4111-8111-111111111111", "first_name": "سارا", "last_name": "معماری", "name": "سارا معماری", "phones": ["09127653114"], "address": "کرج، فردیس، شهرک ناز، پلاک ۱۵", "latitude": 35.73, "longitude": 50.98, "last_service": "یخچال/ساید", "last_amount": 5650000, "service_count": 3, "total_received": 12000000, "total_balance": 0}
    visit = {"id": "22222222-2222-4222-8222-222222222222", "customer_id": customer["id"], "name": customer["name"], "phone": customer["phones"][0], "description": "سرویس ساید", "service_type": "یخچال/ساید", "received_amount": 5650000, "company_share_amount": 2825000, "customer_balance": 0, "date": "2026-08-27T19:00:00+03:30"}
    if path == "stats": return jsonify({"today": {"count": 1, "received": 5650000, "company_share": 2825000, "expenses": 0, "net_profit": 2825000}, "total_customers": 1})
    if path.startswith("customers") and path.endswith("/jobs"): return jsonify({"items": [visit], "pagination": {"page": 1, "pages": 1, "total": 1}})
    if path.startswith("customers"): return jsonify({"items": [customer], "pagination": {"page": 1, "pages": 1, "total": 1}})
    if path.startswith("jobs"): return jsonify({"items": [visit], "pagination": {"page": 1, "pages": 1, "total": 1}})
    if path in {"expenses", "settlements", "reminders", "audit"}: return jsonify([])
    if path == "settings/finance": return jsonify({"company_share_percent": 50})
    if path == "reports/analytics": return jsonify({"totals": {"invoice": 5650000, "received": 5650000, "company_share": 2825000, "expenses": 0, "net_profit": 2825000, "company_due": 2825000}, "months": [], "service_types": []})
    if path == "reports/insights": return jsonify({"top_customers": [], "busy_days": [], "expense_categories": [], "areas": [], "service_analysis": []})
    if path == "bale/jobs/counts": return jsonify({"new": 1, "review": 0, "completed": 0, "cancelled": 0})
    if path.startswith("bale/jobs"): return jsonify([])
    if path == "products": return jsonify([])
    if path == "invoices": return jsonify([])
    if path == "ops/company-share": return jsonify({"days": [], "totals": {}})
    if path in {"ops/cancellations", "ops/financial-report"}: return jsonify({"rows": [], "days": [], "reasons": [], "totals": {}, "total": 0})
    if path == "ops/recurring": return jsonify([])
    if path == "ops/profile": return jsonify({"first_name": "پیمان", "last_name": "مدیر", "title": "مدیر AquaGold", "phone": "09120000000"})
    if path == "ops/health": return jsonify({"database": True, "bale": True, "reporting_bot": True, "groq": True, "elevenlabs": True, "push": True})
    if path == "ops/reporting-bot/settings": return jsonify({"enabled": True, "chat_id": "", "send_nightly": True, "send_backup": True, "token_configured": False})
    if path == "ops/notifications": return jsonify({"rows": [], "unread": 0})
    if path.startswith("ops/customer/") and path.endswith("/timeline"): return jsonify([])
    if request.method != "GET": return jsonify({"ok": True, "id": "33333333-3333-4333-8333-333333333333"})
    return jsonify([])


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
