import os
import sqlite3
from flask import Flask, request, jsonify, session, send_from_directory
import random
import string
import hashlib
from datetime import datetime, timedelta
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)  # Разрешаем запросы от фронтенда

app.secret_key = os.environ.get('SECRET_KEY', 'virtual-bank-secret-2026')

# ========== БАЗА ДАННЫХ ==========

def get_db():
    conn = sqlite3.connect('bank.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL,
            balance REAL DEFAULT 1000.0,
            code TEXT,
            code_time TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ База данных готова")

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

# ========== РОУТЫ ==========

@app.route('/')
def home():
    return '''
    <html>
    <body style="font-family: Arial; padding: 20px;">
        <h1>🏦 Виртуальный Банк</h1>
        <p>✅ Сервер работает!</p>
        <p><a href="/static/index.html">Перейти к банку</a></p>
        <p><a href="/health">Проверить API</a></p>
        <p>Доступные endpoints:</p>
        <ul>
            <li>POST /register - регистрация</li>
            <li>POST /login - вход</li>
            <li>POST /verify_code - проверка кода</li>
            <li>GET /balance - баланс</li>
            <li>POST /transfer - перевод</li>
        </ul>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    return jsonify({
        'status': 'online',
        'service': 'virtual-bank',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        login = data['login'].strip()
        password = data['password'].strip()
        email = data['email'].strip()
        
        conn = get_db()
        c = conn.cursor()
        
        try:
            c.execute(
                "INSERT INTO users (login, password, email) VALUES (?, ?, ?)",
                (login, hash_password(password), email)
            )
            conn.commit()
            return jsonify({'success': True})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Логин занят'})
        finally:
            conn.close()
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        login = data['login'].strip()
        password = data['password'].strip()
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute(
            "SELECT id, email FROM users WHERE login=? AND password=?",
            (login, hash_password(password))
        )
        user = c.fetchone()
        
        if user:
            code = generate_code()
            c.execute(
                "UPDATE users SET code=?, code_time=? WHERE id=?",
                (code, datetime.now().isoformat(), user[0])
            )
            conn.commit()
            conn.close()
            
            session['user_id'] = user[0]
            session['await_code'] = True
            
            return jsonify({
                'success': True,
                'await_code': True,
                'demo_code': code,
                'message': f'Код для входа: {code}'
            })
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Неверный логин/пароль'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/verify_code', methods=['POST'])
def verify_code():
    try:
        data = request.json
        code = data['code'].strip()
        
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Сессия истекла'}), 401
        
        conn = get_db()
        c = conn.cursor()
        
        time_limit = (datetime.now() - timedelta(minutes=5)).isoformat()
        c.execute(
            "SELECT id FROM users WHERE id=? AND code=? AND code_time > ?",
            (user_id, code, time_limit)
        )
        
        if c.fetchone():
            session['logged_in'] = True
            session.pop('await_code', None)
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Неверный код'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/balance', methods=['GET'])
def balance():
    if not session.get('logged_in'):
        return jsonify({'error': 'Авторизуйтесь'}), 401
    
    user_id = session.get('user_id')
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT balance FROM users WHERE id=?", (user_id,))
    bal = c.fetchone()[0]
    conn.close()
    
    return jsonify({'balance': bal})

@app.route('/transfer', methods=['POST'])
def transfer():
    if not session.get('logged_in'):
        return jsonify({'error': 'Авторизуйтесь'}), 401
    
    data = request.json
    amount = float(data['amount'])
    
    conn = get_db()
    c = conn.cursor()
    
    # Отправитель
    c.execute("SELECT id, balance FROM users WHERE id=?", (session['user_id'],))
    sender = c.fetchone()
    
    # Получатель
    c.execute("SELECT id FROM users WHERE login=?", (data['to_login'],))
    receiver = c.fetchone()
    
    if not receiver or sender[1] < amount:
        conn.close()
        return jsonify({'success': False, 'error': 'Ошибка перевода'})
    
    c.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, sender[0]))
    c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, receiver[0]))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Сервер запущен: http://localhost:{port}")
    print(f"📱 Фронтенд: http://localhost:{port}/static/index.html")
    app.run(host='0.0.0.0', port=port, debug=False)
