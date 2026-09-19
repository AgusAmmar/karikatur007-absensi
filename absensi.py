"""
============================================================
  SISTEM ABSENSI KARANG TARUNA KARIKATUR 007
  Desa Mekarsari RT.07/RW.07
  Optimized Black & Gold v6.0 — Super Fast
============================================================
"""

import subprocess, sys, os, sqlite3, webbrowser, threading, time, random, hashlib, csv, io, json, secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

# ============================================================
# SET TIMEZONE KE WIB (Asia/Jakarta)
# ============================================================
os.environ['TZ'] = 'Asia/Jakarta'
try:
    time.tzset()
except AttributeError:
    pass

# Auto-install dependencies
REQUIRED_PACKAGES = [
    ('flask', 'flask'),
    ('flask_cors', 'flask-cors'),
    ('flask_limiter', 'flask-limiter'),
    ('werkzeug', 'werkzeug'),
    ('bcrypt', 'bcrypt')
]

for module_name, pip_name in REQUIRED_PACKAGES:
    try:
        __import__(module_name)
    except ImportError:
        print(f"📦 Installing {pip_name}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name, "--quiet"])
        except Exception as e:
            print(f"⚠️  Gagal install {pip_name}: {e}")

from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for, send_file, make_response, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from queue import Queue, Empty
import bcrypt

# ============================================================
# FUNGSI WAKTU WIB
# ============================================================
def sekarang_wib():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Jakarta"))
    except Exception:
        utc_now = datetime.now(timezone.utc)
        return utc_now.astimezone(timezone(timedelta(hours=7)))

def tgl_wib():
    return sekarang_wib().strftime('%Y-%m-%d')

def jam_wib():
    return sekarang_wib().strftime('%H:%M:%S')

def waktu_lengkap_wib():
    return sekarang_wib().strftime('%Y-%m-%d %H:%M:%S')

def hitung_bulan_next(bulan):
    """Hitung bulan berikutnya (untuk range query)"""
    try:
        th, bl = map(int, bulan.split('-'))
        if bl == 12:
            return f"{th+1}-01"
        return f"{th}-{bl+1:02d}"
    except:
        return bulan

# ============================================================
# KONFIGURASI
# ============================================================
ORG = {
    'nama': 'KARIKATUR 007',
    'jenis': 'Karang Taruna',
    'wilayah': 'RT.07 / RW.07',
    'desa': 'Desa Mekarsari',
    'sistem': 'Sistem Absensi Anggota',
    'tagline': 'Bersatu · Berkarya · Berdaya'
}

SECRET_KEY = os.environ.get('SECRET_KEY', 'karikatur007-fixed-secret-key-2026-aman')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Kar1katur007!Mekarsari#2026')

IS_PRODUCTION = bool(
    os.environ.get('RAILWAY_ENVIRONMENT') or
    os.environ.get('RAILWAY_STATIC_URL') or
    os.environ.get('RENDER') or
    os.environ.get('PRODUCTION') or
    os.environ.get('DYNO') or
    os.environ.get('PORT')
)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_DOMAIN'] = None
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://",
    strategy="fixed-window"
)

CORS(app, supports_credentials=True, origins='*')

DB_FILE = "absensi_k007_v6.db"
sse_clients = []

# ============================================================
# SECURITY HEADERS
# ============================================================
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'"
    )
    return response

@app.before_request
def force_https():
    if IS_PRODUCTION and not request.is_secure:
        if request.headers.get('X-Forwarded-Proto', 'http') != 'https':
            url = request.url.replace('http://', 'https://', 1)
            return redirect(url, code=301)

# ============================================================
# CSRF PROTECTION
# ============================================================
def validate_csrf_token():
    token_from_header = request.headers.get('X-CSRF-Token', '')
    token_from_session = session.get('_csrf_token', '')
    if not token_from_session or not token_from_header:
        return False
    return secrets.compare_digest(token_from_header, token_from_session)

@app.before_request
def csrf_protect():
    if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
        if request.path.startswith('/api/'):
            if request.path == '/api/login':
                return
            if not validate_csrf_token():
                return jsonify({'success': False, 'message': 'CSRF token tidak valid'}), 403

# ============================================================
# ERROR HANDLER
# ============================================================
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Endpoint tidak ditemukan'}), 404
    return redirect(url_for('login_page'))

@app.errorhandler(429)
def ratelimit_handler(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Terlalu banyak percobaan. Coba lagi nanti.'}), 429
    return "Terlalu banyak percobaan.", 429

@app.errorhandler(500)
def server_error(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': 'Server error'}), 500
    return "Server error", 500

# ============================================================
# DATABASE
# ============================================================
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode('utf-8')

def verify_password(password, hashed):
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except:
        return hashlib.sha256(password.encode()).hexdigest() == hashed

def get_db():
    """Buat koneksi DB dengan WAL mode untuk performa maksimal"""
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA cache_size=-64000')  # 64MB cache
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS anggota (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_anggota TEXT UNIQUE,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        nama TEXT NOT NULL,
        jabatan TEXT DEFAULT 'Anggota',
        divisi TEXT DEFAULT 'Umum',
        email TEXT DEFAULT '',
        no_hp TEXT DEFAULT '',
        role TEXT DEFAULT 'anggota',
        aktif INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS absensi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        anggota_id INTEGER NOT NULL,
        tanggal TEXT NOT NULL,
        jam_masuk TEXT,
        jam_pulang TEXT,
        status TEXT DEFAULT 'Hadir',
        kegiatan TEXT DEFAULT '',
        FOREIGN KEY (anggota_id) REFERENCES anggota(id)
    )''')
    
    # Index untuk performa maksimal
    c.execute('CREATE INDEX IF NOT EXISTS idx_absensi_tanggal ON absensi(tanggal)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_absensi_anggota ON absensi(anggota_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_absensi_tanggal_anggota ON absensi(tanggal, anggota_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_anggota_aktif_role ON anggota(aktif, role)')
    
    c.execute('''CREATE TABLE IF NOT EXISTS event_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipe TEXT NOT NULL,
        anggota_id INTEGER,
        nama TEXT,
        pesan TEXT,
        waktu TEXT NOT NULL
    )''')
    
    c.execute('CREATE INDEX IF NOT EXISTS idx_event_waktu ON event_log(id DESC)')
    
    c.execute('''CREATE TABLE IF NOT EXISTS login_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        ip_address TEXT,
        berhasil INTEGER,
        waktu TEXT NOT NULL
    )''')
    
    c.execute('SELECT COUNT(*) FROM anggota WHERE role = "admin"')
    if c.fetchone()[0] == 0:
        c.execute('''INSERT INTO anggota 
            (no_anggota, username, password, nama, jabatan, divisi, email, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            ('K007-001', ADMIN_USERNAME, hash_password(ADMIN_PASSWORD), 'Administrator',
             'Ketua', 'Pengurus', 'admin@karikatur007.id', 'admin',
             waktu_lengkap_wib()))
        print(f"✅ Admin dibuat: {ADMIN_USERNAME}")
    
    conn.commit()
    conn.close()
    print(f"✅ Database siap: {DB_FILE}")

def log_login_attempt(username, berhasil):
    try:
        ip = request.remote_addr or 'unknown'
        if request.headers.get('X-Forwarded-For'):
            ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO login_attempts (username, ip_address, berhasil, waktu) VALUES (?, ?, ?, ?)',
                  (username, ip, 1 if berhasil else 0, waktu_lengkap_wib()))
        conn.commit()
        conn.close()
    except:
        pass

def log_event(tipe, anggota_id, nama, pesan):
    waktu = jam_wib()
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO event_log (tipe, anggota_id, nama, pesan, waktu) VALUES (?, ?, ?, ?, ?)',
              (tipe, anggota_id, nama, pesan, waktu))
    conn.commit()
    conn.close()
    event_data = {'tipe': tipe, 'anggota_id': anggota_id, 'nama': nama,
                  'pesan': pesan, 'waktu': waktu}
    for q in sse_clients[:]:
        try:
            q.put_nowait(event_data)
        except:
            try: sse_clients.remove(q)
            except: pass

# ============================================================
# DECORATORS
# ============================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Sesi login habis. Silakan login ulang.'}), 401
        if session.get('role') != 'admin':
            return jsonify({'success': False, 'message': 'Akses ditolak'}), 403
        return f(*args, **kwargs)
    return decorated

# ============================================================
# API AUTH
# ============================================================
@app.route('/login', methods=['GET'])
def login_page():
    csrf_token = secrets.token_urlsafe(32)
    session['_csrf_token'] = csrf_token
    return render_template_string(LOGIN_HTML, o=ORG, csrf_token=csrf_token)

@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
@limiter.limit("20 per hour")
def api_login():
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()[:50]
        password = data.get('password', '')[:100]
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username dan password wajib diisi'})
        
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id, username, nama, role, aktif, password FROM anggota WHERE username = ?', (username,))
        row = c.fetchone()
        conn.close()
        
        if not row:
            log_login_attempt(username, False)
            time.sleep(0.3)
            return jsonify({'success': False, 'message': 'Username atau password salah'})
        
        if not verify_password(password, row[5]):
            log_login_attempt(username, False)
            time.sleep(0.3)
            return jsonify({'success': False, 'message': 'Username atau password salah'})
        
        if not row[4]:
            log_login_attempt(username, False)
            return jsonify({'success': False, 'message': 'Akun tidak aktif'})
        
        session.permanent = True
        session['user_id'] = row[0]
        session['username'] = row[1]
        session['nama'] = row[2]
        session['role'] = row[3]
        session['_csrf_token'] = secrets.token_urlsafe(32)
        session.modified = True
        
        log_login_attempt(username, True)
        return jsonify({'success': True, 'role': row[3], 'nama': row[2]})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Terjadi kesalahan'})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/me', methods=['GET'])
def api_me():
    if 'user_id' not in session:
        return jsonify({'logged_in': False})
    return jsonify({
        'logged_in': True,
        'user_id': session['user_id'],
        'username': session['username'],
        'nama': session['nama'],
        'role': session['role'],
        'csrf_token': session.get('_csrf_token', ''),
        'server_time_wib': waktu_lengkap_wib()
    })

# ============================================================
# API ABSENSI
# ============================================================
@app.route('/api/absensi/status', methods=['GET'])
def absensi_status():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    user_id = session['user_id']
    today = tgl_wib()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, jam_masuk, jam_pulang, status FROM absensi WHERE anggota_id = ? AND tanggal = ?',
              (user_id, today))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({'sudah_masuk': False, 'sudah_pulang': False})
    return jsonify({
        'sudah_masuk': bool(row[1]), 'sudah_pulang': bool(row[2]),
        'jam_masuk': row[1] or '-', 'jam_pulang': row[2] or '-', 'status': row[3]
    })

@app.route('/api/absensi/masuk', methods=['POST'])
def absensi_masuk():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    user_id = session['user_id']
    today = tgl_wib()
    now = jam_wib()
    data = request.get_json() or {}
    kegiatan = str(data.get('kegiatan', ''))[:200]
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, jam_masuk FROM absensi WHERE anggota_id = ? AND tanggal = ?', (user_id, today))
    row = c.fetchone()
    if row:
        if row[1]:
            conn.close()
            return jsonify({'success': False, 'message': 'Anda sudah absen datang hari ini'})
        c.execute('UPDATE absensi SET jam_masuk = ?, kegiatan = ? WHERE id = ?', (now, kegiatan, row[0]))
    else:
        c.execute('INSERT INTO absensi (anggota_id, tanggal, jam_masuk, kegiatan) VALUES (?, ?, ?, ?)',
                  (user_id, today, now, kegiatan))
    conn.commit()
    conn.close()
    log_event('masuk', user_id, session['nama'], f"{session['nama']} absen datang pukul {now}")
    return jsonify({'success': True, 'message': f'Absen datang berhasil pukul {now}', 'jam': now})

@app.route('/api/absensi/pulang', methods=['POST'])
def absensi_pulang():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    user_id = session['user_id']
    today = tgl_wib()
    now = jam_wib()
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, jam_masuk, jam_pulang FROM absensi WHERE anggota_id = ? AND tanggal = ?', (user_id, today))
    row = c.fetchone()
    if not row or not row[1]:
        conn.close()
        return jsonify({'success': False, 'message': 'Anda belum absen datang hari ini'})
    if row[2]:
        conn.close()
        return jsonify({'success': False, 'message': 'Anda sudah absen pulang hari ini'})
    c.execute('UPDATE absensi SET jam_pulang = ? WHERE id = ?', (now, row[0]))
    conn.commit()
    conn.close()
    log_event('pulang', user_id, session['nama'], f"{session['nama']} absen pulang pukul {now}")
    return jsonify({'success': True, 'message': f'Absen pulang berhasil pukul {now}', 'jam': now})

