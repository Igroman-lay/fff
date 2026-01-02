import os
import sqlite3
from flask import Flask, request, jsonify, session
import random
import string
import hashlib
from datetime import datetime, timedelta
import logging

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'virtual-bank-secret-2026')

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========

def get_db():
    conn = sqlite3.connect('bank.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL,
            balance REAL DEFAULT 1000.0,
            code TEXT,
            code_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных готова")

init_db()

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

# ========== API РОУТЫ ==========

@app.route('/')
def home():
    return '''
    <html>
    <body style="font-family: Arial; padding: 20px;">
        <h1>🏦 Виртуальный Банк</h1>
        <p>✅ Сервер работает!</p>
        <p><a href="/health">Проверить API</a></p>
        <p><a href="/static/index.html">Перейти к банку</a></p>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    return jsonify({
        'status': 'online',
        'service': 'virtual-bank',
        'timestamp': datetime.now().isoformat(),
        'message': '✅ Сервер работает корректно'
    })

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        login = data.get('login', '').strip()
        password = data.get('password', '').strip()
        email = data.get('email', '').strip()
        
        if len(login) < 3:
            return jsonify({'success': False, 'error': 'Логин мин. 3 символа'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM users WHERE login = ?', (login,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Логин уже занят'}), 400
        
        cursor.execute(
            'INSERT INTO users (login, password, email) VALUES (?, ?, ?)',
            (login, hash_password(password), email)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Аккаунт создан!'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        login = data.get('login', '').strip()
        password = data.get('password', '').strip()
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT id, email FROM users WHERE login = ? AND password = ?',
            (login, hash_password(password))
        )
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'error': 'Неверный логин или пароль'}), 401
        
        user_id, user_email = user
        code = generate_code()
        
        cursor.execute(
            'UPDATE users SET code = ?, code_time = ? WHERE id = ?',
            (code, datetime.now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        
        session['user_id'] = user_id
        session['await_code'] = True
        
        # Показываем код в интерфейсе (без email)
        return jsonify({
            'success': True,
            'await_code': True,
            'demo_code': code,
            'message': f'Ваш код: {code} (демо-режим)'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/verify_code', methods=['POST'])
def verify_code():
    try:
        data = request.get_json()
        code = data.get('code', '').strip()
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'Сессия истекла'}), 401
        
        conn = get_db()
        cursor = conn.cursor()
        
        time_limit = (datetime.now() - timedelta(minutes=5)).isoformat()
        cursor.execute(
            'SELECT id FROM users WHERE id = ? AND code = ? AND code_time > ?',
            (user_id, code, time_limit)
        )
        
        if cursor.fetchone():
            cursor.execute('UPDATE users SET code = NULL, code_time = NULL WHERE id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            session['logged_in'] = True
            session.pop('await_code', None)
            
            return jsonify({'success': True, 'message': '✅ Вход выполнен!'})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Неверный код'}), 401
            
    except Exception as e:
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/balance', methods=['GET'])
def get_balance():
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        user_id = session['user_id']
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return jsonify({'success': True, 'balance': float(result[0])})
        else:
            return jsonify({'error': 'Пользователь не найден'}), 404
            
    except Exception as e:
        return jsonify({'error': 'Ошибка сервера'}), 500

@app.route('/transfer', methods=['POST'])
def transfer():
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        data = request.get_json()
        to_login = data['to_login'].strip()
        amount = float(data['amount'])
        
        user_id = session['user_id']
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
        sender = cursor.fetchone()
        
        if not sender or float(sender[0]) < amount:
            conn.close()
            return jsonify({'success': False, 'error': 'Недостаточно средств'}), 400
        
        cursor.execute('SELECT id FROM users WHERE login = ?', (to_login,))
        receiver = cursor.fetchone()
        
        if not receiver:
            conn.close()
            return jsonify({'success': False, 'error': 'Получатель не найден'}), 404
        
        receiver_id = receiver[0]
        
        cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user_id))
        cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, receiver_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': f'✅ Перевод {amount}₽ выполнен!'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Выход выполнен'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
