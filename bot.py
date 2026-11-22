
import os
import re
import logging
import requests
from datetime import datetime, timedelta, timezone
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
    "/accounts": "📘 Accounts\n\nOpen Study Hub to access Accounts lectures.",
    "/law": "⚖️ Business Laws\n\nOpen Study Hub to access Law lectures.",
    "/qa": "📊 Quantitative Aptitude\n\nOpen Study Hub to access QA lectures.",
    "/economics": "📈 Business Economics\n\nOpen Study Hub to access Economics lectures.",
    "/lectures": "🎥 Open Study Hub to explore recorded lectures.",
    "/notes": "📝 Study Notes will be added soon.",
    "/progress": "📈 Your learning progress feature is coming soon.",
    "/continue": "▶️ Open Study Hub to continue learning.",
    "/help": "ℹ️ CA Study Hub Help\n\n/start - Welcome\n/unlock - Unlock lecture access\n/access - Check access status\n/subjects - All subjects\n/lectures - Recorded lectures\n/help - Help"
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


def supabase_headers():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise ValueError("Supabase settings missing in Render.")

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json"
    }

    # Legacy JWT service_role keys need Authorization too.
    # New sb_secret keys use the apikey header.
    if SUPABASE_SERVICE_KEY.startswith("eyJ"):
        headers["Authorization"] = (
            f"Bearer {SUPABASE_SERVICE_KEY}"
        )

    return headers


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
            "Incorrect caption format.\n\n"
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
        raise ValueError("No video or document found.")

    payload = {
        "subject": subject.upper(),
        "chapter_name": chapter,
        "lecture_number": lecture_number,
        "channel_id": channel_post["chat"]["id"],
        "message_id": channel_post["message_id"],
        "caption": caption
    }

    headers = supabase_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

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
            f"{response.text[:2000]}"
        )

    return payload


def unlock_access(user_id):
    headers = supabase_headers()
    now = datetime.now(timezone.utc)

    # Find an active session
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/access_sessions",
        headers=headers,
        params={
            "telegram_user_id": f"eq.{user_id}",
            "expires_at": f"gt.{now.isoformat()}",
            "select": "expires_at,lectures_sent",
            "order": "started_at.desc",
            "limit": "1"
        },
        timeout=20
    )
    response.raise_for_status()

    sessions = response.json()

    if sessions:
        session = sessions[0]

        return (
            "✅ YOUR ACCESS IS ALREADY ACTIVE!\n\n"
            f"⏳ Expires: {session['expires_at']}\n"
            f"🎥 Lectures used: "
            f"{session['lectures_sent']}/10\n\n"
            "Open Study Hub to continue."
        )

    # Create a new 12-hour access session
    expires_at = now + timedelta(hours=12)

    payload = {
        "telegram_user_id": user_id,
        "started_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "lectures_sent": 0
    }

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/access_sessions",
        headers={
            **headers,
            "Prefer": "return=minimal"
        },
        json=payload,
        timeout=20
    )
    response.raise_for_status()

    return (
        "🎉 LECTURE ACCESS UNLOCKED!\n\n"
        "✅ Access duration: 12 hours\n"
        "🎥 Lecture limit: 10\n"
        "📚 Your study session is active!\n\n"
        "Use the button below to open Study Hub."
    )


def check_access(user_id):
    headers = supabase_headers()
    now = datetime.now(timezone.utc)

    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/access_sessions",
        headers=headers,
        params={
            "telegram_user_id": f"eq.{user_id}",
            "expires_at": f"gt.{now.isoformat()}",
            "select": "expires_at,lectures_sent",
            "order": "started_at.desc",
            "limit": "1"
        },
        timeout=20
    )
    response.raise_for_status()

    sessions = response.json()

    if not sessions:
        return (
            "🔒 NO ACTIVE ACCESS\n\n"
            "Send /unlock to activate your "
            "12-hour lecture access."
        )

    session = sessions[0]
    remaining = max(0, 10 - session["lectures_sent"])

    return (
        "✅ YOUR ACCESS IS ACTIVE!\n\n"
        f"⏳ Expires: {session['expires_at']}\n"
        f"🎥 Lectures used: {session['lectures_sent']}/10\n"
        f"📚 Lectures remaining: {remaining}"
    )


@app.route("/")
def home():
    return "CA Study Hub Bot is running!"


@app.route("/webhook", methods=["POST"])
def webhook():
    if (
        not WEBHOOK_SECRET
        or request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token"
        ) != WEBHOOK_SECRET
    ):
        abort(403)

    update = request.get_json(silent=True) or {}

    # Handle videos uploaded to the private storage channel
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
                            f"{str(error)[:2500]}"
                        )
                    except Exception:
                        logging.exception(
                            "Could not notify admin"
                        )

        return "OK"

    # Handle normal Telegram messages
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return "OK"

    command = text.split()[0].split("@")[0].lower()

    if command == "/id":
        send_message(
            chat_id,
            f"Your Telegram Chat ID is:\n{chat_id}"
        )
        return "OK"

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
            "📚 Accounts\n"
            "⚖️ Business Laws\n"
            "📊 Quantitative Aptitude\n"
            "📈 Business Economics\n\n"
            "Send /unlock to activate lecture access.",
            keyboard
        )

    elif command == "/unlock":
        try:
            result = unlock_access(chat_id)

            keyboard = {
                "inline_keyboard": [[
                    {
                        "text": "🚀 Open Study Hub",
                        "web_app": {"url": SITE_URL}
                    }
                ]]
            }

            send_message(chat_id, result, keyboard)

        except Exception as error:
            logging.exception("Unlock failed")

            send_message(
                chat_id,
                "❌ ACCESS ERROR\n\n"
                f"{str(error)[:1500]}"
            )

    elif command == "/access":
        try:
            send_message(chat_id, check_access(chat_id))

        except Exception as error:
            logging.exception("Access check failed")

            send_message(
                chat_id,
                "❌ ACCESS CHECK ERROR\n\n"
                f"{str(error)[:1500]}"
            )

    elif command in RESPONSES:
        send_message(chat_id, RESPONSES[command])

    return "OK"
