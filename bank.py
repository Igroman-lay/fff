from flask import Flask, request, jsonify, render_template, session
import sqlite3
import random
import string
import hashlib
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_2026'
app.static_folder = 'static'
app.template_folder = 'templates'

EMAIL = 'genaklimov2005@gmail.com'
APP_PASSWORD = 'zmxmndpmmiawfbsp'  # ← ЗАМЕНИТЕ на реальный!

def init_db():
    conn = sqlite3.connect('bank.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, login TEXT UNIQUE, password TEXT, 
                  email TEXT, balance REAL DEFAULT 1000.0, code TEXT, code_time TEXT)''')
    conn.commit()
    conn.close()

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_code():
    return ''.join(random.choices(string.digits, k=6))

def send_code(email, code):
    msg = MIMEText(f'🚀 Код банка: {code}\n\nДействует 5 минут.')
    msg['Subject'] = '🏦 Банк: код входа'
    msg['From'] = EMAIL
    msg['To'] = email
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL, APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"✅ Отправлено на {email}: {code}")
    except Exception as e:
        print(f"❌ Ошибка email: {e}")
        print(f"🔄 СИМУЛЯЦИЯ: на {email} код {code}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    conn = sqlite3.connect('bank.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (login, password, email) VALUES (?, ?, ?)", 
                 (data['login'], hash_password(data['password']), data['email']))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'success': False, 'error': 'Логин занят'})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = sqlite3.connect('bank.db')
    c = conn.cursor()
    c.execute("SELECT id, email FROM users WHERE login=? AND password=?", 
             (data['login'], hash_password(data['password'])))
    user = c.fetchone()
    conn.close()
    
    if user:
        code = generate_code()
        conn = sqlite3.connect('bank.db')
        c = conn.cursor()
        c.execute("UPDATE users SET code=?, code_time=? WHERE id=?", 
                 (code, datetime.now().isoformat(), user[0]))
        conn.commit()
        conn.close()
        send_code(user[1], code)
        session['user_id'] = user[0]
        session['await_code'] = True
        return jsonify({'success': True, 'await_code': True})
    return jsonify({'success': False, 'error': 'Неверный логин/пароль'})

@app.route('/verify_code', methods=['POST'])
def verify_code():
    data = request.json
    conn = sqlite3.connect('bank.db')
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE id=? AND code=? AND code_time > datetime('now', '-5 minutes')",
              (session.get('user_id'), data['code']))
    user = c.fetchone()
    conn.close()
    
    if user:
        session['logged_in'] = True
        session.pop('await_code', None)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': 'Неверный/просроченный код'})

@app.route('/balance')
def balance():
    if not session.get('logged_in'):
        return jsonify({'error': 'Авторизуйтесь'}), 401
    conn = sqlite3.connect('bank.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE id=?", (session['user_id'],))
    bal = c.fetchone()[0]
    conn.close()
    return jsonify({'balance': bal})

@app.route('/transfer', methods=['POST'])
def transfer():
    if not session.get('logged_in'):
        return jsonify({'error': 'Авторизуйтесь'}), 401
    data = request.json
    amount = float(data['amount'])
    conn = sqlite3.connect('bank.db')
    c = conn.cursor()
    c.execute("SELECT id, balance FROM users WHERE login=?", (data['to_login'],))
    target = c.fetchone()
    if not target or target[1] < amount:
        conn.close()
        return jsonify({'success': False, 'error': 'Получатель не найден или мало средств'})
    
    c.execute("UPDATE users SET balance = balance - ? WHERE id=?", (amount, session['user_id']))
    c.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, target[0]))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    session.clear()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
