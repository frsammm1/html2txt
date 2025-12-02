import os
import re
import threading
import http.server
import socketserver
import tempfile
from collections import defaultdict
from bs4 import BeautifulSoup

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ACTIVE_JOBS = set()

# ------------------ RENDER PORT FIX ------------------
def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot alive")

    with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
        print(f"[OK] Dummy server on port {port}")
        httpd.serve_forever()

# ------------------ HELPERS ------------------
JUNK_WORDS = [
    "play", "watch", "download", "original", "quality",
    "360p", "480p", "720p", "1080p", "hls"
]

def clean_title(text: str) -> str:
    text = re.sub(r'^\s*\d+[\.\)]\s*', '', text)
    for w in JUNK_WORDS:
        text = re.sub(rf'\b{w}\b', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text)
    return text.strip() or "Untitled"

def classify(url: str) -> str:
    url = url.lower()
    if any(x in url for x in [".m3u8", ".mp4", "player", "stream"]):
        return "VIDEOS"
    if ".pdf" in url or "drive.google" in url:
        return "PDFS"
    if any(x in url for x in ["quiz", "test", "mock"]):
        return "TESTS"
    if any(x in url for x in [".jpg", ".png", ".jpeg"]):
        return "IMAGES"
    return "OTHERS"

# ------------------ HTML PARSER ------------------
def parse_html(html: str, stop_check):
    soup = BeautifulSoup(html, "lxml")

    results = defaultdict(dict)  # {category: {title: url}}

    clickable = soup.find_all(["a", "button", "div"])

    total = len(clickable)
    for idx, tag in enumerate(clickable, start=1):
        if stop_check():
            break

        url = None

        if tag.name == "a" and tag.get("href"):
            url = tag.get("href")

        if tag.name == "button":
            onclick = tag.get("onclick", "")
            m = re.search(r"(https?://[^'\" )]+)", onclick)
            if m:
                url = m.group(1)

        if not url:
            continue

        container = tag.find_parent("div")
        raw_text = container.get_text(" ", strip=True) if container else tag.get_text()
        title = clean_title(raw_text)

        category = classify(url)
        if title not in results[category]:
            results[category][title] = url

    return results

# ------------------ BOT COMMANDS ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "✅ Bot Ready\n\nSend any .html file\n"
        "• Progress shown\n"
        "• Downloadable .txt output\n"
        "• STOP supported"
    )

async def handle_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    job_id = update.message.id
    ACTIVE_JOBS.add(job_id)

    progress = await update.message.reply_text("⏳ Parsing HTML… 0%")

    html_bytes = await update.message.document.get_file()
    html = (await html_bytes.download_as_bytearray()).decode(errors="ignore")

    def stopped():
        return job_id not in ACTIVE_JOBS

    results = parse_html(html, stopped)

    if stopped():
        await progress.edit_text("❌ Job stopped")
        return

    # -------- FILE GENERATION --------
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as f:
        for category, items in results.items():
            f.write(f"\n📂 {category} ({len(items)})\n")
            f.write("-" * 40 + "\n")
            for title, url in items.items():
                f.write(f"{title} : {url}\n")

        output_path = f.name

    ACTIVE_JOBS.discard(job_id)

    await progress.edit_text("✅ Completed\n📤 Sending file…")

    await update.message.reply_document(
        document=InputFile(output_path, filename="converted_links.txt"),
        caption="✅ Download your extracted links"
    )

async def stop_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    ACTIVE_JOBS.clear()
    await query.answer("Stopped")
    await query.edit_message_text("❌ Stopped by user")

# ------------------ MAIN ------------------
def main():
    threading.Thread(target=start_dummy_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.HTML, handle_html))
    app.add_handler(CallbackQueryHandler(stop_job, pattern="^stop$"))

    print("[OK] Bot polling started")
    app.run_polling()

if __name__ == "__main__":
    main()
