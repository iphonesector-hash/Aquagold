"""Final CSS-only guard for Aqua Map mobile controls.

No JavaScript ownership changes here: the existing PR29 navigation guard keeps
its runtime behavior. This layer only guarantees the restored Map controls stay
compact even if the DOM mover does not run in an iPhone/in-app browser.
"""
from flask import request

import app_v3


_CSS = r'''
/* Aqua map compact CSS lock — PR29 20260909 */
@media(max-width:700px){
 section[x-show*="page==='map'"]>div:first-child>.no-print,
 .aq-map-compact-actions,
 .aq-map-primary-actions{
  display:grid!important;
  grid-template-columns:repeat(3,minmax(0,1fr))!important;
  gap:4px!important;
  width:100%!important;
  align-items:stretch!important;
  flex-wrap:nowrap!important;
 }
 section[x-show*="page==='map'"]>div:first-child>.no-print>button:nth-child(-n+3),
 .aq-map-compact-actions>button,
 .aq-map-primary-actions>button{
  width:100%!important;
  min-width:0!important;
  max-width:none!important;
  height:35px!important;
  min-height:35px!important;
  padding:0 2px!important;
  margin:0!important;
  border-radius:11px!important;
  font-size:.64rem!important;
  line-height:1!important;
  white-space:nowrap!important;
  overflow:hidden!important;
  text-overflow:ellipsis!important;
  display:flex!important;
  align-items:center!important;
  justify-content:center!important;
  gap:2px!important;
 }
 section[x-show*="page==='map'"]>div:first-child>.no-print>button:nth-child(4){grid-column:1/-1!important;height:34px!important}
 section[x-show*="page==='map'"]>div:first-child>.no-print svg,
 .aq-map-compact-actions svg,
 .aq-map-primary-actions svg{width:14px!important;height:14px!important;flex:0 0 14px!important}
 #aq-smart-tour{margin-bottom:5px!important}
 #aq-smart-tour .aqst-search{margin:0 0 5px!important}
 #aq-smart-tour .aqst-searchbar{grid-template-columns:minmax(0,1fr) auto!important;gap:5px!important;align-items:center!important}
 #aq-smart-tour .aqst-searchbar input{height:38px!important;min-height:38px!important;padding:5px 9px!important;border-radius:11px!important;font-size:16px!important;line-height:1.1!important;margin:0!important}
 #aq-smart-tour .aqst-iconbtn{width:38px!important;height:38px!important;min-width:38px!important;min-height:38px!important;border-radius:11px!important;margin:0!important;padding:0!important}
 #aq-smart-tour .aqst-selected{margin-top:5px!important;padding:6px 8px!important;border-radius:11px!important;min-height:0!important;gap:5px!important}
 #aq-smart-tour .aqst-selected b{font-size:.76rem!important;line-height:1.25!important}
 #aq-smart-tour .aqst-selected small{font-size:.66rem!important;line-height:1.25!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
 #aq-smart-tour .aqst-selected .aqst-btn{min-height:32px!important;padding:5px 7px!important;border-radius:10px!important;font-size:.65rem!important}
 #aqst-free-search{margin:5px 0!important}
 #aqst-free-search .aqst-free-searchbar{grid-template-columns:minmax(0,1fr) auto!important;gap:5px!important;align-items:center!important}
 #aqst-free-search .aqst-free-searchbar input{height:38px!important;min-height:38px!important;padding:5px 9px!important;border-radius:11px!important;font-size:16px!important;margin:0!important}
 #aqst-free-search .aqst-free-searchbar button{height:38px!important;min-height:38px!important;padding:0 9px!important;border-radius:11px!important;font-size:.7rem!important;margin:0!important}
 #aqst-free-search .aqst-free-hint{padding:3px 1px!important;font-size:.63rem!important;line-height:1.35!important}
}
@media(max-width:370px){
 section[x-show*="page==='map'"]>div:first-child>.no-print>button:nth-child(-n+3),
 .aq-map-compact-actions>button,.aq-map-primary-actions>button{font-size:.59rem!important;letter-spacing:-.015em!important}
}
'''.strip()


@app_v3.app.after_request
def aqua_map_compact_css_guard(response):
    try:
        if response.status_code == 200 and request.path == "/aqua-smart-tour.css":
            response.direct_passthrough = False
            css = response.get_data(as_text=True)
            if "Aqua map compact CSS lock — PR29 20260909" not in css:
                css += "\n" + _CSS + "\n"
                response.set_data(css)
                response.headers["Content-Length"] = str(len(response.get_data()))
                response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_map_compact_css_guard_failed: %s", str(exc)[:180])
    return response
