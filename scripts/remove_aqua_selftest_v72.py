from pathlib import Path
p=Path('aqua_ai.py'); s=p.read_text(encoding='utf-8')
marker='\n@app_v3.app.get("/api/aqua-ai/selftest")\n'
if marker not in s:
    raise SystemExit('selftest marker missing')
s=s.split(marker,1)[0].rstrip()+'\n'
p.write_text(s,encoding='utf-8')
