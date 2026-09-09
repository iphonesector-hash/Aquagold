"""Deduplicate Aria maneuver guidance without changing route calculation.

This branch-only response patch keeps one owner for each spoken maneuver. It
prevents GPS distance jitter (for example 100m -> 110m) or adjacent duplicate
Neshan steps from replaying the same instruction, while preserving the useful
final "now" cue close to the turn.
"""
import re

from flask import request

import app_v3


_VOICE_DEDUPE_BLOCK = r'''function voiceManeuverBand(distance){const d=Number(distance||0);if(d<=40)return'now';if(d<=110)return'100';if(d<=260)return'250';if(d<=650)return'600';return null}
function voiceManeuverBandRank(band){return({600:1,250:2,100:3,now:4})[band]||0}
function voiceManeuverSignature(step){return[String(step?.type||'').toLowerCase(),String(step?.modifier||'').toLowerCase(),String(step?.instruction||step?.name||'').toLowerCase().replace(/[۰-۹٠-٩0-9]+/g,'#').replace(/[،,.؛;:!?؟\-–—]+/g,' ').replace(/\s+/g,' ').trim()].join('|')}
function maneuverVoiceGuard(){return ST.nav.voiceGuard||(ST.nav.voiceGuard={lastSig:'',lastAt:0,lastBand:'',lastIndex:-99})}
function rememberManeuverVoice(info,band,at=Date.now()){const step=info?.step;if(!step||info.index==null)return;const key=String(info.index),done=ST.nav.announced[key]||(ST.nav.announced[key]=new Set());if(band)done.add(band);const guard=maneuverVoiceGuard();guard.lastSig=voiceManeuverSignature(step);guard.lastAt=Number(at||Date.now());guard.lastBand=band||'';guard.lastIndex=Number(info.index)}
function maybeAnnounceManeuver(info){const step=info.step;if(!step||info.index<0||step.type==='arrive')return;const d=Number(info.distance||0),band=voiceManeuverBand(d);if(!band)return;const key=String(info.index),done=ST.nav.announced[key]||(ST.nav.announced[key]=new Set()),rank=voiceManeuverBandRank(band),best=[...done].reduce((n,b)=>Math.max(n,voiceManeuverBandRank(b)),0);if(best>=rank)return;const guard=maneuverVoiceGuard(),now=Date.now(),sig=voiceManeuverSignature(step),sameInstruction=!!sig&&sig===guard.lastSig&&Math.abs(Number(info.index)-Number(guard.lastIndex))<=1,age=now-Number(guard.lastAt||0);if(sameInstruction&&band!=='now'&&age<18000){done.add(band);return}if(sameInstruction&&band==='now'&&age<3500){done.add(band);return}rememberManeuverVoice(info,band,now);ariaSpeak(maneuverSpeech(step,d),{replace:band==='now'})}'''.strip()


@app_v3.app.after_request
def aqua_navigation_voice_dedupe_asset(response):
    try:
        if request.path != "/aqua-smart-tour.js" or response.status_code != 200:
            return response
        response.direct_passthrough = False
        source = response.get_data(as_text=True)

        # Replace the old per-band-only announcer. The old logic could replay the
        # same turn if GPS jitter moved 105m -> 114m because those distances fall
        # into different announcement bands even though the maneuver is identical.
        pattern = r"function maybeAnnounceManeuver\(info\)\{.*?\}\n(?=function pointAhead)"
        source, count = re.subn(
            pattern,
            lambda _: _VOICE_DEDUPE_BLOCK + "\n",
            source,
            count=1,
            flags=re.S,
        )
        if count != 1:
            raise RuntimeError("navigation maneuver announcer was not found exactly once")

        # Reset the semantic guard whenever a fresh route model is prepared.
        old_prepare = "route._total=route._cum[route._cum.length-1]||Number(route.distance_m||0);ST.nav.announced={};ST.nav.currentStep=-1}"
        new_prepare = "route._total=route._cum[route._cum.length-1]||Number(route.distance_m||0);ST.nav.announced={};ST.nav.voiceGuard={lastSig:'',lastAt:0,lastBand:'',lastIndex:-99};ST.nav.currentStep=-1}"
        if old_prepare not in source:
            raise RuntimeError("route voice reset hook was not found")
        source = source.replace(old_prepare, new_prepare, 1)

        # startNavigation already speaks the first maneuver inside its intro. Mark
        # that exact maneuver/band as spoken before watchPosition starts so the
        # first GPS fix cannot immediately say it again with a slightly different
        # rounded distance.
        old_intro = "const first=findNextStep(route,nearestPointInfo(pos,route.points||[])),intro=`مسیر شروع شد. تا ${target.name||'مقصد'} حدود ${fmtDur(route.duration_s)} و ${fmtKm(route.distance_m)} راه داری.${first.step&&first.step.type!=='arrive'?' '+maneuverSpeech(first.step,first.distance):''}`;ariaSpeak(intro,{replace:true});"
        new_intro = "const first=findNextStep(route,nearestPointInfo(pos,route.points||[])),firstBand=voiceManeuverBand(first.distance);if(first.step&&first.step.type!=='arrive'&&firstBand)rememberManeuverVoice(first,firstBand);const intro=`مسیر شروع شد. تا ${target.name||'مقصد'} حدود ${fmtDur(route.duration_s)} و ${fmtKm(route.distance_m)} راه داری.${first.step&&first.step.type!=='arrive'?' '+maneuverSpeech(first.step,first.distance):''}`;ariaSpeak(intro,{replace:true});"
        if old_intro not in source:
            raise RuntimeError("navigation intro voice hook was not found")
        source = source.replace(old_intro, new_intro, 1)

        response.set_data(source)
        response.headers["Content-Length"] = str(len(response.get_data()))
        response.headers["Cache-Control"] = "no-store, max-age=0"
    except Exception as exc:
        app_v3.logger.warning("aqua_navigation_voice_dedupe_failed: %s", str(exc)[:180])
    return response
