import os
import re
import base64
from functools import wraps
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ====== CONFIG ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# ====== ADMIN ONLY DECORATOR ======
def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("❌ Access Denied")
            return
        return await func(update, context)
    return wrapped

# ====== BASIC COMMANDS ======
@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bot Ready!\nSend me any .html file (educational page)\n"
        "I'll decrypt + extract all links and return a clean categorized .txt."
    )

@admin_only
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💡 Usage:\n"
        "1️⃣ Upload .html file.\n"
        "2️⃣ Bot auto-decrypts & parses nested folders.\n"
        "3️⃣ You'll get structured .txt with all links:\n"
        "🎬 VIDEOS | 📚 PDFs | 📝 Tests | 🖼️ Images."
    )

# ====== UTILS ======
JUNK_WORDS = ["play", "original", "watch", "download", "view", "quality", "test", "attempt"]

def clean_title(text):
    text = re.sub(r'^\s*\d+[\.\)]*\s*', '', text)
    for w in JUNK_WORDS:
        text = re.sub(rf'\b{w}\b', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text)
    return text.strip(" -:\n\t")

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

def categorize(url: str, title: str) -> str:
    u = url.lower()
    if any(x in u for x in [".mp4", ".m3u8", "player", "transcoded-videos"]):
        return "VIDEOS"
    if u.endswith(".pdf") or "drive.google" in u:
        if re.search(r'\b(test|quiz)\b', title, re.I):
            return "TESTS"
        return "PDFS"
    if any(x in u for x in [".jpg", ".jpeg", ".png"]):
        return "IMAGES"
    if re.search(r'\b(test|quiz)\b', title, re.I):
        return "TESTS"
    return None

# ====== PARSER ======
def extract_links(html):
    soup = BeautifulSoup(html, "lxml")
    data = {"VIDEOS": {}, "PDFS": {}, "TESTS": {}, "IMAGES": {}}
    seen = set()

    def parse_section(div, context=""):
        for topic_btn in div.find_all("button", class_="topic-button"):
            tname = re.sub(r'\s*\(\d+\)$', '', topic_btn.get_text(strip=True))
            sub_id = topic_btn.get("onclick", "").split("'")
            if len(sub_id) > 1:
                sub_div = div.find("div", id=sub_id[1])
                if sub_div:
                    parse_section(sub_div, f"{context} {tname}".strip())

        for li in div.find_all("li"):
            text = li.get_text(" ", strip=True)
            a = li.find("a", href=True)
            if not a:
                continue
            url = a["href"]
            if url.startswith("javascript"):
                orig = li.find("a", string=re.compile("Original", re.I))
                if orig and orig.has_attr("href"):
                    url = orig["href"]
            title = a.get_text(strip=True)
            if not title or title.isdigit():
                title = f"{context} {title}".strip()
            title = clean_title(title or text)
            if not title or title.lower() in seen:
                continue
            cat = categorize(url, title)
            if not cat:
                continue
            seen.add(title.lower())
            data[cat][title] = url

    for btn in soup.find_all("button", class_="section-button"):
        if "topic-button" in btn.get("class", []):
            continue
        sname = re.sub(r'\s*\(\d+\)$', '', btn.get_text(strip=True))
        sec_id = btn.get("onclick", "").split("'")
        if len(sec_id) > 1:
            div = soup.find("div", id=sec_id[1])
            if div:
                parse_section(div, sname)

    return data

# ====== FILE HANDLER ======
@admin_only
async def handle_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(".html"):
        await update.message.reply_text("❌ Only .html files supported.")
        return

    path = doc.file_name
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(path)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    html = decrypt_if_needed(html)
    result = extract_links(html)

    lines = []
    for emoji, cat in [("🎬", "VIDEOS"), ("📚", "PDFS"), ("📝", "TESTS"), ("🖼️", "IMAGES")]:
        items = result.get(cat, {})
        if not items:
            continue
        lines.append(f"{emoji} {cat} ({len(items)})")
        lines.append("-" * 25)
        for t, u in items.items():
            lines.append(f"{t} : {u}")
        lines.append("")

    out_path = "output.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    await context.bot.send_document(chat_id=update.message.chat_id, document=open(out_path, "rb"))

# ====== MAIN ======
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_html))
    app.run_polling()

if __name__ == "__main__":
    main()
