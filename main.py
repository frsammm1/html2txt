#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter Bot - NUCLEAR EDITION
✨ Extracts EVERYTHING: Videos, PDFs, Notes, Drive Links
🚀 Fixes missing PDFs in encrypted files
"""

import os
import re
import logging
import base64
import asyncio
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from aiohttp import web

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# ==================== LOGGING ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class NuclearHTMLParser:
    """🔥 Aggressive Parser to catch Videos AND PDFs"""
    
    def __init__(self):
        # Broad extension matching
        self.video_ext = ['.m3u8', '.mp4', '.mkv', 'youtu', 'vimeo', 'playlist']
        self.pdf_ext = ['.pdf', 'drive.google', 'docs.google', 'viewpdf', 'doc', 'ppt']
        
    def xor_decrypt(self, encoded_b64, key):
        """Decryption Logic for Selection/Mains Batch"""
        try:
            encrypted_data = base64.b64decode(encoded_b64).decode('latin1')
            result = []
            key_len = len(key)
            for i in range(len(encrypted_data)):
                char_code = ord(encrypted_data[i]) ^ ord(key[i % key_len])
                result.append(chr(char_code))
            decrypted_layer = "".join(result)
            return base64.b64decode(decrypted_layer).decode('utf-8')
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return None

    def extract_secret_key(self, html_content):
        default_key = "TusharSuperSecreT2025!"
        try:
            p1 = re.search(r'let\s+P1\s*=\s*["\']([^"\']+)["\']', html_content)
            p2 = re.search(r'let\s+P2\s*=\s*["\']([^"\']+)["\']', html_content)
            p3 = re.search(r'let\s+P3_Reversed\s*=\s*["\']([^"\']+)["\']', html_content)
            p4 = re.search(r'let\s+P4\s*=\s*["\']([^"\']+)["\']', html_content)
            
            if p1 and p2 and p3 and p4:
                part3 = p3.group(1)[::-1]
                return f"{p4.group(1)}{p1.group(1)}{p2.group(1)}{part3}"
            return default_key
        except:
            return default_key

    def detect_and_decrypt(self, html_content):
        if "encodedContent" in html_content:
            logger.info("🔒 Encrypted content found, decrypting...")
            match = re.search(r"encodedContent\s*=\s*['\"]([^'\"]+)['\"]", html_content)
            if match:
                key = self.extract_secret_key(html_content)
                decrypted = self.xor_decrypt(match.group(1), key)
                if decrypted: return decrypted
        return html_content

    def clean_title(self, text):
        if not text: return "Untitled"
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove common buttons text
        text = re.sub(r'(Play|View|Download|Watch|Video|PDF|Class)', '', text, flags=re.IGNORECASE)
        return text.strip() if text.strip() else "Untitled"

    def parse(self, html_content):
        # 1. Decrypt
        final_html = self.detect_and_decrypt(html_content)
        soup = BeautifulSoup(final_html, 'lxml')
        
        links_data = {'videos': [], 'pdfs': [], 'others': []}
        seen_urls = set()

        page_title = soup.title.string.strip() if soup.title else "Extracted_Content"

        # 2. Strategy A: Standard Tags (<a>)
        for a in soup.find_all('a'):
            raw_text = a.get_text()
            title = self.clean_title(raw_text)
            
            # Check href
            href = a.get('href')
            if href: self.process_link(title, href, links_data, seen_urls)
            
            # Check onclick (Critical for PDFs in these batches)
            onclick = a.get('onclick')
            if onclick:
                # Catch patterns like viewPdf('url') or playVideo('url')
                urls = re.findall(r"['\"](https?://[^'\"]+)['\"]", onclick)
                for url in urls:
                    # If title is empty, try to find a sibling text
                    if title == "Untitled":
                        parent = a.find_parent()
                        if parent: title = self.clean_title(parent.get_text())
                    self.process_link(title, url, links_data, seen_urls)

        # 3. Strategy B: Global Regex Sweep (Fallback for hidden links)
        # This finds links that are just in the script variables but not in <a> tags
        # Format: "Title" : "URL" or just URLs
        
        # Find all https links in the raw text
        raw_links = re.findall(r'(https?://[^\s<>"\';]+)', final_html)
        for url in raw_links:
            # We assume untitled for raw regex matches unless we can map them
            # This is a fallback to ensure NOTHING is missed
            self.process_link("Direct Link (Raw)", url, links_data, seen_urls)

        return page_title, links_data

    def process_link(self, title, url, data, seen_urls):
        url = url.strip()
        if not url.startswith('http'): return
        if url in seen_urls: return
        
        seen_urls.add(url)
        item = {'title': title, 'url': url}

        # Categorization Logic
        url_lower = url.lower()
        title_lower = title.lower()

        is_video = any(x in url_lower for x in self.video_ext)
        is_pdf = any(x in url_lower for x in self.pdf_ext)
        
        # If URL is generic, check title
        if not is_video and not is_pdf:
            if 'pdf' in title_lower or 'notes' in title_lower:
                is_pdf = True
            elif 'video' in title_lower or 'class' in title_lower:
                is_video = True

        if is_video:
            data['videos'].append(item)
        elif is_pdf:
            data['pdfs'].append(item)
        else:
            # If it's a very long link, it might be a signed URL, put in others
            data['others'].append(item)

    def generate_txt(self, title, data):
        lines = []
        lines.append(f"📂 {title}")
        lines.append("="*40 + "\n")
        
        # Format: Name : Link
        
        if data['videos']:
            lines.append(f"🎬 VIDEOS ({len(data['videos'])})")
            for v in data['videos']:
                lines.append(f"{v['title']} : {v['url']}")
            lines.append("")
            
        if data['pdfs']:
            lines.append(f"📚 PDFs / NOTES ({len(data['pdfs'])})")
            for p in data['pdfs']:
                lines.append(f"{p['title']} : {p['url']}")
            lines.append("")
            
        if data['others']:
            lines.append(f"🔗 OTHER LINKS ({len(data['others'])})")
            for o in data['others']:
                lines.append(f"{o['title']} : {o['url']}")
                
        return "\n".join(lines)

# ==================== BOT HANDLERS ====================
parser = NuclearHTMLParser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("☢️ **Nuclear HTML Parser Active**\nDrop your HTML file. I will extract Videos, PDFs, and everything else.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file_name = doc.file_name
    
    if not (file_name.endswith('.html') or file_name.endswith('.htm') or file_name.endswith('.txt')):
        await update.message.reply_text("❌ Please send HTML file.")
        return

    status_msg = await update.message.reply_text("🔄 **Scanning Deep Layers...**")
    
    try:
        new_file = await context.bot.get_file(doc.file_id)
        file_content = await new_file.download_as_bytearray()
        html_text = file_content.decode('utf-8', errors='ignore')
        
        title, links = parser.parse(html_text)
        output_text = parser.generate_txt(title, links)
        
        total_found = len(links['videos']) + len(links['pdfs']) + len(links['others'])
        
        if total_found == 0:
            await status_msg.edit_text("⚠️ Found 0 links. The file might be empty or format is unsupported.")
            return
            
        out_filename = f"{file_name}_extracted.txt"
        with open(out_filename, "w", encoding="utf-8") as f:
            f.write(output_text)
            
        with open(out_filename, "rb") as f:
            await update.message.reply_document(
                document=f,
                caption=f"✅ **Extraction Success**\nTotal: {total_found}\n📹 Vid: {len(links['videos'])}\n📚 PDF: {len(links['pdfs'])}\n🔗 Oth: {len(links['others'])}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        os.remove(out_filename)
        await status_msg.delete()
        
    except Exception as e:
        logger.error(e)
        await status_msg.edit_text(f"❌ Error: {str(e)}")

# ==================== SERVER ====================
async def health_check(request):
    return web.Response(text="Alive", status=200)

async def start_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

async def main():
    await start_server()
    if not BOT_TOKEN: return
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    if WEBHOOK_URL:
        await app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    
    stop_signal = asyncio.Future()
    await stop_signal

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
                
