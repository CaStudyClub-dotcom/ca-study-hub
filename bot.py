
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

SUBJECTS = [
    "ACCOUNTS",
    "LAW",
    "QA",
    "ECONOMICS"
]


def telegram(method, data):
    response = requests.post(
        f"{API_URL}/{method}",
        json=data,
        timeout=30
    )
    response.raise_for_status()
    result = response.json()

    if not result.get("ok"):
        raise Exception(result.get("description", "Telegram API error"))

    return result.get("result")


def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard
    return telegram("sendMessage", data)


def answer_callback(callback_id, text=""):
    return telegram("answerCallbackQuery", {
        "callback_query_id": callback_id,
        "text": text
    })


def supabase_headers():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise ValueError("Supabase settings missing.")

    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json"
    }

    if SUPABASE_SERVICE_KEY.startswith("eyJ"):
        headers["Authorization"] = (
            f"Bearer {SUPABASE_SERVICE_KEY}"
        )

    return headers


def db_get(table, params):
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=supabase_headers(),
        params=params,
        timeout=25
    )
    response.raise_for_status()
    return response.json()


def db_insert(table, payload):
    headers = supabase_headers()
    headers["Prefer"] = "return=representation"

    response = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=headers,
        json=payload,
        timeout=25
    )
    response.raise_for_status()
    return response.json()


def db_update(table, filters, payload):
    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=supabase_headers(),
        params=filters,
        json=payload,
        timeout=25
    )
    response.raise_for_status()


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
            "Caption format required:\n"
            "SUBJECT: ACCOUNTS\n"
            "CHAPTER: Introduction\n"
            "LECTURE: 01"
        )

    media = channel_post.get("video") or channel_post.get("document")
    if not media:
        raise ValueError("No video or document found.")

    payload = {
        "subject": subject.upper(),
        "chapter_name": chapter,
        "lecture_number": int(match.group()),
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
            f"Supabase HTTP {response.status_code}: "
            f"{response.text[:1500]}"
        )

    return payload


def active_session(user_id):
    now = datetime.now(timezone.utc).isoformat()

    sessions = db_get(
        "access_sessions",
        {
            "telegram_user_id": f"eq.{user_id}",
            "expires_at": f"gt.{now}",
            "select": "id,expires_at,lectures_sent",
            "order": "started_at.desc",
            "limit": "1"
        }
    )

    return sessions[0] if sessions else None


def unlock_access(user_id):
    session = active_session(user_id)

    if session:
        return (
            "✅ YOUR ACCESS IS ALREADY ACTIVE!\n\n"
            f"⏳ Expires: {session['expires_at']}\n"
            f"🎥 Used: {session['lectures_sent']}/10"
        )

    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=12)

    db_insert("access_sessions", {
        "telegram_user_id": user_id,
        "started_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "lectures_sent": 0
    })

    return (
        "🎉 ACCESS UNLOCKED!\n\n"
        "⏳ Duration: 12 hours\n"
        "🎥 Maximum lectures: 10\n\n"
        "Send /lectures to choose your videos."
    )


def show_subjects(chat_id):
    rows = db_get(
        "lectures",
        {
            "select": "subject",
            "order": "subject.asc",
            "limit": "1000"
        }
    )

    subjects = sorted({
        row["subject"] for row in rows if row.get("subject")
    })

    if not subjects:
        send_message(chat_id, "📭 No lectures have been uploaded yet.")
        return

    buttons = [
        [{"text": f"📚 {subject}", "callback_data": f"sub:{subject}"}]
        for subject in subjects
    ]

    send_message(
        chat_id,
        "📚 SELECT YOUR SUBJECT",
        {"inline_keyboard": buttons}
    )


