from pathlib import Path
p=Path('aqua_ai.py'); s=p.read_text(encoding='utf-8')
marker='''@app_v3.app.post("/api/aqua-ai/speak")'''
# Append a one-time diagnostic route after normal routes. Token is hashed in DB and consumed before providers are called.
route=r'''

@app_v3.app.get("/api/aqua-ai/selftest")
@app_v3.limiter.limit("5 per minute")
def aqua_selftest():
    supplied = str(request.args.get("token") or "")
    if not supplied:
        return jsonify({"error": "not_found"}), 404
    with app_v3.get_db() as db, db.cursor() as cur:
        cur.execute("select value from app_settings where key='aqua_ai_selftest' for update")
        row = cur.fetchone()
        cfg = dict((row or {}).get("value") or {})
        expected = str(cfg.get("token_hash") or "")
        if not expected or hashlib.sha256(supplied.encode()).hexdigest() != expected:
            return jsonify({"error": "not_found"}), 404
        cur.execute("delete from app_settings where key='aqua_ai_selftest'")
        context = _workspace_context(cur)
    settings = _load_settings()
    result = {"database": True, "groq": False, "tts": False, "voice_id": settings.get("voice_id"), "tts_model": settings.get("tts_model")}
    try:
        answer = _groq_answer(settings, "فقط کلمه «اوکی» را پاسخ بده.", [], context)
        result["groq"] = bool(str(answer or "").strip())
        result["groq_preview"] = str(answer or "")[:80]
    except Exception as exc:
        result["groq_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    key = settings.get("elevenlabs_api_key")
    voice_id = settings.get("voice_id") or DEFAULTS["voice_id"]
    models = [settings.get("tts_model") or "eleven_v3", "eleven_multilingual_v2"]
    seen = set()
    for model_id in models:
        if model_id in seen or result["tts"]:
            continue
        seen.add(model_id)
        try:
            req = urllib.request.Request(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
                data=json.dumps({"text": "سلام، تست صدای آریا با موفقیت انجام شد.", "model_id": model_id}, ensure_ascii=False).encode(),
                headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as response:
                audio = response.read()
                result["tts"] = bool(audio)
                result["tts_bytes"] = len(audio)
                result["tts_model_used"] = model_id
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:180]
            result["tts_error"] = f"HTTP {exc.code}: {detail}"
        except Exception as exc:
            result["tts_error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
    result["ok"] = bool(result["database"] and result["groq"] and result["tts"])
    return jsonify(result), (200 if result["ok"] else 503)
'''
if 'def aqua_selftest():' in s:
    raise SystemExit('selftest already exists')
s=s.rstrip()+route+'\n'
p.write_text(s,encoding='utf-8')
