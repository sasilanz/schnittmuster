from flask import Flask, request, jsonify, send_from_directory
import sqlite3, os, uuid, json, base64, shutil
from datetime import datetime
import anthropic
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
BASE = Path(__file__).parent
DB_PATH = BASE / 'schnittmuster.db'
SCANS_DIR = BASE / 'data' / 'scans'
BILDER_DIR = BASE / 'data' / 'bilder'
BACKUP_DIR = BASE / 'backups'

def auto_backup():
    if not DB_PATH.exists():
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    dest = BACKUP_DIR / f'schnittmuster_{today}.db'
    if not dest.exists():
        shutil.copy2(DB_PATH, dest)
    # Nur die letzten 7 Backups behalten
    backups = sorted(BACKUP_DIR.glob('schnittmuster_*.db'))
    for old in backups[:-7]:
        old.unlink()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS hefte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            notiz TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            heft_id INTEGER REFERENCES hefte(id) ON DELETE CASCADE,
            datei TEXT NOT NULL,
            seite INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS muster (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            heft_id INTEGER REFERENCES hefte(id) ON DELETE CASCADE,
            nr TEXT DEFAULT '',
            bezeichnung TEXT DEFAULT '',
            kollektion TEXT DEFAULT '',
            groessen TEXT DEFAULT '',
            seite_heft TEXT DEFAULT '',
            beschreibung TEXT DEFAULT '',
            notiz TEXT DEFAULT '',
            favorit INTEGER DEFAULT 0,
            bild TEXT DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            muster_id INTEGER REFERENCES muster(id) ON DELETE CASCADE,
            tag TEXT NOT NULL
        );
        """)

init_db()
auto_backup()

def muster_dict(row, tags=None):
    d = dict(row)
    d['favorit'] = bool(d['favorit'])
    d['tags'] = tags or []
    return d

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/images/<path:filename>')
def images(filename):
    return send_from_directory(str(BASE / 'data'), filename)

# ── HEFTE ─────────────────────────────────────────────────────────────────────

@app.route('/api/hefte', methods=['GET'])
def get_hefte():
    with get_db() as c:
        rows = c.execute("""
            SELECT h.*, COUNT(m.id) as anzahl
            FROM hefte h LEFT JOIN muster m ON m.heft_id = h.id
            GROUP BY h.id ORDER BY h.name
        """).fetchall()
        result = []
        for row in rows:
            h = dict(row)
            h['scans'] = [dict(s) for s in c.execute(
                "SELECT * FROM scans WHERE heft_id=? ORDER BY seite", (h['id'],)
            ).fetchall()]
            result.append(h)
    return jsonify(result)

@app.route('/api/hefte', methods=['POST'])
def create_heft():
    data = request.json
    with get_db() as c:
        c.execute("INSERT OR IGNORE INTO hefte (name, notiz) VALUES (?,?)",
                  (data['name'], data.get('notiz', '')))
        row = c.execute("SELECT * FROM hefte WHERE name=?", (data['name'],)).fetchone()
    return jsonify(dict(row))

@app.route('/api/hefte/<int:hid>', methods=['DELETE'])
def delete_heft(hid):
    with get_db() as c:
        scans = c.execute("SELECT datei FROM scans WHERE heft_id=?", (hid,)).fetchall()
        bilder = c.execute("SELECT bild FROM muster WHERE heft_id=? AND bild IS NOT NULL", (hid,)).fetchall()
        c.execute("DELETE FROM hefte WHERE id=?", (hid,))
    for s in scans:
        f = SCANS_DIR / s['datei']
        if f.exists(): f.unlink()
    for b in bilder:
        f = BILDER_DIR / b['bild']
        if f.exists(): f.unlink()
    return jsonify({'ok': True})

# ── SCANS ─────────────────────────────────────────────────────────────────────

@app.route('/api/upload/scan', methods=['POST'])
def upload_scan():
    heft_id = request.form.get('heft_id')
    seite = int(request.form.get('seite', 1))
    file = request.files.get('file')
    if not file or not heft_id:
        return jsonify({'error': 'missing'}), 400
    ext = Path(file.filename).suffix.lower() or '.jpg'
    fname = f"{uuid.uuid4()}{ext}"
    file.save(SCANS_DIR / fname)
    with get_db() as c:
        c.execute("INSERT INTO scans (heft_id, datei, seite) VALUES (?,?,?)", (heft_id, fname, seite))
        sid = c.execute("SELECT last_insert_rowid() as id").fetchone()['id']
    return jsonify({'id': sid, 'datei': fname, 'seite': seite})

# ── MUSTER ────────────────────────────────────────────────────────────────────

@app.route('/api/muster', methods=['GET'])
def get_muster():
    q = request.args.get('q', '').strip()
    heft_id = request.args.get('heft_id', '')
    groesse = request.args.get('groesse', '').strip()
    favorit = request.args.get('favorit', '')

    sql = "SELECT m.*, h.name as heft_name FROM muster m LEFT JOIN hefte h ON h.id=m.heft_id WHERE 1=1"
    params = []
    if q:
        sql += " AND (m.nr LIKE ? OR m.bezeichnung LIKE ? OR m.kollektion LIKE ? OR m.beschreibung LIKE ? OR m.notiz LIKE ?)"
        p = f'%{q}%'
        params += [p, p, p, p, p]
    if heft_id:
        sql += " AND m.heft_id=?"
        params.append(heft_id)
    if groesse:
        sql += " AND m.groessen LIKE ?"
        params.append(f'%{groesse}%')
    if favorit == '1':
        sql += " AND m.favorit=1"
    sql += " ORDER BY m.favorit DESC, m.id DESC"

    with get_db() as c:
        rows = c.execute(sql, params).fetchall()
        result = []
        for row in rows:
            tags = [t['tag'] for t in c.execute("SELECT tag FROM tags WHERE muster_id=?", (row['id'],)).fetchall()]
            result.append(muster_dict(row, tags))
    return jsonify(result)

@app.route('/api/muster/bulk', methods=['POST'])
def create_muster_bulk():
    data = request.json
    heft_id = data['heft_id']
    with get_db() as c:
        ids = []
        for m in data['muster']:
            c.execute("""INSERT INTO muster (heft_id, nr, bezeichnung, kollektion, groessen, seite_heft, beschreibung)
                         VALUES (?,?,?,?,?,?,?)""",
                      (heft_id, m.get('nr',''), m.get('bezeichnung',''), m.get('kollektion',''),
                       m.get('groessen',''), m.get('seite',''), m.get('beschreibung','')))
            ids.append(c.execute("SELECT last_insert_rowid() as id").fetchone()['id'])
    return jsonify({'ids': ids, 'count': len(ids)})

@app.route('/api/muster/<int:mid>', methods=['PUT'])
def update_muster(mid):
    data = request.json
    tags = data.pop('tags', None)
    fields = ['nr', 'bezeichnung', 'kollektion', 'groessen', 'seite_heft', 'beschreibung', 'notiz', 'favorit', 'bild']
    updates = {k: data[k] for k in fields if k in data}
    if 'favorit' in updates:
        updates['favorit'] = int(updates['favorit'])
    if updates:
        sql = "UPDATE muster SET " + ", ".join(f"{k}=?" for k in updates) + " WHERE id=?"
        with get_db() as c:
            c.execute(sql, list(updates.values()) + [mid])
    if tags is not None:
        with get_db() as c:
            c.execute("DELETE FROM tags WHERE muster_id=?", (mid,))
            for tag in tags:
                if tag.strip():
                    c.execute("INSERT INTO tags (muster_id, tag) VALUES (?,?)", (mid, tag.strip()))
    with get_db() as c:
        row = c.execute("SELECT m.*, h.name as heft_name FROM muster m LEFT JOIN hefte h ON h.id=m.heft_id WHERE m.id=?", (mid,)).fetchone()
        tags_out = [t['tag'] for t in c.execute("SELECT tag FROM tags WHERE muster_id=?", (mid,)).fetchall()]
    return jsonify(muster_dict(row, tags_out))

@app.route('/api/muster/<int:mid>', methods=['DELETE'])
def delete_muster(mid):
    with get_db() as c:
        row = c.execute("SELECT bild FROM muster WHERE id=?", (mid,)).fetchone()
        if row and row['bild']:
            f = BILDER_DIR / row['bild']
            if f.exists(): f.unlink()
        c.execute("DELETE FROM muster WHERE id=?", (mid,))
    return jsonify({'ok': True})

@app.route('/api/muster/<int:mid>/bild', methods=['POST'])
def save_bild(mid):
    img_data = base64.b64decode(request.json['image'])
    with get_db() as c:
        row = c.execute("SELECT bild FROM muster WHERE id=?", (mid,)).fetchone()
        if row and row['bild']:
            f = BILDER_DIR / row['bild']
            if f.exists(): f.unlink()
    fname = f"{uuid.uuid4()}.jpg"
    (BILDER_DIR / fname).write_bytes(img_data)
    with get_db() as c:
        c.execute("UPDATE muster SET bild=? WHERE id=?", (fname, mid))
    return jsonify({'bild': fname})

# ── EXTRAKTION ────────────────────────────────────────────────────────────────

@app.route('/api/scan/<int:sid>', methods=['DELETE'])
def delete_scan(sid):
    with get_db() as c:
        row = c.execute("SELECT datei FROM scans WHERE id=?", (sid,)).fetchone()
        if row:
            f = SCANS_DIR / row['datei']
            if f.exists(): f.unlink()
        c.execute("DELETE FROM scans WHERE id=?", (sid,))
    return jsonify({'ok': True})

@app.route('/api/scan/<int:sid>/move', methods=['POST'])
def move_scan(sid):
    direction = request.json.get('direction', 1)
    with get_db() as c:
        row = c.execute("SELECT * FROM scans WHERE id=?", (sid,)).fetchone()
        if not row: return jsonify({'error': 'nicht gefunden'}), 404
        scans = c.execute("SELECT * FROM scans WHERE heft_id=? ORDER BY seite", (row['heft_id'],)).fetchall()
        ids = [s['id'] for s in scans]
        idx = ids.index(sid)
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(ids): return jsonify({'ok': True})
        # Swap seite values
        id_a, id_b = ids[idx], ids[new_idx]
        seite_a = scans[idx]['seite']
        seite_b = scans[new_idx]['seite']
        c.execute("UPDATE scans SET seite=? WHERE id=?", (seite_b, id_a))
        c.execute("UPDATE scans SET seite=? WHERE id=?", (seite_a, id_b))
    return jsonify({'ok': True})

@app.route('/api/scan/<int:sid>/rotate', methods=['POST'])
def rotate_scan(sid):
    from PIL import Image as PILImage
    degrees = request.json.get('degrees', 90)
    with get_db() as c:
        row = c.execute("SELECT datei FROM scans WHERE id=?", (sid,)).fetchone()
    if not row:
        return jsonify({'error': 'nicht gefunden'}), 404
    path = SCANS_DIR / row['datei']
    img = PILImage.open(path)
    img = img.rotate(-degrees, expand=True)
    img.save(path)
    return jsonify({'ok': True})

@app.route('/api/extract', methods=['POST'])
def extract():
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'Kein API Key in .env'}), 500
    files = request.files.getlist('images')
    if not files:
        return jsonify({'error': 'Keine Bilder'}), 400

    contents = []
    for f in files:
        b64 = base64.b64encode(f.read()).decode()
        contents.append({"type": "image", "source": {
            "type": "base64", "media_type": f.content_type or 'image/jpeg', "data": b64
        }})
    contents.append({"type": "text", "text": """Übersichtsseite(n) eines Näh-Magazins ("Alle Modelle").
Extrahiere alle Schnittmuster als JSON-Array:
- nr: Muster-Nummer
- bezeichnung: Kleidungsstück (Bluse, Hose, Kleid, Jacke, Rock, etc.)
- kollektion: Gruppe falls erkennbar, sonst ""
- groessen: Grössenbereich (z.B. "36-46"), sonst ""
- seite: Seitenzahl im Heft falls erkennbar, sonst ""
- beschreibung: 1 Satz visuelle Beschreibung (Stil, Details)
Nur JSON-Array, kein Markdown."""})

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(model="claude-sonnet-4-5", max_tokens=8192,
                                  messages=[{"role": "user", "content": contents}])
    raw = msg.content[0].text.strip().replace("```json","").replace("```","").strip()
    return jsonify(json.loads(raw))

if __name__ == '__main__':
    print("✂️  Schnittmuster-DB → http://localhost:7331")
    app.run(port=7331, debug=False)
