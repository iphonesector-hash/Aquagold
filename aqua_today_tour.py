"""Today Tour compatibility API backed by the proven Smart Tour job source."""
from __future__ import annotations
import hashlib
from flask import jsonify, request
import app_v3
import aqua_smart_tour


def _active_rows():
    # Reuse Smart Tour's source because it performs the read-only Preview→main
    # Bale sync before filtering new/review jobs for Tehran's current day.
    return aqua_smart_tour._active_today_rows()


def _public(row):
    return {k:v for k,v in row.items() if k != '_schedule'}

@app_v3.app.get('/api/map/today-tour/jobs')
@app_v3.roles_required('technician')
def today_tour_jobs():
    rows=_active_rows();sig='|'.join(f"{r['id']}:{r.get('status')}:{r.get('updated_at')}" for r in rows)
    return jsonify({'count':len(rows),'signature':hashlib.sha256(sig.encode()).hexdigest()[:18],'jobs':[_public(r) for r in rows]})

@app_v3.app.get('/api/map/today-tour/plan')
@app_v3.roles_required('technician')
@app_v3.limiter.limit('20 per hour')
def today_tour_plan():
    try:
        lat=float(request.args.get('lat'));lng=float(request.args.get('lng'))
        if not(-90<=lat<=90 and -180<=lng<=180):raise ValueError
    except Exception:return jsonify({'error':'موقعیت فعلی معتبر نیست'}),400
    mode='walking' if request.args.get('mode')=='walking' else 'car'
    jobs=_active_rows()
    for job in jobs:job['location']=aqua_smart_tour._customer_location(job)
    ordered,matrix,point_index=aqua_smart_tour._schedule_order(jobs,(lat,lng),mode)
    _leg_map,route=aqua_smart_tour._route_legs(ordered,(lat,lng),mode)
    for i,job in enumerate(ordered,1):
        job['order']=i
        loc=job.get('location') or {}
        # Compatibility shape for the older Today Tour client.
        if loc.get('lat') is not None:loc['latitude']=loc['lat']
        if loc.get('lng') is not None:loc['longitude']=loc['lng']
    exact=sum((j.get('location') or {}).get('quality')=='exact' for j in ordered);approx=sum((j.get('location') or {}).get('quality')=='approximate' for j in ordered);unresolved=len(ordered)-exact-approx
    return jsonify({'generated_at':aqua_smart_tour._now().isoformat(),'jobs':[_public(j) for j in ordered],'summary':{'jobs':len(ordered),'exact':exact,'approximate':approx,'unresolved':unresolved,'distance_m':route.get('distance_m',0),'duration_s':route.get('duration_s',0)},'route':{'provider':'neshan','geometry':None,'distance_m':route.get('distance_m',0),'duration_s':route.get('duration_s',0)}})

@app_v3.app.get('/aqua-today-tour.js')
def aqua_today_tour_js():return app_v3.send_from_directory('.', 'aqua-today-tour.js',mimetype='application/javascript',max_age=0)

@app_v3.app.after_request
def inject_today_tour(response):
    if request.path in {'/','/index.html'} and response.mimetype=='text/html':
        response.direct_passthrough=False;body=response.get_data(as_text=True)
        if '/aqua-today-tour.js' not in body:body=body.replace('</body>','<script src="/aqua-today-tour.js?v=20260914-3"></script></body>',1);response.set_data(body);response.headers['Content-Length']=str(len(response.get_data()))
    return response