def show_chapters(chat_id, subject):
    rows = db_get(
        "lectures",
        {
            "subject": f"eq.{subject}",
            "select": "id,chapter_name,lecture_number",
            "order": "chapter_name.asc,lecture_number.asc",
            "limit": "1000"
        }
    )

    chapters = {}

    for row in rows:
        name = row["chapter_name"]
        if name not in chapters:
            chapters[name] = row["id"]

    if not chapters:
        send_message(chat_id, "No chapters found for this subject.")
        return

    buttons = [
        [{
            "text": f"📖 {name}",
            "callback_data": f"ch:{first_id}"
        }]
        for name, first_id in chapters.items()
    ]

    buttons.append([{
        "text": "⬅️ Back to subjects",
        "callback_data": "back:subjects"
    }])

    send_message(
        chat_id,
        f"📖 {subject} — SELECT CHAPTER",
        {"inline_keyboard": buttons}
    )


def show_lectures(chat_id, first_id):
    first = db_get(
        "lectures",
        {
            "id": f"eq.{first_id}",
            "select": "subject,chapter_name",
            "limit": "1"
        }
    )

    if not first:
        send_message(chat_id, "Lecture chapter not found.")
        return

    subject = first[0]["subject"]
    chapter = first[0]["chapter_name"]

    rows = db_get(
        "lectures",
        {
            "subject": f"eq.{subject}",
            "chapter_name": f"eq.{chapter}",
            "select": "id,lecture_number",
            "order": "lecture_number.asc",
            "limit": "100"
        }
    )

    buttons = [
        [{
            "text": f"🎥 Lecture {row['lecture_number']}",
            "callback_data": f"lec:{row['id']}"
        }]
        for row in rows
    ]

    buttons.append([{
        "text": "⬅️ Back to chapters",
        "callback_data": f"sub:{subject}"
    }])

    send_message(
        chat_id,
        f"📚 {subject}\n📖 {chapter}\n\nSELECT YOUR LECTURE:",
        {"inline_keyboard": buttons}
    )


def deliver_lecture(chat_id, user_id, lecture_id):
    session = active_session(user_id)

    if not session:
        send_message(
            chat_id,
            "🔒 Your access has expired.\n\nSend /unlock to activate access."
        )
        return

    used = int(session["lectures_sent"])

    if used >= 10:
        send_message(
            chat_id,
            "⚠️ Your 10-lecture limit has been reached."
        )
        return

    rows = db_get(
        "lectures",
        {
            "id": f"eq.{lecture_id}",
            "select": "subject,chapter_name,lecture_number,channel_id,message_id",
            "limit": "1"
        }
    )

    if not rows:
        send_message(chat_id, "Lecture not found.")
        return

    lecture = rows[0]

    # Copy the original video from the private storage channel.
    telegram("copyMessage", {
        "chat_id": chat_id,
        "from_chat_id": lecture["channel_id"],
        "message_id": lecture["message_id"]
    })

    # Count only after Telegram confirms successful delivery.
    db_update(
        "access_sessions",
        {"id": f"eq.{session['id']}"},
        {"lectures_sent": used + 1}
    )

    send_message(
        chat_id,
        f"✅ Lecture delivered!\n\n"
        f"📚 {lecture['subject']}\n"
        f"📖 {lecture['chapter_name']}\n"
        f"🎥 Lecture {lecture['lecture_number']}\n\n"
        f"Remaining: {9 - used}/10"
    )


