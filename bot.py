import os
import re
import threading
import http.server
import socketserver
import tempfile
from collections import OrderedDict, defaultdict

from bs4 import BeautifulSoup
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ======================================================
# CONFIG
# ======================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ======================================================
# ✅ RENDER PORT FIX (SAFE VERSION)
# ======================================================
def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return  # silence logs

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot Alive")

    class ReuseTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    try:
        with ReuseTCPServer(("0.0.0.0", port), Handler) as httpd:
            print(f"[OK] Dummy HTTP server on port {port}")
            httpd.serve_forever()
    except OSError:
        # Port already in use → ignore (Render restart case)
        print("[WARN] Port already in use, skipping dummy server")

# ======================================================
# TITLE CLEANING
# ======================================================
JUNK_WORDS = [
    "play","watch","download","original","quality",
    "360p","480p","720p","1080p","hls",
    "view","attempt","solution"
]

def clean_title(text: str) -> str:
    text = re.sub(r'^\s*\d+[\.\)]\s*', '', text)
    for w in JUNK_WORDS:
        text = re.sub(rf'\b{w}\b', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) > 2 else "Untitled"

# ======================================================
# ✅ FIX .m3u8.m3u8
# ======================================================
def fix_m3u8(url: str) -> str:
    if url.count(".m3u8") > 1:
        url = url.split(".m3u8")[0] + ".m3u8"
    url = re.sub(r'\.m3u8\.m3u8$', '.m3u8', url)
    url = re.sub(r'\.mp4\.m3u8$', '.m3u8', url)
    return url

# ======================================================
# CLASSIFY
# ======================================================
def classify(url: str) -> str:
    u = url.lower()
    if any(x in u for x in [".m3u8",".mp4","playlist","stream","player"]):
        return "VIDEOS"
    if ".pdf" in u or "drive.google" in u:
        return "PDFS"
    if any(x in u for x in ["quiz","mock","test"]):
        return "TESTS"
    if any(x in u for x in [".jpg",".jpeg",".png",".webp"]):
        return "IMAGES"
    return None

# ======================================================
# HTML PARSER
# ======================================================
def extract_links(html: str):
    soup = BeautifulSoup(html, "lxml")
    results = defaultdict(OrderedDict)

    for el in soup.find_all(["a", "button"]):
        url = None

        if el.name == "a" and el.get("href"):
            url = el["href"]

        if el.name == "button":
            onclick = el.get("onclick","")
            m = re.search(r"(https?://[^'\" )]+)", onclick)
            if m:
                url = m.group(1)

        if not url or not url.startswith("http"):
            continue

        url = fix_m3u8(url)
        cat = classify(url)
        if not cat:
            continue

        parent = el.find_parent(["li","div","section"]) or el
        title = clean_title(parent.get_text(" ", strip=True))

        old = results[cat].get(title)
        if not old or len(url) > len(old):
            results[cat][title] = url

    return results

# ======================================================
# OUTPUT
# ======================================================
def write_txt(data: dict) -> str:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
    for cat in ["VIDEOS","PDFS","TESTS","IMAGES"]:
        items = data.get(cat)
        if not items:
            continue
        f.write(f"\n📂 {cat} ({len(items)})\n")
        f.write("-" * 60 + "\n")
        for t,u in items.items():
            f.write(f"{t} : {u}\n")
    f.close()
    return f.name

# ======================================================
# TELEGRAM HANDLERS
# ======================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "✅ Bot Ready\n"
        "Send HTML file\n"
        "Output will be downloadable"
    )

async def handle_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith(".html"):
        await update.message.reply_text("❌ Only HTML files allowed")
        return

    msg = await update.message.reply_text("⏳ Processing HTML…")

    tg_file = await doc.get_file()
    html = (await tg_file.download_as_bytearray()).decode(errors="ignore")

    try:
        data = extract_links(html)
        path = write_txt(data)

        await msg.edit_text("✅ Completed\n📤 Sending file…")
        await update.message.reply_document(
            document=InputFile(path, filename="extracted_links.txt"),
            caption="✅ Download output"
        )

    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

# ======================================================
# MAIN
# ======================================================
def main():
    threading.Thread(target=start_dummy_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_html))

    print("[OK] Bot running")
    app.run_polling()

if __name__ == "__main__":
    main()
