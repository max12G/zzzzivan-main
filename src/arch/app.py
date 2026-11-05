from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import json
import os
import threading
import traceback
from pathlib import Path

import requests
from dotenv import load_dotenv
from llama_cpp import Llama

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'tvoja_super_sekretnaja_kluch_fraza_2026')

MODEL_DIR = Path(__file__).resolve().parent / 'models'
MODEL_FILENAME = 'Qwen3-1.7B-Q4_K_M.gguf'
MODEL_PATH = MODEL_DIR / MODEL_FILENAME
MODEL_URL = (
    'https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/'
    f'{MODEL_FILENAME}?download=true'
)
_llm = None
_llm_lock = threading.Lock()

DB_PATH = os.environ.get(
    'LOCAL_DB_PATH',
    os.path.join(os.path.dirname(__file__), 'data', 'app.db'),
)

def ensure_model() -> Path:
    if MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 0:
        return MODEL_PATH

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    partial_path = MODEL_PATH.with_suffix('.gguf.part')
    print(f'[MODEL] Скачивание {MODEL_FILENAME} с Hugging Face…(я сам ждал примерно минуты 2-3)')
    try:
        with requests.get(MODEL_URL, stream=True, timeout=(15, 180)) as response:
            response.raise_for_status()
            with partial_path.open('wb') as model_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        model_file.write(chunk)
        if partial_path.stat().st_size == 0:
            raise RuntimeError('Hugging Face вернул пустой файл модели')
        partial_path.replace(MODEL_PATH)
    except (OSError, requests.RequestException) as error:
        if partial_path.exists():
            partial_path.unlink()
        raise RuntimeError(f'Не удалось скачать модель: {error}') from error

    print(f'[MODEL] Модель сохранена: {MODEL_PATH}')
    return MODEL_PATH


def get_llm() -> Llama:
    global _llm
    with _llm_lock:
        if _llm is None:
            _llm = Llama(
                model_path=str(ensure_model()),
                n_ctx=4096,
                n_threads=0,
                verbose=False,
            )
        return _llm


def get_db_connection():
    try:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        cnx = sqlite3.connect(DB_PATH)
        cnx.row_factory = sqlite3.Row
        return cnx
    except sqlite3.Error as e:
        print(f"[DB] Ошибка подключения: {e}")
        return None


def ensure_schema():
    cnx = get_db_connection()
    if not cnx:
        print("[DB] Не удалось подключиться — БД не настроена или недоступна")
        return False

    cur = cnx.cursor()
    try:
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

        columns = {row['name'] for row in cur.execute("PRAGMA table_info(users)")}
        if 'balance' not in columns:
            print("[DB] Добавляю колонку balance…")
            cur.execute("ALTER TABLE users ADD COLUMN balance REAL NOT NULL DEFAULT 0")

        cnx.commit()
        print("[DB] Схема готова")
        return True
    except sqlite3.Error as e:
        print(f"[DB] Ошибка при создании схемы: {e}")
        traceback.print_exc()
        return False
    finally:
        cur.close(); cnx.close()



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


def deduct_tokens(user_id: int, token_count: int) -> float:
    """Charge 0.1 RUB per generated token and return the new balance."""
    cost = token_count / 10
    cnx = get_db_connection()
    if not cnx:
        raise RuntimeError('Ошибка подключения к БД')

    try:
        cur = cnx.cursor()
        cur.execute(
            'UPDATE users SET balance = balance - ? '
            'WHERE id = ? AND balance >= ?',
            (cost, user_id, cost),
        )
        if cur.rowcount != 1:
            cnx.rollback()
            raise RuntimeError('Недостаточно средств для оплаты ответа')
        cnx.commit()
        row = cur.execute(
            'SELECT balance FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        return float(row[0]) if row else 0.0
    except sqlite3.Error as error:
        cnx.rollback()
        raise RuntimeError(f'Ошибка списания баланса: {error}') from error
    finally:
        cnx.close()


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template(
        'dashboard.html',
        username=session.get('username'),
        email=session.get('email'),
        balance=get_balance(),
    )


@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('profile.html', username=session.get('username'))


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


@app.route('/api/chat', methods=['POST'])
def chat():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401

    data = request.get_json(silent=True) or {}
    messages = data.get('messages', [])

    if not isinstance(messages, list) or not messages:
        return jsonify({'error': 'Пустой запрос'}), 400

    balance = get_balance()
    max_tokens = min(1024, int(balance * 10))
    if max_tokens < 1:
        return jsonify({'error': 'Недостаточно средств. Пополните баланс.'}), 402

    user_id = session['user_id']
    try:
        llm = get_llm()
    except (OSError, RuntimeError, ValueError) as error:
        return jsonify({'error': str(error)}), 500

    def stream():
        try:
            full_text = ''
            for chunk in llm.create_chat_completion(
                messages=messages,
                stream=True,
                max_tokens=max_tokens,
                temperature=0.7,
            ):
                delta = (chunk.get('choices') or [{}])[0].get('delta', {})
                content = delta.get('content')
                if content:
                    full_text += content
                    yield f"data: {json.dumps({'delta': content})}\n\n"
            token_count = len(llm.tokenize(full_text.encode('utf-8'), add_bos=False))
            new_balance = deduct_tokens(user_id, token_count)
            yield f"data: {json.dumps({'balance': new_balance, 'tokens': token_count})}\n\n"
            yield "data: [DONE]\n\n"
        except (RuntimeError, ValueError, OSError) as error:
            yield f"data: {json.dumps({'error': f'Ошибка генерации: {error}'})}\n\n"
            yield "data: [DONE]\n\n"

    return Response(stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
    })


if __name__ == '__main__':
    print("=" * 50)
    print("  NeuroAPI — запуск")
    print("=" * 50)
    print(f"  Локальная БД: {DB_PATH}")
    print(f"  Локальная модель: {MODEL_FILENAME}")
    print("-" * 50)

    ensure_schema()

    print("-" * 50)
    print("  Сервер: http://127.0.0.1:5000")
    print("-" * 50)

    app.run(debug=True, host='0.0.0.0', port=5000)
