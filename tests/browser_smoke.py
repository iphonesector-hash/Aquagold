import os
from playwright.sync_api import sync_playwright, expect

BASE_URL = os.getenv("AQUAGOLD_SMOKE_URL", "http://127.0.0.1:5000")
USERNAME = os.getenv("AQUAGOLD_ADMIN_USERNAME", "ci-admin")
PASSWORD = os.getenv("AQUAGOLD_ADMIN_PASSWORD", "ci-bootstrap-password")


def open_section(page, label, heading):
    button = page.locator("aside .side-link", has_text=label).first
    expect(button).to_be_visible()
    button.click()
    expect(page.get_by_text(heading, exact=False).first).to_be_visible(timeout=10000)


with sync_playwright() as p:
    api = p.request.new_context(base_url=BASE_URL)
    auth_probe = api.post("/api/login", data={"username": USERNAME, "password": PASSWORD})
    assert auth_probe.status == 200, f"backend login probe failed: {auth_probe.status} {auth_probe.text()}"
    api.dispose()

    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    page.goto(BASE_URL, wait_until="domcontentloaded")
    expect(page.get_by_placeholder("نام کاربری")).to_be_visible(timeout=10000)
    page.wait_for_timeout(1800)
    expect(page.get_by_placeholder("نام کاربری")).to_be_visible(timeout=10000)
    page.get_by_placeholder("نام کاربری").fill(USERNAME)
    page.get_by_placeholder("رمز عبور").fill(PASSWORD)
    expect(page.get_by_placeholder("نام کاربری")).to_have_value(USERNAME)
    expect(page.get_by_placeholder("رمز عبور")).to_have_value(PASSWORD)
    page.get_by_role("button", name="ورود به AquaGold").click()
    expect(page.get_by_text("داشبورد هوشمند آکوا گلد", exact=True)).to_be_visible(timeout=15000)

    open_section(page, "محصولات", "کاتالوگ محصولات")
    open_section(page, "فاکتورها", "فاکتورها")
    open_section(page, "هوش مصنوعی آکوا", "هوش مصنوعی آکوا")
    open_section(page, "تنظیمات", "تنظیمات")

    assert not errors, f"browser page errors: {errors}"
    browser.close()
