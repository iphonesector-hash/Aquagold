import re
import subprocess
import tempfile
from pathlib import Path

from app import app


def _generated_js() -> str:
    with app.test_client() as client:
        response = client.get("/aqua-smart-tour.js")
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_phase4a_generated_navigation_voice_guard_is_installed_once():
    js = _generated_js()

    assert js.count("function voiceManeuverBand(distance)") == 1
    assert js.count("function voiceManeuverBandRank(band)") == 1
    assert js.count("function voiceManeuverSignature(step)") == 1
    assert js.count("function maneuverVoiceGuard()") == 1
    assert js.count("function rememberManeuverVoice(info,band,at=Date.now())") == 1
    assert js.count("function maybeAnnounceManeuver(info)") == 1

    # Starting navigation already speaks the first maneuver inside the intro, so
    # it must mark that maneuver before watchPosition can announce it again.
    assert "firstBand=voiceManeuverBand(first.distance)" in js
    assert "rememberManeuverVoice(first,firstBand)" in js

    # Existing approved Map phases must still be present.
    assert "function bindMainMapLongPress()" in js
    assert "function searchFreePlaces()" in js
    assert "function evaluateReroute(pos,coords,near,initial=false)" in js
    assert "routeCorridorDistance(pos,points,nearIndex=0)" in js


def test_phase4a_voice_guard_blocks_distance_jitter_and_adjacent_duplicate_steps():
    js = _generated_js()
    match = re.search(
        r"(function voiceManeuverBand\(distance\).*?function maybeAnnounceManeuver\(info\)\{.*?\})\nfunction pointAhead",
        js,
        re.S,
    )
    assert match, "generated voice-dedupe function block was not found"
    block = match.group(1)

    script = f"""
const ST={{nav:{{voice:true,announced:{{}},voiceGuard:null}}}};
const spoken=[];
function maneuverSpeech(step,distance){{return `${{Math.round(distance)}}:${{step.instruction}}`;}}
function ariaSpeak(text){{spoken.push(text);return Promise.resolve();}}
{block}

const assert=(ok,msg)=>{{if(!ok)throw new Error(msg)}};
const step={{instruction:'به چپ بپیچید و وارد لاله ۳ شوید',type:'turn',modifier:'left'}};
let now=100000;
Date.now=()=>now;

// The first spoken cue is around 100m.
maybeAnnounceManeuver({{step,index:4,distance:105}});
assert(spoken.length===1,'first 100m cue should speak once');

// GPS jitter moves the computed distance farther (114m). Old logic treated this
// as another band and repeated the same sentence. The new guard must not.
now+=900;
maybeAnnounceManeuver({{step,index:4,distance:114}});
assert(spoken.length===1,'distance jitter must not replay the same maneuver');

// Neshan can expose adjacent duplicate semantic steps. They must share the same
// short semantic guard even if the raw step index changes by one.
now+=900;
maybeAnnounceManeuver({{step:{{...step}},index:5,distance:108}});
assert(spoken.length===1,'adjacent duplicate maneuver must not replay');

// A useful final "now" cue remains allowed once enough time has passed.
now+=5000;
maybeAnnounceManeuver({{step,index:4,distance:32}});
assert(spoken.length===2,'final now cue should still be allowed');

// Simulate startNavigation marking the first maneuver that was already included
// in the intro. The first GPS update must not immediately speak it again.
ST.nav.announced={{}};ST.nav.voiceGuard=null;spoken.length=0;now+=20000;
const introInfo={{step,index:2,distance:102}};
rememberManeuverVoice(introInfo,voiceManeuverBand(introInfo.distance),now);
now+=700;
maybeAnnounceManeuver({{step,index:2,distance:113}});
assert(spoken.length===0,'intro maneuver must not be repeated by first GPS fix');
"""

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "voice-dedupe-test.js"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            ["node", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    assert result.returncode == 0, result.stderr or result.stdout
