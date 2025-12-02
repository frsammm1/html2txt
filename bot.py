import os, re, base64, logging
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, filters, ContextTypes
)

# Logging setup (optional)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Read environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 0))

def decrypt_html_content(html: str) -> str:
    """Detect and decrypt encodedContent if present."""
    # Search for encodedContent in HTML
    m = re.search(r"encodedContent\s*=\s*'([^']+)'", html)
    p1 = re.search(r"let\s+P1\s*=\s*\"([^\"]+)\"", html)
    p2 = re.search(r"let\s+P2\s*=\s*\"([^\"]+)\"", html)
    p3 = re.search(r"let\s+P3_Reversed\s*=\s*\"([^\"]+)\"", html)
    p4 = re.search(r"let\s+P4\s*=\s*\"([^\"]+)\"", html)
    if m and p1 and p2 and p3 and p4:
        encoded = m.group(1)
        # Build key: P4 + P1 + P2 + reverse(P3_Reversed)
        key = p4.group(1) + p1.group(1) + p2.group(1) + p3.group(1)[::-1]
        try:
            data = base64.b64decode(encoded)
        except Exception:
            return html  # if decode fails, return original
        # XOR decryption
        xored = bytearray(len(data))
        for i in range(len(data)):
            xored[i] = data[i] ^ ord(key[i % len(key)])
        try:
            xored_str = xored.decode('utf-8', errors='ignore')
        except Exception:
            return html
        # Remove any non-base64 chars and decode again
        clean_b64 = re.sub(r'[^A-Za-z0-9+/=]', '', xored_str)
        try:
            final_bytes = base64.b64decode(clean_b64)
            return final_bytes.decode('utf-8', errors='ignore')
        except Exception:
            return html
    return html

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming document (HTML) from the admin user."""
    user_id = update.effective_user.id
    # Only admin can use this
    if user_id != ADMIN_ID:
        await update.message.reply_text("Unauthorized user.")
        return
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith('.html'):
        await update.message.reply_text("Please send an HTML file.")
        return
    # Download the HTML file
    file = await context.bot.get_file(doc.file_id)
    html_path = 'temp_input.html'
    await file.download_to_drive(html_path)
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    # Decrypt if needed
    html_content = decrypt_html_content(html_content)
    soup = BeautifulSoup(html_content, 'lxml')

    videos = []
    pdfs = []
    tests = []
    images = []
    seen_titles = set()

    # Traverse all anchor tags
    for a in soup.find_all('a'):
        href = a.get('href', '') or ''
        onclick = a.get('onclick', '') or ''
        title = ''
        link = None

        text = a.get_text().strip()
        # Case: anchor text "Original" - use its href
        if text.lower() == 'original' and href:
            link = href
        # Case: direct links with known extensions
        elif href:
            href_lower = href.lower()
            if href_lower.endswith('.mp4') or href_lower.endswith('.m3u8'):
                link = href
            elif href_lower.endswith('.pdf') or 'drive.google.com' in href_lower:
                link = href
            elif href_lower.endswith('.jpg') or href_lower.endswith('.jpeg') or href_lower.endswith('.png') or href_lower.endswith('.gif'):
                link = href
            elif 'test' in href_lower or 'quiz' in href_lower or 'attempt' in href_lower:
                link = href
        # Case: onclick contains URL (e.g. video player)
        if not link and onclick:
            m = re.search(r"'(https?://[^']+)'", onclick)
            if m:
                url = m.group(1)
                # categorize based on extension or keywords
                url_lower = url.lower()
                if url_lower.endswith('.mp4') or url_lower.endswith('.m3u8') or 'video' in url_lower:
                    link = url
                elif url_lower.endswith('.pdf'):
                    link = url
                elif url_lower.endswith('.jpg') or url_lower.endswith('.png'):
                    link = url

        if not link:
            continue  # skip if not a recognized content link

        # Derive title from surrounding text
        # We take the parent element's text as a base
        parent = a.find_parent(['li', 'div', 'span']) or a.parent
        title_text = parent.get_text(separator=" ", strip=True) if parent else ''
        # Remove junk words and original indicators
        title_clean = re.sub(r'\b(Original|Play|Download|Click here)\b', '', title_text, flags=re.I)
        title_clean = re.sub(r'^\d+\s*\.?', '', title_clean)  # remove leading numbers
        title_clean = title_clean.strip()
        # Avoid empty titles
        if not title_clean:
            title_clean = text or 'Untitled'

        # Skip duplicates
        if title_clean in seen_titles:
            continue
        seen_titles.add(title_clean)

        # Categorize
        link_lower = link.lower()
        if link_lower.endswith(('.mp4', '.m3u8')) or 'youtube.com' in link_lower or 'video' in link_lower:
            videos.append((title_clean, link))
        elif link_lower.endswith('.pdf') or 'drive.google.com' in link_lower:
            pdfs.append((title_clean, link))
        elif 'test' in link_lower or 'quiz' in link_lower or 'attempt' in link_lower:
            tests.append((title_clean, link))
        elif link_lower.endswith(('.jpg', '.jpeg', '.png', '.gif')):
            images.append((title_clean, link))

    # Optionally filter out broken links
    def filter_broken(items):
        valid = []
        for (t, url) in items:
            try:
                resp = requests.head(url, allow_redirects=True, timeout=5)
                if resp.status_code < 400:
                    valid.append((t, url))
            except Exception:
                continue
        return valid

    videos = filter_broken(videos)
    pdfs   = filter_broken(pdfs)
    tests  = filter_broken(tests)
    images = filter_broken(images)

    # Write output.txt
    with open('output.txt', 'w', encoding='utf-8') as out:
        if videos:
            out.write(f"🎬 VIDEOS ({len(videos)})\n")
            out.write("------------------\n")
            for t, url in videos:
                out.write(f"{t} : {url}\n")
            out.write("\n")
        if pdfs:
            out.write(f"📚 PDFS ({len(pdfs)})\n")
            out.write("------------------\n")
            for t, url in pdfs:
                out.write(f"{t} : {url}\n")
            out.write("\n")
        if tests:
            out.write(f"📝 TESTS ({len(tests)})\n")
            out.write("------------------\n")
            for t, url in tests:
                out.write(f"{t} : {url}\n")
            out.write("\n")
        if images:
            out.write(f"🖼️ IMAGES ({len(images)})\n")
            out.write("------------------\n")
            for t, url in images:
                out.write(f"{t} : {url}\n")
            out.write("\n")

    # Send output.txt back to admin
    await context.bot.send_document(chat_id=ADMIN_ID, document=open('output.txt','rb'))

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    # Run in polling or webhook mode
    port = os.environ.get('PORT')
    if port:
        # Webhook mode (example placeholder URL)
        WEBHOOK_URL = os.environ.get('WEBHOOK_URL')  # e.g. https://yourapp.com
        app.run_webhook(listen='0.0.0.0', port=int(port), url_path=BOT_TOKEN,
                        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    else:
        await app.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
