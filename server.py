from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import sqlite3
import os
from datetime import datetime, timedelta
from functools import wraps
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["100 per minute"])

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "aquagold-secret-key-change-in-production")
DB_PATH = os.getenv("DB_PATH", "/app/data/app.db")
TOKEN_EXPIRY_HOURS = 24

def cfg(key):
    return os.getenv(key, {
        "LOGIN_RATE_LIMIT": "5 per minute",
        "API_RATE_LIMIT": "100 per minute"
    }.get(key, ""))

# Database functions
def get_db():
    try:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        return db
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def init_db():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        if os.path.exists(DB_PATH):
            try:
                db = get_db()
                cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                if cursor.fetchone():
                    logger.info("Database already initialized")
                    db.close()
                    return
                db.close()
            except:
                pass
        
        db = get_db()
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                role TEXT DEFAULT 'user',
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                address TEXT,
                device_model TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER,
                name TEXT,
                phone TEXT,
                address TEXT,
                device_model TEXT,
                description TEXT,
                amount REAL DEFAULT 0,
                status TEXT DEFAULT 'registered',
                date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
        """)
        
        db.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                quantity INTEGER DEFAULT 0,
                min_quantity INTEGER DEFAULT 0,
                unit TEXT,
                price REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        db.commit()
        
        cursor = db.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            db.execute("""
                INSERT INTO users (username, password_hash, first_name, last_name, role)
                VALUES (?, ?, ?, ?, ?)
            """, (
                "admin",
                generate_password_hash("admin1234"),
                "مدیر",
                "اصلی",
                "superadmin"
            ))
            db.commit()
            logger.info("Admin user created: admin / admin1234")
        
        db.close()
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

# Authentication helpers
def create_token(user_id, role):
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

@app.before_request
def check_authentication():
    # ✅ Bypass auth for public & static routes
    if request.path in ['/', '/health', '/api/login', '/api/logout'] \
       or request.path.startswith('/static/') \
       or request.path.endswith(('.js', '.css', '.png', '.svg', '.ico')):
        return None

    # ✅ NEW: Bypass auth for all non-API routes
    if not request.path.startswith('/api/'):
        return None

    # ✅ Require token for all other /api/* routes
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        logger.warning(f"auth_fail: missing/invalid Authorization header for {request.path}")
        return jsonify({'error': 'Authorization header missing'}), 401

    try:
        token = auth_header.split(" ")[1]
    except IndexError:
        logger.warning(f"auth_fail: malformed token format for {request.path}")
        return jsonify({'error': 'Invalid token format'}), 401

    payload = verify_token(token)
    if not payload:
        logger.warning(f"auth_fail: expired/invalid token for {request.path}")
        return jsonify({'error': 'Token is invalid or expired'}), 401

    request.current_user = payload

def token_required(f):
    """Decorator for endpoints that require authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Auth already checked by before_request middleware
        if not hasattr(request, 'current_user'):
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated

def require_perm(permission):
    """Decorator for endpoints that require specific permissions"""
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            try:
                user_role = request.current_user.get('role', 'user')
                
                if user_role == 'superadmin':
                    return f(*args, **kwargs)
                
                allowed = {
                    'dashboard': ['admin', 'user'],
                    'jobs': ['admin', 'user'],
                    'customers': ['admin', 'user'],
                    'inventory': ['admin', 'user'],
                    'users': ['superadmin']
                }
                
                if permission in allowed and user_role in allowed[permission]:
                    return f(*args, **kwargs)
                
                return jsonify({'error': 'Permission denied'}), 403
            except Exception as e:
                logger.error(f"Permission check error: {e}")
                return jsonify({'error': 'Authorization error'}), 500
        
        return decorated
    return decorator

def safe_call(f):
    """Decorator for error handling"""
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {f.__name__}: {str(e)}", exc_info=True)
            return jsonify({'error': 'Internal server error', 'details': str(e)}), 500
    return decorated

# Health check endpoint (PUBLIC)
@app.route('/health')
def health():
    try:
        db = get_db()
        db.execute("SELECT 1")
        db.close()
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 503

# Serve frontend (PUBLIC)
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ✅ PUBLIC: Login endpoint - NO authentication required
@app.route('/api/login', methods=['POST'])
@limiter.limit(cfg("LOGIN_RATE_LIMIT"))
@safe_call
def login():
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'Request body required'}), 400
    
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()
    db.close()
    
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = create_token(user['id'], user['role'])
    
    logger.info(f"Login successful: {username}")
    
    return jsonify({
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'role': user['role']
        }
    })