@app.route('/api/absensi/riwayat', methods=['GET'])
def absensi_riwayat():
    """Riwayat absensi — pakai RANGE query (lebih cepat dari LIKE)"""
    if 'user_id' not in session:
        return jsonify([]), 401
    user_id = session['user_id']
    role = session['role']
    bulan = request.args.get('bulan', sekarang_wib().strftime('%Y-%m'))
    if len(bulan) != 7 or bulan[4] != '-':
        bulan = sekarang_wib().strftime('%Y-%m')
    
    bulan_next = hitung_bulan_next(bulan)
    filter_user = request.args.get('user_id')
    
    conn = get_db()
    c = conn.cursor()
    
    if role == 'admin' and filter_user:
        try:
            filter_user = int(filter_user)
            c.execute('''SELECT a.id, a.tanggal, a.jam_masuk, a.jam_pulang, a.status, a.kegiatan,
                         k.nama, k.jabatan, k.id
                         FROM absensi a JOIN anggota k ON a.anggota_id = k.id
                         WHERE a.tanggal >= ? AND a.tanggal < ? AND a.anggota_id = ?
                         ORDER BY a.tanggal DESC, a.jam_masuk DESC
                         LIMIT 500''', (bulan + '-01', bulan_next + '-01', filter_user))
        except:
            c.execute('''SELECT a.id, a.tanggal, a.jam_masuk, a.jam_pulang, a.status, a.kegiatan,
                         k.nama, k.jabatan, k.id
                         FROM absensi a JOIN anggota k ON a.anggota_id = k.id
                         WHERE a.tanggal >= ? AND a.tanggal < ?
                         ORDER BY a.tanggal DESC, a.jam_masuk DESC
                         LIMIT 500''', (bulan + '-01', bulan_next + '-01'))
    elif role == 'admin':
        c.execute('''SELECT a.id, a.tanggal, a.jam_masuk, a.jam_pulang, a.status, a.kegiatan,
                     k.nama, k.jabatan, k.id
                     FROM absensi a JOIN anggota k ON a.anggota_id = k.id
                     WHERE a.tanggal >= ? AND a.tanggal < ?
                     ORDER BY a.tanggal DESC, a.jam_masuk DESC
                     LIMIT 500''', (bulan + '-01', bulan_next + '-01'))
    else:
        c.execute('''SELECT a.id, a.tanggal, a.jam_masuk, a.jam_pulang, a.status, a.kegiatan,
                     k.nama, k.jabatan, k.id
                     FROM absensi a JOIN anggota k ON a.anggota_id = k.id
                     WHERE a.tanggal >= ? AND a.tanggal < ? AND a.anggota_id = ?
                     ORDER BY a.tanggal DESC
                     LIMIT 500''', (bulan + '-01', bulan_next + '-01', user_id))
    
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'tanggal': r[1], 'jam_masuk': r[2] or '-', 'jam_pulang': r[3] or '-',
        'status': r[4], 'kegiatan': r[5], 'nama': r[6], 'jabatan': r[7], 'anggota_id': r[8]
    } for r in rows])

