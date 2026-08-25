"""AquaGold smart CRM application entrypoint.

Keeps the existing Flask app intact while adding the new field-service APIs.
SQLite remains a compatibility store until the dedicated Supabase project is provisioned.
"""
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime

from flask import request, jsonify, send_from_directory

from server import app, get_db, require_perm, safe_call
from smart_intake import parse_intake


def ensure_smart_schema():
    db = get_db()
    columns = {row[1] for row in db.execute("PRAGMA table_info(customers)").fetchall()}
    if "latitude" not in columns:
        db.execute("ALTER TABLE customers ADD COLUMN latitude REAL")
    if "longitude" not in columns:
        db.execute("ALTER TABLE customers ADD COLUMN longitude REAL")
    if "location_accuracy_m" not in columns:
        db.execute("ALTER TABLE customers ADD COLUMN location_accuracy_m REAL")

    db.execute("""
        CREATE TABLE IF NOT EXISTS customer_phones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            phone TEXT NOT NULL,
            is_primary INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(customer_id, phone),
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS service_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            visitor_code TEXT,
            service_type TEXT,
            description TEXT,
            amount INTEGER DEFAULT 0,
            status TEXT DEFAULT 'registered',
            time_text TEXT,
            visited_at TEXT,
            latitude REAL,
            longitude REAL,
            raw_chat_input TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        )
    """)
    db.commit()
    db.close()


def haversine_m(lat1, lon1, lat2, lon2):
    earth = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return earth * 2 * atan2(sqrt(a), sqrt(1 - a))


ensure_smart_schema()


@app.route('/smart')
def smart_page():
    return send_from_directory('.', 'smart.html')


@app.route('/api/smart/parse', methods=['POST'])
@require_perm('customers')
@safe_call
def smart_parse():
    data = request.get_json() or {}
    text = data.get('text', '')
    if not text.strip():
        return jsonify({'error': 'text is required'}), 400
    return jsonify(parse_intake(text))


@app.route('/api/smart/register', methods=['POST'])
@require_perm('customers')
@safe_call
def smart_register():
    data = request.get_json() or {}
    parsed = data.get('parsed') or parse_intake(data.get('text', ''))
    last_name = (parsed.get('last_name') or '').strip()
    if not last_name:
        return jsonify({'error': 'customer last name could not be detected'}), 400

    phones = parsed.get('phones') or []
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy')

    db = get_db()
    existing = None
    for phone in phones:
        existing = db.execute("""
            SELECT c.* FROM customers c
            LEFT JOIN customer_phones cp ON cp.customer_id = c.id
            WHERE cp.phone = ? OR c.phone = ?
            LIMIT 1
        """, (phone, phone)).fetchone()
        if existing:
            break

    if existing:
        customer_id = existing['id']
        db.execute("""
            UPDATE customers SET name=?, address=COALESCE(?, address),
                latitude=COALESCE(?, latitude), longitude=COALESCE(?, longitude),
                location_accuracy_m=COALESCE(?, location_accuracy_m)
            WHERE id=?
        """, (last_name, parsed.get('address'), latitude, longitude, accuracy, customer_id))
    else:
        cursor = db.execute("""
            INSERT INTO customers (name, phone, address, notes, latitude, longitude, location_accuracy_m)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (last_name, phones[0] if phones else None, parsed.get('address'), None, latitude, longitude, accuracy))
        customer_id = cursor.lastrowid

    for i, phone in enumerate(phones):
        db.execute("""
            INSERT OR IGNORE INTO customer_phones (customer_id, phone, is_primary)
            VALUES (?, ?, ?)
        """, (customer_id, phone, 1 if i == 0 else 0))

    amount = parsed.get('amount') or 0
    visit = db.execute("""
        INSERT INTO service_visits (
            customer_id, visitor_code, service_type, description, amount,
            status, time_text, visited_at, latitude, longitude, raw_chat_input
        ) VALUES (?, ?, ?, ?, ?, 'registered', ?, ?, ?, ?, ?)
    """, (
        customer_id,
        parsed.get('visitor_code'),
        parsed.get('service_type'),
        data.get('description') or parsed.get('service_type'),
        amount,
        parsed.get('time_text'),
        data.get('visited_at') or datetime.now().isoformat(timespec='seconds'),
        latitude,
        longitude,
        parsed.get('raw_text') or data.get('text')
    ))
    visit_id = visit.lastrowid
    db.commit()
    db.close()

    return jsonify({'customer_id': customer_id, 'visit_id': visit_id, 'parsed': parsed}), 201


@app.route('/api/smart/visits/<int:visit_id>/amount', methods=['PATCH'])
@require_perm('jobs')
@safe_call
def smart_update_amount(visit_id):
    data = request.get_json() or {}
    parsed = parse_intake(data.get('text', ''))
    amount = data.get('amount') if data.get('amount') is not None else parsed.get('amount')
    if amount is None:
        return jsonify({'error': 'amount could not be detected'}), 400
    db = get_db()
    db.execute("UPDATE service_visits SET amount=? WHERE id=?", (int(amount), visit_id))
    db.commit()
    db.close()
    return jsonify({'visit_id': visit_id, 'amount': int(amount)})


@app.route('/api/customers/<int:customer_id>/location', methods=['PATCH'])
@require_perm('customers')
@safe_call
def update_customer_location(customer_id):
    data = request.get_json() or {}
    lat, lng = data.get('latitude'), data.get('longitude')
    if lat is None or lng is None:
        return jsonify({'error': 'latitude and longitude are required'}), 400
    db = get_db()
    db.execute("UPDATE customers SET latitude=?, longitude=?, location_accuracy_m=? WHERE id=?",
               (float(lat), float(lng), data.get('accuracy'), customer_id))
    db.commit()
    db.close()
    return jsonify({'message': 'location updated'})


@app.route('/api/customers/nearby')
@require_perm('customers')
@safe_call
def nearby_customers():
    try:
        lat = float(request.args['lat'])
        lng = float(request.args['lng'])
        radius = min(max(float(request.args.get('radius', 70)), 5), 5000)
    except (KeyError, ValueError):
        return jsonify({'error': 'valid lat/lng are required'}), 400

    db = get_db()
    rows = db.execute("""
        SELECT c.*,
          (SELECT group_concat(phone, ',') FROM customer_phones cp WHERE cp.customer_id=c.id) AS phones,
          (SELECT amount FROM service_visits sv WHERE sv.customer_id=c.id ORDER BY sv.created_at DESC LIMIT 1) AS last_amount,
          (SELECT service_type FROM service_visits sv WHERE sv.customer_id=c.id ORDER BY sv.created_at DESC LIMIT 1) AS last_service,
          (SELECT visited_at FROM service_visits sv WHERE sv.customer_id=c.id ORDER BY sv.created_at DESC LIMIT 1) AS last_visit
        FROM customers c
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """).fetchall()
    db.close()

    result = []
    for row in rows:
        item = dict(row)
        distance = haversine_m(lat, lng, float(item['latitude']), float(item['longitude']))
        if distance <= radius:
            item['distance_m'] = round(distance, 1)
            item['phones'] = item.get('phones', '').split(',') if item.get('phones') else ([item['phone']] if item.get('phone') else [])
            result.append(item)
    result.sort(key=lambda x: x['distance_m'])
    return jsonify(result[:50])