# ✅ PUBLIC: Logout endpoint - NO authentication required
@app.route('/api/logout', methods=['POST'])
@safe_call
def logout():
    return jsonify({'message': 'Logged out successfully'})

# ✅ PROTECTED: Stats endpoint
@app.route('/api/stats')
@require_perm('dashboard')
@safe_call
def get_stats():
    db = get_db()
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    today_jobs = db.execute("""
        SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total
        FROM jobs WHERE date = ?
    """, (today,)).fetchone()
    
    total_customers = db.execute("SELECT COUNT(*) as count FROM customers").fetchone()['count']
    
    low_stock = db.execute("""
        SELECT COUNT(*) as count FROM inventory 
        WHERE quantity <= min_quantity AND quantity > 0
    """).fetchone()['count']
    
    out_of_stock = db.execute("""
        SELECT COUNT(*) as count FROM inventory 
        WHERE quantity = 0
    """).fetchone()['count']
    
    db.close()
    
    return jsonify({
        'today': {
            'count': today_jobs['count'],
            'total': today_jobs['total']
        },
        'total_customers': total_customers,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock
    })

# ✅ PROTECTED: Jobs endpoints
@app.route('/api/jobs', methods=['GET'])
@require_perm('jobs')
@safe_call
def list_jobs():
    db = get_db()
    jobs = db.execute("""
        SELECT j.*, c.name as customer_name
        FROM jobs j
        LEFT JOIN customers c ON j.customer_id = c.id
        ORDER BY j.created_at DESC
    """).fetchall()
    db.close()
    
    return jsonify([dict(job) for job in jobs])

