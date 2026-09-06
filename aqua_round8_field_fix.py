"""Final field-runtime repair for AquaGold test preview.

This module intentionally does NOT touch the boot/loading screen.
It only injects the final iPhone microphone + daily report edit runtime script.
"""
from __future__ import annotations

from flask import request

import app_v3


FINAL_JS = "/aqua-round8-mic-edit-only.js"

# The mic runtime also contains a capture-phase fallback for the daily edit
# button. On Alpine x-for rows that fallback can resolve the local `j` scope
# instead of the body app state and then stop the canonical Alpine click. Keep
# the mic runtime untouched and make only the daily button use the canonical
# app handler directly.
DAILY_EDIT_CLICK_FIX = r'''
<script id="aqua-daily-edit-canonical-click-fix">
(()=>{
  const patchDailyEditClick=()=>{
    const section=[...document.querySelectorAll('section')].find(
      el=>(el.getAttribute('x-show')||'').includes("page==='daily'")
    );
    if(!section)return;
    for(const template of section.querySelectorAll('template')){
      if(!template.innerHTML.includes('data-aqua-daily-edit'))continue;
      template.innerHTML=template.innerHTML.replace(
        /<button\b[^>]*data-aqua-daily-edit[^>]*>ویرایش<\/button>/g,
        '<button type="button" class="btn soft !py-1.5 !px-3 no-print" x-on:click.stop.prevent="openServiceEdit(j)">ویرایش</button>'
      );
    }
  };
  patchDailyEditClick();
  document.addEventListener('alpine:init',patchDailyEditClick,{once:true});
})();
</script>
'''


@app_v3.app.get(FINAL_JS)
def aqua_round8_mic_edit_only_js():
    return app_v3.send_from_directory(
        ".",
        "aqua-round8-mic-edit-only.js",
        mimetype="application/javascript",
        max_age=0,
    )


@app_v3.app.after_request
def finalize_aqua_round8_field_runtime(response):
    try:
        if request.path not in {"/", "/index.html"} or response.mimetype != "text/html":
            return response

        response.direct_passthrough = False
        body = response.get_data(as_text=True)

        # Important: leave every loader/splash asset and observer exactly as the
        # previous working preview had it. This layer is mic + daily edit only.
        if FINAL_JS + "?" not in body:
            body = body.replace(
                "</body>",
                f'<script src="{FINAL_JS}?v=20260906-4"></script></body>',
                1,
            )
        if 'id="aqua-daily-edit-canonical-click-fix"' not in body:
            body = body.replace("</body>", DAILY_EDIT_CLICK_FIX + "</body>", 1)

        response.set_data(body)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_round8_field_runtime_failed detail=%s", str(exc)[:320])
    return response
