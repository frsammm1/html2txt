import os
import re
import threading
import http.server
import socketserver
import tempfile
from collections import OrderedDict, defaultdict

from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            return

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
        print("[WARN] Port already in use, skipping dummy server")

JUNK_WORDS = [
    "play", "watch", "download", "original", "quality",
    "360p", "480p", "720p", "1080p", "hls", "view",
    "attempt", "solution", "test"
]

def clean_title(text: str) -> str:
    text = re.sub(r'^\s*\d+[\.\)]\s*', '', text)
    for w in JUNK_WORDS:
        text = re.sub(rf'\b{w}\b', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) > 2 else None

def fix_m3u8(url: str) -> str:
    if ".m3u8" in url:
        parts = url.split(".m3u8")
        url = parts[0] + ".m3u8"
    url = re.sub(r'\.mp4\.m3u8$', '.m3u8', url)
    return url

def classify(url: str) -> str:
    u = url.lower()
    
    if any(x in u for x in ["quiz", "mock"]) and "test" in u:
        return "TESTS"
    
    if any(x in u for x in [".m3u8", ".mp4", "playlist", "stream", "player", "akamai"]):
        return "VIDEOS"
    
    if ".pdf" in u or "drive.google" in u:
        return "PDFS"
    
    if "test" in u and not any(x in u for x in [".m3u8", ".mp4", "stream"]):
        return "TESTS"
    
    if any(x in u for x in [".jpg", ".jpeg", ".png", ".webp"]):
        return "IMAGES"
    
    return None

def extract_links(html: str):
    soup = BeautifulSoup(html, "lxml")
    results = defaultdict(OrderedDict)

    for el in soup.find_all(["a", "button"]):
        url = None

        if el.name == "a" and el.get("href"):
            url = el["href"]

        if el.name == "button":
            onclick = el.get("onclick", "")
            match = re.search(r"['\"]?(https?://[^'\" )]+)['\"]?", onclick)
            if match:
                url = match.group(1)
            
            if not url:
                data_attrs = [el.get(k) for k in el.attrs if k.startswith("data-")]
                for attr in data_attrs:
                    if attr and isinstance(attr, str) and attr.startswith("http"):
                        url = attr
                        break

        if not url or not url.startswith("http"):
            continue

        url = fix_m3u8(url)
        cat = classify(url)
        if not cat:
            continue

        parent = el.find_parent(["li", "div", "section", "article"]) or el
        
        title_text = None
        for tag in ["h1", "h2", "h3", "h4", "h5", "b", "strong", "span", "p"]:
            title_elem = parent.find(tag)
            if title_elem:
                title_text = title_elem.get_text(" ", strip=True)
                if title_text and len(title_text) > 3:
                    break
        
        if not title_text:
            title_text = parent.get_text(" ", strip=True)
        
        title = clean_title(title_text)
        if not title:
            continue

        old = results[cat].get(title)
        if not old or len(url) > len(old):
            results[cat][title] = url

    return results

def write_txt(data: dict) -> str:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
    
    for cat in ["VIDEOS", "PDFS", "TESTS", "IMAGES"]:
        items = data.get(cat)
        if not items:
            continue
        
        if cat == "VIDEOS":
            icon = "🎬"
        elif cat == "PDFS":
            icon = "📚"
        elif cat == "TESTS":
            icon = "📝"
        else:
            icon = "🖼️"
        
        f.write(f"\n{icon} {cat} ({len(items)})\n")
        f.write("-" * 60 + "\n")
        for t, u in items.items():
            f.write(f"{t} : {u}\n")
    
    f.close()
    return f.name

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "✅ Bot Ready\n"
        "Send HTML file to extract links\n"
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
        
        if not any(data.values()):
            await msg.edit_text("❌ No links found in HTML")
            return
        
        path = write_txt(data)

        await msg.edit_text("✅ Completed\n📤 Sending file…")
        with open(path, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename="extracted_links.txt",
                caption="✅ Download your extracted links"
            )
        
        os.unlink(path)

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

def main():
    threading.Thread(target=start_dummy_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_html))

    print("[OK] Bot running with polling")
    app.run_polling()

if __name__ == "__main__":
    main()