def handle_callback(query):
    callback_id = query["id"]
    data = query.get("data", "")
    user_id = query["from"]["id"]
    chat_id = query["message"]["chat"]["id"]

    try:
        answer_callback(callback_id)

        if data == "back:subjects":
            show_subjects(chat_id)

        elif data.startswith("sub:"):
            subject = data[4:]
            show_chapters(chat_id, subject)

        elif data.startswith("ch:"):
            first_id = int(data[3:])
            show_lectures(chat_id, first_id)

        elif data.startswith("lec:"):
            lecture_id = int(data[4:])
            deliver_lecture(chat_id, user_id, lecture_id)

    except Exception as error:
        logging.exception("Button action failed")
        send_message(
            chat_id,
            f"❌ ERROR\n\n{str(error)[:1200]}"
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

    if update.get("channel_post"):
        post = update["channel_post"]

        if post.get("video") or post.get("document"):
            try:
                saved = save_lecture(post)

                if ADMIN_CHAT_ID:
                    send_message(
                        ADMIN_CHAT_ID,
                        "✅ LECTURE SAVED!\n\n"
                        f"Subject: {saved['subject']}\n"
                        f"Chapter: {saved['chapter_name']}\n"
                        f"Lecture: {saved['lecture_number']}"
                    )

            except Exception as error:
                logging.exception("Lecture save failed")

                if ADMIN_CHAT_ID:
                    send_message(
                        ADMIN_CHAT_ID,
                        f"❌ DATABASE ERROR\n\n{str(error)[:2000]}"
                    )

        return "OK"

    if update.get("callback_query"):
        handle_callback(update["callback_query"])
        return "OK"

    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return "OK"

    command = text.split()[0].split("@")[0].lower()

    if command == "/start":
        keyboard = {
            "inline_keyboard": [[{
                "text": "🚀 Open Study Hub",
                "web_app": {"url": SITE_URL}
            }]]
        }

        send_message(
            chat_id,
            "👋 Welcome to CA Study Hub!\n\n"
            "📚 CA Foundation Lectures\n"
            "⚖️ Business Laws\n"
            "📊 Quantitative Aptitude\n"
            "📈 Business Economics\n\n"
            "Send /unlock to activate your access.",
            keyboard
        )

    elif command == "/unlock":
        try:
            send_message(chat_id, unlock_access(chat_id))
        except Exception as error:
            logging.exception("Unlock failed")
            send_message(chat_id, f"❌ ACCESS ERROR\n\n{str(error)[:1200]}")

    elif command == "/access":
        try:
            session = active_session(chat_id)

            if session:
                remaining = max(
                    0, 10 - int(session["lectures_sent"])
                )
                send_message(
                    chat_id,
                    "✅ ACCESS ACTIVE\n\n"
                    f"Expires: {session['expires_at']}\n"
                    f"Lectures remaining: {remaining}/10"
                )
            else:
                send_message(
                    chat_id,
                    "🔒 No active access.\nSend /unlock to begin."
                )

        except Exception as error:
            logging.exception("Access check failed")
            send_message(chat_id, f"❌ ERROR\n\n{str(error)[:1200]}")

    elif command == "/lectures":
        session = active_session(chat_id)

        if not session:
            send_message(
                chat_id,
                "🔒 First unlock your access using /unlock."
            )
        else:
            show_subjects(chat_id)

    elif command == "/id":
        send_message(chat_id, f"Your Telegram ID: {chat_id}")

    elif command == "/help":
        send_message(
            chat_id,
            "/start - Welcome\n"
            "/unlock - Activate 12-hour access\n"
            "/access - Check access\n"
            "/lectures - Browse and receive videos\n"
            "/help - Help"
        )

    return "OK"


# Register button clicks as webhook updates.
def configure_webhook():
    if not BOT_TOKEN or not WEBHOOK_SECRET:
        logging.warning("Bot webhook settings missing.")
        return

    try:
        result = telegram("setWebhook", {
            "url": "https://ca-study-hub.onrender.com/webhook",
            "secret_token": WEBHOOK_SECRET,
            "allowed_updates": [
                "message",
                "channel_post",
                "callback_query"
            ]
        })
        logging.info("Webhook configured: %s", result)
    except Exception:
        logging.exception("Webhook configuration failed")


configure_webhook()


# Telegram Mini App signed-data verification and access API.
import hashlib
import hmac
import json
from urllib.parse import parse_qsl
from flask import jsonify


def verify_telegram_init_data(init_data):
    if not BOT_TOKEN or not init_data or not isinstance(init_data, str):
        return None
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed.items())
        )
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None
        auth_date = int(parsed.get("auth_date", "0"))
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if auth_date <= 0 or now_ts - auth_date > 86400 or auth_date > now_ts + 60:
            return None
        user_id = json.loads(parsed.get("user", "{}")).get("id")
        return user_id if isinstance(user_id, int) else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def access_payload(user_id):
    session = active_session(user_id)
    if not session:
        return {"active": False, "remaining": 10, "message": "Your 12-hour study pass is ready to unlock."}
    used = int(session.get("lectures_sent") or 0)
    return {"active": True, "expires_at": session["expires_at"], "lectures_sent": used,
            "remaining": max(0, 10-used), "message": "Your study pass is active. Keep learning!"}


