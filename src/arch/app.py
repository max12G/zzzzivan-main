from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os, json, requests, traceback
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tvoja_super_sekretnaja_kluch_fraza_2026')

# ============ MISTRAL LA PLATEFORME ============
MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY', '').strip()
MISTRAL_URL = 'https://api.mistral.ai/v1/chat/completions'

# ============ ЛОКАЛЬНАЯ БД ============
DB_PATH = os.environ.get(
    'LOCAL_DB_PATH',
    os.path.join(os.path.dirname(__file__), 'data', 'app.db'),
)

MODELS = [
    {'id': 'mistral-small-latest', 'name': 'Mistral Small',      'vendor': 'Mistral', 'desc': 'Умная модель общего назначения'},
    {'id': 'open-mistral-nemo',    'name': 'Mistral NeMo 12B',   'vendor': 'Mistral', 'desc': 'Быстрая, контекст 128K'},
    {'id': 'ministral-8b-latest',  'name': 'Ministral 8B',       'vendor': 'Mistral', 'desc': 'Баланс скорости и качества'},
    {'id': 'ministral-3b-latest',  'name': 'Ministral 3B',       'vendor': 'Mistral', 'desc': 'Самая быстрая, лёгкая'},
    {'id': 'open-mixtral-8x7b',    'name': 'Mixtral 8x7B',       'vendor': 'Mistral', 'desc': 'MoE-архитектура'},
    {'id': 'open-mixtral-8x22b',   'name': 'Mixtral 8x22B',      'vendor': 'Mistral', 'desc': 'Мощная MoE-модель'},
    {'id': 'codestral-latest',     'name': 'Codestral',          'vendor': 'Mistral', 'desc': 'Специализация — код'},
    {'id': 'pixtral-12b-2409',     'name': 'Pixtral 12B (Vision)','vendor': 'Mistral', 'desc': 'Понимает изображения'},
]


def get_db_connection():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        cnx = sqlite3.connect(DB_PATH)
        cnx.row_factory = sqlite3.Row
        return cnx
    except sqlite3.Error as e:
        print(f"[DB] Ошибка подключения: {e}")
        return None


# ============ АВТОСОЗДАНИЕ ТАБЛИЦЫ ============
def ensure_schema():
    """Создаёт таблицу users и колонку balance, если их нет."""
    cnx = get_db_connection()
    if not cnx:
        print("[DB] Не удалось подключиться — БД не настроена или недоступна")
        return False

    cur = cnx.cursor()
    try:
        # Создаём таблицу users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS `users` (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                balance REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Проверяем, есть ли колонка balance (если таблица была создана ранее)
        columns = {row['name'] for row in cur.execute("PRAGMA table_info(users)")}
        if 'balance' not in columns:
            print("[DB] Добавляю колонку balance…")
            cur.execute("ALTER TABLE users ADD COLUMN balance REAL NOT NULL DEFAULT 0")

        cnx.commit()
        print("[DB] Схема готова ✅")
        return True
    except sqlite3.Error as e:
        print(f"[DB] Ошибка при создании схемы: {e}")
        traceback.print_exc()
        return False
    finally:
        cur.close(); cnx.close()


# ============ РЕГИСТРАЦИЯ / ВХОД / ВЫХОД ============