@app.route('/api/absensi/hari-ini', methods=['GET'])
def absensi_hari_ini():
    """Absen hari ini dengan fallback UTC untuk data lama"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify([]), 403
    
    today_wib = tgl_wib()
    now_wib = sekarang_wib()
    today_utc = now_wib.astimezone(timezone.utc).strftime('%Y-%m-%d')
    yesterday_wib = (now_wib - timedelta(days=1)).strftime('%Y-%m-%d')
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT a.id, k.nama, k.jabatan, k.divisi, a.jam_masuk, a.jam_pulang, a.status, a.tanggal
                 FROM absensi a JOIN anggota k ON a.anggota_id = k.id
                 WHERE (a.tanggal = ? OR a.tanggal = ? OR a.tanggal = ?) 
                 AND a.jam_masuk IS NOT NULL
                 ORDER BY a.jam_masuk DESC
                 LIMIT 100''', (today_wib, today_utc, yesterday_wib))
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'nama': r[1], 'jabatan': r[2], 'divisi': r[3],
        'jam_masuk': r[4] or '-', 'jam_pulang': r[5] or '-', 'status': r[6], 'tanggal': r[7]
    } for r in rows])

# ============================================================
# REALTIME
# ============================================================
@app.route('/api/events')
def sse_events():
    if 'user_id' not in session:
        return "Unauthorized", 401
    def event_stream():
        q = Queue()
        sse_clients.append(q)
        try:
            yield f"data: {json.dumps({'tipe':'connected'})}\n\n"
            while True:
                try:
                    event = q.get(timeout=25)
                    yield f"data: {json.dumps(event)}\n\n"
                except Empty:
                    yield f"data: {json.dumps({'tipe':'heartbeat'})}\n\n"
        except GeneratorExit:
            pass
        finally:
            if q in sse_clients:
                sse_clients.remove(q)
    return Response(event_stream(), mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'})

@app.route('/api/events/riwayat')
def events_riwayat():
    if 'user_id' not in session:
        return jsonify([]), 401
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT tipe, nama, pesan, waktu FROM event_log ORDER BY id DESC LIMIT 15')
    rows = c.fetchall()
    conn.close()
    return jsonify([{'tipe': r[0], 'nama': r[1], 'pesan': r[2], 'waktu': r[3]} for r in rows])

# ============================================================
# REKAP — Optimasi 1 Query Agregat
# ============================================================
@app.route('/api/rekap', methods=['GET'])
def api_rekap():
    """Rekap — pakai 1 query agregat (bukan N×4 query)"""
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({'success': False, 'rekap': [], 'hari_kerja': 0}), 403
    bulan = request.args.get('bulan', sekarang_wib().strftime('%Y-%m'))
    if len(bulan) != 7:
        bulan = sekarang_wib().strftime('%Y-%m')
    
    bulan_next = hitung_bulan_next(bulan)
    
    conn = get_db()
    c = conn.cursor()
    
    # Ambil daftar anggota aktif
    c.execute('SELECT id, nama, jabatan, divisi FROM anggota WHERE aktif = 1 ORDER BY nama')
    anggota_list = c.fetchall()
    
    # Hitung hari kerja (Senin-Sabtu)
    tahun, bln = map(int, bulan.split('-'))
    hari_kerja = 0
    for d in range(1, 32):
        try:
            tgl = datetime(tahun, bln, d)
            if tgl.weekday() != 6:
                hari_kerja += 1
        except: break
    
    # 1 QUERY AGREGAT untuk semua anggota
    c.execute('''SELECT 
                    anggota_id,
                    SUM(CASE WHEN jam_masuk IS NOT NULL THEN 1 ELSE 0 END) as hadir,
                    SUM(CASE WHEN status = 'Izin' THEN 1 ELSE 0 END) as izin,
                    SUM(CASE WHEN status = 'Sakit' THEN 1 ELSE 0 END) as sakit,
                    SUM(CASE WHEN status = 'Cuti' THEN 1 ELSE 0 END) as cuti
                 FROM absensi
                 WHERE tanggal >= ? AND tanggal < ?
                 GROUP BY anggota_id''', (bulan + '-01', bulan_next + '-01'))
    
    rekap_map = {}
    for row in c.fetchall():
        rekap_map[row[0]] = {
            'hadir': row[1] or 0,
            'izin': row[2] or 0,
            'sakit': row[3] or 0,
            'cuti': row[4] or 0
        }
    conn.close()
    
    # Gabung dengan daftar anggota
    rekap = []
    for k in anggota_list:
        kid, nama, jabatan, divisi = k
        stats = rekap_map.get(kid, {'hadir': 0, 'izin': 0, 'sakit': 0, 'cuti': 0})
        hadir = stats['hadir']
        izin = stats['izin']
        sakit = stats['sakit']
        cuti = stats['cuti']
        alpha = max(0, hari_kerja - hadir - izin - sakit - cuti)
        rekap.append({
            'anggota_id': kid, 'nama': nama, 'jabatan': jabatan, 'divisi': divisi,
            'hadir': hadir, 'izin': izin, 'sakit': sakit, 'cuti': cuti, 'alpha': alpha
        })
    
    return jsonify({'bulan': bulan, 'hari_kerja': hari_kerja, 'rekap': rekap})

# ============================================================
# EXPORT
# ============================================================
@app.route('/api/export/csv')
def export_csv():
    if 'user_id' not in session or session.get('role') != 'admin':
        return "Akses ditolak", 403
    bulan = request.args.get('bulan', sekarang_wib().strftime('%Y-%m'))
    if len(bulan) != 7:
        bulan = sekarang_wib().strftime('%Y-%m')
    bulan_next = hitung_bulan_next(bulan)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT k.no_anggota, k.nama, k.jabatan, k.divisi, a.tanggal, a.jam_masuk, a.jam_pulang, a.status
                 FROM absensi a JOIN anggota k ON a.anggota_id = k.id
                 WHERE a.tanggal >= ? AND a.tanggal < ?
                 ORDER BY a.tanggal DESC, k.nama
                 LIMIT 1000''', (bulan + '-01', bulan_next + '-01'))
    rows = c.fetchall()
    conn.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['No Anggota', 'Nama', 'Jabatan', 'Divisi', 'Tanggal', 'Datang', 'Pulang', 'Status'])
    for r in rows:
        writer.writerow(r)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename=absensi-k007-{bulan}.csv'
    return response

@app.route('/api/export/pdf', methods=['GET'])
def export_pdf():
    if 'user_id' not in session or session.get('role') != 'admin':
        return "Akses ditolak", 403
    bulan = request.args.get('bulan', sekarang_wib().strftime('%Y-%m'))
    if len(bulan) != 7:
        bulan = sekarang_wib().strftime('%Y-%m')
    bulan_next = hitung_bulan_next(bulan)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT k.no_anggota, k.nama, k.jabatan, k.divisi, a.tanggal, a.jam_masuk, a.jam_pulang, a.status
                 FROM absensi a JOIN anggota k ON a.anggota_id = k.id
                 WHERE a.tanggal >= ? AND a.tanggal < ?
                 ORDER BY a.tanggal DESC, k.nama
                 LIMIT 1000''', (bulan + '-01', bulan_next + '-01'))
    rows = c.fetchall()
    conn.close()
    th, bl = bulan.split('-')
    nama_bulan = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
                  'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
    judul_bulan = f"{nama_bulan[int(bl)]} {th}"
    html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Absensi {ORG['nama']} - {judul_bulan}</title>
<style>
    @page {{ margin: 20mm; }}
    * {{ margin:0; padding:0; box-sizing:border-box; font-family:'Helvetica','Arial',sans-serif; }}
    body {{ padding:30px; color:#111827; font-size:12px; }}
    .header {{ border-bottom:2px solid #b45309; padding-bottom:15px; margin-bottom:20px; text-align:center; }}
    .header h1 {{ font-size:20px; letter-spacing:3px; margin-bottom:4px; color:#b45309; }}
    .header .sub {{ font-size:11px; color:#6b7280; }}
    .header .loc {{ font-size:10px; color:#9ca3af; margin-top:2px; }}
    .doc-title {{ text-align:center; margin-bottom:20px; }}
    .doc-title h2 {{ font-size:13px; letter-spacing:2px; margin-bottom:4px; }}
    .doc-title .sub {{ font-size:11px; color:#6b7280; }}
    .meta {{ display:flex; gap:30px; margin-bottom:18px; padding:10px 14px; background:#fef3c7; border-left:3px solid #b45309; }}
    .meta .label {{ font-size:9px; color:#6b7280; text-transform:uppercase; letter-spacing:1px; margin-bottom:2px; }}
    .meta .value {{ font-size:12px; font-weight:700; }}
    table {{ width:100%; border-collapse:collapse; }}
    th {{ background:#111827; color:#fbbf24; padding:9px 8px; text-align:left; font-size:9px; text-transform:uppercase; font-weight:600; letter-spacing:0.5px; }}
    td {{ padding:7px 8px; border-bottom:1px solid #e5e7eb; font-size:10.5px; }}
    tr:nth-child(even) td {{ background:#f9fafb; }}
    .center {{ text-align:center; }}
    .footer {{ margin-top:30px; padding-top:12px; border-top:1px solid #e5e7eb; display:flex; justify-content:space-between; font-size:9px; color:#9ca3af; }}
    .btn-print {{ position:fixed; top:20px; right:20px; background:#111827; color:#fbbf24; padding:10px 18px; border:none; border-radius:3px; font-size:11px; font-weight:600; cursor:pointer; }}
    @media print {{ body {{ padding:0; }} .no-print {{ display:none !important; }} }}
</style></head><body>
<button class="btn-print no-print" onclick="window.print()">PRINT / SAVE PDF</button>
<div class="header">
    <h1>{ORG['nama']}</h1>
    <div class="sub">{ORG['jenis']} · {ORG['tagline']}</div>
    <div class="loc">{ORG['wilayah']} · {ORG['desa']}</div>
</div>
<div class="doc-title">
    <h2>LAPORAN ABSENSI ANGGOTA</h2>
    <div class="sub">Periode: {judul_bulan}</div>
</div>
<div class="meta">
    <div><div class="label">Total Anggota</div><div class="value">{len(set([r[0] for r in rows]))}</div></div>
    <div><div class="label">Total Record</div><div class="value">{len(rows)}</div></div>
    <div><div class="label">Status</div><div class="value">FINAL</div></div>
</div>
<table>
<thead><tr>
    <th style="width:35px;">No</th><th style="width:75px;">No. Anggota</th><th>Nama</th>
    <th>Jabatan</th><th>Divisi</th><th>Tanggal</th>
    <th class="center">Datang</th><th class="center">Pulang</th><th>Status</th>
</tr></thead><tbody>'''
    for i, r in enumerate(rows, 1):
        html += f'''<tr><td class="center">{i}</td><td>{r[0]}</td><td><strong>{r[1]}</strong></td>
            <td>{r[2]}</td><td>{r[3]}</td><td>{r[4]}</td>
            <td class="center">{r[5] or '-'}</td><td class="center">{r[6] or '-'}</td><td>{r[7]}</td></tr>'''
    html += f'''</tbody></table>
<div class="footer">
    <div>Dicetak otomatis oleh {ORG['sistem']}</div>
    <div>{ORG['nama']} &copy; {sekarang_wib().year}</div>
</div>
<script>setTimeout(() => window.print(), 500);</script>
</body></html>'''
    return html

# ============================================================
# KELOLA ANGGOTA
# ============================================================
@app.route('/api/anggota', methods=['GET'])
def get_anggota():
    if 'user_id' not in session:
        return jsonify([]), 401
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, no_anggota, username, nama, jabatan, divisi, email, no_hp, role, aktif FROM anggota ORDER BY nama')
    rows = c.fetchall()
    conn.close()
    return jsonify([{
        'id': r[0], 'no_anggota': r[1], 'username': r[2], 'nama': r[3], 'jabatan': r[4],
        'divisi': r[5], 'email': r[6], 'no_hp': r[7], 'role': r[8], 'aktif': bool(r[9])
    } for r in rows])

@app.route('/api/anggota', methods=['POST'])
@admin_required
def tambah_anggota():
    data = request.get_json() or {}
    username = str(data.get('username', '')).strip()[:50]
    password = str(data.get('password', '')).strip()
    nama = str(data.get('nama', '')).strip()[:100]
    jabatan = str(data.get('jabatan', 'Anggota'))[:50]
    divisi = str(data.get('divisi', 'Umum'))[:50]
    email = str(data.get('email', ''))[:100]
    no_hp = str(data.get('no_hp', ''))[:20]
    no_anggota = str(data.get('no_anggota', ''))[:20]
    
    if not username or not password or not nama:
        return jsonify({'success': False, 'message': 'Username, password, dan nama wajib diisi'})
    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password minimal 6 karakter'})
    if len(username) < 3:
        return jsonify({'success': False, 'message': 'Username minimal 3 karakter'})
    
    try:
        conn = get_db()
        c = conn.cursor()
        if not no_anggota:
            c.execute('SELECT COUNT(*) FROM anggota WHERE role = "anggota"')
            count = c.fetchone()[0] + 2
            no_anggota = f'K007-{count:03d}'
        c.execute('''INSERT INTO anggota 
            (no_anggota, username, password, nama, jabatan, divisi, email, no_hp, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'anggota', ?)''',
            (no_anggota, username, hash_password(password), nama, jabatan, divisi, email, no_hp,
             waktu_lengkap_wib()))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Anggota berhasil ditambahkan', 'no_anggota': no_anggota})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Username atau No. Anggota sudah dipakai'})

@app.route('/api/anggota/<int:kid>', methods=['PUT'])
@admin_required
def edit_anggota(kid):
    data = request.get_json() or {}
    nama = str(data.get('nama', '')).strip()[:100]
    jabatan = str(data.get('jabatan', ''))[:50]
    divisi = str(data.get('divisi', ''))[:50]
    email = str(data.get('email', ''))[:100]
    no_hp = str(data.get('no_hp', ''))[:20]
    password = str(data.get('password', '')).strip()
    aktif = 1 if data.get('aktif', True) else 0
    
    if not nama:
        return jsonify({'success': False, 'message': 'Nama wajib diisi'})
    if password and len(password) < 6:
        return jsonify({'success': False, 'message': 'Password minimal 6 karakter'})
    
    conn = get_db()
    c = conn.cursor()
    if password:
        c.execute('''UPDATE anggota SET nama=?, jabatan=?, divisi=?, email=?, no_hp=?, aktif=?, password=? WHERE id=?''',
                  (nama, jabatan, divisi, email, no_hp, aktif, hash_password(password), kid))
    else:
        c.execute('''UPDATE anggota SET nama=?, jabatan=?, divisi=?, email=?, no_hp=?, aktif=? WHERE id=?''',
                  (nama, jabatan, divisi, email, no_hp, aktif, kid))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Data anggota diperbarui'})

@app.route('/api/anggota/<int:kid>', methods=['DELETE'])
@admin_required
def hapus_anggota(kid):
    if kid == session['user_id']:
        return jsonify({'success': False, 'message': 'Tidak dapat menghapus akun sendiri'})
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM absensi WHERE anggota_id = ?', (kid,))
    c.execute('DELETE FROM anggota WHERE id = ?', (kid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Anggota dihapus'})

# ============================================================
# HALAMAN UTAMA
# ============================================================
@app.route('/')
@login_required
def index():
    return render_template_string(MAIN_HTML, o=ORG)


# ============================================================
# INISIALISASI DATABASE
# ============================================================
init_db()


# ============================================================
# LOGIN PAGE
# ============================================================
LOGIN_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>Masuk — {{ o.nama }}</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
html, body { height:100%; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: #0a0a0a;
    background-image: 
        radial-gradient(circle at 20% 30%, rgba(180, 83, 9, 0.08) 0%, transparent 50%),
        radial-gradient(circle at 80% 70%, rgba(180, 83, 9, 0.06) 0%, transparent 50%),
        linear-gradient(180deg, #0a0a0a 0%, #111111 100%);
    color: #e5e7eb;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
    position: relative;
}
body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image: 
        linear-gradient(rgba(251,191,36,0.02) 1px, transparent 1px),
        linear-gradient(90deg, rgba(251,191,36,0.02) 1px, transparent 1px);
    background-size: 32px 32px;
    pointer-events: none;
}
.login-container { width: 100%; max-width: 440px; position: relative; z-index: 1; }
.org-header { text-align: center; margin-bottom: 28px; }
.org-badge {
    display: inline-block;
    padding: 6px 18px;
    background: transparent;
    border: 1px solid #b45309;
    color: #fbbf24;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 16px;
}
.org-name {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 42px;
    font-weight: 800;
    background: linear-gradient(135deg, #fbbf24 0%, #d97706 50%, #fbbf24 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: 2px;
    line-height: 1.05;
    margin-bottom: 8px;
}
.org-divider {
    width: 60px;
    height: 2px;
    background: linear-gradient(90deg, transparent, #b45309, transparent);
    margin: 12px auto;
}
.org-type {
    font-size: 11px;
    color: #9ca3af;
    letter-spacing: 2px;
    text-transform: uppercase;
    font-weight: 600;
    margin-bottom: 6px;
}
.org-loc { font-size: 11px; color: #6b7280; letter-spacing: 1px; }
.login-card {
    background: linear-gradient(145deg, #161616 0%, #0f0f0f 100%);
    border: 1px solid #262626;
    border-radius: 12px;
    padding: 32px 28px;
    box-shadow: 
        0 0 0 1px rgba(251,191,36,0.05),
        0 20px 60px -20px rgba(0,0,0,0.8),
        0 0 80px -20px rgba(180,83,9,0.15);
    position: relative;
}
.login-card::before {
    content: '';
    position: absolute;
    top: -1px;
    left: 30%; right: 30%;
    height: 1px;
    background: linear-gradient(90deg, transparent, #b45309, transparent);
}
.login-title {
    font-size: 20px;
    font-weight: 700;
    color: #f9fafb;
    margin-bottom: 6px;
    font-family: Georgia, serif;
}
.login-desc {
    font-size: 12.5px;
    color: #9ca3af;
    margin-bottom: 26px;
    line-height: 1.6;
}
.form-row { margin-bottom: 18px; }
.form-row label {
    display: block;
    font-size: 10.5px;
    font-weight: 700;
    color: #fbbf24;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 8px;
}
.form-row input {
    width: 100%;
    padding: 13px 16px;
    border: 1px solid #262626;
    border-radius: 6px;
    font-size: 14px;
    font-family: inherit;
    outline: none;
    transition: all 0.2s;
    background: #0a0a0a;
    color: #f9fafb;
}
.form-row input:focus {
    border-color: #b45309;
    background: #0f0f0f;
    box-shadow: 0 0 0 3px rgba(180,83,9,0.15);
}
.form-row input::placeholder { color: #4b5563; }
.btn-submit {
    width: 100%;
    padding: 14px;
    background: linear-gradient(135deg, #fbbf24 0%, #b45309 100%);
    color: #0a0a0a;
    border: none;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 2px;
    cursor: pointer;
    transition: all 0.2s;
    font-family: inherit;
    min-height: 48px;
    box-shadow: 0 4px 20px -4px rgba(251,191,36,0.4);
}
.btn-submit:hover {
    background: linear-gradient(135deg, #fcd34d 0%, #d97706 100%);
    box-shadow: 0 6px 24px -4px rgba(251,191,36,0.6);
    transform: translateY(-1px);
}
.btn-submit:disabled { 
    background: #374151; 
    color: #6b7280;
    box-shadow: none;
    cursor: not-allowed;
    transform: none;
}
.error-msg {
    background: rgba(220,38,38,0.1);
    border: 1px solid rgba(220,38,38,0.3);
    border-left: 3px solid #dc2626;
    color: #fca5a5;
    padding: 12px 14px;
    border-radius: 6px;
    font-size: 12.5px;
    margin-bottom: 18px;
    display: none;
}
.error-msg.show { display: block; }
.footer-text {
    text-align: center;
    margin-top: 28px;
    font-size: 10.5px;
    color: #4b5563;
    letter-spacing: 1px;
}
.footer-text .sep { padding: 0 8px; color: #b45309; }
@media (max-width: 480px) {
    body { padding: 16px; }
    .org-name { font-size: 34px; }
    .login-card { padding: 26px 20px; }
}
</style>
</head>
<body>
<div class="login-container">
    <div class="org-header">
        <div class="org-badge">KARANG TARUNA</div>
        <div class="org-name">{{ o.nama }}</div>
        <div class="org-divider"></div>
        <div class="org-type">{{ o.tagline }}</div>
        <div class="org-loc">{{ o.wilayah }} · {{ o.desa }}</div>
    </div>
    
    <div class="login-card">
        <div class="login-title">Masuk Sistem</div>
        <div class="login-desc">Silakan masukkan kredensial akun Anda untuk mengakses sistem absensi.</div>
        
        <div class="error-msg" id="errorBox"></div>
        
        <form onsubmit="doLogin(event)">
            <div class="form-row">
                <label>Username</label>
                <input type="text" id="username" placeholder="Masukkan username" autocomplete="username" required autofocus maxlength="50">
            </div>
            <div class="form-row">
                <label>Password</label>
                <input type="password" id="password" placeholder="Masukkan password" autocomplete="current-password" required maxlength="100">
            </div>
            <button type="submit" class="btn-submit" id="btnLogin">MASUK</button>
        </form>
    </div>
    
    <div class="footer-text">
        {{ o.sistem }}<span class="sep">·</span>{{ o.nama }}<span class="sep">·</span>{{ o.desa }}
    </div>
</div>

<script>
const CSRF_TOKEN = "{{ csrf_token }}";
let failCount = 0;

async function doLogin(e) {
    e.preventDefault();
    const btn = document.getElementById('btnLogin');
    const err = document.getElementById('errorBox');
    err.classList.remove('show');
    
    if (failCount >= 3) {
        err.textContent = 'Terlalu banyak percobaan gagal. Tunggu 30 detik.';
        err.classList.add('show');
        btn.disabled = true;
        setTimeout(() => {
            failCount = 0;
            btn.disabled = false;
            btn.textContent = 'MASUK';
        }, 30000);
        return;
    }
    
    btn.disabled = true;
    btn.textContent = 'MEMPROSES...';
    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: {
                'Content-Type':'application/json',
                'X-CSRF-Token': CSRF_TOKEN
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                username: document.getElementById('username').value,
                password: document.getElementById('password').value
            })
        });
        const data = await res.json();
        if (data.success) {
            window.location.href = '/';
        } else {
            failCount++;
            err.textContent = data.message;
            err.classList.add('show');
            btn.disabled = false;
            btn.textContent = 'MASUK';
        }
    } catch (err2) {
        err.textContent = 'Terjadi kesalahan: ' + err2.message;
        err.classList.add('show');
        btn.disabled = false;
        btn.textContent = 'MASUK';
    }
}
</script>
</body>
</html>
"""


