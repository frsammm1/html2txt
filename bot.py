import re
import os
import base64
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

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# ============== ADMIN LOCK =================
def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            return
        return await func(update, context)
    return wrapped

# ============== BASIC COMMANDS =============
@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ HTML Extractor Bot Ready\n\n"
        "बस कोई भी .html file भेजो\n"
        "मैं clean categorized .txt दे दूँगा 🙂"
    )

@admin_only
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Steps:\n"
        "1️⃣ HTML file upload करो\n"
        "2️⃣ Bot auto decrypt करेगा (अगर encrypted है)\n"
        "3️⃣ Videos / PDFs / Tests / Images segregate करेगा\n"
        "4️⃣ Deduplicated .txt भेजेगा"
    )

# ============= UTILITY FUNCTIONS ============
JUNK_WORDS = [
    "play", "watch", "download", "view",
    "original", "quality", "test", "attempt",
    "360p", "480p", "720p", "1080p"
]

def clean_title(text: str) -> str:
    text = re.sub(r'^\s*\d+[\.\)]*\s*', '', text)
    for w in JUNK_WORDS:
        text = re.sub(rf'\b{w}\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def xor_decrypt(data: bytes, key: str) -> bytes:
    key = key.encode()
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))

def decrypt_if_needed(html: str) -> str:
    if "encodedContent" not in html:
        return html

    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", string=re.compile("encodedContent"))
    if not script:
        return html

    js = script.string

    try:
        enc = re.search(r"encodedContent\s*=\s*'([^']+)'", js).group(1)
        P1 = re.search(r'P1\s*=\s*"([^"]+)"', js).group(1)
        P2 = re.search(r'P2\s*=\s*"([^"]+)"', js).group(1)
        P3 = re.search(r'P3_Reversed\s*=\s*"([^"]+)"', js).group(1)
        P4 = re.search(r'P4\s*=\s*"([^"]+)"', js).group(1)

        key = P4 + P1 + P2 + P3[::-1]

        enc_clean = re.sub(r'[^A-Za-z0-9+/=]', '', enc)
        raw = base64.b64decode(enc_clean)
        xored = xor_decrypt(raw, key)

        clean_b64 = re.sub(r'[^A-Za-z0-9+/=]', '', xored.decode(errors="ignore"))
        decoded = base64.b64decode(clean_b64).decode("utf-8", "ignore")

        return decoded
    except Exception:
        return html

def categorize(url: str) -> str | None:
    u = url.lower()
    if any(x in u for x in [".mp4", ".m3u8", "player"]):
        return "VIDEOS"
    if u.endswith(".pdf") or "drive.google" in u:
        return "PDFS"
    if any(x in u for x in [".jpg", ".jpeg", ".png"]):
        return "IMAGES"
    if any(x in u for x in ["quiz", "test"]):
        return "MOCK TESTS"
    return None

# ================= FILE HANDLER =================
@admin_only
async def handle_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".html"):
        await update.message.reply_text("❌ Sirf .html file bhejo")
        return

    file = await context.bot.get_file(doc.file_id)
    path = doc.file_name
    await file.download_to_drive(path)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    html = decrypt_if_needed(html)
    soup = BeautifulSoup(html, "lxml")

    data = {
        "VIDEOS": {},
        "PDFS": {},
        "MOCK TESTS": {},
        "IMAGES": {}
    }

    # a tags
    for a in soup.find_all("a", href=True):
        url = a["href"]
        cat = categorize(url)
        if not cat:
            continue
        
        block_text = a.find_parent().get_text(" ", strip=True)
        title = clean_title(block_text)

        if title and title not in data[cat]:
            data[cat][title] = url

    # onclick buttons
    for btn in soup.find_all("button", onclick=True):
        found = re.findall(r"'(https?[^']+)'", btn["onclick"])
        for url in found:
            cat = categorize(url)
            if not cat:
                continue

            parent_text = btn.parent.get_text(" ", strip=True)
            title = clean_title(parent_text)

            if title and title not in data[cat]:
                data[cat][title] = url

    # OUTPUT FILE
    out = []
    for cat in ["VIDEOS", "PDFS", "MOCK TESTS", "IMAGES"]:
        items = data[cat]
        if not items:
            continue
        emoji = "🎬" if cat == "VIDEOS" else "📚" if cat == "PDFS" else "📝" if cat == "MOCK TESTS" else "🖼️"
        out.append(f"{emoji} {cat} ({len(items)})")
        out.append("-" * 20)
        for t, u in items.items():
            out.append(f"{t} : {u}")
        out.append("")

    out_file = "output.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    await context.bot.send_document(
        chat_id=update.message.chat.id,
        document=open(out_file, "rb")
    )

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_html))

    app.run_polling()

if __name__ == "__main__":
    main()
