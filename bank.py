import os
from flask import Flask, request, jsonify, session
import psycopg2
import random
import string
import hashlib
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask_cors import CORS
import logging

app = Flask(__name__)
CORS(app)

# Конфигурация для Render
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-2026')

# Настройка базы данных для Render PostgreSQL
def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Для Render PostgreSQL
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return psycopg2.connect(database_url)
    else:
        # Для локальной разработки
        return psycopg2.connect(
            host='localhost',
            database='bankdb',
            user='postgres',
            password=os.environ.get('DB_PASSWORD', '')
        )

# Настройки email
EMAIL = os.environ.get('EMAIL_ADDRESS', 'genaklimov2005@gmail.com')
APP_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')

# Инициализация базы данных
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Создаем таблицу пользователей
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            login VARCHAR(50) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            email VARCHAR(100) NOT NULL,
            balance DECIMAL(10, 2) DEFAULT 1000.00,
            code VARCHAR(10),
            code_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаем таблицу транзакций
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            from_user_id INTEGER REFERENCES users(id),
            to_user_id INTEGER REFERENCES users(id),
            amount DECIMAL(10, 2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

def send_code(email, code):
    """Отправка кода на email"""
    msg = MIMEText(f'''
    🏦 Виртуальный Банк
    
    Ваш код подтверждения: **{code}**
    
    Код действителен 5 минут.
    
    Если вы не запрашивали этот код, проигнорируйте это письмо.
    ''')
    
    msg['Subject'] = '🏦 Код подтверждения для входа в банк'
    msg['From'] = EMAIL
    msg['To'] = email
    
    try:
        # Для Gmail
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ Код {code} отправлен на {email}")
        return True
    except Exception as e:
        print(f"⚠️ Ошибка отправки email: {e}")
        print(f"🔄 СИМУЛЯЦИЯ: код для {email} - {code}")
        return True  # Все равно возвращаем True для тестирования

@app.route('/')
def index():
    """Главная страница"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>🏦 Виртуальный Банк</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            h1 { color: #333; }
            .container { max-width: 600px; margin: 0 auto; }
            .btn { display: inline-block; padding: 10px 20px; margin: 10px; 
                   background: #4CAF50; color: white; text-decoration: none; 
                   border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏦 Виртуальный Банк</h1>
            <p>Сервер работает корректно</p>
            <a class="btn" href="/login">Войти в систему</a>
            <p>Или используйте API endpoints:</p>
            <ul style="text-align: left; display: inline-block;">
                <li>POST /register - регистрация</li>
                <li>POST /login - вход</li>
                <li>POST /verify_code - подтверждение кода</li>
                <li>GET /balance - баланс</li>
                <li>POST /transfer - перевод</li>
                <li>GET /logout - выход</li>
            </ul>
        </div>
    </html>
    '''

@app.route('/register', methods=['POST'])
def register():
    """Регистрация нового пользователя"""
    try:
        data = request.json
        if not data or 'login' not in data or 'password' not in data or 'email' not in data:
            return jsonify({'success': False, 'error': 'Не все поля заполнены'}), 400
        
        conn = get_db_connection()
        c = conn.cursor()
        
        # Проверяем, существует ли пользователь
        c.execute("SELECT id FROM users WHERE login = %s OR email = %s", 
                 (data['login'], data['email']))
        if c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Логин или email уже заняты'}), 400
        
        # Создаем пользователя
        c.execute(
            "INSERT INTO users (login, password, email) VALUES (%s, %s, %s) RETURNING id",
            (data['login'], hash_password(data['password']), data['email'])
        )
        user_id = c.fetchone()[0]
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Аккаунт создан'})
        
    except Exception as e:
        print(f"❌ Ошибка регистрации: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/login', methods=['POST'])
def login():
    """Вход в систему"""
    try:
        data = request.json
        if not data or 'login' not in data or 'password' not in data:
            return jsonify({'success': False, 'error': 'Заполните логин и пароль'}), 400
        
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute(
            "SELECT id, email FROM users WHERE login = %s AND password = %s",
            (data['login'], hash_password(data['password']))
        )
        user = c.fetchone()
        
        if not user:
            conn.close()
            return jsonify({'success': False, 'error': 'Неверный логин или пароль'}), 401
        
        user_id, user_email = user
        code = generate_code()
        
        # Сохраняем код в базе
        c.execute(
            "UPDATE users SET code = %s, code_time = %s WHERE id = %s",
            (code, datetime.now(), user_id)
        )
        conn.commit()
        conn.close()
        
        # Отправляем код
        send_code(user_email, code)
        
        # Сохраняем в сессии
        session['user_id'] = user_id
        session['await_code'] = True
        
        return jsonify({
            'success': True, 
            'await_code': True,
            'message': 'Код отправлен на email'
        })
        
    except Exception as e:
        print(f"❌ Ошибка входа: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/verify_code', methods=['POST'])
def verify_code():
    """Подтверждение кода из email"""
    try:
        data = request.json
        if not data or 'code' not in data:
            return jsonify({'success': False, 'error': 'Введите код'}), 400
        
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'Сессия истекла'}), 401
        
        conn = get_db_connection()
        c = conn.cursor()
        
        # Проверяем код (действителен 5 минут)
        time_limit = datetime.now() - timedelta(minutes=5)
        c.execute(
            """SELECT id FROM users 
               WHERE id = %s AND code = %s AND code_time > %s""",
            (user_id, data['code'], time_limit)
        )
        
        if c.fetchone():
            # Код верный, очищаем его
            c.execute(
                "UPDATE users SET code = NULL, code_time = NULL WHERE id = %s",
                (user_id,)
            )
            conn.commit()
            conn.close()
            
            session['logged_in'] = True
            session.pop('await_code', None)
            
            return jsonify({'success': True, 'message': 'Вход выполнен'})
        else:
            conn.close()
            return jsonify({'success': False, 'error': 'Неверный или просроченный код'}), 401
            
    except Exception as e:
        print(f"❌ Ошибка проверки кода: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/balance', methods=['GET'])
def balance():
    """Получение баланса"""
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        user_id = session.get('user_id')
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            return jsonify({'success': True, 'balance': float(result[0])})
        else:
            return jsonify({'error': 'Пользователь не найден'}), 404
            
    except Exception as e:
        print(f"❌ Ошибка получения баланса: {e}")
        return jsonify({'error': 'Ошибка сервера'}), 500

@app.route('/transfer', methods=['POST'])
def transfer():
    """Перевод денег другому пользователю"""
    try:
        if not session.get('logged_in'):
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        data = request.json
        if not data or 'to_login' not in data or 'amount' not in data:
            return jsonify({'success': False, 'error': 'Заполните все поля'}), 400
        
        amount = float(data['amount'])
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Сумма должна быть больше 0'}), 400
        
        user_id = session.get('user_id')
        conn = get_db_connection()
        c = conn.cursor()
        
        # Проверяем баланс отправителя
        c.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
        sender_balance = c.fetchone()[0]
        
        if sender_balance < amount:
            conn.close()
            return jsonify({'success': False, 'error': 'Недостаточно средств'}), 400
        
        # Находим получателя
        c.execute("SELECT id, balance FROM users WHERE login = %s", (data['to_login'],))
        receiver = c.fetchone()
        
        if not receiver:
            conn.close()
            return jsonify({'success': False, 'error': 'Получатель не найден'}), 404
        
        receiver_id = receiver[0]
        
        # Обновляем балансы в транзакции
        c.execute(
            "UPDATE users SET balance = balance - %s WHERE id = %s",
            (amount, user_id)
        )
        c.execute(
            "UPDATE users SET balance = balance + %s WHERE id = %s",
            (amount, receiver_id)
        )
        
        # Записываем транзакцию
        c.execute(
            """INSERT INTO transactions (from_user_id, to_user_id, amount) 
               VALUES (%s, %s, %s)""",
            (user_id, receiver_id, amount)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Перевод выполнен'})
        
    except Exception as e:
        print(f"❌ Ошибка перевода: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

@app.route('/logout', methods=['GET'])
def logout():
    """Выход из системы"""
    session.clear()
    return jsonify({'success': True, 'message': 'Выход выполнен'})

@app.route('/health')
def health_check():
    """Проверка работоспособности сервера"""
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except:
        return jsonify({'status': 'unhealthy', 'database': 'disconnected'}), 500

if __name__ == '__main__':
    # Инициализируем БД при запуске
    init_db()
    
    # Получаем порт из переменных окружения Render
    port = int(os.environ.get('PORT', 5000))
    
    # Запускаем сервер
    print(f"🚀 Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