# ============================================================
# MAIN PAGE
# ============================================================
MAIN_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>{{ o.nama }} — {{ o.sistem }}</title>
<style>
:root {
    --black-900: #0a0a0a;
    --black-800: #111111;
    --black-700: #161616;
    --black-600: #1a1a1a;
    --black-500: #1f1f1f;
    --gold-500: #fbbf24;
    --gold-600: #d97706;
    --gold-700: #b45309;
    --border-dark: #262626;
    --border-mid: #333333;
    --text-primary: #f9fafb;
    --text-secondary: #d1d5db;
    --text-muted: #9ca3af;
    --text-dim: #6b7280;
    --success: #10b981;
    --success-bg: rgba(16,185,129,0.1);
    --danger: #ef4444;
    --danger-bg: rgba(239,68,68,0.1);
    --warning: #f59e0b;
    --warning-bg: rgba(245,158,11,0.1);
    --info: #3b82f6;
    --info-bg: rgba(59,130,246,0.1);
    --purple: #a78bfa;
    --purple-bg: rgba(167,139,250,0.1);
    --safe-top: env(safe-area-inset-top, 0px);
    --safe-bottom: env(safe-area-inset-bottom, 0px);
}
* { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
html, body { height: 100%; overscroll-behavior: none; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: var(--black-900);
    color: var(--text-secondary);
    font-size: 13px;
    line-height: 1.5;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
    height: 100vh;
    height: 100dvh;
}
.app-header {
    background: var(--black-800);
    color: white;
    display: flex;
    align-items: center;
    height: 64px;
    flex-shrink: 0;
    padding: 0 20px;
    gap: 16px;
    border-bottom: 1px solid var(--border-dark);
    position: relative;
    padding-top: var(--safe-top);
    height: calc(64px + var(--safe-top));
}
.app-header::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--gold-700), transparent);
}
.app-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-right: 20px;
    border-right: 1px solid var(--border-dark);
    height: 60%;
    flex-shrink: 0;
}
.app-brand .monogram {
    width: 38px;
    height: 38px;
    border: 1.5px solid var(--gold-600);
    color: var(--gold-500);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 12px;
    letter-spacing: 0.5px;
    flex-shrink: 0;
    font-family: 'SF Mono', Consolas, monospace;
    background: rgba(180,83,9,0.08);
}
.app-brand .text { line-height: 1.15; min-width: 0; }
.app-brand .name {
    font-family: Georgia, serif;
    font-size: 14px;
    font-weight: 700;
    background: linear-gradient(135deg, #fbbf24 0%, #d97706 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: 1.5px;
    white-space: nowrap;
}
.app-brand .sub {
    font-size: 9px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1.2px;
    white-space: nowrap;
}
.app-nav {
    display: flex;
    gap: 0;
    flex: 1;
    height: 100%;
    align-items: stretch;
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: none;
}
.app-nav::-webkit-scrollbar { display: none; }
.nav-item {
    padding: 0 18px;
    background: transparent;
    border: none;
    color: var(--text-dim);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    font-family: inherit;
    letter-spacing: 0.4px;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    display: flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
    flex-shrink: 0;
}
.nav-item:hover { color: var(--gold-500); }
.nav-item.active { 
    color: var(--gold-500);
    border-bottom-color: var(--gold-600);
}
.app-user {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}
.app-user .info { text-align: right; line-height: 1.2; }
.app-user .info .name { font-size: 12px; font-weight: 700; color: var(--text-primary); white-space: nowrap; }
.app-user .info .role {
    font-size: 9.5px;
    color: var(--gold-600);
    text-transform: uppercase;
    font-weight: 700;
    letter-spacing: 0.8px;
}
.app-user .avatar {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, var(--gold-500), var(--gold-700));
    color: var(--black-900);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 900;
    font-size: 14px;
    flex-shrink: 0;
    box-shadow: 0 0 0 2px rgba(180,83,9,0.2);
}
.btn-logout {
    background: transparent;
    border: 1px solid var(--border-mid);
    color: var(--text-muted);
    padding: 7px 14px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 1px;
    font-family: inherit;
    text-transform: uppercase;
    min-height: 32px;
    flex-shrink: 0;
    transition: all 0.15s;
}
.btn-logout:hover { 
    background: rgba(180,83,9,0.1);
    border-color: var(--gold-600);
    color: var(--gold-500);
}
.app-main {
    flex: 1;
    overflow: hidden;
    position: relative;
    display: flex;
    flex-direction: column;
}
.view {
    display: none;
    height: 100%;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}
.view.active { display: block; }
.page {
    padding: 22px;
    padding-bottom: calc(22px + var(--safe-bottom));
    display: flex;
    flex-direction: column;
    gap: 16px;
    max-width: 1400px;
    margin: 0 auto;
    width: 100%;
    min-height: 100%;
}
.page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    flex-wrap: wrap;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border-dark);
    position: relative;
}
.page-header::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 0;
    width: 80px;
    height: 2px;
    background: linear-gradient(90deg, var(--gold-600), transparent);
}
.page-header .titles { min-width: 0; flex: 1; }
.page-header .titles .eyebrow {
    font-size: 10px;
    color: var(--gold-600);
    text-transform: uppercase;
    letter-spacing: 2px;
    font-weight: 800;
    margin-bottom: 4px;
}
.page-header .titles h1 {
    font-family: Georgia, serif;
    font-size: 26px;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}
.page-header .titles .subtitle {
    font-size: 12px;
    color: var(--text-muted);
}
.greeting {
    background: linear-gradient(135deg, var(--black-700) 0%, var(--black-800) 100%);
    border: 1px solid var(--border-dark);
    border-left: 3px solid var(--gold-600);
    padding: 18px 22px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.greeting .icon {
    width: 46px;
    height: 46px;
    background: rgba(180,83,9,0.1);
    border: 1px solid var(--gold-700);
    color: var(--gold-500);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    font-size: 22px;
}
.greeting .content h2 {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 2px;
}
.greeting .content p {
    font-size: 12px;
    color: var(--text-muted);
}
.clock-card {
    background: linear-gradient(135deg, var(--black-700) 0%, var(--black-800) 100%);
    color: white;
    padding: 32px 28px;
    border-radius: 10px;
    position: relative;
    overflow: hidden;
    border: 1px solid var(--border-dark);
    border-bottom: 3px solid var(--gold-600);
    box-shadow: 
        0 20px 40px -20px rgba(0,0,0,0.6),
        0 0 60px -20px rgba(180,83,9,0.15);
}
.clock-card::before {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 280px;
    height: 280px;
    background: radial-gradient(circle, rgba(251,191,36,0.08), transparent 70%);
    border-radius: 50%;
    pointer-events: none;
}
.clock-content { position: relative; z-index: 1; }
.clock-label {
    font-size: 10px;
    color: var(--gold-500);
    text-transform: uppercase;
    letter-spacing: 2.5px;
    font-weight: 800;
    margin-bottom: 14px;
}
.clock-time {
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 56px;
    font-weight: 600;
    line-height: 1;
    letter-spacing: -2px;
    margin-bottom: 12px;
    word-break: break-all;
    color: var(--text-primary);
    text-shadow: 0 0 30px rgba(251,191,36,0.15);
}
.clock-date {
    font-size: 13px;
    color: var(--text-muted);
    font-weight: 500;
}
.att-card {
    background: var(--black-800);
    border: 1px solid var(--border-dark);
    border-radius: 10px;
    padding: 24px;
}
.att-status-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1px;
    background: var(--border-dark);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 20px;
    border: 1px solid var(--border-dark);
}
.att-status-cell {
    background: var(--black-700);
    padding: 18px 20px;
}
.att-status-cell .lbl {
    font-size: 10px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-weight: 800;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.att-status-cell .lbl::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--gold-600);
}
.att-status-cell:last-child .lbl::before { background: var(--gold-500); }
.att-status-cell .val {
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 26px;
    font-weight: 600;
    color: var(--gold-500);
    line-height: 1.1;
}
.att-status-cell .val.empty { color: var(--text-dim); }
.att-buttons {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
}
.btn-clock {
    padding: 22px 18px;
    border: none;
    border-radius: 10px;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.2s;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    text-align: center;
    min-height: 130px;
    font-weight: 700;
    position: relative;
    overflow: hidden;
}
.btn-in { 
    background: linear-gradient(135deg, #fbbf24 0%, #b45309 100%);
    color: var(--black-900);
    box-shadow: 0 8px 24px -8px rgba(251,191,36,0.5);
}
.btn-in .icon-wrap { 
    background: rgba(0,0,0,0.15); 
    color: var(--black-900);
}
.btn-in .label { color: var(--black-900); }
.btn-in .time { color: rgba(0,0,0,0.7); }
.btn-in:hover:not(:disabled) { 
    transform: translateY(-2px);
    box-shadow: 0 12px 30px -8px rgba(251,191,36,0.6);
}
.btn-out { 
    background: var(--black-600);
    border: 1.5px solid var(--gold-700);
    color: var(--gold-500);
}
.btn-out .icon-wrap { 
    background: rgba(180,83,9,0.15); 
    color: var(--gold-500);
}
.btn-out .label { color: var(--gold-500); }
.btn-out .time { color: var(--gold-600); }
.btn-out:hover:not(:disabled) { 
    background: rgba(180,83,9,0.15);
    border-color: var(--gold-500);
    transform: translateY(-2px);
}
.btn-clock:disabled {
    background: var(--black-500);
    border-color: var(--border-dark);
    color: var(--text-dim);
    cursor: not-allowed;
    box-shadow: none;
    transform: none;
}
.btn-clock:disabled .icon-wrap { 
    background: rgba(75,85,99,0.3); 
    color: var(--text-dim);
}
.btn-clock:disabled .label { color: var(--text-dim); }
.btn-clock:disabled .time { color: var(--text-dim); }
.btn-clock .icon-wrap {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
}
.btn-clock .label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.8px;
    font-weight: 800;
}
.btn-clock .time {
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 14px;
    font-weight: 600;
}
.card {
    background: var(--black-800);
    border: 1px solid var(--border-dark);
    border-radius: 10px;
    overflow: hidden;
}
.card-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-dark);
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    background: var(--black-700);
}
.card-header .title {
    font-weight: 800;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 10px;
    text-transform: uppercase;
    font-size: 11.5px;
    letter-spacing: 1.5px;
}
.card-header .title::before {
    content: '';
    width: 3px;
    height: 16px;
    background: linear-gradient(180deg, var(--gold-500), var(--gold-700));
    border-radius: 2px;
}
.card-header .subtitle {
    font-size: 11px;
    color: var(--text-dim);
    margin-top: 4px;
    padding-left: 13px;
}
.card-body {
    padding: 0;
    max-height: 500px;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { width: 100%; border-collapse: collapse; min-width: 520px; }
thead th {
    padding: 12px 16px;
    text-align: left;
    font-size: 10px;
    text-transform: uppercase;
    color: var(--gold-600);
    background: var(--black-700);
    border-bottom: 1px solid var(--border-dark);
    font-weight: 800;
    letter-spacing: 1.2px;
    position: sticky;
    top: 0;
    z-index: 1;
    white-space: nowrap;
}
tbody td {
    padding: 13px 16px;
    border-bottom: 1px solid var(--border-dark);
    font-size: 12.5px;
    vertical-align: middle;
    color: var(--text-secondary);
}
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover { background: rgba(180,83,9,0.04); }
tbody td strong { color: var(--text-primary); font-weight: 700; }
.mono { font-family: 'SF Mono', Consolas, monospace; font-size: 12px; }
.right { text-align: right; }
.center { text-align: center; }
.muted { color: var(--text-muted); }
.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    white-space: nowrap;
}
.badge-hadir { background: var(--success-bg); color: var(--success); border: 1px solid rgba(16,185,129,0.3); }
.badge-izin { background: var(--info-bg); color: var(--info); border: 1px solid rgba(59,130,246,0.3); }
.badge-sakit { background: var(--warning-bg); color: var(--warning); border: 1px solid rgba(245,158,11,0.3); }
.badge-cuti { background: var(--purple-bg); color: var(--purple); border: 1px solid rgba(167,139,250,0.3); }
.badge-alpha { background: var(--danger-bg); color: var(--danger); border: 1px solid rgba(239,68,68,0.3); }
.badge-aktif { background: var(--success-bg); color: var(--success); border: 1px solid rgba(16,185,129,0.3); }
.badge-nonaktif { background: rgba(107,114,128,0.15); color: var(--text-dim); border: 1px solid var(--border-dark); }
.btn {
    padding: 10px 16px;
    border: 1px solid var(--border-mid);
    background: var(--black-700);
    color: var(--text-secondary);
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 700;
    transition: all 0.15s;
    font-family: inherit;
    letter-spacing: 0.5px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    white-space: nowrap;
    min-height: 40px;
}
.btn:hover { 
    background: var(--black-600); 
    border-color: var(--gold-700);
    color: var(--gold-500);
}
.btn:active { transform: scale(0.98); }
.btn-primary { 
    background: linear-gradient(135deg, #fbbf24 0%, #b45309 100%);
    border-color: var(--gold-600);
    color: var(--black-900);
    font-weight: 800;
    box-shadow: 0 4px 16px -4px rgba(251,191,36,0.4);
}
.btn-primary:hover { 
    background: linear-gradient(135deg, #fcd34d 0%, #d97706 100%);
    color: var(--black-900);
    box-shadow: 0 6px 20px -4px rgba(251,191,36,0.5);
}
.btn-danger { 
    background: var(--black-700); 
    border-color: rgba(239,68,68,0.3); 
    color: var(--danger);
}
.btn-danger:hover { 
    background: rgba(239,68,68,0.1);
    border-color: var(--danger); 
    color: var(--danger);
}
.btn-sm { padding: 7px 12px; font-size: 11px; min-height: 32px; }
.btn-icon {
    width: 34px;
    height: 34px;
    padding: 0;
    justify-content: center;
    font-size: 13px;
    min-height: 34px;
}
.form-row { margin-bottom: 16px; }
.form-row label {
    display: block;
    font-size: 10.5px;
    font-weight: 800;
    color: var(--gold-600);
    margin-bottom: 7px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
}
.form-row input, .form-row select {
    width: 100%;
    padding: 12px 14px;
    border: 1px solid var(--border-mid);
    border-radius: 6px;
    font-size: 13px;
    font-family: inherit;
    outline: none;
    transition: all 0.15s;
    background: var(--black-900);
    color: var(--text-primary);
    min-height: 44px;
}
.form-row input:focus, .form-row select:focus {
    border-color: var(--gold-600);
    box-shadow: 0 0 0 3px rgba(180,83,9,0.15);
}
.form-row input::placeholder { color: var(--text-dim); }
.toolbar {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
}
.toolbar input, .toolbar select {
    padding: 11px 14px;
    border: 1px solid var(--border-mid);
    border-radius: 6px;
    font-size: 12.5px;
    font-family: inherit;
    outline: none;
    background: var(--black-800);
    color: var(--text-primary);
    min-height: 42px;
    transition: all 0.15s;
}
.toolbar input:focus, .toolbar select:focus { 
    border-color: var(--gold-600);
    box-shadow: 0 0 0 3px rgba(180,83,9,0.1);
}
.toolbar input::placeholder { color: var(--text-dim); }
.toolbar input { flex: 1; min-width: 180px; }
.toolbar select { min-width: 150px; }
.stats-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 14px;
}
.stat-card {
    background: var(--black-800);
    border: 1px solid var(--border-dark);
    border-radius: 10px;
    padding: 20px 22px;
    position: relative;
    overflow: hidden;
    transition: all 0.2s;
}
.stat-card:hover {
    border-color: var(--gold-700);
    transform: translateY(-2px);
}
.stat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px;
    height: 100%;
    background: linear-gradient(180deg, var(--gold-500), var(--gold-700));
}
.stat-card.blue::before { background: linear-gradient(180deg, var(--info), #1e40af); }
.stat-card.gold::before { background: linear-gradient(180deg, var(--gold-500), var(--gold-700)); }
.stat-card.red::before { background: linear-gradient(180deg, var(--danger), #991b1b); }
.stat-card .lbl {
    font-size: 10px;
    color: var(--text-muted);
    text-transform: uppercase;
    font-weight: 800;
    letter-spacing: 1.5px;
    margin-bottom: 10px;
}
.stat-card .val {
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 28px;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1;
    letter-spacing: -0.5px;
}
.stat-card .val .unit {
    font-size: 11px;
    color: var(--text-muted);
    margin-left: 6px;
    font-weight: 500;
    font-family: inherit;
}
.live-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
}
.live-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    background: rgba(16,185,129,0.08);
    color: var(--success);
    border: 1px solid rgba(16,185,129,0.3);
    border-radius: 20px;
    font-size: 9.5px;
    font-weight: 800;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}
.live-dot {
    width: 6px;
    height: 6px;
    background: var(--success);
    border-radius: 50%;
    animation: blink 1.5s infinite;
    box-shadow: 0 0 8px var(--success);
}
@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
}
.event-item {
    padding: 13px 18px;
    border-bottom: 1px solid var(--border-dark);
    display: flex;
    gap: 13px;
    align-items: center;
    animation: slideDown 0.3s;
}
@keyframes slideDown {
    from { opacity: 0; transform: translateY(-5px); }
    to { opacity: 1; transform: translateY(0); }
}
.event-item:last-child { border-bottom: none; }
.event-icon {
    width: 36px;
    height: 36px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    flex-shrink: 0;
    font-weight: bold;
}
.event-item.masuk .event-icon { 
    background: var(--success-bg); 
    color: var(--success); 
    border: 1px solid rgba(16,185,129,0.3);
}
.event-item.pulang .event-icon { 
    background: rgba(180,83,9,0.1); 
    color: var(--gold-500); 
    border: 1px solid rgba(180,83,9,0.3);
}
.event-content { flex: 1; min-width: 0; }
.event-content .title {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.event-content .desc {
    font-size: 11px;
    color: var(--text-muted);
    margin-top: 2px;
}
.event-time {
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 11px;
    color: var(--gold-600);
    flex-shrink: 0;
    font-weight: 600;
}
.modal {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.85);
    z-index: 1000;
    align-items: center;
    justify-content: center;
    padding: 16px;
    backdrop-filter: blur(4px);
}
.modal.show { display: flex; }
.modal-box {
    background: var(--black-800);
    border: 1px solid var(--border-dark);
    border-radius: 12px;
    width: 100%;
    max-width: 500px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    box-shadow: 
        0 25px 50px -12px rgba(0,0,0,0.8),
        0 0 80px -20px rgba(180,83,9,0.2);
}
.modal-header {
    padding: 18px 24px;
    border-bottom: 1px solid var(--border-dark);
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--black-700);
    position: relative;
}
.modal-header::after {
    content: '';
    position: absolute;
    bottom: -1px;
    left: 24px;
    width: 60px;
    height: 2px;
    background: linear-gradient(90deg, var(--gold-500), transparent);
}
.modal-header h2 {
    font-family: Georgia, serif;
    font-size: 16px;
    font-weight: 700;
    color: var(--gold-500);
    letter-spacing: 0.8px;
}
.modal-header .close {
    background: transparent;
    border: 1px solid var(--border-mid);
    color: var(--text-muted);
    font-size: 18px;
    cursor: pointer;
    width: 34px;
    height: 34px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
    transition: all 0.15s;
}
.modal-header .close:hover { 
    background: rgba(239,68,68,0.1);
    border-color: var(--danger);
    color: var(--danger);
}
.modal-body {
    padding: 24px;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}
