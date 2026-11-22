
import os
import re
import logging
import requests
from flask import Flask, request, abort

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

SITE_URL = "https://castudyclub-dotcom.github.io/ca-study-hub/"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

RESPONSES = {
    "/subjects": "📚 CA Foundation Subjects\n\n1. Accounts\n2. Business Laws\n3. Quantitative Aptitude\n4. Business Economics",
    "/accounts": "📘 Accounts\n\nYour Accounts lectures will be available here soon.",
    "/law": "⚖️ Business Laws\n\nYour Business Laws lectures will be available here soon.",
    "/qa": "📊 Quantitative Aptitude\n\nYour QA lectures will be available here soon.",
    "/economics": "📈 Business Economics\n\nYour Economics lectures will be available here soon.",
    "/lectures": "🎥 Recorded Lectures\n\nOpen Study Hub to explore lectures.",
    "/notes": "📝 Study Notes\n\nNotes and PDFs will be added soon.",
    "/progress": "📈 Your learning progress feature is coming soon.",
    "/continue": "▶️ Continue Learning\n\nOpen Study Hub to continue.",
    "/help": "ℹ️ CA Study Hub Help\n\n/start - Welcome\n/subjects - All subjects\n/accounts - Accounts\n/law - Business Laws\n/qa - Quantitative Aptitude\n/economics - Business Economics\n/lectures - Recorded lectures\n/notes - Notes\n/progress - Progress\n/continue - Continue learning"
}


def send_message(chat_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "text": text
    }

    if keyboard:
        data["reply_markup"] = keyboard

    response = requests.post(
        f"{API_URL}/sendMessage",
        json=data,
        timeout=20
    )
    response.raise_for_status()


def save_lecture(channel_post):

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise ValueError(
            "SUPABASE_URL or SUPABASE_SERVICE_KEY is missing in Render."
        )

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
            "Incorrect caption format.\n"
            "Required:\n"
            "SUBJECT: ACCOUNTS\n"
            "CHAPTER: Introduction\n"
            "LECTURE: 01"
        )

    lecture_number = int(match.group())

    media = (
        channel_post.get("video")
        or channel_post.get("document")
    )

    if not media:
        raise ValueError("No video or document found in channel post.")

    payload = {
        "subject": subject.upper(),
        "chapter_name": chapter,
        "lecture_number": lecture_number,
        "channel_id": channel_post["chat"]["id"],
        "message_id": channel_post["message_id"],
        "caption": caption
    }

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation"
    }

    # Legacy service_role JWT also works as a Bearer token.
    # New sb_secret keys are sent through the apikey header.
    if SUPABASE_SERVICE_KEY.startswith("eyJ"):
        headers["Authorization"] = (
            f"Bearer {SUPABASE_SERVICE_KEY}"
        )

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/lectures"
        "?on_conflict=channel_id,message_id",
        headers=headers,
        json=payload,
        timeout=25
    )

    if not response.ok:
        raise Exception(
            f"Supabase HTTP {response.status_code}\n"
            f"Details: {response.text[:2000]}"
        )

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

    # Handle new channel videos
    channel_post = update.get("channel_post")

    if channel_post:

        media = (
            channel_post.get("video")
            or channel_post.get("document")
        )

        if media:
            try:
                saved = save_lecture(channel_post)

                logging.info("Lecture saved: %s", saved)

                if ADMIN_CHAT_ID:
                    send_message(
                        ADMIN_CHAT_ID,
                        "✅ LECTURE SAVED TO DATABASE!\n\n"
                        f"📚 Subject: {saved['subject']}\n"
                        f"📖 Chapter: {saved['chapter_name']}\n"
                        f"🎥 Lecture: {saved['lecture_number']}\n"
                        f"🆔 Message ID: {saved['message_id']}"
                    )

            except Exception as error:

                logging.exception("Lecture database save failed")

                if ADMIN_CHAT_ID:
                    try:
                        send_message(
                            ADMIN_CHAT_ID,
                            "❌ LECTURE DATABASE ERROR\n\n"
                            f"{str(error)[:3000]}"
                        )
                    except Exception:
                        logging.exception(
                            "Could not notify admin"
                        )

        return "OK"

    # Handle private messages
    message = update.get("message", {})

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id:
        return "OK"

    if text == "/id":
        send_message(
            chat_id,
            f"Your Telegram Chat ID is:\n{chat_id}"
        )
        return "OK"

    if not text:
        return "OK"

    command = text.split()[0].split("@")[0].lower()

    if command == "/start":

        keyboard = {
            "inline_keyboard": [[
                {
                    "text": "🚀 Open Study Hub",
                    "web_app": {
                        "url": SITE_URL
                    }
                }
            ]]
        }

        send_message(
            chat_id,
            "👋 Welcome to CA Study Hub!\n\n"
            "Your CA Foundation preparation starts here.\n\n"
            "📚 Accounts\n"
            "⚖️ Business Laws\n"
            "📊 Quantitative Aptitude\n"
            "📈 Business Economics\n\n"
            "Learn. Practice. Progress. 🚀",
            keyboard
        )

    elif command in RESPONSES:
        send_message(chat_id, RESPONSES[command])

    return "OK"
