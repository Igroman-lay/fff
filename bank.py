import os
import sqlite3
from flask import Flask, request, jsonify, session, send_from_directory
import random
import string
import hashlib
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Настройки email (замени на свои или оставь пустым для демо)
GMAIL_USER = "genaklimov2005@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get('GMAIL_PASSWORD', '')  # Пароль приложения

def send_email_code(to_email, code):
    """Отправляет код на email"""
    if not GMAIL_APP_PASSWORD:
        print(f"📧 Демо-режим: код для {to_email} - {code}")
        return False  # В демо-режиме не отправляем
    
    try:
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = to_email
        msg['Subject'] = '🏦 Код подтверждения Виртуального Банка'
        
        html = f"""
        <html>
        <body>
            <h2>🏦 Виртуальный Банк</h2>
            <p>Ваш код подтверждения: <strong>{code}</strong></p>
            <p>Код действителен 5 минут.</p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(html, 'html'))
        
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Email отправлен на {to_email}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка отправки email: {e}")
        return False
app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'virtual-bank-secret-2026')

# Разрешаем CORS вручную
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

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
    """Перенаправляем сразу на страницу банка"""
    try:
        # Пробуем отдать index.html как главную страницу
        return app.send_static_file('index.html')
    except:
        # Если файл не найден, показываем простую страницу
        return '''
        <html>
        <head>
            <meta http-equiv="refresh" content="0; url=/static/index.html">
        </head>
        <body>
            <p>Перенаправление на банк...</p>
            <script>window.location.href = "/static/index.html";</script>
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
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
        login = data.get('login', '').strip()
        password = data.get('password', '').strip()
        email = data.get('email', '').strip()
        
        if not login or not password or not email:
            return jsonify({'success': False, 'error': 'Все поля обязательны'}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        try:
            c.execute(
                "INSERT INTO users (login, password, email) VALUES (?, ?, ?)",
                (login, hash_password(password), email)
            )
            conn.commit()
            return jsonify({'success': True, 'message': 'Аккаунт создан!'})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'error': 'Логин уже занят'})
        finally:
            conn.close()
            
    except Exception as e:
        print(f"Ошибка регистрации: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
        login = data.get('login', '').strip()
        password = data.get('password', '').strip()
        
        if not login or not password:
            return jsonify({'success': False, 'error': 'Введите логин и пароль'}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        c.execute(
            "SELECT id, email FROM users WHERE login=? AND password=?",
            (login, hash_password(password))
        )
        user = c.fetchone()
        
        if user:
            user_id, user_email = user
            code = generate_code()
            c.execute(
                "UPDATE users SET code=?, code_time=? WHERE id=?",
                (code, datetime.now().isoformat(), user_id)
            )
            conn.commit()
            conn.close()
            
            session['user_id'] = user_id
            session['await_code'] = True
            
            return jsonify({
                'success': True,
                'await_code': True,
                'demo_code': code,
                'message': f'Ваш код для входа: {code}'
            })
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Неверный логин или пароль'})
            
    except Exception as e:
        print(f"Ошибка входа: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/verify_code', methods=['POST'])
def verify_code():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
        code = data.get('code', '').strip()
        
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
            return jsonify({'success': True, 'message': 'Вход выполнен!'})
        else:
            return jsonify({'success': False, 'error': 'Неверный или просроченный код'})
            
    except Exception as e:
        print(f"Ошибка проверки кода: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/balance', methods=['GET'])
def balance():
    if not session.get('logged_in'):
        return jsonify({'error': 'Авторизуйтесь'}), 401
    
    user_id = session.get('user_id')
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT balance FROM users WHERE id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        return jsonify({'success': True, 'balance': float(result[0])})
    else:
        return jsonify({'error': 'Пользователь не найден'}), 404

@app.route('/transfer', methods=['POST'])
def transfer():
    if not session.get('logged_in'):
        return jsonify({'error': 'Авторизуйтесь'}), 401
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Нет данных'}), 400
        
        to_login = data.get('to_login', '').strip()
        amount = float(data.get('amount', 0))
        
        if not to_login or amount <= 0:
            return jsonify({'success': False, 'error': 'Некорректные данные'}), 400
        
        user_id = session.get('user_id')
        conn = get_db()
        c = conn.cursor()
        
        # Проверяем баланс
        c.execute("SELECT balance FROM users WHERE id=?", (user_id,))
        sender = c.fetchone()
        
        if not sender or float(sender[0]) < amount:
            conn.close()
            return jsonify({'success': False, 'error': 'Недостаточно средств'})
        
        # Ищем получателя
        c.execute("SELECT id FROM users WHERE login=?", (to_login,))
        receiver = c.fetchone()
        
        if not receiver:
            conn.close()
            return jsonify({'success': False, 'error': 'Получатель не найден'})
        
        # Выполняем перевод
        c.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, user_id))
        c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, receiver[0]))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': f'Перевод {amount}₽ выполнен!'})
        
    except Exception as e:
        print(f"Ошибка перевода: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/logout', methods=['GET'])
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Выход выполнен'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Сервер запущен на порту {port}")
    print(f"📱 Открой: http://localhost:{port}/static/index.html")
    app.run(host='0.0.0.0', port=port, debug=False)
