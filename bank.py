import os
import sqlite3
from flask import Flask, request, jsonify, session, send_from_directory
import random
import string
import hashlib
from datetime import datetime, timedelta
import logging
import json

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-12345-change-me')

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Путь к базе данных
DB_PATH = os.environ.get('DATABASE_URL', 'bank.db').replace('postgresql://', '').replace('postgres://', '')

def get_db_connection():
    """Получение соединения с SQLite"""
    conn = sqlite3.connect('bank.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Инициализация базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей
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
    
    # Таблица транзакций
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER,
            to_user_id INTEGER,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

def hash_password(password):
    """Хеширование пароля"""
    return hashlib.sha256(password.encode()).hexdigest()

def generate_code():
    """Генерация 6-значного кода"""
    return ''.join(random.choices(string.digits, k=6))

# Инициализируем БД
init_db()

# ========== РОУТЫ ==========

@app.route('/')
def index():
    """Главная страница"""
    try:
        return app.send_static_file('index.html')
    except:
        return '''
        <html>
        <head><title>Virtual Bank</title></head>
        <body>
            <h1>🏦 Виртуальный Банк</h1>
            <p>Сервер работает. Используйте API:</p>
            <ul>
                <li>POST /register - регистрация</li>
                <li>POST /login - вход</li>
                <li>POST /verify_code - подтверждение кода</li>
                <li>GET /balance - баланс</li>
                <li>POST /transfer - перевод</li>
            </ul>
        </body>
        </html>
        '''

@app.route('/health')
def health():
    """Health check для Render"""
    try:
        conn = get_db_connection()
        conn.execute('SELECT 1')
        conn.close()
        return jsonify({
            'status': 'ok',
            'database': 'connected',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/register', methods=['POST'])
def register():
    """Регистрация"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
        login = data.get('login', '').strip()
        password = data.get('password', '').strip()
        email = data.get('email', '').strip()
        
        if not login or not password or not email:
            return jsonify({'success': False, 'error': 'Все поля обязательны'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверка существующего пользователя
        cursor.execute('SELECT id FROM users WHERE login = ? OR email = ?', (login, email))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Логин или email уже заняты'}), 400
        
        # Создание пользователя
        cursor.execute(
            'INSERT INTO users (login, password, email) VALUES (?, ?, ?)',
            (login, hash_password(password), email)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Аккаунт создан'})
        
    except Exception as e:
        logger.error(f"Register error: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/login', methods=['POST'])
def login():
    """Вход"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
        login = data.get('login', '').strip()
        password = data.get('password', '').strip()
        
        if not login or not password:
            return jsonify({'success': False, 'error': 'Введите логин и пароль'}), 400
        
        conn = get_db_connection()
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
        
        # Сохраняем код
        cursor.execute(
            'UPDATE users SET code = ?, code_time = ? WHERE id = ?',
            (code, datetime.now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        
        # Сохраняем в сессии
        session['user_id'] = user_id
        session['await_code'] = True
        
        # Для демо показываем код
        return jsonify({
            'success': True,
            'await_code': True,
            'demo_code': code,
            'message': f'Для демо: код {code} (в реальном приложении отправлялся бы на email)'
        })
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/verify_code', methods=['POST'])
def verify_code():
    """Подтверждение кода"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
        code = data.get('code', '').strip()
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'Сессия истекла'}), 401
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем код (5 минут)
        time_limit = (datetime.now() - timedelta(minutes=5)).isoformat()
        cursor.execute(
            'SELECT id FROM users WHERE id = ? AND code = ? AND code_time > ?',
            (user_id, code, time_limit)
        )
        
        if cursor.fetchone():
            # Код верный
            cursor.execute('UPDATE users SET code = NULL, code_time = NULL WHERE id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            session['logged_in'] = True
            session.pop('await_code', None)
            
            return jsonify({'success': True, 'message': 'Вход выполнен'})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Неверный или просроченный код'}), 401
            
    except Exception as e:
        logger.error(f"Verify code error: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/balance', methods=['GET'])
def balance():
    """Получение баланса"""
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        user_id = session.get('user_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return jsonify({'success': True, 'balance': float(result[0])})
        else:
            return jsonify({'error': 'Пользователь не найден'}), 404
            
    except Exception as e:
        logger.error(f"Balance error: {e}")
        return jsonify({'error': 'Ошибка сервера'}), 500

@app.route('/transfer', methods=['POST'])
def transfer():
    """Перевод"""
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
        to_login = data.get('to_login', '').strip()
        amount = float(data.get('amount', 0))
        
        if not to_login or amount <= 0:
            return jsonify({'success': False, 'error': 'Некорректные данные'}), 400
        
        user_id = session.get('user_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Проверяем баланс отправителя
        cursor.execute('SELECT balance FROM users WHERE id = ?', (user_id,))
        sender_balance = cursor.fetchone()
        
        if not sender_balance or float(sender_balance[0]) < amount:
            conn.close()
            return jsonify({'success': False, 'error': 'Недостаточно средств'}), 400
        
        # Находим получателя
        cursor.execute('SELECT id FROM users WHERE login = ?', (to_login,))
        receiver = cursor.fetchone()
        
        if not receiver:
            conn.close()
            return jsonify({'success': False, 'error': 'Получатель не найден'}), 404
        
        receiver_id = receiver[0]
        
        # Выполняем перевод
        cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (amount, user_id))
        cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (amount, receiver_id))
        
        cursor.execute(
            'INSERT INTO transactions (from_user_id, to_user_id, amount) VALUES (?, ?, ?)',
            (user_id, receiver_id, amount)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Перевод выполнен'})
        
    except Exception as e:
        logger.error(f"Transfer error: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/logout', methods=['GET'])
def logout():
    """Выход"""
    session.clear()
    return jsonify({'success': True, 'message': 'Выход выполнен'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
