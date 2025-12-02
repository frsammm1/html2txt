#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter Bot - GOD MODE PRO
✨ Logic: Extracts Titles from JS Arguments & Parent Containers
🚀 Fixes: 'Original' names, Missing PDF names, Junk Links
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

class UltraParser:
    def __init__(self):
        # Ignore these words in titles if they appear alone
        self.ignore_titles = [
            'view', 'play', 'download', 'watch', 'pdf', 'notes', 'video', 
            'click here', 'open', 'original', 'quality', '360p', '480p', '720p', '1080p'
        ]
        # Valid extensions for OTHERS category (to avoid junk)
        self.valid_other_exts = ['.zip', '.rar', '.7z', '.tar', '.iso', '.apk', '.exe']

    def xor_decrypt(self, encoded_b64, key):
        try:
            encrypted_data = base64.b64decode(encoded_b64).decode('latin1')
            result = []
            key_len = len(key)
            for i in range(len(encrypted_data)):
                char_code = ord(encrypted_data[i]) ^ ord(key[i % key_len])
                result.append(chr(char_code))
            return base64.b64decode("".join(result)).decode('utf-8')
        except: return None

    def extract_secret_key(self, html_content):
        default = "TusharSuperSecreT2025!"
        try:
            p4 = re.search(r'let\s+P4\s*=\s*["\']([^"\']+)["\']', html_content)
            p1 = re.search(r'let\s+P1\s*=\s*["\']([^"\']+)["\']', html_content)
            p2 = re.search(r'let\s+P2\s*=\s*["\']([^"\']+)["\']', html_content)
            p3 = re.search(r'let\s+P3_Reversed\s*=\s*["\']([^"\']+)["\']', html_content)
            if p4 and p1 and p2 and p3:
                return f"{p4.group(1)}{p1.group(1)}{p2.group(1)}{p3.group(1)[::-1]}"
            return default
        except: return default

    def clean_title(self, text):
        if not text: return "Untitled"
        
        # 1. Remove Symbols that confuse extraction bots
        # Replace | _ with space
        text = text.replace('|', ' ').replace('_', ' ').replace(':', ' - ')
        
        # 2. Basic Cleanup
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 3. Remove Button keywords from the end or start
        lower_text = text.lower()
        for word in self.ignore_titles:
            # If the title IS just the word, ignore it (handled later)
            if lower_text == word: return "" 
            # Remove "Download" from "Download Physics Notes"
            text = re.sub(f'(?i)^{word}\s+', '', text)
            text = re.sub(f'(?i)\s+{word}$', '', text)
            
        return text.strip()

    def get_title_from_js(self, onclick_text):
        """Extracts title from function calls like openVideoPopup(id, url, 'TITLE')"""
        if not onclick_text: return None
        
        # Pattern for 3 arguments inside quotes
        # Looks for: func('arg1', 'arg2', 'TARGET')
        matches = re.findall(r"['\"]([^'\"]+)['\"]", onclick_text)
        if len(matches) >= 3:
            # Usually the 3rd arg is title in these templates
            possible_title = matches[2] 
            if len(possible_title) > 3 and not possible_title.startswith('http'):
                return self.clean_title(possible_title)
        return None

    def get_best_title(self, tag):
        """Finds the best title by looking at JS, siblings, or parent"""
        
        # Priority 1: JS Argument (Highest accuracy for Aman Vashisth files)
        if tag.has_attr('onclick'):
            js_title = self.get_title_from_js(tag['onclick'])
            if js_title: return js_title

        # Priority 2: Tag's own text (if it's not generic)
        text = self.clean_title(tag.get_text(" ", strip=True))
        if text and text.lower() not in self.ignore_titles:
            return text

        # Priority 3: Previous Sibling (e.g. <strong>Title</strong> <a>Link</a>)
        prev = tag.find_previous_sibling()
        if prev:
            prev_text = self.clean_title(prev.get_text(" ", strip=True))
            if len(prev_text) > 4: return prev_text

        # Priority 4: Parent Container Text (The "Card" method)
        # Finds the longest text in the parent div that ISN'T the button text
        parent = tag.parent
        if parent:
            parent_text = parent.get_text(" ", strip=True)
            # Remove the button text from parent text to leave only the title
            button_text = tag.get_text(" ", strip=True)
            clean_parent = parent_text.replace(button_text, "").strip()
            title_candidate = self.clean_title(clean_parent)
            if len(title_candidate) > 4: return title_candidate

        return "Untitled_Topic"

    def parse(self, html_content):
        # Decryption Phase
        if "encodedContent" in html_content:
            key = self.extract_secret_key(html_content)
            match = re.search(r"encodedContent\s*=\s*['\"]([^'\"]+)['\"]", html_content)
            if match:
                dec = self.xor_decrypt(match.group(1), key)
                if dec: html_content = dec

        soup = BeautifulSoup(html_content, 'lxml')
        links_data = []
        seen_urls = set()

        # Find all clickable elements
        elements = soup.find_all(['a', 'button', 'div', 'span'])

        for tag in elements:
            url = None
            
            # Extract URL
            if tag.name == 'a' and tag.get('href'):
                url = tag.get('href')
            elif tag.has_attr('onclick'):
                # Extract HTTP/HTTPS url
                u_match = re.search(r"['\"](https?://[^'\"]+)['\"]", tag['onclick'])
                if u_match: url = u_match.group(1)

            if url and url.startswith('http') and url not in seen_urls:
                # FILTER JUNK
                if any(x in url for x in ['w3.org', 'cloudflare', 'javascript:', 'jquery']):
                    continue
                
                seen_urls.add(url)
                title = self.get_best_title(tag)
                
                # Categorize
                l_type = 'other'
                u_low = url.lower()
                
                if any(x in u_low for x in ['.mp4', '.m3u8', 'youtu', 'vimeo', 'playlist', 'manifest']):
                    l_type = 'video'
                elif any(x in u_low for x in ['.pdf', 'drive.google', 'doc', 'ppt', 'notes']):
                    l_type = 'pdf'
                elif any(x in u_low for x in ['.jpg', '.png', '.jpeg']):
                    l_type = 'image' # New Category
                # Check for valid OTHER files (zips etc)
                elif any(x in u_low for x in self.valid_other_exts):
                    l_type = 'other'
                else:
                    # If it's a generic web link, we skip it unless user wants EVERYTHING
                    # For now, skipping generic html links to avoid clutter
                    continue 

                links_data.append({'title': title, 'url': url, 'type': l_type})
        
        return links_data

    def generate_txt(self, filename, links):
        lines = [f"📂 Source: {filename}", "="*40, ""]
        
        # Grouping
        videos = [x for x in links if x['type'] == 'video']
        pdfs = [x for x in links if x['type'] == 'pdf']
        images = [x for x in links if x['type'] == 'image']
        others = [x for x in links if x['type'] == 'other']
        
        if videos:
            lines.append(f"🎬 VIDEOS ({len(videos)})")
            for v in videos: lines.append(f"{v['title']} : {v['url']}")
            lines.append("")
            
        if pdfs:
            lines.append(f"📚 PDFS / NOTES ({len(pdfs)})")
            for p in pdfs: lines.append(f"{p['title']} : {p['url']}")
            lines.append("")

        if images:
            lines.append(f"🖼 IMAGES ({len(images)})")
            for i in images: lines.append(f"{i['title']} : {i['url']}")
            lines.append("")
            
        if others:
            lines.append(f"🔗 OTHERS ({len(others)})")
            for o in others: lines.append(f"{o['title']} : {o['url']}")
            
        return "\n".join(lines)

