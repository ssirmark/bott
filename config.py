# ============================================================
#  config.py - الإعدادات
# ============================================================
import os

BOT_TOKEN = os.environ.get('BOT_TOKEN', '8847400367:AAHNhfgMGGuo3eCIiNjMD8u4EjnL7OkNLls')
BASE_URL = os.environ.get('BASE_URL', 'https://instagrm.up.railway.app')
SECRET_KEY = os.environ.get('SECRET_KEY', 'my-super-secret-key')
DB_PATH = 'data.db'