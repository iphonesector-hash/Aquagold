import shutil
import subprocess
import tempfile
from pathlib import Path

from app import app


def _asset(path: str) -> str:
    response = app.test_client().get(path)
    assert response.status_code == 200, path
    return response.get_data(as_text=True)


def _phase3_guard_block(js: str) -> str:
    start = js.index("function routeCorridorDistance(")
    end = js.index("function updateNavPosition(", start)
    return js[start:end].rstrip()


def _run_phase3_behavior(js: str) -> None:
    node = shutil.which("node")
    assert node, "Node.js is required for the Phase 3 navigation behavior test"
    block = _phase3_guard_block(js)
    script = f"""
const ST={{nav:{{
  active:true,
  target:{{name:'مقصد',lat:35.71,lng:51.01}},
  route:{{points:[[35.7000,51.0000],[35.7000,51.0040]]}},
  offCount:0,
  lastReroute:0,
  rerouting:false
}}}};
let fakeNow=100000;
Date.now=()=>fakeNow;
function hav(a,b){{
  const R=6371000,p=Math.PI/180,d1=(b[0]-a[0])*p,d2=(b[1]-a[1])*p;
  const x=Math.sin(d1/2)**2+Math.cos(a[0]*p)*Math.cos(b[0]*p)*Math.sin(d2/2)**2;
  return 2*R*Math.asin(Math.sqrt(x));
}}
let reroutes=0;
function reroute(pos){{reroutes+=1;}}
{block}

resetOffRouteGuard(ST.nav.route,true);

// Core regression: a sparse route can have vertices >200m apart. A driver at
// the middle of that road is far from both vertices but zero metres from the
// actual route segment, so this must never be treated as off-route.
const onRoad={{lat:35.7000,lng:51.0020}};
const misleadingNear={{i:0,d:220}};
const corridor=routeCorridorDistance(onRoad,ST.nav.route.points,0);
if(corridor>2)throw new Error('route corridor distance still uses sparse vertices');
for(let i=0;i<5;i++){{
  fakeNow+=2200;
  evaluateReroute(onRoad,{{accuracy:8,speed:12}},misleadingNear,false);
}}
if(reroutes!==0)throw new Error('on-route sparse polyline falsely rerouted');

// Poor GPS accuracy must not build an off-route streak.
const offRoad={{lat:35.7012,lng:51.0020}};
for(let i=0;i<5;i++){{
  fakeNow+=2200;
  evaluateReroute(offRoad,{{accuracy:95,speed:10}},{{i:0,d:150}},false);
}}
if(reroutes!==0)throw new Error('poor GPS accuracy triggered reroute');

// One transient good-quality jump followed by a valid on-route fix must reset.
fakeNow+=2200;
evaluateReroute(offRoad,{{accuracy:8,speed:8}},{{i:0,d:150}},false);
fakeNow+=2200;
evaluateReroute(onRoad,{{accuracy:8,speed:8}},misleadingNear,false);
if(reroutes!==0)throw new Error('single GPS jump triggered reroute');

// A stationary off-route reading must not reroute just because GPS jitters.
for(let i=0;i<5;i++){{
  fakeNow+=2200;
  evaluateReroute(offRoad,{{accuracy:8,speed:0}},{{i:0,d:150}},false);
}}
if(reroutes!==0)throw new Error('stationary GPS drift triggered reroute');

// A real, sustained, good-quality moving deviation should still reroute once.
clearOffRouteCandidate(ST.nav.offTrack);
ST.nav.offTrack.lastFix=null;
for(let i=0;i<4;i++){{
  if(i)fakeNow+=2300;
  evaluateReroute({{lat:35.7012,lng:51.0010+i*0.00015}},{{accuracy:8,speed:7}},{{i:0,d:150}},false);
}}
if(reroutes!==1)throw new Error(`sustained real deviation rerouted ${{reroutes}} times`);

// Cooldown prevents repeated "از مسیر خارج شدی" announcements in the same
// short GPS episode.
for(let i=0;i<5;i++){{
  fakeNow+=2300;
  evaluateReroute({{lat:35.7012,lng:51.0017+i*0.00015}},{{accuracy:8,speed:7}},{{i:0,d:150}},false);
}}
if(reroutes!==1)throw new Error('reroute cooldown did not suppress repeat reroute');
"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "phase3-reroute.mjs"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [node, str(path)],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    assert result.returncode == 0, result.stderr or result.stdout


def test_phase3_generated_navigation_rejects_false_reroutes():
    js = _asset("/aqua-smart-tour.js")

    assert js.count("function routeCorridorDistance(") == 1
    assert js.count("function evaluateReroute(") == 1
    assert "accuracy:p.coords.accuracy" in js
    assert "accuracy>65" in js
    assert "guard.samples>=4" in js
    assert "now-guard.since>=6500" in js
    assert ">=45000" in js
    assert "if(near.d>100)" not in js
    _run_phase3_behavior(js)


def test_phase3_keeps_phase1_and_phase2_generated_contracts():
    js = _asset("/aqua-smart-tour.js")

    assert "aqst-customer-search" in js
    assert "aqst-map-place-q" in js
    assert "/api/map/smart-tour/place-search" in js
    assert js.count("function bindMainMapLongPress()") == 1
    assert "const el=$('#mainMap');if(!el||el.dataset.aqLongPress==='2')return" in js
    assert "['touchend','touchcancel']" in js