# ==================== BOT ====================
parser = UltraParser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 **Bot Ready**\nSend HTML. I will extract Full Names and Links.")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(('.html', '.htm', '.txt')):
        await update.message.reply_text("❌ Only HTML/TXT allowed.")
        return

    msg = await update.message.reply_text("⚙️ **Processing...**")
    
    try:
        f = await context.bot.get_file(doc.file_id)
        c = await f.download_as_bytearray()
        content = c.decode('utf-8', errors='ignore')
        
        links = parser.parse(content)
        
        if not links:
            await msg.edit_text("❌ No valid links found.")
            return
            
        out_txt = parser.generate_txt(doc.file_name, links)
        out_name = f"{doc.file_name}_Fixed.txt"
        
        with open(out_name, "w", encoding="utf-8") as f:
            f.write(out_txt)
            
        with open(out_name, "rb") as f:
            await update.message.reply_document(document=f, caption="✅ Done")
            
        os.remove(out_name)
        await msg.delete()
        
    except Exception as e:
        logger.error(e)
        await msg.edit_text("❌ Error.")

# ==================== MAIN ====================
async def health(r): return web.Response(text="OK")

async def main():
    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_get('/health', health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    
    if not BOT_TOKEN: return
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    
    if WEBHOOK_URL: await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
