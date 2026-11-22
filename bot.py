
import os
import requests
from flask import Flask, request, abort

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

SITE_URL = "https://castudyclub-dotcom.github.io/ca-study-hub/"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

RESPONSES = {
    "/subjects": "📚 CA Foundation Subjects\n\n1. Accounts\n2. Business Laws\n3. Quantitative Aptitude\n4. Business Economics",
    "/accounts": "📘 Accounts\n\nYour Accounts lectures will be available here soon.",
    "/law": "⚖️ Business Laws\n\nYour Business Laws lectures will be available here soon.",
    "/qa": "📊 Quantitative Aptitude\n\nYour QA lectures will be available here soon.",
    "/economics": "📈 Business Economics\n\nYour Economics lectures will be available here soon.",
    "/lectures": "🎥 Recorded Lectures\n\nChoose a subject from the Study Hub to explore lectures.",
    "/notes": "📝 Study Notes\n\nNotes and PDFs will be added here soon.",
    "/progress": "📈 Your learning progress feature is coming soon.",
    "/continue": "▶️ Continue Learning\n\nOpen Study Hub to continue your preparation.",
    "/help": "ℹ️ CA Study Hub Help\n\n/start - Welcome\n/subjects - All subjects\n/accounts - Accounts\n/law - Business Laws\n/qa - Quantitative Aptitude\n/economics - Business Economics\n/lectures - Recorded lectures\n/notes - Notes\n/progress - Learning progress\n/continue - Continue learning"
}

def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard

    response = requests.post(
        f"{API_URL}/sendMessage",
        json=data,
        timeout=15
    )
    response.raise_for_status()

@app.route("/")
def home():
    return "CA Study Hub Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        abort(403)

    update = request.get_json(silent=True) or {}

    # 1. Handle new videos uploaded to the storage channel
    channel_post = update.get("channel_post")

    if channel_post:
        chat = channel_post.get("chat", {})
        channel_id = chat.get("id")
        message_id = channel_post.get("message_id")
        caption = channel_post.get("caption", "No caption")

        video = channel_post.get("video")
        document = channel_post.get("document")

        media = video or document

        if media and ADMIN_CHAT_ID:
            file_id = media.get("file_id")
            file_size = media.get("file_size", "Unknown")

            details = (
                "✅ NEW LECTURE RECEIVED!\n\n"
                f"📚 Channel ID: {channel_id}\n"
                f"🆔 Message ID: {message_id}\n"
                f"📝 Caption: {caption}\n"
                f"📦 File size: {file_size} bytes\n\n"
                f"🔑 File ID:\n{file_id}\n\n"
                "Video detected successfully!"
            )

            send_message(ADMIN_CHAT_ID, details)

        return "OK"

    # 2. Handle normal private messages and commands
    message = update.get("message", {})

    chat = message.get("chat", {})
    chat_id = chat.get("id")
    text = message.get("text", "").strip()

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
