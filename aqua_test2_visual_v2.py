"""Final presentation-only injector for AquaGold test-2.

It deliberately runs after the legacy HTML is produced, cache-busts the old visual layer,
and appends the v2 CSS/JS at the end of the document. No API/database behavior is changed.
"""
from __future__ import annotations

import app_v3


@app_v3.app.after_request
def inject_aqua_test2_visual_v2(response):
    ctype = str(response.headers.get("Content-Type") or "")
    if response.status_code >= 400 or "text/html" not in ctype:
        return response
    try:
        html = response.get_data(as_text=True)
    except Exception:
        return response

    # Force iPhone/Safari to request the current visual file rather than the old v69 URL.
    html = html.replace(
        "/ui-visual-polish.js?v=20260827-v69",
        "/ui-visual-polish.js?v=20260902-test2-v2",
    )
    html = html.replace(
        "/sw.js?v=20260901-stable1",
        "/sw.js?v=20260902-test2-v2",
    )

    marker = "</body>"
    payload = (
        '<link rel="stylesheet" href="/aqua-test2-redesign-v2.css?v=20260902-2">'
        '<script src="/aqua-test2-redesign-v2.js?v=20260902-2"></script>'
    )
    if payload not in html and marker in html:
        html = html.replace(marker, payload + marker, 1)
    response.set_data(html)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response