@app.route('/user_register', methods=['POST'])
def user_register():
    req = request.get_json(silent=True)
    if not req or not all(k in req for k in ('name', 'email', 'password')):
        return jsonify({'status': 'error', 'message': 'Не все данные переданы'}), 400

    name, login, password = req['name'], req['email'], req['password']
    password_hash = generate_password_hash(password)

    cnx = get_db_connection()
    if not cnx:
        return jsonify({'status': 'error', 'message': 'Не удалось подключиться к БД'}), 500

    cur = cnx.cursor()
    try:
        cur.execute('SELECT id FROM users WHERE email = ?', (login,))
        if cur.fetchone():
            return jsonify({'status': 'error', 'message': 'Email уже занят'}), 409

        cur.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
            (name, login, password_hash)
        )
        cnx.commit()
        print(f"[REG] Зарегистрирован: {login}")
        return jsonify({'status': 'ok', 'message': 'Регистрация успешна'})
    except sqlite3.Error as e:
        cnx.rollback()
        print(f"[REG] Ошибка: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Ошибка БД: {e}'}), 500
    finally:
        cur.close(); cnx.close()


@app.route('/user_login', methods=['POST'])
def user_login():
    req = request.get_json(silent=True)
    if not req or 'username' not in req or 'password' not in req:
        return jsonify({'status': 'error', 'message': 'Не все данные переданы'}), 400

    login, password = req['username'], req['password']

    cnx = get_db_connection()
    if not cnx:
        return jsonify({'status': 'error', 'message': 'Не удалось подключиться к БД'}), 500

    cur = cnx.cursor()
    try:
        cur.execute('SELECT id, username, email, password_hash FROM users WHERE email = ?', (login,))
        user = cur.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            print(f"[LOGIN] Успех: {login}")
            return jsonify({'status': 'ok', 'redirect': '/dashboard'})

        print(f"[LOGIN] Провал: {login}")
        return jsonify({'status': 'error', 'message': 'Неверный логин или пароль'}), 401
    except sqlite3.Error as e:
        print(f"[LOGIN] Ошибка: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Ошибка БД: {e}'}), 500
    finally:
        cur.close(); cnx.close()


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ============ СТРАНИЦЫ ============

@app.route("/")
def registration():
    return render_template('registration.html')


@app.route("/login")
def login():
    return render_template('login.html')


def get_balance():
    cnx = get_db_connection()
    if not cnx:
        return 0.0
    cur = cnx.cursor()
    try:
        cur.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],))
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0
    except sqlite3.Error:
        return 0.0
    finally:
        cur.close(); cnx.close()


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template(
        'dashboard.html',
        username=session.get('username'),
        email=session.get('email'),
        models=MODELS,
        balance=get_balance(),
    )


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('profile.html', username=session.get('username'))


# ============ API: МОДЕЛИ / БАЛАНС / ПОПОЛНЕНИЕ ============

@app.route('/api/models')
def api_models():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    return jsonify({'models': MODELS})


@app.route('/api/profile')
def api_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401

    cnx = get_db_connection()
    if not cnx:
        return jsonify({'error': 'Ошибка БД'}), 500
    try:
        row = cnx.execute(
            'SELECT username, email, balance FROM users WHERE id = ?',
            (session['user_id'],),
        ).fetchone()
        if not row:
            return jsonify({'error': 'Пользователь не найден'}), 404
        return jsonify({
            'username': row['username'],
            'email': row['email'],
            'balance': float(row['balance'] or 0),
        })
    except sqlite3.Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cnx.close()