.modal-footer {
    padding: 16px 24px;
    background: var(--black-900);
    border-top: 1px solid var(--border-dark);
    display: flex;
    gap: 10px;
    justify-content: flex-end;
}
.toast {
    position: fixed;
    top: calc(80px + var(--safe-top));
    right: 20px;
    left: 20px;
    z-index: 2000;
    padding: 15px 18px;
    border-radius: 8px;
    background: var(--black-700);
    color: var(--text-primary);
    font-size: 13px;
    font-weight: 600;
    box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5);
    opacity: 0;
    transform: translateY(-20px);
    transition: all 0.3s;
    max-width: 420px;
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 10px;
    border: 1px solid var(--border-dark);
}
.toast.show { opacity: 1; transform: translateY(0); }
.toast.success { border-left: 3px solid var(--success); }
.toast.error { border-left: 3px solid var(--danger); }
.toast.info { border-left: 3px solid var(--info); }
.toast.warning { border-left: 3px solid var(--warning); }
.empty-state {
    padding: 48px 20px;
    text-align: center;
    color: var(--text-dim);
    font-size: 12.5px;
}
.loading-state {
    padding: 48px 20px;
    text-align: center;
    color: var(--gold-600);
    font-size: 12.5px;
    font-weight: 600;
}
@media (max-width: 1024px) {
    .page { padding: 18px; gap: 14px; }
    .live-grid { grid-template-columns: 1fr; }
    .clock-time { font-size: 46px; }
}
@media (max-width: 768px) {
    .app-header {
        padding: 0 12px;
        gap: 10px;
        height: calc(60px + var(--safe-top));
    }
    .app-brand { padding-right: 10px; gap: 8px; }
    .app-brand .monogram { width: 32px; height: 32px; font-size: 10px; }
    .app-brand .name { font-size: 12px; letter-spacing: 1px; }
    .app-brand .sub { display: none; }
    .app-user .info { display: none; }
    .app-user .avatar { width: 32px; height: 32px; font-size: 12px; }
    .btn-logout { padding: 6px 10px; font-size: 9.5px; min-height: 30px; }
    .nav-item { padding: 0 12px; font-size: 11px; }
    .page { padding: 14px; gap: 12px; }
    .page-header { padding-bottom: 14px; }
    .page-header .titles h1 { font-size: 22px; }
    .page-header .titles .subtitle { font-size: 11px; }
    .greeting { padding: 14px 16px; gap: 12px; }
    .greeting .icon { width: 40px; height: 40px; font-size: 19px; }
    .greeting .content h2 { font-size: 13.5px; }
    .greeting .content p { font-size: 11px; }
    .clock-card { padding: 24px 22px; }
    .clock-time { font-size: 40px; letter-spacing: -1.5px; }
    .clock-date { font-size: 12px; }
    .att-card { padding: 18px; }
    .att-status-cell { padding: 15px 16px; }
    .att-status-cell .val { font-size: 22px; }
    .att-buttons { grid-template-columns: 1fr; gap: 10px; }
    .btn-clock {
        padding: 18px 16px;
        min-height: 90px;
        flex-direction: row;
        justify-content: center;
        gap: 14px;
    }
    .btn-clock .icon-wrap { width: 42px; height: 42px; }
    .btn-clock .label { font-size: 10px; }
    .btn-clock .time { font-size: 13px; }
    table.responsive-table { min-width: 0; }
    table.responsive-table thead { display: none; }
    table.responsive-table, 
    table.responsive-table tbody, 
    table.responsive-table tr, 
    table.responsive-table td { 
        display: block; 
        width: 100%;
    }
    table.responsive-table tr {
        border: 1px solid var(--border-dark);
        border-radius: 8px;
        margin-bottom: 12px;
        padding: 16px;
        background: var(--black-700);
    }
    table.responsive-table tr:hover { background: var(--black-700); }
    table.responsive-table td {
        padding: 7px 0;
        border: none;
        font-size: 12.5px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
    }
    table.responsive-table td::before {
        content: attr(data-label);
        font-size: 10px;
        font-weight: 800;
        color: var(--gold-600);
        text-transform: uppercase;
        letter-spacing: 1px;
        flex-shrink: 0;
    }
    table.responsive-table td:last-child { padding-bottom: 0; }
    table.responsive-table td:first-child {
        padding-top: 0;
        padding-bottom: 12px;
        border-bottom: 1px solid var(--border-dark);
        margin-bottom: 8px;
        font-size: 14px;
        font-weight: 800;
        color: var(--text-primary);
    }
    table.responsive-table td:first-child::before { display: none; }
    .toolbar { flex-direction: column; align-items: stretch; }
    .toolbar input, .toolbar select, .toolbar .btn { width: 100%; min-width: 0; }
    .stats-row { grid-template-columns: 1fr 1fr; gap: 12px; }
    .stat-card { padding: 16px 18px; }
    .stat-card .lbl { font-size: 9px; letter-spacing: 1.2px; }
    .stat-card .val { font-size: 22px; }
    .stat-card .val .unit { font-size: 10px; }
    .card-header { padding: 14px 18px; }
    .card-header .title { font-size: 11px; }
    .card-body { max-height: none; }
    .modal { align-items: flex-end; padding: 0; }
    .modal-box {
        max-width: 100%;
        max-height: 92vh;
        border-radius: 16px 16px 0 0;
        animation: slideUp 0.25s ease-out;
    }
    @keyframes slideUp {
        from { transform: translateY(100%); }
        to { transform: translateY(0); }
    }
    .modal-header { padding: 16px 20px; }
    .modal-body { padding: 20px; }
    .modal-footer { padding: 14px 20px; padding-bottom: calc(14px + var(--safe-bottom)); }
    .modal-footer .btn { flex: 1; }
    .toast {
        top: calc(70px + var(--safe-top));
        right: 12px;
        left: 12px;
        max-width: none;
        font-size: 12px;
    }
}
@media (max-width: 480px) {
    .app-brand .text { display: none; }
    .nav-item .nav-text { display: none; }
    .nav-item { padding: 0 14px; }
    .stats-row { grid-template-columns: 1fr; }
    .clock-time { font-size: 34px; letter-spacing: -1px; }
    .page-header .titles h1 { font-size: 20px; }
    .card-header { padding: 12px 15px; }
    .btn { padding: 9px 14px; font-size: 11.5px; }
    .btn-icon { width: 32px; height: 32px; }
}
</style>
</head>
<body>

