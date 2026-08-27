from pathlib import Path
p=Path('aqua_ai.py'); s=p.read_text(encoding='utf-8')
old='''    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST")'''
new='''    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Mozilla/5.0 AquaGold/7.2", **headers}, method="POST")'''
if old not in s:
    raise SystemExit('post_json request marker missing')
s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