@app.route('/api/jobs', methods=['POST'])
@require_perm('jobs')
@safe_call
def create_job():
    data = request.get_json()
    
    db = get_db()
    cursor = db.execute("""
        INSERT INTO jobs (customer_id, name, phone, address, device_model, description, amount, status, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get('customer_id'),
        data.get('name'),
        data.get('phone'),
        data.get('address'),
        data.get('device_model'),
        data.get('description'),
        data.get('amount', 0),
        data.get('status', 'registered'),
        data.get('date', datetime.now().strftime('%Y-%m-%d'))
    ))
    db.commit()
    job_id = cursor.lastrowid
    db.close()
    
    return jsonify({'id': job_id, 'message': 'Job created'}), 201

@app.route('/api/jobs/<int:job_id>', methods=['GET'])
@require_perm('jobs')
@safe_call
def get_job(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    db.close()
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(dict(job))

@app.route('/api/jobs/<int:job_id>', methods=['PUT'])
@require_perm('jobs')
@safe_call
def update_job(job_id):
    data = request.get_json()
    
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    
    if not job:
        db.close()
        return jsonify({'error': 'Job not found'}), 404
    
    db.execute("""
        UPDATE jobs SET
            customer_id = ?, name = ?, phone = ?, address = ?,
            device_model = ?, description = ?, amount = ?, status = ?, date = ?
        WHERE id = ?
    """, (
        data.get('customer_id', job['customer_id']),
        data.get('name', job['name']),
        data.get('phone', job['phone']),
        data.get('address', job['address']),
        data.get('device_model', job['device_model']),
        data.get('description', job['description']),
        data.get('amount', job['amount']),
        data.get('status', job['status']),
        data.get('date', job['date']),
        job_id
    ))
    db.commit()
    db.close()
    
    return jsonify({'message': 'Job updated'})

@app.route('/api/jobs/<int:job_id>', methods=['DELETE'])
@require_perm('jobs')
@safe_call
def delete_job(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    
    if not job:
        db.close()
        return jsonify({'error': 'Job not found'}), 404
    
    db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    db.commit()
    db.close()
    
    return jsonify({'message': 'Job deleted'})

# ✅ PROTECTED: Customers endpoints
@app.route('/api/customers', methods=['GET'])
@require_perm('customers')
@safe_call
def list_customers():
    db = get_db()
    customers = db.execute("SELECT * FROM customers ORDER BY created_at DESC").fetchall()
    db.close()
    
    return jsonify([dict(c) for c in customers])

@app.route('/api/customers', methods=['POST'])
@require_perm('customers')
@safe_call
def create_customer():
    data = request.get_json()
    
    db = get_db()
    cursor = db.execute("""
        INSERT INTO customers (name, phone, address, device_model, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (
        data.get('name'),
        data.get('phone'),
        data.get('address'),
        data.get('device_model'),
        data.get('notes')
    ))
    db.commit()
    customer_id = cursor.lastrowid
    db.close()
    
    return jsonify({'id': customer_id, 'message': 'Customer created'}), 201

@app.route('/api/customers/<int:cid>', methods=['GET'])
@require_perm('customers')
@safe_call
def get_customer(cid):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
    db.close()
    
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    
    return jsonify(dict(customer))

@app.route('/api/customers/<int:cid>', methods=['PUT'])
@require_perm('customers')
@safe_call
def update_customer(cid):
    data = request.get_json()
    
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
    
    if not customer:
        db.close()
        return jsonify({'error': 'Customer not found'}), 404
    
    db.execute("""
        UPDATE customers SET name = ?, phone = ?, address = ?, device_model = ?, notes = ?
        WHERE id = ?
    """, (
        data.get('name', customer['name']),
        data.get('phone', customer['phone']),
        data.get('address', customer['address']),
        data.get('device_model', customer['device_model']),
        data.get('notes', customer['notes']),
        cid
    ))
    db.commit()
    db.close()
    
    return jsonify({'message': 'Customer updated'})

@app.route('/api/customers/<int:cid>', methods=['DELETE'])
@require_perm('customers')
@safe_call
def delete_customer(cid):
    db = get_db()
    customer = db.execute("SELECT * FROM customers WHERE id = ?", (cid,)).fetchone()
    
    if not customer:
        db.close()
        return jsonify({'error': 'Customer not found'}), 404
    
    db.execute("DELETE FROM customers WHERE id = ?", (cid,))
    db.commit()
    db.close()
    
    return jsonify({'message': 'Customer deleted'})

@app.route('/api/customers/<int:cid>/jobs', methods=['GET'])
@require_perm('customers')
@safe_call
def customer_jobs(cid):
    db = get_db()
    jobs = db.execute("SELECT * FROM jobs WHERE customer_id = ? ORDER BY created_at DESC", (cid,)).fetchall()
    db.close()
    
    return jsonify([dict(j) for j in jobs])

# ✅ PROTECTED: Inventory endpoints
@app.route('/api/inventory', methods=['GET'])
@require_perm('inventory')
@safe_call
def list_inventory():
    db = get_db()
    items = db.execute("SELECT * FROM inventory ORDER BY name").fetchall()
    db.close()
    
    return jsonify([dict(item) for item in items])

@app.route('/api/inventory', methods=['POST'])
@require_perm('inventory')
@safe_call
def create_inventory_item():
    data = request.get_json()
    
    db = get_db()
    cursor = db.execute("""
        INSERT INTO inventory (name, category, quantity, min_quantity, unit, price)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        data.get('name'),
        data.get('category'),
        data.get('quantity', 0),
        data.get('min_quantity', 0),
        data.get('unit'),
        data.get('price', 0)
    ))
    db.commit()
    item_id = cursor.lastrowid
    db.close()
    
    return jsonify({'id': item_id, 'message': 'Inventory item created'}), 201

@app.route('/api/inventory/<int:item_id>', methods=['GET'])
@require_perm('inventory')
@safe_call
def get_inventory_item(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
    db.close()
    
    if not item:
        return jsonify({'error': 'Item not found'}), 404
    
    return jsonify(dict(item))

@app.route('/api/inventory/<int:item_id>', methods=['PUT'])
@require_perm('inventory')
@safe_call
def update_inventory_item(item_id):
    data = request.get_json()
    
    db = get_db()
    item = db.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
    
    if not item:
        db.close()
        return jsonify({'error': 'Item not found'}), 404
    
    db.execute("""
        UPDATE inventory SET name = ?, category = ?, quantity = ?, min_quantity = ?, unit = ?, price = ?
        WHERE id = ?
    """, (
        data.get('name', item['name']),
        data.get('category', item['category']),
        data.get('quantity', item['quantity']),
        data.get('min_quantity', item['min_quantity']),
        data.get('unit', item['unit']),
        data.get('price', item['price']),
        item_id
    ))
    db.commit()
    db.close()
    
    return jsonify({'message': 'Inventory item updated'})

@app.route('/api/inventory/<int:item_id>', methods=['DELETE'])
@require_perm('inventory')
@safe_call
def delete_inventory_item(item_id):
    db = get_db()
    item = db.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
    
    if not item:
        db.close()
        return jsonify({'error': 'Item not found'}), 404
    
    db.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    db.commit()
    db.close()
    
    return jsonify({'message': 'Inventory item deleted'})

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500

# Initialize database on startup
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