<header class="app-header">
    <div class="app-brand">
        <div class="monogram">K007</div>
        <div class="text">
            <div class="name">{{ o.nama }}</div>
            <div class="sub">{{ o.wilayah }}</div>
        </div>
    </div>
    <nav class="app-nav" id="navContainer"></nav>
    <div class="app-user">
        <div class="info">
            <div class="name" id="userNama">-</div>
            <div class="role" id="userRole">-</div>
        </div>
        <div class="avatar" id="userAvatar">?</div>
        <button class="btn-logout" onclick="doLogout()">KELUAR</button>
    </div>
</header>

<main class="app-main">

<div class="view" id="view-absen">
    <div class="page">
        <div class="page-header">
            <div class="titles">
                <div class="eyebrow">Beranda</div>
                <h1>Kehadiran Saya</h1>
                <div class="subtitle">Catat kehadiran Anda pada kegiatan Karang Taruna</div>
            </div>
        </div>
        <div class="greeting">
            <div class="icon">👋</div>
            <div class="content">
                <h2 id="greetingText">Selamat datang!</h2>
                <p id="greetingSub">Semoga kegiatan hari ini berjalan lancar</p>
            </div>
        </div>
        <div class="clock-card">
            <div class="clock-content">
                <div class="clock-label">Waktu Saat Ini (WIB)</div>
                <div class="clock-time" id="jamLive">--:--:--</div>
                <div class="clock-date" id="tanggalLive">--</div>
            </div>
        </div>
        <div class="att-card">
            <div class="att-status-row">
                <div class="att-status-cell">
                    <div class="lbl">Jam Datang</div>
                    <div class="val empty" id="valMasuk">--:--:--</div>
                </div>
                <div class="att-status-cell">
                    <div class="lbl">Jam Pulang</div>
                    <div class="val empty" id="valPulang">--:--:--</div>
                </div>
            </div>
            <div class="att-buttons">
                <button class="btn-clock btn-in" id="btnMasuk" onclick="absenMasuk()">
                    <div class="icon-wrap">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
                    </div>
                    <div>
                        <div class="label">Absen Datang</div>
                        <div class="time">Masuk Kegiatan</div>
                    </div>
                </button>
                <button class="btn-clock btn-out" id="btnPulang" onclick="absenPulang()">
                    <div class="icon-wrap">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                    </div>
                    <div>
                        <div class="label">Absen Pulang</div>
                        <div class="time">Selesai Kegiatan</div>
                    </div>
                </button>
            </div>
        </div>
        <div class="card">
            <div class="card-header">
                <div>
                    <div class="title">Riwayat Kehadiran</div>
                    <div class="subtitle">Catatan absensi pribadi Anda</div>
                </div>
                <input type="month" id="filterBulanAnggota" onchange="loadRiwayatAnggota()" style="padding:9px 12px;border:1px solid var(--border-mid);border-radius:6px;font-size:12px;background:var(--black-900);color:var(--text-primary);">
            </div>
            <div class="card-body">
                <div class="table-wrap">
                    <table class="responsive-table">
                        <thead><tr><th>Tanggal</th><th class="center">Datang</th><th class="center">Pulang</th><th>Status</th></tr></thead>
                        <tbody id="riwayatBodyAnggota"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="view" id="view-dashboard">
    <div class="page">
        <div class="page-header">
            <div class="titles">
                <div class="eyebrow">Dashboard</div>
                <h1>Ringkasan Kehadiran</h1>
                <div class="subtitle">Statistik absensi anggota hari ini</div>
            </div>
            <div class="live-badge"><span class="live-dot"></span>LIVE</div>
        </div>
        <div class="stats-row">
            <div class="stat-card">
                <div class="lbl">Hadir Hari Ini</div>
                <div class="val" id="statHadirHariIni">0<span class="unit">anggota</span></div>
            </div>
            <div class="stat-card blue">
                <div class="lbl">Total Anggota Aktif</div>
                <div class="val" id="statTotalAnggota">0<span class="unit">orang</span></div>
            </div>
            <div class="stat-card gold">
                <div class="lbl">Belum Absen</div>
                <div class="val" id="statBelumAbsen">0<span class="unit">orang</span></div>
            </div>
            <div class="stat-card red">
                <div class="lbl">Sudah Pulang</div>
                <div class="val" id="statSudahPulang">0<span class="unit">orang</span></div>
            </div>
        </div>
        <div class="live-grid">
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="title">Kehadiran Hari Ini</div>
                        <div class="subtitle">Daftar anggota yang sudah absen</div>
                    </div>
                </div>
                <div class="card-body" style="max-height:360px;">
                    <div class="table-wrap">
                        <table class="responsive-table">
                            <thead><tr><th>Nama</th><th>Divisi</th><th class="center">Datang</th><th class="center">Pulang</th></tr></thead>
                            <tbody id="absenHariIni"></tbody>
                        </table>
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">
                    <div>
                        <div class="title">Aktivitas Terkini</div>
                        <div class="subtitle">Log kehadiran real-time</div>
                    </div>
                    <div class="live-badge"><span class="live-dot"></span>LIVE</div>
                </div>
                <div class="card-body" style="max-height:360px;" id="eventLog">
                    <div class="empty-state">Memuat data...</div>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="view" id="view-anggota">
    <div class="page">
        <div class="page-header">
            <div class="titles">
                <div class="eyebrow">Manajemen</div>
                <h1>Data Anggota</h1>
                <div class="subtitle">Kelola data anggota Karang Taruna</div>
            </div>
            <button class="btn btn-primary" onclick="bukaModalAnggota()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                TAMBAH ANGGOTA
            </button>
        </div>
        <div class="toolbar">
            <input type="text" id="searchAnggota" placeholder="Cari nama, no. anggota, atau username..." oninput="renderAnggota()">
            <select id="filterDivisi" onchange="renderAnggota()">
                <option value="">Semua Divisi</option>
                <option value="Pengurus">Pengurus</option>
                <option value="Acara">Acara</option>
                <option value="Humas">Humas</option>
                <option value="Olahraga">Olahraga</option>
                <option value="Seni">Seni</option>
                <option value="Keamanan">Keamanan</option>
                <option value="Sosial">Sosial</option>
                <option value="Keagamaan">Keagamaan</option>
                <option value="Umum">Umum</option>
            </select>
        </div>
        <div class="card">
            <div class="card-header">
                <div>
                    <div class="title">Daftar Anggota</div>
                    <div class="subtitle">Total <span id="totalAnggota">0</span> anggota terdaftar</div>
                </div>
            </div>
            <div class="card-body">
                <div class="table-wrap">
                    <table class="responsive-table">
                        <thead><tr>
                            <th style="width:110px;">No. Anggota</th>
                            <th>Nama</th>
                            <th>Jabatan</th>
                            <th>Divisi</th>
                            <th>Kontak</th>
                            <th style="width:100px;">Status</th>
                            <th style="width:100px;" class="center">Aksi</th>
                        </tr></thead>
                        <tbody id="anggotaBody"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="view" id="view-semua">
    <div class="page">
        <div class="page-header">
            <div class="titles">
                <div class="eyebrow">Laporan</div>
                <h1>Detail Kehadiran</h1>
                <div class="subtitle">Riwayat absensi seluruh anggota</div>
            </div>
        </div>
        <div class="toolbar">
            <input type="month" id="filterBulanSemua" onchange="loadSemuaAbsen()">
            <select id="filterAnggotaSemua" onchange="loadSemuaAbsen()">
                <option value="">Semua Anggota</option>
            </select>
            <button class="btn" onclick="exportCSV()">EXPORT CSV</button>
            <button class="btn btn-primary" onclick="exportPDF()">EXPORT PDF</button>
        </div>
        <div class="card">
            <div class="card-header">
                <div>
                    <div class="title">Data Kehadiran</div>
                    <div class="subtitle">Total <span id="totalAbsen">0</span> record ditampilkan</div>
                </div>
            </div>
            <div class="card-body">
                <div class="table-wrap">
                    <table class="responsive-table">
                        <thead><tr>
                            <th style="width:120px;">Tanggal</th>
                            <th>Nama Anggota</th>
                            <th>Jabatan</th>
                            <th class="center" style="width:110px;">Datang</th>
                            <th class="center" style="width:110px;">Pulang</th>
                            <th style="width:120px;">Status</th>
                        </tr></thead>
                        <tbody id="semuaBody"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="view" id="view-rekap">
    <div class="page">
        <div class="page-header">
            <div class="titles">
                <div class="eyebrow">Laporan</div>
                <h1>Rekapitulasi Bulanan</h1>
                <div class="subtitle">Rekap kehadiran per anggota per bulan</div>
            </div>
        </div>
        <div class="toolbar">
            <input type="month" id="filterBulanRekap" onchange="loadRekap()">
            <button class="btn" onclick="exportCSV()">EXPORT CSV</button>
            <button class="btn btn-primary" onclick="exportPDF()">EXPORT PDF</button>
        </div>
        <div class="stats-row">
            <div class="stat-card gold">
                <div class="lbl">Hari Kerja Bulan Ini</div>
                <div class="val" id="statHariKerja">0<span class="unit">hari</span></div>
            </div>
            <div class="stat-card blue">
                <div class="lbl">Total Anggota</div>
                <div class="val" id="statTotalAnggotaRekap">0<span class="unit">orang</span></div>
            </div>
            <div class="stat-card">
                <div class="lbl">Total Kehadiran</div>
                <div class="val" id="statTotalHadir">0<span class="unit">hari</span></div>
            </div>
        </div>
        <div class="card">
            <div class="card-header">
                <div>
                    <div class="title">Rekapitulasi Kehadiran</div>
                    <div class="subtitle">Perbandingan kehadiran antar anggota</div>
                </div>
            </div>
            <div class="card-body">
                <div class="table-wrap">
                    <table class="responsive-table">
                        <thead><tr>
                            <th>Nama</th>
                            <th>Divisi</th>
                            <th class="center">Hadir</th>
                            <th class="center">Izin</th>
                            <th class="center">Sakit</th>
                            <th class="center">Cuti</th>
                            <th class="center">Alpha</th>
                            <th class="center">Kehadiran</th>
                        </tr></thead>
                        <tbody id="rekapBody"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

</main>

<div class="modal" id="modalAnggota">
    <div class="modal-box">
        <div class="modal-header">
            <h2 id="modalAnggotaTitle">Tambah Anggota</h2>
            <button class="close" onclick="tutupModalAnggota()">×</button>
        </div>
        <div class="modal-body">
            <div class="form-row">
                <label>No. Anggota</label>
                <input type="text" id="inputNoAnggota" placeholder="Kosongkan untuk auto-generate" maxlength="20">
            </div>
            <div class="form-row">
                <label>Username</label>
                <input type="text" id="inputUsername" placeholder="Username untuk login" maxlength="50">
            </div>
            <div class="form-row">
                <label>Password</label>
                <input type="text" id="inputPassword" placeholder="Minimal 6 karakter" maxlength="100">
            </div>
            <div class="form-row">
                <label>Nama Lengkap</label>
                <input type="text" id="inputNamaAnggota" placeholder="Nama lengkap anggota" maxlength="100">
            </div>
            <div class="form-row">
                <label>Jabatan</label>
                <select id="inputJabatan">
                    <option value="Anggota">Anggota</option>
                    <option value="Ketua">Ketua</option>
                    <option value="Wakil Ketua">Wakil Ketua</option>
                    <option value="Sekretaris">Sekretaris</option>
                    <option value="Bendahara">Bendahara</option>
                    <option value="Sie Humas">Sie Humas</option>
                    <option value="Sie Keagamaan">Sie Keagamaan</option>
                    <option value="Sie Olahraga">Sie Olahraga</option>
                    <option value="Koordinator">Koordinator</option>
                </select>
            </div>
            <div class="form-row">
                <label>Divisi</label>
                <select id="inputDivisi">
                    <option value="Pengurus">Pengurus</option>
                    <option value="Acara">Acara</option>
                    <option value="Humas">Humas</option>
                    <option value="Olahraga">Olahraga</option>
                    <option value="Seni">Seni</option>
                    <option value="Keamanan">Keamanan</option>
                    <option value="Sosial">Sosial</option>
                    <option value="Keagamaan">Keagamaan</option>
                    <option value="Umum">Umum</option>
                </select>
            </div>
            <div class="form-row">
                <label>Email (opsional)</label>
                <input type="email" id="inputEmail" placeholder="email@contoh.com" maxlength="100">
            </div>
            <div class="form-row">
                <label>No. HP (opsional)</label>
                <input type="text" id="inputNoHp" placeholder="08xxxxxxxxxx" maxlength="20">
            </div>
            <div class="form-row" id="rowAktif" style="display:none;">
                <label>Status Anggota</label>
                <select id="inputAktif">
                    <option value="1">Aktif</option>
                    <option value="0">Nonaktif</option>
                </select>
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn" onclick="tutupModalAnggota()">BATAL</button>
            <button class="btn btn-primary" onclick="simpanAnggota()">SIMPAN</button>
        </div>
    </div>
