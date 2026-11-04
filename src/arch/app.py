from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import Error
import os, json, requests, traceback
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tvoja_super_sekretnaja_kluch_fraza_2026')

# ============ MISTRAL LA PLATEFORME ============
MISTRAL_API_KEY = os.environ.get('MISTRAL_API_KEY', '').strip()
MISTRAL_URL = 'https://api.mistral.ai/v1/chat/completions'

# ============ ПОДКЛЮЧЕНИЕ К БД ============
DB_CONFIG = {
    'host':     os.environ.get('DB_HOST', '185.114.247.43'),
    'port':     int(os.environ.get('DB_PORT', 3306)),
    'database': os.environ.get('DB_NAME', 'sch688_vvedenie'),
    'user':     os.environ.get('DB_USER', 'sch688_vvedenie'),
    'password': os.environ.get('DB_PASS', 'Qwerty123'),
    'charset':  'utf8mb4',
    'connection_timeout': 10,
}

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
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
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
                `id` INT AUTO_INCREMENT PRIMARY KEY,
                `username` VARCHAR(100) NOT NULL,
                `email` VARCHAR(150) NOT NULL UNIQUE,
                `password_hash` VARCHAR(255) NOT NULL,
                `balance` DECIMAL(10,2) NOT NULL DEFAULT 0,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        # Проверяем, есть ли колонка balance (если таблица была создана ранее)
        cur.execute("SHOW COLUMNS FROM `users` LIKE 'balance'")
        if not cur.fetchone():
            print("[DB] Добавляю колонку balance…")
            cur.execute("ALTER TABLE `users` ADD COLUMN `balance` DECIMAL(10,2) NOT NULL DEFAULT 0")

        cnx.commit()
        print("[DB] Схема готова ✅")
        return True
    except Error as e:
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

    cur = cnx.cursor(dictionary=True)
    try:
        cur.execute('SELECT id FROM users WHERE email = %s', (login,))
        if cur.fetchone():
            return jsonify({'status': 'error', 'message': 'Email уже занят'}), 409

        cur.execute(
            'INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)',
            (name, login, password_hash)
        )
        cnx.commit()
        print(f"[REG] Зарегистрирован: {login}")
        return jsonify({'status': 'ok', 'message': 'Регистрация успешна'})
    except Error as e:
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

    cur = cnx.cursor(dictionary=True)
    try:
        cur.execute('SELECT id, username, email, password_hash FROM users WHERE email = %s', (login,))
        user = cur.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            print(f"[LOGIN] Успех: {login}")
            return jsonify({'status': 'ok', 'redirect': '/dashboard'})

        print(f"[LOGIN] Провал: {login}")
        return jsonify({'status': 'error', 'message': 'Неверный логин или пароль'}), 401
    except Error as e:
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
        cur.execute('SELECT balance FROM users WHERE id = %s', (session['user_id'],))
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0
    except Error:
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
        models=MODELS,
        balance=get_balance(),
    )


# ============ API: МОДЕЛИ / БАЛАНС / ПОПОЛНЕНИЕ ============

@app.route('/api/models')
def api_models():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
    return jsonify({'models': MODELS})


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
            'UPDATE users SET balance = balance + %s WHERE id = %s',
            (amount, session['user_id'])
        )
        cnx.commit()
        cur.execute('SELECT balance FROM users WHERE id = %s', (session['user_id'],))
        new_balance = float(cur.fetchone()[0])
        return jsonify({'status': 'ok', 'balance': new_balance})
    except Error as e:
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
        'db_host': DB_CONFIG['host'],
        'db_name': DB_CONFIG['database'],
        'db_user': DB_CONFIG['user'],
    }
    cnx = get_db_connection()
    if not cnx:
        info['db_status'] = '❌ ОШИБКА ПОДКЛЮЧЕНИЯ'
        return jsonify(info)

    try:
        cur = cnx.cursor()
        cur.execute("SHOW TABLES LIKE 'users'")
        info['users_table'] = '✅ есть' if cur.fetchone() else '❌ нет'

        if info['users_table'].startswith('✅'):
            cur.execute("SHOW COLUMNS FROM users LIKE 'balance'")
            info['balance_column'] = '✅ есть' if cur.fetchone() else '❌ нет'

            cur.execute("SELECT COUNT(*) FROM users")
            info['users_count'] = cur.fetchone()[0]

        info['db_status'] = '✅ OK'
        cur.close()
    except Error as e:
        info['db_status'] = f'❌ {e}'
    finally:
        cnx.close()

    return jsonify(info)


# ============ СТАРТ ============
if __name__ == '__main__':
    print("=" * 50)
    print("  NeuroAPI — запуск")
    print("=" * 50)
    print(f"  БД: {DB_CONFIG['user']}@{DB_CONFIG['host']}/{DB_CONFIG['database']}")
    print(f"  Mistral ключ: {'✅ задан' if MISTRAL_API_KEY else '❌ НЕ ЗАДАН'}")
    print("-" * 50)

    ensure_schema()   # ← автосоздание таблицы и колонки balance

    print("-" * 50)
    print("  Сервер: http://127.0.0.1:5000")
    print("  Диагностика: http://127.0.0.1:5000/api/debug")
    print("=" * 50)

    app.run(debug=True, host='0.0.0.0', port=5000)
