from flask import jsonify, request

import app_v3

app = app_v3.app
get_db = app_v3.get_db
token_required = app_v3.token_required
roles_required = app_v3.roles_required
row_json = lambda row: app_v3.row_json(row)
from aquagold_validation import coordinates as valid_coordinates, integer as valid_integer


@app.get('/api/reports/insights')
@token_required
def reports_insights():
    with get_db() as db, db.cursor() as cur:
        cur.execute("""
          select c.id,trim(concat_ws(' ',c.first_name,c.last_name)) name,
                 coalesce(sum(v.received_amount),0)::bigint received,count(v.id)::int services
          from customers_v2 c join service_visits v on v.customer_id=c.id
          group by c.id order by received desc limit 10
        """)
        top_customers=[{**row_json(r),'id':str(r['id'])} for r in cur.fetchall()]

        cur.execute("""
          select extract(isodow from (coalesce(visited_at,created_at) at time zone 'Asia/Tehran'))::int weekday,
                 count(*)::int services,coalesce(sum(received_amount),0)::bigint received
          from service_visits group by 1 order by services desc
        """)
        busy_days=[row_json(r) for r in cur.fetchall()]

        cur.execute("""
          select category,count(*)::int count,coalesce(sum(amount),0)::bigint amount
          from expenses group by category order by amount desc
        """)
        expense_categories=[row_json(r) for r in cur.fetchall()]

        cur.execute("""
          select array_to_string((regexp_split_to_array(trim(address),'\\s+'))[1:2],' ') area,
                 count(*)::int customers
          from customers_v2
          where address is not null and trim(address)<>'' and archived=false
          group by 1 order by customers desc limit 10
        """)
        areas=[row_json(r) for r in cur.fetchall()]

        cur.execute("""
          select coalesce(service_type,'نامشخص') service_type,count(*)::int services,
                 coalesce(avg(received_amount),0)::bigint avg_received,
                 coalesce(sum(received_amount),0)::bigint received
          from service_visits group by service_type order by received desc limit 15
        """)
        service_analysis=[row_json(r) for r in cur.fetchall()]

    return jsonify({
        'top_customers':top_customers,
        'busy_days':busy_days,
        'expense_categories':expense_categories,
        'areas':areas,
        'service_analysis':service_analysis,
    })


@app.get('/api/route/nearest')
@token_required
def route_nearest():
    lat, lng = valid_coordinates(request.args.get('lat'), request.args.get('lng'), required=True)
    limit = valid_integer(request.args.get('limit'), 'تعداد مقصد', minimum=1, maximum=25, default=10)
    with get_db() as db, db.cursor() as cur:
        cur.execute("""
          select c.id,trim(concat_ws(' ',c.first_name,c.last_name)) name,c.map_label,c.address,
                 st_y(c.location::geometry) latitude,st_x(c.location::geometry) longitude,
                 round(st_distance(c.location,st_setsrid(st_makepoint(%s,%s),4326)::geography)::numeric,1) distance_m,
                 (select phone from customer_phones p where p.customer_id=c.id order by is_primary desc,id limit 1) phone,
                 (select next_service_at from service_visits v where v.customer_id=c.id and v.next_service_at is not null order by next_service_at desc limit 1) next_service_at
          from customers_v2 c where c.location is not null and c.archived=false
          order by distance_m limit %s
        """,(lng,lat,limit))
        rows=cur.fetchall()
    return jsonify([{**row_json(r),'id':str(r['id'])} for r in rows])


@app.get('/api/audit')
@roles_required('admin')
def audit_list():
    limit = valid_integer(request.args.get('limit'), 'تعداد رویداد', minimum=1, maximum=500, default=100)
    with get_db() as db, db.cursor() as cur:
        cur.execute("select * from audit_log order by created_at desc limit %s",(limit,))
        rows=cur.fetchall()
    return jsonify([row_json(r) for r in rows])
