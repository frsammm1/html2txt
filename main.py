#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter Bot - ULTIMATE HARDCORE Edition
✨ Multi-Strategy Parser | Auto-Decryption | No Link Left Behind
🚀 Optimized for Render.com
"""

import os
import re
import logging
import base64
import asyncio
import urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from aiohttp import web

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# अगर रेंडर पर PORT env नहीं मिलता तो डिफॉल्ट 8080
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# ==================== LOGGING ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class HardcoreHTMLParser:
    """🔥 Decrypts & Extracts links from any HTML"""
    
    def __init__(self):
        # Video/Doc identifiers
        self.video_extensions = ['.m3u8', '.mp4', '.avi', '.mkv', '.mov', '.webm', 'jwplayer', 'vimeo', 'youtube', 'youtu.be']
        self.pdf_extensions = ['.pdf', 'drive.google.com', 'docs.google.com']
        
    def xor_decrypt(self, encoded_b64, key):
        """Selection Batch वाली specific XOR decryption"""
        try:
            # Step 1: Base64 Decode
            encrypted_data = base64.b64decode(encoded_b64).decode('latin1')
            
            # Step 2: XOR Decrypt
            result = []
            key_len = len(key)
            for i in range(len(encrypted_data)):
                char_code = ord(encrypted_data[i]) ^ ord(key[i % key_len])
                result.append(chr(char_code))
            
            decrypted_layer = "".join(result)
            
            # Step 3: Base64 Decode again (Cleaned)
            # JS code replaces non-base64 chars, but usually python's b64decode handles padding or ignores junk if strict=False not set, 
            # but let's try raw decode first.
            decrypted_content = base64.b64decode(decrypted_layer).decode('utf-8')
            return decrypted_content
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None

    def extract_secret_key(self, html_content):
        """JS से Key components निकालकर Key बनाता है"""
        # Default key just in case extraction fails but patterns match
        default_key = "TusharSuperSecreT2025!" 
        
        try:
            p1 = re.search(r'let\s+P1\s*=\s*["\']([^"\']+)["\']', html_content)
            p2 = re.search(r'let\s+P2\s*=\s*["\']([^"\']+)["\']', html_content)
            p3 = re.search(r'let\s+P3_Reversed\s*=\s*["\']([^"\']+)["\']', html_content)
            p4 = re.search(r'let\s+P4\s*=\s*["\']([^"\']+)["\']', html_content)
            
            if p1 and p2 and p3 and p4:
                part1 = p1.group(1)
                part2 = p2.group(1)
                part3 = p3.group(1)[::-1] # Reverse it
                part4 = p4.group(1)
                # Logic: P4 + P1 + P2 + P3_Reversed
                return f"{part4}{part1}{part2}{part3}"
            return default_key
        except:
            return default_key

    def detect_and_decrypt(self, html_content):
        """Checks for encryption and returns plain HTML"""
        if "const encodedContent =" in html_content or "var encodedContent =" in html_content:
            logger.info("🔒 Encrypted content detected! Attempting decryption...")
            
            # Extract Encoded String
            match = re.search(r"encodedContent\s*=\s*['\"]([^'\"]+)['\"]", html_content)
            if match:
                encoded_str = match.group(1)
                key = self.extract_secret_key(html_content)
                logger.info(f"🔑 Using Key: {key}")
                
                decrypted = self.xor_decrypt(encoded_str, key)
                if decrypted:
                    logger.info("🔓 Decryption successful!")
                    return decrypted
                else:
                    logger.error("❌ Decryption returned empty.")
        
        return html_content

    def clean_text(self, text):
        if not text: return "Untitled"
        # Remove garbage
        text = re.sub(r'\s+', ' ', text).strip()
        text = text.replace('Mendax', '').replace('Download', '').replace('Watch', '').replace('Play', '')
        return text[:100]

    def parse(self, html_content):
        # 1. Decrypt if needed
        processed_html = self.detect_and_decrypt(html_content)
        
        soup = BeautifulSoup(processed_html, 'lxml')
        links_data = {'videos': [], 'pdfs': [], 'others': []}
        
        # 2. Extract Title
        page_title = "Extracted_Links"
        if soup.title:
            page_title = soup.title.string.strip()
            
        # 3. General Extraction Strategy (Regex + Soup)
        # यह हर तरह के लिंक को ढूंढेगा चाहे वो href में हो, onclick में हो या टेक्स्ट में
        
        # a) All <a> tags
        for a in soup.find_all('a'):
            title = self.clean_text(a.get_text())
            
            # Check href
            href = a.get('href')
            if href and href != '#' and not href.startswith('javascript'):
                self.categorize_link(title, href, links_data)
                
            # Check onclick (Super 100 Batch style)
            onclick = a.get('onclick')
            if onclick:
                # Extract URL inside playVideo('URL') or viewPDF('URL')
                urls = re.findall(r"['\"](https?://[^'\"]+)['\"]", onclick)
                for url in urls:
                    self.categorize_link(title, url, links_data)

        # b) Regex Fallback for loose links (अगर HTML बहुत खराब है)
        if len(links_data['videos']) == 0 and len(links_data['pdfs']) == 0:
             raw_urls = re.findall(r'(https?://[^\s<>"\'()]+)', processed_html)
             for url in raw_urls:
                 self.categorize_link("Unknown Link", url, links_data)

        return page_title, links_data

    def categorize_link(self, title, url, data):
        # Remove duplicates based on URL
        url = url.strip()
        
        # Check validity
        if not url.startswith('http'): return

        # Check duplication
        for cat in data.values():
            for item in cat:
                if item['url'] == url:
                    return

        item = {'title': title, 'url': url}
        
        if any(x in url.lower() for x in self.video_extensions):
            data['videos'].append(item)
        elif any(x in url.lower() for x in self.pdf_extensions):
            data['pdfs'].append(item)
        else:
            data['others'].append(item)

    def generate_txt(self, title, data):
        lines = []
        lines.append(f"📂 {title}")
        lines.append("="*40 + "\n")
        
        if data['videos']:
            lines.append(f"🎬 VIDEOS ({len(data['videos'])})")
            for idx, v in enumerate(data['videos'], 1):
                # Format: Topic Name : URL
                # User asked for: "Name : URL" format basically
                name = v['title'] if v['title'] != "Untitled" else f"Video {idx}"
                lines.append(f"{name} : {v['url']}")
            lines.append("")
            
        if data['pdfs']:
            lines.append(f"📚 PDFs ({len(data['pdfs'])})")
            for idx, p in enumerate(data['pdfs'], 1):
                name = p['title'] if p['title'] != "Untitled" else f"PDF {idx}"
                lines.append(f"{name} : {p['url']}")
            lines.append("")
            
        if data['others']:
            lines.append(f"🔗 OTHERS ({len(data['others'])})")
            for idx, o in enumerate(data['others'], 1):
                name = o['title'] if o['title'] != "Untitled" else f"Link {idx}"
                lines.append(f"{name} : {o['url']}")
                
        return "\n".join(lines)

# ==================== BOT HANDLERS ====================
parser = HardcoreHTMLParser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 Hardcore HTML2TXT Bot Online!\nकोइ भी HTML फाइल भेजो, एन्क्रिप्टेड भी चलेगी।")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file_name = doc.file_name
    
    if not (file_name.endswith('.html') or file_name.endswith('.htm') or file_name.endswith('.txt')):
        await update.message.reply_text("❌ सिर्फ HTML या TXT फाइल भेजें।")
        return

    status_msg = await update.message.reply_text("⏳ Processing... (Decrypting if needed)")
    
    try:
        new_file = await context.bot.get_file(doc.file_id)
        file_content = await new_file.download_as_bytearray()
        html_text = file_content.decode('utf-8', errors='ignore')
        
        # Parse
        title, links = parser.parse(html_text)
        
        # Generate TXT
        output_text = parser.generate_txt(title, links)
        
        if len(links['videos']) + len(links['pdfs']) + len(links['others']) == 0:
            await status_msg.edit_text("⚠️ कोई लिंक नहीं मिला। शायद फाइल का फॉर्मेट बहुत अलग है।")
            return
            
        # Save to file
        out_filename = f"{file_name}_converted.txt"
        with open(out_filename, "w", encoding="utf-8") as f:
            f.write(output_text)
            
        # Reply
        total = len(links['videos']) + len(links['pdfs']) + len(links['others'])
        with open(out_filename, "rb") as f:
            await update.message.reply_document(
                document=f,
                caption=f"✅ **Extraction Complete**\nTotal Links: {total}\nVideos: {len(links['videos'])}\nPDFs: {len(links['pdfs'])}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        os.remove(out_filename)
        await status_msg.delete()
        
    except Exception as e:
        logger.error(e)
        await status_msg.edit_text(f"❌ Error: {str(e)}")

# ==================== SERVER FOR RENDER ====================
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
    logger.info(f"🌐 Server started on port {PORT}")

async def main():
    # Start Web Server first (Important for Render)
    await start_server()
    
    # Start Bot
    if not BOT_TOKEN:
        logger.error("Bot token missing!")
        return

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Webhook mode (Recommended for Render)
    if WEBHOOK_URL:
        logger.info(f"Using Webhook: {WEBHOOK_URL}")
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        # Render manages SSL, so usually no need for internal SSL handling
        # But typically python-telegram-bot runs its own webhook server or uses the existing aiohttp app.
        # For simplicity on Render free tier, Polling + Separate Healthcheck server is safest to avoid port conflicts
        # or complex setup. 
        # We will use Polling here as it's easier to set up with the side-car server above.
        # If you strictly want webhook, you need to integrate it into the aiohttp app.
        
    # Using Polling for stability on free tier (Webhook often tricky with ports on simple scripts)
    logger.info("🚀 Bot started (Polling mode)")
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    # Keep alive
    stop_signal = asyncio.Future()
    await stop_signal

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
                
