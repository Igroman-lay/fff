import os
import sqlite3
from flask import Flask, request, jsonify, session
import random
import string
import hashlib
from datetime import datetime, timedelta
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'virtual-bank-secret-2026')

# Настройки для Gmail
GMAIL_USER = "genaklimov2005@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get(' ikkq tpvd wfot tqnp', '')  # Пароль приложения

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Проверяем конфигурацию
if not GMAIL_APP_PASSWORD:
    logger.warning("⚠️  GMAIL_APP_PASSWORD не настроен. Email отправляться не будут.")
else:
    logger.info("✅ Email настроен для отправки")

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

# ========== ОТПРАВКА EMAIL ==========

def send_email_code(to_email, code):
    """Отправляет код подтверждения на email"""
    
    if not GMAIL_APP_PASSWORD:
        logger.warning(f"⚠️  Пропускаем отправку email (пароль не настроен). Код для {to_email}: {code}")
        return False
    
    try:
        # Создаем email сообщение
        msg = MIMEMultipart('alternative')
        msg['Subject'] = '🏦 Код подтверждения Виртуального Банка'
        msg['From'] = GMAIL_USER
        msg['To'] = to_email
        
        # Текстовый вариант
        text = f"""
        Виртуальный Банк
        
        Ваш код подтверждения: {code}
        
        Код действителен 5 минут.
        
        Если вы не запрашивали вход, проигнорируйте это письмо.
        """
        
        # HTML вариант
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <h1 style="color: #2c3e50;">🏦 Виртуальный Банк</h1>
                <p>Здравствуйте!</p>
                <p>Для входа в ваш аккаунт используйте следующий код подтверждения:</p>
                
                <div style="background-color: #f8f9fa; padding: 20px; text-align: center; 
                            margin: 20px 0; border-radius: 5px; border: 2px dashed #3498db;">
                    <span style="font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #2c3e50;">
                        {code}
                    </span>
                </div>
                
                <p><strong>⚠️ Внимание:</strong> Код действителен в течение <strong>5 минут</strong>.</p>
                
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;">
                        <strong>Безопасность:</strong> Никогда не сообщайте этот код третьим лицам.
                    </p>
                </div>
                
                <p>Если вы не запрашивали вход в аккаунт, просто проигнорируйте это письмо.</p>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                
                <p style="font-size: 12px; color: #888;">
                    Это автоматическое сообщение от системы Виртуального Банка.<br>
                    Пожалуйста, не отвечайте на это письмо.
                </p>
            </div>
        </body>
        </html>
        """
        
        # Прикрепляем оба варианта
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Отправляем через SMTP Gmail
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"✅ Email с кодом отправлен на {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки email на {to_email}: {str(e)}")
        return False

# ========== API РОУТЫ ==========

@app.route('/')
def home():
    try:
        return app.send_static_file('index.html')
    except:
        return '''
        <html>
        <body style="font-family: Arial; padding: 20px;">
            <h1>🏦 Виртуальный Банк</h1>
            <p>✅ Сервер работает</p>
            <p>📧 Статус отправки email: <strong>''' + ('АКТИВЕН' if GMAIL_APP_PASSWORD else 'НЕ НАСТРОЕН') + '''</strong></p>
            <a href="/test_email">Проверить отправку email</a>
        </body>
        </html>
        '''

@app.route('/test_email')
def test_email():
    """Страница для тестирования отправки email"""
    test_code = generate_code()
    test_email = "genaklimov2005@gmail.com"
    
    email_sent = send_email_code(test_email, test_code)
    
    return f'''
    <html>
    <body style="font-family: Arial; padding: 20px;">
        <h1>📧 Тест отправки email</h1>
        <div style="background: {'#d4edda' if email_sent else '#f8d7da'}; 
                    padding: 20px; border-radius: 5px; margin: 20px 0;">
            <h3>{'✅ Email отправлен!' if email_sent else '❌ Ошибка отправки'}</h3>
            <p><strong>Код:</strong> {test_code}</p>
            <p><strong>Получатель:</strong> {test_email}</p>
            <p><strong>Статус пароля:</strong> {'Настроен' if GMAIL_APP_PASSWORD else 'Не настроен'}</p>
        </div>
        <a href="/">На главную</a>
    </body>
    </html>
    '''

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
        
        # Сохраняем код в базе
        cursor.execute(
            'UPDATE users SET code = ?, code_time = ? WHERE id = ?',
            (code, datetime.now().isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        
        # Отправляем email с кодом
        email_sent = send_email_code(user_email, code)
        
        # Сохраняем сессию
        session['user_id'] = user_id
        session['await_code'] = True
        
        if email_sent:
            return jsonify({
                'success': True,
                'await_code': True,
                'message': '✅ Код подтверждения отправлен на ваш email!'
            })
        else:
            # Если email не отправился, показываем код в интерфейсе
            return jsonify({
                'success': True,
                'await_code': True,
                'demo_code': code,  # Для отладки
                'message': f'⚠️ Email не отправлен. Ваш код: {code}'
            })
        
    except Exception as e:
        logger.error(f"Ошибка входа: {e}")
        return jsonify({'success': False, 'error': 'Ошибка сервера'}), 500

# ... остальные функции (register, verify_code, balance, transfer, logout) 
# остаются такими же как в предыдущем коде ...

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Виртуальный Банк запущен на порту {port}")
    logger.info(f"📧 Отправка email: {'ВКЛЮЧЕНА' if GMAIL_APP_PASSWORD else 'ВЫКЛЮЧЕНА'}")
    app.run(host='0.0.0.0', port=port, debug=False)
