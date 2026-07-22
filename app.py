import os
import io
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
from google import genai
import psycopg2
import psycopg2.extras

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-render-env-vars')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'changeme')

# New 2026 SDK Method: Yeh automatic Render ke Environment Variable se chabi utha lega
client = genai.Client()

PLAN_DAYS = {
    "1_month": 30,
    "3_months": 90,
    "6_months": 180,
    "1_year": 365,
}
PLAN_LABELS = {
    "1_month": "1 Month",
    "3_months": "3 Months",
    "6_months": "6 Months",
    "1_year": "1 Year",
}

# ============ DATABASE HELPERS ============

def get_db():
    db_url = os.environ.get('DATABASE_URL')
    conn = psycopg2.connect(db_url, sslmode='require')
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            plan_type VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            expiry_date TIMESTAMP NOT NULL
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print("DB init skipped/failed at startup:", e)

# JSON file se panic data load karne ka function
def load_database():
    file_path = os.path.join(os.path.dirname(__file__), 'data.json')
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# ============ PUBLIC PAGES ============

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/decode', methods=['POST'])
def decode():
    data = request.json
    code = data.get('code', '').strip().upper()
    panic_database = load_database()
    if code in panic_database:
        return jsonify({"status": "success", "data": panic_database[code]})
    else:
        return jsonify({"status": "error", "message": "This code is not in the database yet."})

@app.route('/scan-panic', methods=['POST'])
def scan_panic():
    # Server-side VIP check — never trust the frontend alone
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'Please login first'}), 401
    try:
        expiry = datetime.fromisoformat(session['expiry'])
    except Exception:
        return jsonify({'success': False, 'error': 'Session invalid, please login again'}), 401
    if datetime.utcnow() > expiry:
        session.clear()
        return jsonify({'success': False, 'error': 'Your VIP membership has expired'}), 401

    if 'panic_image' not in request.files:
        return jsonify({'success': False, 'error': 'No photo was selected'}), 400
    file = request.files['panic_image']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'File name is empty'}), 400
    try:
        image_bytes = file.read()
        image = Image.open(io.BytesIO(image_bytes))
        prompt = """Ye ek iPhone panic-log crash report ki photo hai (chahe angle se li ho, dhundhli ho, andheri ho, background mein haath/table dikh raha ho — jo bhi ho).

Tumhara kaam: is photo mein jitna bhi panic/crash text (panicString) visible hai, use BILKUL WAISA HI, jaisa likha hai, transcribe karo. Khaaskar dhyan rakhna in cheezon ka agar dikhein:
- "S.sensor array 0 - N is ..." wali poori line (numbers exactly jaise likhe hain, comma samet)
- "F.sensor array ..." line
- "Missing sensor(s): ..." line
- "SMC PANIC", "AOP PANIC", "DCP PANIC", "SCMto", "userspace watchdog timeout" jaise keywords
- koi bhi 0x hex code ya panic identifier

Sirf transcribed text return karo — koi explanation, koi "here is the text", koi markdown formatting nahi. Agar text bilkul illegible/unreadable hai to sirf "UNREADABLE" likhna."""
        response = client.models.generate_content(model='gemini-2.5-flash', contents=[image, prompt])
        if not response or not response.text:
            return jsonify({'success': False, 'error': "AI response khali mila."}), 500
        extracted_text = response.text.strip()
        return jsonify({'success': True, 'text': extracted_text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============ CUSTOMER LOGIN / VIP PORTAL ============

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'GET' and 'username' in session:
        try:
            if datetime.utcnow() <= datetime.fromisoformat(session['expiry']):
                return redirect(url_for('vip_portal'))
        except Exception:
            session.clear()

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user or not check_password_hash(user['password_hash'], password):
            error = "Galat username ya password."
        elif datetime.utcnow() > user['expiry_date']:
            error = "Aapki VIP membership expire ho gayi hai. Renew karne ke liye WhatsApp par contact karein."
        else:
            session['username'] = user['username']
            session['expiry'] = user['expiry_date'].isoformat()
            return redirect(url_for('vip_portal'))

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/vip')
def vip_portal():
    if 'username' not in session:
        return redirect(url_for('login'))
    expiry = datetime.fromisoformat(session['expiry'])
    if datetime.utcnow() > expiry:
        session.clear()
        return redirect(url_for('login'))
    days_left = (expiry - datetime.utcnow()).days
    return render_template('vip.html', username=session['username'], expiry=expiry.strftime('%d %b %Y'), days_left=days_left)

# ============ ADMIN PANEL (owner only) ============

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if pw == ADMIN_PASSWORD:
            session['is_admin'] = True
            return redirect(url_for('admin_panel'))
        error = "Galat admin password."
    return render_template('admin_login.html', error=error)

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))

    message = None
    created_creds = None

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        plan_type = request.form.get('plan_type', '1_month')

        if not username or not password:
            message = "Username aur password dono zaroori hain."
        else:
            days = PLAN_DAYS.get(plan_type, 30)
            expiry_date = datetime.utcnow() + timedelta(days=days)
            password_hash = generate_password_hash(password)

            conn = None
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO users (username, password_hash, plan_type, expiry_date) VALUES (%s, %s, %s, %s)",
                    (username, password_hash, plan_type, expiry_date)
                )
                conn.commit()
                cur.close()
                created_creds = {
                    "username": username,
                    "password": password,
                    "plan": PLAN_LABELS.get(plan_type, plan_type),
                    "expiry": expiry_date.strftime('%d %b %Y')
                }
                message = "VIP account ban gaya!"
            except psycopg2.errors.UniqueViolation:
                if conn: conn.rollback()
                message = "Ye username already exist karta hai. Doosra try karein."
            except Exception as e:
                if conn: conn.rollback()
                message = "Error: " + str(e)
            finally:
                if conn: conn.close()

    # Fetch existing users list for reference
    users = []
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT username, plan_type, expiry_date, created_at FROM users ORDER BY created_at DESC")
        users = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print("Could not fetch users:", e)

    return render_template('admin.html', message=message, created_creds=created_creds, users=users, plans=PLAN_LABELS)

@app.route('/admin-logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
