
import os
import re
import requests
from flask import Flask, request, abort

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

SITE_URL = "https://castudyclub-dotcom.github.io/ca-study-hub/"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

RESPONSES = {
    "/subjects": "📚 CA Foundation Subjects\n\n1. Accounts\n2. Business Laws\n3. Quantitative Aptitude\n4. Business Economics",
    "/accounts": "📘 Accounts",
    "/law": "⚖️ Business Laws",
    "/qa": "📊 Quantitative Aptitude",
    "/economics": "📈 Business Economics",
    "/lectures": "🎥 Open Study Hub to explore lectures.",
    "/notes": "📝 Study notes coming soon.",
    "/progress": "📈 Learning progress coming soon.",
    "/continue": "▶️ Continue learning in Study Hub.",
    "/help": "Use /subjects, /accounts, /law, /qa, /economics, /lectures or /notes."
}

def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard

    r = requests.post(
        f"{API_URL}/sendMessage",
        json=data,
        timeout=20
    )
    r.raise_for_status()

def save_lecture(channel_post):
    caption = channel_post.get("caption", "")
    fields = {}

    for line in caption.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip().upper()] = value.strip()

    subject = fields.get("SUBJECT")
    chapter = fields.get("CHAPTER")
    lecture_text = fields.get("LECTURE", "")

    match = re.search(r"\d+", lecture_text)

    if not subject or not chapter or not match:
        raise ValueError(
            "Caption format incorrect. Use SUBJECT, CHAPTER and LECTURE."
        )

    lecture_number = int(match.group())

    media = channel_post.get("video") or channel_post.get("document")

    if not media:
        raise ValueError("No video or document found.")

    payload = {
        "subject": subject.upper(),
        "chapter_name": chapter,
        "lecture_number": lecture_number,
        "channel_id": channel_post["chat"]["id"],
        "message_id": channel_post["message_id"],
        "caption": caption
    }

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/lectures?on_conflict=channel_id,message_id",
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation"
        },
        json=payload,
        timeout=20
    )

    response.raise_for_status()
    return payload

@app.route("/")
def home():
    return "CA Study Hub Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    if not WEBHOOK_SECRET or request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    ) != WEBHOOK_SECRET:
        abort(403)

    update = request.get_json(silent=True) or {}

    # Handle new channel uploads
    channel_post = update.get("channel_post")

    if channel_post:
        media = channel_post.get("video") or channel_post.get("document")

        if media:
            try:
                saved = save_lecture(channel_post)

                if ADMIN_CHAT_ID:
                    send_message(
                        ADMIN_CHAT_ID,
                        "✅ LECTURE SAVED TO DATABASE!\n\n"
                        f"📚 Subject: {saved['subject']}\n"
                        f"📖 Chapter: {saved['chapter_name']}\n"
                        f"🎥 Lecture: {saved['lecture_number']}\n"
                        f"🆔 Message ID: {saved['message_id']}"
                    )

            except Exception as e:
                app.logger.exception("Lecture save failed")

                if ADMIN_CHAT_ID:
                    try:
                        send_message(
                            ADMIN_CHAT_ID,
                            f"❌ Lecture database save failed:\n{str(e)[:1000]}"
                        )
                    except Exception:
                        app.logger.exception("Admin notification failed")

        return "OK"

    # Handle normal Telegram messages
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return "OK"

    if text == "/id":
        send_message(chat_id, f"Your Telegram Chat ID is:\n{chat_id}")
        return "OK"

    if not text:
        return "OK"

    command = text.split()[0].split("@")[0].lower()

    if command == "/start":
        keyboard = {
            "inline_keyboard": [[
                {
                    "text": "🚀 Open Study Hub",
                    "web_app": {"url": SITE_URL}
                }
            ]]
        }

        send_message(
            chat_id,
            "👋 Welcome to CA Study Hub!\n\n"
            "Your CA Foundation preparation starts here.\n\n"
            "📚 Accounts\n⚖️ Business Laws\n"
            "📊 Quantitative Aptitude\n📈 Business Economics\n\n"
            "Learn. Practice. Progress. 🚀",
            keyboard
        )

    elif command in RESPONSES:
        send_message(chat_id, RESPONSES[command])

    return "OK"