@app.after_request
def add_miniapp_cors(response):
    if request.headers.get("Origin") == "https://castudyclub-dotcom.github.io":
        response.headers["Access-Control-Allow-Origin"] = "https://castudyclub-dotcom.github.io"
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


@app.route("/api/access/<action>", methods=["POST", "OPTIONS"])
def miniapp_access(action):
    if request.method == "OPTIONS":
        return ("", 204)
    if action not in ("status", "unlock"):
        return jsonify({"message": "Unknown access action."}), 404
    body = request.get_json(silent=True) or {}
    user_id = verify_telegram_init_data(body.get("initData"))
    if not user_id:
        return jsonify({"message": "Telegram verification failed. Please reopen the Mini App from the bot."}), 401
    try:
        if action == "unlock" and not active_session(user_id):
            now = datetime.now(timezone.utc)
            db_insert("access_sessions", {"telegram_user_id": user_id, "started_at": now.isoformat(),
                       "expires_at": (now + timedelta(hours=12)).isoformat(), "lectures_sent": 0})
        return jsonify(access_payload(user_id))
    except Exception:
        logging.exception("Mini App access API failed")
        return jsonify({"message": "Access service is temporarily unavailable. Please retry."}), 503



# Mini App lecture catalogue and one-tap delivery endpoints.
@app.route("/api/lectures/list", methods=["POST", "OPTIONS"])
def miniapp_lecture_list():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    user_id = verify_telegram_init_data(body.get("initData"))
    if not user_id:
        return jsonify({"message": "Telegram verification failed. Reopen the Mini App from the bot."}), 401
    try:
        rows = db_get("lectures", {
            "select": "id,subject,chapter_name,lecture_number,caption",
            "order": "subject.asc,chapter_name.asc,lecture_number.asc",
            "limit": "1000"
        })
        return jsonify({"lectures": rows})
    except Exception:
        logging.exception("Mini App lecture catalogue failed")
        return jsonify({"message": "Lecture library is temporarily unavailable."}), 503


@app.route("/api/lectures/send", methods=["POST", "OPTIONS"])
def miniapp_send_lecture():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    user_id = verify_telegram_init_data(body.get("initData"))
    if not user_id:
        return jsonify({"message": "Telegram verification failed. Reopen the Mini App from the bot."}), 401
    try:
        lecture_id = int(body.get("lecture_id"))
        session = active_session(user_id)
        if not session:
            return jsonify({"message": "Your access has expired. Unlock access first."}), 403
        if int(session.get("lectures_sent") or 0) >= 10:
            return jsonify({"message": "Your 10-lecture limit has been reached."}), 403
        rows = db_get("lectures", {
            "id": f"eq.{lecture_id}",
            "select": "id",
            "limit": "1"
        })
        if not rows:
            return jsonify({"message": "This lecture is not available."}), 404
        # Sends the original stored Telegram channel post to the verified user's private bot chat.
        deliver_lecture(user_id, user_id, lecture_id)
        updated = active_session(user_id)
        return jsonify({"ok": True, "remaining": max(0, 10 - int((updated or {}).get("lectures_sent") or 0)),
                        "message": "Lecture delivered to your Telegram chat."})
    except (TypeError, ValueError):
        return jsonify({"message": "Invalid lecture selection."}), 400
    except Exception:
        logging.exception("Mini App lecture delivery failed")
        return jsonify({"message": "Telegram could not deliver this lecture. Please try again."}), 502