</div>

<div class="toast" id="toast"></div>

<script>
let currentUser = null;
let anggotaList = [];
let editAnggotaId = null;
let currentView = 'dashboard';
let eventSource = null;
let pollingInterval = null;
let CSRF_TOKEN = '';
let idleTimer = null;
let loadedTabs = { dashboard: false, anggota: false, semua: false, rekap: false };
let cacheAnggota = null;
let cacheTime = 0;
const IDLE_TIMEOUT = 2 * 60 * 60 * 1000;
const CACHE_DURATION = 30000;

async function fetchJSON(url, options = {}) {
    try {
        options.credentials = 'same-origin';
        if (!options.headers) options.headers = {};
        if (options.method && ['POST', 'PUT', 'DELETE', 'PATCH'].includes(options.method.toUpperCase())) {
            options.headers['X-CSRF-Token'] = CSRF_TOKEN;
        }
        const res = await fetch(url, options);
        const contentType = res.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            const text = await res.text();
            if (text.trim().startsWith('<!') || text.trim().startsWith('<html')) {
                window.location.href = '/login';
                return null;
            }
            return null;
        }
        return await res.json();
    } catch (err) {
        console.error('fetchJSON error:', err, 'URL:', url);
        return null;
    }
}

function resetIdleTimer() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
        alert('Sesi berakhir karena tidak ada aktivitas. Silakan login ulang.');
        window.location.href = '/login';
    }, IDLE_TIMEOUT);
}

window.addEventListener('load', async () => {
    const data = await fetchJSON('/api/me');
    if (!data || !data.logged_in) {
        window.location.href = '/login';
        return;
    }
    currentUser = data;
    CSRF_TOKEN = data.csrf_token || '';
    document.getElementById('userNama').textContent = data.nama;
    document.getElementById('userRole').textContent = data.role === 'admin' ? 'Administrator' : 'Anggota';
    document.getElementById('userAvatar').textContent = data.nama.charAt(0).toUpperCase();
    buildNav();
    
    const now = new Date();
    const opsBulan = { timeZone: 'Asia/Jakarta', year: 'numeric', month: '2-digit' };
    const parts = new Intl.DateTimeFormat('id-ID', opsBulan).formatToParts(now);
    let th = '', bl = '';
    parts.forEach(p => {
        if (p.type === 'year') th = p.value;
        if (p.type === 'month') bl = p.value;
    });
    const bulanIni = `${th}-${bl}`;
    ['filterBulanAnggota', 'filterBulanSemua', 'filterBulanRekap'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = bulanIni;
    });
    
    if (data.role === 'admin') {
        switchView('dashboard');
        loadDashboard();
        muatRiwayatEvent();
        setTimeout(() => setupRealtime(), 1200);
    } else {
        switchView('absen');
        cekStatusAbsen();
        loadRiwayatAnggota();
        const hour = parseInt(now.toLocaleString('id-ID', { timeZone: 'Asia/Jakarta', hour: 'numeric', hour12: false }));
        let greet = 'Selamat datang';
        if (hour < 11) greet = 'Selamat pagi';
        else if (hour < 15) greet = 'Selamat siang';
        else if (hour < 18) greet = 'Selamat sore';
        else greet = 'Selamat malam';
        document.getElementById('greetingText').textContent = `${greet}, ${data.nama.split(' ')[0]}`;
    }
    setInterval(updateJam, 1000);
    updateJam();
    
    resetIdleTimer();
    ['click', 'keydown', 'scroll', 'touchstart'].forEach(evt => {
        document.addEventListener(evt, resetIdleTimer, { passive: true });
    });
});

function updateJam() {
    const now = new Date();
    const opsJam = { timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
    const opsTgl = { timeZone: 'Asia/Jakarta', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' };
    const elJam = document.getElementById('jamLive');
    const elTgl = document.getElementById('tanggalLive');
    if (elJam) elJam.textContent = now.toLocaleTimeString('id-ID', opsJam);
    if (elTgl) elTgl.textContent = now.toLocaleDateString('id-ID', opsTgl);
}

function buildNav() {
    const container = document.getElementById('navContainer');
    let nav = '';
    if (currentUser.role === 'admin') {
        nav = `
            <button class="nav-item active" onclick="switchView('dashboard', this)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/></svg>
                <span class="nav-text">Dashboard</span>
            </button>
            <button class="nav-item" onclick="switchView('anggota', this)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>
                <span class="nav-text">Anggota</span>
            </button>
            <button class="nav-item" onclick="switchView('semua', this)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span class="nav-text">Laporan</span>
            </button>
            <button class="nav-item" onclick="switchView('rekap', this)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>
                <span class="nav-text">Rekap</span>
            </button>
        `;
    } else {
        nav = `
            <button class="nav-item active" onclick="switchView('absen', this)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                <span class="nav-text">Absensi</span>
            </button>
        `;
    }
    container.innerHTML = nav;
}

function switchView(name, btn) {
    currentView = name;
    if (btn) {
        document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + name).classList.add('active');
    
    // Lazy load — hanya load saat pertama kali buka tab
    if (name === 'dashboard') loadDashboard();
    if (name === 'anggota' && !loadedTabs.anggota) { loadAnggota(); loadedTabs.anggota = true; }
    if (name === 'semua' && !loadedTabs.semua) { loadSemuaAbsen(); loadedTabs.semua = true; }
    if (name === 'rekap' && !loadedTabs.rekap) { loadRekap(); loadedTabs.rekap = true; }
    if (name === 'absen') { cekStatusAbsen(); loadRiwayatAnggota(); }
}

function showToast(msg, type='info') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast show ' + type;
    clearTimeout(window.toastTimer);
    window.toastTimer = setTimeout(() => t.className = 'toast ' + type, 3500);
}

async function doLogout() {
    if (!confirm('Yakin mau keluar dari sistem?')) return;
    if (eventSource) eventSource.close();
    if (pollingInterval) clearInterval(pollingInterval);
    await fetch('/api/logout', {method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': CSRF_TOKEN}});
    window.location.href = '/login';
}

function setupRealtime() {
    try {
        eventSource = new EventSource('/api/events');
        eventSource.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);
                if (event.tipe === 'heartbeat' || event.tipe === 'connected') return;
                if (event.tipe === 'masuk') {
                    showToast(event.nama + ' telah absen datang pukul ' + event.waktu, 'success');
                } else if (event.tipe === 'pulang') {
                    showToast(event.nama + ' telah absen pulang pukul ' + event.waktu, 'warning');
                }
                muatRiwayatEvent();
                loadDashboard();
                if (currentView === 'semua') loadSemuaAbsen();
                if (currentView === 'rekap') loadRekap();
            } catch (err) { console.error(err); }
        };
        eventSource.onerror = () => setupPolling();
    } catch (err) { setupPolling(); }
}

function setupPolling() {
    if (pollingInterval) return;
    pollingInterval = setInterval(() => {
        if (currentView === 'dashboard') loadDashboard();
        if (currentView === 'semua') loadSemuaAbsen();
    }, 8000);
}

async function muatRiwayatEvent() {
    const events = await fetchJSON('/api/events/riwayat');
    const container = document.getElementById('eventLog');
    if (!container) return;
    if (!events || events.length === 0) {
        container.innerHTML = '<div class="empty-state">Belum ada aktivitas hari ini</div>';
        return;
    }
    container.innerHTML = '';
    events.forEach(e => {
        const div = document.createElement('div');
        div.className = 'event-item ' + e.tipe;
        const icon = e.tipe === 'masuk' ? '→' : '←';
        div.innerHTML = `
            <div class="event-icon">${icon}</div>
            <div class="event-content">
                <div class="title">${escapeHtml(e.nama)}</div>
                <div class="desc">${escapeHtml(e.pesan)}</div>
            </div>
            <div class="event-time">${e.waktu}</div>
        `;
        container.appendChild(div);
    });
}