@app.route('/api/profile', methods=['PUT'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401

    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    current_password = data.get('current_password', '')
    if not username or not email or '@' not in email:
        return jsonify({'error': 'Введите корректные имя и почту'}), 400

    cnx = get_db_connection()
    if not cnx:
        return jsonify({'error': 'Ошибка БД'}), 500
    try:
        user = cnx.execute(
            'SELECT password_hash FROM users WHERE id = ?',
            (session['user_id'],),
        ).fetchone()
        if not user or not check_password_hash(user['password_hash'], current_password):
            return jsonify({'error': 'Неверный текущий пароль'}), 400

        cnx.execute(
            'UPDATE users SET username = ?, email = ? WHERE id = ?',
            (username, email, session['user_id']),
        )
        cnx.commit()
        session['username'] = username
        session['email'] = email
        return jsonify({'status': 'ok'})
    except sqlite3.IntegrityError:
        cnx.rollback()
        return jsonify({'error': 'Эта почта уже используется'}), 409
    except sqlite3.Error as e:
        cnx.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cnx.close()


@app.route('/api/profile/password', methods=['POST'])
def change_password():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401

    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    if len(new_password) < 8:
        return jsonify({'error': 'Новый пароль должен быть не короче 8 символов'}), 400

    cnx = get_db_connection()
    if not cnx:
        return jsonify({'error': 'Ошибка БД'}), 500
    try:
        user = cnx.execute(
            'SELECT password_hash FROM users WHERE id = ?',
            (session['user_id'],),
        ).fetchone()
        if not user or not check_password_hash(user['password_hash'], current_password):
            return jsonify({'error': 'Неверный текущий пароль'}), 400

        cnx.execute(
            'UPDATE users SET password_hash = ? WHERE id = ?',
            (generate_password_hash(new_password), session['user_id']),
        )
        cnx.commit()
        return jsonify({'status': 'ok'})
    except sqlite3.Error as e:
        cnx.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cnx.close()


@app.route('/api/balance')
def api_balance():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    return jsonify({'balance': get_balance()})


@app.route('/api/topup', methods=['POST'])
def api_topup():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401

    data = request.get_json(silent=True) or {}
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        amount = 0

    if amount <= 0:
        return jsonify({'error': 'Сумма должна быть больше нуля'}), 400

    cnx = get_db_connection()
    if not cnx:
        return jsonify({'error': 'Ошибка БД'}), 500

    cur = cnx.cursor()
    try:
        cur.execute(
            'UPDATE users SET balance = balance + ? WHERE id = ?',
            (amount, session['user_id'])
        )
        cnx.commit()
        cur.execute('SELECT balance FROM users WHERE id = ?', (session['user_id'],))
        new_balance = float(cur.fetchone()[0])
        return jsonify({'status': 'ok', 'balance': new_balance})
    except sqlite3.Error as e:
        cnx.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close(); cnx.close()


# ============ API: ЧАТ С MISTRAL ============

@app.route('/api/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401

    if not MISTRAL_API_KEY:
        return jsonify({'error': 'Не задан MISTRAL_API_KEY в .env'}), 500

    data = request.get_json(silent=True) or {}
    messages = data.get('messages', [])
    model = data.get('model', MODELS[0]['id'])

    if not messages:
        return jsonify({'error': 'Пустой запрос'}), 400

    allowed = {m['id'] for m in MODELS}
    if model not in allowed:
        model = MODELS[0]['id']

    headers = {
        'Authorization': f'Bearer {MISTRAL_API_KEY}',
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
    }
    payload = {'model': model, 'messages': messages, 'stream': True}

    def stream():
        try:
            with requests.post(MISTRAL_URL, headers=headers, json=payload,
                               stream=True, timeout=180) as r:
                if r.status_code != 200:
                    yield f"data: {json.dumps({'error': f'Mistral {r.status_code}: {r.text[:400]}'})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                for raw in r.iter_lines(decode_unicode=True):
                    if not raw or not raw.startswith('data: '):
                        continue
                    chunk = raw[6:].strip()
                    if chunk == '[DONE]':
                        yield "data: [DONE]\n\n"
                        return
                    try:
                        parsed = json.loads(chunk)
                    except json.JSONDecodeError:
                        continue
                    delta = (parsed.get('choices') or [{}])[0].get('delta', {})
                    content = delta.get('content')
                    if content:
                        yield f"data: {json.dumps({'delta': content})}\n\n"
                yield "data: [DONE]\n\n"
        except requests.exceptions.RequestException as e:
            yield f"data: {json.dumps({'error': f'Сеть: {e}'})}\n\n"
            yield "data: [DONE]\n\n"

    return Response(stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
    })


# ============ ДИАГНОСТИКА ============
@app.route('/api/debug')
def api_debug():
    """Открой в браузере /api/debug — покажет состояние сервера."""
    info = {
        'mistral_key_set': bool(MISTRAL_API_KEY),
        'mistral_key_prefix': MISTRAL_API_KEY[:8] if MISTRAL_API_KEY else '',
        'db_path': DB_PATH,
    }
    cnx = get_db_connection()
    if not cnx:
        info['db_status'] = '❌ ОШИБКА ПОДКЛЮЧЕНИЯ'
        return jsonify(info)

    try:
        cur = cnx.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users'")
        info['users_table'] = '✅ есть' if cur.fetchone() else '❌ нет'

        if info['users_table'].startswith('✅'):
            columns = {row['name'] for row in cur.execute("PRAGMA table_info(users)")}
            info['balance_column'] = '✅ есть' if 'balance' in columns else '❌ нет'

            cur.execute("SELECT COUNT(*) FROM users")
            info['users_count'] = cur.fetchone()[0]

        info['db_status'] = '✅ OK'
        cur.close()
    except sqlite3.Error as e:
        info['db_status'] = f'❌ {e}'
    finally:
        cnx.close()

    return jsonify(info)


# ============ СТАРТ ============
if __name__ == '__main__':
    print("=" * 50)
    print("  NeuroAPI — запуск")
    print("=" * 50)
    print(f"  Локальная БД: {DB_PATH}")
    print(f"  Mistral ключ: {'✅ задан' if MISTRAL_API_KEY else '❌ НЕ ЗАДАН'}")
    print("-" * 50)

    ensure_schema()   # ← автосоздание таблицы и колонки balance

    print("-" * 50)
    print("  Сервер: http://127.0.0.1:5000")
    print("  Диагностика: http://127.0.0.1:5000/api/debug")
    print("=" * 50)

    app.run(debug=True, host='0.0.0.0', port=5000)
