import os
import re
import base64
import requests
from functools import wraps
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ================== ADMIN ONLY ==================
def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Access denied")
            return
        return await func(update, context)
    return wrapper

# ================== COMMANDS ==================
@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot Ready\n"
        "Send any .html file\n"
        "I will extract Videos / PDFs / Tests properly."
    )

@admin_only
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Usage:\n"
        "1) Upload HTML file\n"
        "2) Bot decrypts & parses deeply\n"
        "3) Returns clean output.txt"
    )

# ================== DECRYPT ==================
def xor_decrypt(data: bytes, key: str) -> bytes:
    k = key.encode()
    return bytes(b ^ k[i % len(k)] for i, b in enumerate(data))

def decrypt_if_needed(html: str) -> str:
    if "encodedContent" not in html:
        return html
    try:
        enc = re.search(r"encodedContent\s*=\s*'([^']+)'", html).group(1)
        P1 = re.search(r'P1\s*=\s*"([^"]+)"', html).group(1)
        P2 = re.search(r'P2\s*=\s*"([^"]+)"', html).group(1)
        P3 = re.search(r'P3_Reversed\s*=\s*"([^"]+)"', html).group(1)
        P4 = re.search(r'P4\s*=\s*"([^"]+)"', html).group(1)

        key = P4 + P1 + P2 + P3[::-1]
        raw = base64.b64decode(re.sub(r'[^A-Za-z0-9+/=]', '', enc))
        step1 = xor_decrypt(raw, key).decode(errors="ignore")
        clean = base64.b64decode(re.sub(r'[^A-Za-z0-9+/=]', '', step1))
        return clean.decode("utf-8", errors="ignore")
    except Exception:
        return html

# ================== HELPERS ==================
JUNK = ["play", "original", "watch", "download", "view"]

def clean_title(t: str) -> str:
    t = re.sub(r'^\d+[\.\)]*', '', t)
    for w in JUNK:
        t = re.sub(rf'\b{w}\b', '', t, flags=re.I)
    return re.sub(r'\s+', ' ', t).strip(" -:\n")

def link_alive(url: str) -> bool:
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        return r.status_code < 400
    except:
        return False

def classify(url: str, title: str):
    u = url.lower()
    if any(x in u for x in [".mp4", ".m3u8", "player"]):
        return "VIDEOS"
    if u.endswith(".pdf") or "drive.google" in u:
        if re.search(r'\b(test|quiz)\b', title, re.I):
            return "TESTS"
        return "PDFS"
    if any(x in u for x in [".jpg", ".png", ".jpeg"]):
        return "IMAGES"
    if re.search(r'\b(test|quiz)\b', title, re.I):
        return "TESTS"
    return None

# ================== PARSER ==================
def parse_html(html: str):
    soup = BeautifulSoup(html, "lxml")
    out = {"VIDEOS": {}, "PDFS": {}, "TESTS": {}, "IMAGES": {}}

    for li in soup.find_all("li"):
        txt = clean_title(li.get_text(" ", strip=True))
        a = li.find("a", href=True)
        if not a:
            continue

        url = a["href"]
        if url.startswith("javascript"):
            org = li.find("a", string=re.compile("Original", re.I))
            if org and org.has_attr("href"):
                url = org["href"]

        title = clean_title(a.get_text() or txt)
        if not title or not link_alive(url):
            continue

        cat = classify(url, title)
        if cat and title not in out[cat]:
            out[cat][title] = url

    return out

# ================== FILE HANDLER ==================
@admin_only
async def handle_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".html"):
        await update.message.reply_text("❌ Only .html files allowed")
        return

    path = doc.file_name
    tg_file = await context.bot.get_file(doc.file_id)
    await tg_file.download_to_drive(path)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    html = decrypt_if_needed(html)
    data = parse_html(html)

    lines = []
    for emoji, cat in [("🎬", "VIDEOS"), ("📚", "PDFS"), ("📝", "TESTS"), ("🖼️", "IMAGES")]:
        if not data[cat]:
            continue
        lines.append(f"{emoji} {cat} ({len(data[cat])})")
        lines.append("-" * 30)
        for t, u in data[cat].items():
            lines.append(f"{t} : {u}")
        lines.append("")

    with open("output.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    await context.bot.send_document(update.effective_chat.id, open("output.txt", "rb"))

# ================== MAIN (FIXED) ==================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_html))

    print("✅ Bot running in POLLING mode (Render safe)")
    app.run_polling()

if __name__ == "__main__":
    main()