async function loadDashboard() {
    try {
        const dataHariIni = await fetchJSON('/api/absensi/hari-ini') || [];
        let semuaAnggota = cacheAnggota;
        if (!semuaAnggota) {
            semuaAnggota = await fetchJSON('/api/anggota') || [];
            cacheAnggota = semuaAnggota;
            cacheTime = Date.now();
        }
        const aktifAnggota = semuaAnggota.filter(k => k.aktif && k.role === 'anggota');
        document.getElementById('statHadirHariIni').innerHTML = dataHariIni.length + '<span class="unit">anggota</span>';
        document.getElementById('statTotalAnggota').innerHTML = aktifAnggota.length + '<span class="unit">orang</span>';
        document.getElementById('statBelumAbsen').innerHTML = Math.max(0, aktifAnggota.length - dataHariIni.length) + '<span class="unit">orang</span>';
        const sudahPulang = dataHariIni.filter(a => a.jam_pulang !== '-').length;
        document.getElementById('statSudahPulang').innerHTML = sudahPulang + '<span class="unit">orang</span>';
        const tbody = document.getElementById('absenHariIni');
        if (dataHariIni.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Belum ada anggota yang absen hari ini</td></tr>';
            return;
        }
        tbody.innerHTML = '';
        dataHariIni.forEach(a => {
            const row = document.createElement('tr');
            const masuk = a.jam_masuk !== '-' ? `<strong style="color:var(--gold-500);font-family:'SF Mono',Consolas,monospace;">${a.jam_masuk}</strong>` : '<span class="muted">-</span>';
            const pulang = a.jam_pulang !== '-' ? `<strong style="color:var(--success);font-family:'SF Mono',Consolas,monospace;">${a.jam_pulang}</strong>` : '<span class="muted">-</span>';
            row.innerHTML = `
                <td data-label="Nama"><strong>${escapeHtml(a.nama)}</strong></td>
                <td data-label="Divisi">${escapeHtml(a.divisi)}</td>
                <td data-label="Datang" class="center">${masuk}</td>
                <td data-label="Pulang" class="center">${pulang}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (err) { console.error(err); }
}

async function cekStatusAbsen() {
    const data = await fetchJSON('/api/absensi/status');
    if (!data) return;
    const valMasuk = document.getElementById('valMasuk');
    const valPulang = document.getElementById('valPulang');
    const btnMasuk = document.getElementById('btnMasuk');
    const btnPulang = document.getElementById('btnPulang');
    if (data.sudah_masuk) {
        valMasuk.textContent = data.jam_masuk;
        valMasuk.classList.remove('empty');
        btnMasuk.disabled = true;
        btnMasuk.querySelector('.time').textContent = 'Sudah absen';
    } else {
        valMasuk.textContent = '--:--:--';
        valMasuk.classList.add('empty');
        btnMasuk.disabled = false;
    }
    if (data.sudah_pulang) {
        valPulang.textContent = data.jam_pulang;
        valPulang.classList.remove('empty');
        btnPulang.disabled = true;
        btnPulang.querySelector('.time').textContent = 'Sudah absen';
    } else {
        valPulang.textContent = '--:--:--';
        valPulang.classList.add('empty');
        btnPulang.disabled = !data.sudah_masuk;
    }
}

async function absenMasuk() {
    if (!confirm('Konfirmasi absen datang sekarang?')) return;
    const data = await fetchJSON('/api/absensi/masuk', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({kegiatan: ''})
    });
    if (data && data.success) {
        showToast(data.message, 'success');
        cekStatusAbsen();
        loadRiwayatAnggota();
    } else if (data) { showToast(data.message, 'error'); }
}

async function absenPulang() {
    if (!confirm('Konfirmasi absen pulang sekarang?')) return;
    const data = await fetchJSON('/api/absensi/pulang', {method: 'POST'});
    if (data && data.success) {
        showToast(data.message, 'success');
        cekStatusAbsen();
        loadRiwayatAnggota();
    } else if (data) { showToast(data.message, 'error'); }
}

async function loadRiwayatAnggota() {
    const tbody = document.getElementById('riwayatBodyAnggota');
    tbody.innerHTML = '<tr><td colspan="4" class="loading-state">⏳ Memuat riwayat...</td></tr>';
    
    const bulan = document.getElementById('filterBulanAnggota').value || new Date().toISOString().slice(0, 7);
    const data = await fetchJSON('/api/absensi/riwayat?bulan=' + bulan) || [];
    
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-state">Belum ada riwayat absen untuk periode ini</td></tr>';
        return;
    }
    const fragment = document.createDocumentFragment();
    data.forEach(r => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td data-label="Tanggal">${formatTanggal(r.tanggal)}</td>
            <td data-label="Datang" class="center mono">${r.jam_masuk}</td>
            <td data-label="Pulang" class="center mono">${r.jam_pulang}</td>
            <td data-label="Status"><span class="badge badge-${r.status.toLowerCase()}">${r.status}</span></td>
        `;
        fragment.appendChild(row);
    });
    tbody.innerHTML = '';
    tbody.appendChild(fragment);
}

async function loadAnggota(forceRefresh = false) {
    const now = Date.now();
    if (!forceRefresh && cacheAnggota && (now - cacheTime) < CACHE_DURATION) {
        anggotaList = cacheAnggota;
    } else {
        anggotaList = await fetchJSON('/api/anggota') || [];
        cacheAnggota = anggotaList;
        cacheTime = now;
    }
    renderAnggota();
    const sel = document.getElementById('filterAnggotaSemua');
    if (sel) {
        sel.innerHTML = '<option value="">Semua Anggota</option>';
        anggotaList.forEach(k => {
            sel.innerHTML += `<option value="${k.id}">${escapeHtml(k.nama)}</option>`;
        });
    }
}

function renderAnggota() {
    const search = (document.getElementById('searchAnggota').value || '').toLowerCase();
    const dept = document.getElementById('filterDivisi').value;
    const filtered = anggotaList.filter(k => {
        const matchSearch = k.nama.toLowerCase().includes(search) || 
                           k.username.toLowerCase().includes(search) ||
                           (k.no_anggota || '').toLowerCase().includes(search);
        const matchDept = !dept || k.divisi === dept;
        return matchSearch && matchDept;
    });
    document.getElementById('totalAnggota').textContent = filtered.length;
    const tbody = document.getElementById('anggotaBody');
    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Tidak ada anggota ditemukan</td></tr>';
        return;
    }
    const fragment = document.createDocumentFragment();
    filtered.forEach(k => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td data-label="No. Anggota" class="mono">${escapeHtml(k.no_anggota || '-')}</td>
            <td data-label="Nama"><strong>${escapeHtml(k.nama)}</strong><br><span class="muted mono" style="font-size:11px;">@${escapeHtml(k.username)}</span></td>
            <td data-label="Jabatan">${escapeHtml(k.jabatan)}</td>
            <td data-label="Divisi">${escapeHtml(k.divisi)}</td>
            <td data-label="Kontak" class="muted" style="font-size:11.5px;">${escapeHtml(k.email || '-')}<br>${escapeHtml(k.no_hp || '-')}</td>
            <td data-label="Status"><span class="badge badge-${k.aktif ? 'aktif' : 'nonaktif'}">${k.aktif ? 'Aktif' : 'Nonaktif'}</span></td>
            <td data-label="Aksi" class="center">
                <div style="display:flex;gap:6px;justify-content:center;">
                    <button class="btn btn-sm btn-icon" onclick="editAnggota(${k.id})" title="Edit">✏</button>
                    <button class="btn btn-sm btn-icon btn-danger" onclick="hapusAnggota(${k.id}, '${escapeAttr(k.nama)}')" title="Hapus">🗑</button>
                </div>
            </td>
        `;
        fragment.appendChild(row);
    });
    tbody.innerHTML = '';
    tbody.appendChild(fragment);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function escapeAttr(text) {
    if (!text) return '';
    return String(text).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function bukaModalAnggota() {
    editAnggotaId = null;
    document.getElementById('modalAnggotaTitle').textContent = 'Tambah Anggota';
    ['inputNoAnggota', 'inputUsername', 'inputPassword', 'inputNamaAnggota', 'inputEmail', 'inputNoHp'].forEach(id => {
        document.getElementById(id).value = '';
    });
    document.getElementById('inputNoAnggota').disabled = false;
    document.getElementById('inputUsername').disabled = false;
    document.getElementById('inputPassword').placeholder = 'Minimal 6 karakter';
    document.getElementById('inputJabatan').value = 'Anggota';
    document.getElementById('inputDivisi').value = 'Umum';
    document.getElementById('rowAktif').style.display = 'none';
    document.getElementById('modalAnggota').classList.add('show');
}

function editAnggota(id) {
    const k = anggotaList.find(x => x.id === id);
    if (!k) return;
    editAnggotaId = id;
    document.getElementById('modalAnggotaTitle').textContent = 'Edit Data Anggota';
    document.getElementById('inputNoAnggota').value = k.no_anggota || '';
    document.getElementById('inputNoAnggota').disabled = true;
    document.getElementById('inputUsername').value = k.username;
    document.getElementById('inputUsername').disabled = true;
    document.getElementById('inputPassword').value = '';
    document.getElementById('inputPassword').placeholder = 'Kosongkan jika tidak diubah';
    document.getElementById('inputNamaAnggota').value = k.nama;
    document.getElementById('inputJabatan').value = k.jabatan;
    document.getElementById('inputDivisi').value = k.divisi;
    document.getElementById('inputEmail').value = k.email || '';
    document.getElementById('inputNoHp').value = k.no_hp || '';
    document.getElementById('inputAktif').value = k.aktif ? '1' : '0';
    document.getElementById('rowAktif').style.display = 'block';
    document.getElementById('modalAnggota').classList.add('show');
}

function tutupModalAnggota() {
    document.getElementById('modalAnggota').classList.remove('show');
}

async function simpanAnggota() {
    const no_anggota = document.getElementById('inputNoAnggota').value.trim();
    const username = document.getElementById('inputUsername').value.trim();
    const password = document.getElementById('inputPassword').value.trim();
    const nama = document.getElementById('inputNamaAnggota').value.trim();
    const jabatan = document.getElementById('inputJabatan').value;
    const divisi = document.getElementById('inputDivisi').value;
    const email = document.getElementById('inputEmail').value.trim();
    const no_hp = document.getElementById('inputNoHp').value.trim();
    if (!nama) { showToast('Nama wajib diisi', 'error'); return; }
    if (!editAnggotaId && (!username || !password)) {
        showToast('Username dan password wajib diisi', 'error'); return;
    }
    if (password && password.length < 6) {
        showToast('Password minimal 6 karakter', 'error'); return;
    }
    let url, method, body;
    if (editAnggotaId) {
        url = '/api/anggota/' + editAnggotaId;
        method = 'PUT';
        body = { nama, jabatan, divisi, email, no_hp, password,
                 aktif: document.getElementById('inputAktif').value === '1' };
    } else {
        url = '/api/anggota';
        method = 'POST';
        body = { no_anggota, username, password, nama, jabatan, divisi, email, no_hp };
    }
    const data = await fetchJSON(url, {
        method: method,
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
    });
    if (data && data.success) {
        showToast(data.message, 'success');
        cacheAnggota = null;
        tutupModalAnggota();
        loadAnggota(true);
    } else if (data) { showToast(data.message, 'error'); }
}

async function hapusAnggota(id, nama) {
    if (!confirm('Hapus anggota "' + nama + '"?')) return;
    const data = await fetchJSON('/api/anggota/' + id, {method: 'DELETE'});
    if (data && data.success) {
        showToast(data.message, 'success');
        cacheAnggota = null;
        loadAnggota(true);
    } else if (data) { showToast(data.message, 'error'); }
}

async function loadSemuaAbsen() {
    const tbody = document.getElementById('semuaBody');
    tbody.innerHTML = '<tr><td colspan="6" class="loading-state">⏳ Memuat data kehadiran...</td></tr>';
    
    const bulan = document.getElementById('filterBulanSemua').value || new Date().toISOString().slice(0, 7);
    const userId = document.getElementById('filterAnggotaSemua').value;
    let url = '/api/absensi/riwayat?bulan=' + bulan;
    if (userId) url += '&user_id=' + userId;
    const data = await fetchJSON(url) || [];
    document.getElementById('totalAbsen').textContent = data.length;
    
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Belum ada data absensi untuk periode ini</td></tr>';
        return;
    }
    
    const fragment = document.createDocumentFragment();
    data.forEach(r => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td data-label="Tanggal" class="mono">${formatTanggal(r.tanggal)}</td>
            <td data-label="Nama"><strong>${escapeHtml(r.nama)}</strong></td>
            <td data-label="Jabatan">${escapeHtml(r.jabatan)}</td>
            <td data-label="Datang" class="center mono">${r.jam_masuk}</td>
            <td data-label="Pulang" class="center mono">${r.jam_pulang}</td>
            <td data-label="Status"><span class="badge badge-${r.status.toLowerCase()}">${r.status}</span></td>
        `;
        fragment.appendChild(row);
    });
    tbody.innerHTML = '';
    tbody.appendChild(fragment);
}

async function loadRekap() {
    const tbody = document.getElementById('rekapBody');
    tbody.innerHTML = '<tr><td colspan="8" class="loading-state">⏳ Menghitung rekap...</td></tr>';
    
    const bulan = document.getElementById('filterBulanRekap').value || new Date().toISOString().slice(0, 7);
    const data = await fetchJSON('/api/rekap?bulan=' + bulan);
    
    if (!data) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Gagal memuat data</td></tr>';
        return;
    }
    document.getElementById('statHariKerja').innerHTML = data.hari_kerja + '<span class="unit">hari</span>';
    document.getElementById('statTotalAnggotaRekap').innerHTML = data.rekap.length + '<span class="unit">orang</span>';
    document.getElementById('statTotalHadir').innerHTML = data.rekap.reduce((s, r) => s + r.hadir, 0) + '<span class="unit">hari</span>';
    
    if (data.rekap.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Belum ada data untuk periode ini</td></tr>';
        return;
    }
    
    const fragment = document.createDocumentFragment();
    data.rekap.forEach(r => {
        const persen = data.hari_kerja > 0 ? Math.round((r.hadir / data.hari_kerja) * 100) : 0;
        const row = document.createElement('tr');
        row.innerHTML = `
            <td data-label="Nama"><strong>${escapeHtml(r.nama)}</strong></td>
            <td data-label="Divisi">${escapeHtml(r.divisi)}</td>
            <td data-label="Hadir" class="center mono" style="color:var(--gold-500);font-weight:700;">${r.hadir}</td>
            <td data-label="Izin" class="center mono">${r.izin}</td>
            <td data-label="Sakit" class="center mono">${r.sakit}</td>
            <td data-label="Cuti" class="center mono">${r.cuti}</td>
            <td data-label="Alpha" class="center mono" style="color:var(--danger);font-weight:700;">${r.alpha}</td>
            <td data-label="Kehadiran" class="center"><strong class="mono">${persen}%</strong></td>
        `;
        fragment.appendChild(row);
    });
    tbody.innerHTML = '';
    tbody.appendChild(fragment);
}

function exportCSV() {
    const bulan = document.getElementById('filterBulanSemua').value || new Date().toISOString().slice(0, 7);
    window.location.href = '/api/export/csv?bulan=' + bulan;
    showToast('Mengunduh file CSV...', 'info');
}

function exportPDF() {
    const bulan = document.getElementById('filterBulanSemua').value || new Date().toISOString().slice(0, 7);
    window.open('/api/export/pdf?bulan=' + bulan, '_blank');
}

function formatTanggal(tgl) {
    const d = new Date(tgl);
    return d.toLocaleDateString('id-ID', { day:'2-digit', month:'short', year:'numeric' });
}

window.addEventListener('beforeunload', () => {
    if (eventSource) eventSource.close();
    if (pollingInterval) clearInterval(pollingInterval);
});
</script>
</body>
</html>
"""


# ============================================================
# MAIN
# ============================================================
def buka_browser():
    time.sleep(1.5)
    try: webbrowser.open('http://localhost:5000')
    except: pass

if __name__ == '__main__':
    print()
    print("=" * 70)
    print(f"  {ORG['nama']}")
    print(f"  {ORG['jenis']} · {ORG['wilayah']}")
    print(f"  {ORG['desa']}")
    print("=" * 70)
    print()
    print("  ⚡ OPTIMIZED v6.0 — SUPER FAST")
    print("  - Query pakai range tanggal (bukan LIKE)")
    print("  - Index gabungan (tanggal, anggota)")
    print("  - Rekap 1 query agregat (bukan N×4)")
    print("  - LIMIT 500 (tidak fetch berlebihan)")
    print("  - Loading indicator di setiap tab")
    print("  - DocumentFragment untuk render cepat")
    print("  - SQLite WAL mode + 64MB cache")
    print()
    
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0'
    
    if IS_PRODUCTION:
        print(f"  Mode     : PRODUCTION")
        print(f"  Port     : {port}")
        print(f"  Waktu    : {waktu_lengkap_wib()} WIB")
    else:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_lokal = s.getsockname()[0]
            s.close()
        except: ip_lokal = "192.168.x.x"
        print(f"  Server          : http://localhost:{port}")
        print(f"  Local Network   : http://{ip_lokal}:{port}")
        print(f"  Waktu WIB       : {waktu_lengkap_wib()}")
    
    print()
    print("  Tekan CTRL+C untuk menghentikan server")
    print("=" * 70)
    print()
    
    if not IS_PRODUCTION:
        threading.Thread(target=buka_browser, daemon=True).start()
    
    app.run(host=host, port=port, debug=False, threaded=True)
