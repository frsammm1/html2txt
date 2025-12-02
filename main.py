#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter - UNIVERSAL SMART PARSER
✨ Features:
   - Separates VIDEOS, PDFS, MOCK TESTS, IMAGES
   - Fixes "1", "2" titles by finding real text nearby
   - auto-detects structure differences
"""

import os
import re
import logging
import base64
import asyncio
import urllib.parse
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

class UniversalParser:
    def __init__(self):
        # Words to ignore when finding titles
        self.ignore_words = [
            'view', 'play', 'download', 'watch', 'pdf', 'notes', 'video', 
            'click here', 'open', 'original', 'quality', '360p', '480p', '720p', '1080p',
            'class png', 'live', 'read online', 'attempt', 'start', 'test'
        ]
        
    def clean_url(self, url):
        """Cleans and fixes URLs"""
        if not url: return None
        # Marshmallow/Wrapper fix
        if "video=" in url:
            try:
                parsed = urllib.parse.urlparse(url)
                qs = urllib.parse.parse_qs(parsed.query)
                if 'video' in qs: return qs['video'][0]
            except: pass
            
        # Fix Double Extensions
        if '.m3u8' in url: url = url.split('.m3u8')[0] + '.m3u8'
        if '.pdf' in url: url = url.split('.pdf')[0] + '.pdf'
        
        return url.strip()

    def is_junk_title(self, text):
        """Checks if a title is just a number or generic word"""
        if not text: return True
        text = text.strip().lower()
        
        # If it's just digits like "1", "2", "01"
        if text.replace('.', '').isdigit(): return True
        
        # If it's a single letter
        if len(text) < 2: return True
        
        # If it's a generic action word
        if text in self.ignore_words: return True
        
        return False

    def get_smart_title(self, element):
        """
        🧠 Logic:
        1. Check JS arguments (High Priority)
        2. Check Parent Text - but remove the Button Text and Indexes (1., 2.)
        """
        # 1. Try JS Argument (e.g. openVideo('...','Title'))
        if element.has_attr('onclick'):
            matches = re.findall(r"['\"]([^'\"]+)['\"]", element['onclick'])
            if len(matches) >= 3:
                candidate = matches[-1].strip()
                if not self.is_junk_title(candidate):
                    return candidate

        # 2. DOM Walking (Parent/Grandparent)
        current = element
        button_text = element.get_text(" ", strip=True)
        
        for _ in range(3): # Go up 3 levels
            parent = current.parent
            if not parent: break
            
            # Get full text of the container
            full_text = parent.get_text(" ", strip=True)
            
            # Remove the button text (e.g. remove "Watch")
            clean_text = full_text.replace(button_text, "")
            
            # Split by newlines or common separators to find the longest part
            # This helps separate "1." from "Noun Class"
            parts = re.split(r'[\n\t•|]+', clean_text)
            
            best_part = "Untitled"
            max_len = 0
            
            for part in parts:
                part = part.strip()
                # Remove leading numbers like "1.", "02"
                part = re.sub(r'^\d+[\.\-\s]+', '', part)
                
                if not self.is_junk_title(part) and len(part) > max_len:
                    max_len = len(part)
                    best_part = part
            
            if best_part != "Untitled":
                return best_part
            
            current = parent

        return "Untitled_Topic"

    def parse(self, html_content):
        # Basic Decryption check
        if "encodedContent" in html_content:
            try:
                # Basic XOR pattern match (if simple JS)
                pass 
            except: pass

        soup = BeautifulSoup(html_content, 'lxml')
        links_data = []
        seen_urls = set()

        # Find all interactive elements
        targets = soup.find_all(lambda tag: tag.has_attr('href') or tag.has_attr('onclick'))

        for tag in targets:
            url = None
            if tag.has_attr('href'): url = tag['href']
            elif tag.has_attr('onclick'):
                m = re.search(r"['\"](https?://[^'\"]+)['\"]", tag['onclick'])
                if m: url = m.group(1)

            if url and "http" in url:
                clean_url = self.clean_url(url)
                
                # JUNK FILTER
                if any(x in clean_url for x in ['w3.org', 'cloudflare', 'javascript:', 'jquery', 'facebook', 'twitter']):
                    continue
                
                if clean_url in seen_urls: continue
                seen_urls.add(clean_url)
                
                # Get Title
                title = self.get_smart_title(tag)
                # Cleanup Title Presentation
                title = title.replace('_', ' ').strip()
                
                # CATEGORIZATION LOGIC
                l_type = 'other'
                u_low = clean_url.lower()
                t_low = title.lower()
                
                # 1. Mock Tests (Priority)
                if any(x in u_low for x in ['test', 'quiz', 'mock', 'exam']) or \
                   any(x in t_low for x in ['mock', 'quiz', 'test series']):
                    l_type = 'mock'
                
                # 2. Videos
                elif any(x in u_low for x in ['.mp4', '.m3u8', 'youtu', 'vimeo', 'manifest']):
                    l_type = 'video'
                    
                # 3. PDFs / Notes
                elif any(x in u_low for x in ['.pdf', 'drive.google', 'doc', 'notes', 'sheet']):
                    l_type = 'pdf'
                    
                # 4. Images
                elif any(x in u_low for x in ['.jpg', '.png', '.jpeg']):
                    l_type = 'image'
                    
                # 5. Others (Zip, Rar)
                elif '.zip' in u_low or '.rar' in u_low:
                    l_type = 'other'
                
                # Skip if it's still 'other' and looks like a generic webpage link (unless it has a good title)
                if l_type == 'other' and (title == "Untitled_Topic" or len(title) < 4):
                    continue

                links_data.append({'title': title, 'url': clean_url, 'type': l_type})
        
        return links_data

    def generate_txt(self, filename, links):
        lines = [f"📂 Source: {filename}", "="*50, ""]
        
        # Categorized Lists
        videos = [x for x in links if x['type'] == 'video']
        pdfs = [x for x in links if x['type'] == 'pdf']
        mocks = [x for x in links if x['type'] == 'mock']
        images = [x for x in links if x['type'] == 'image']
        others = [x for x in links if x['type'] == 'other']
        
        if videos:
            lines.append(f"🎬 VIDEOS ({len(videos)})")
            lines.append("-" * 20)
            for v in videos: lines.append(f"{v['title']} : {v['url']}")
            lines.append("")
            
        if pdfs:
            lines.append(f"📚 PDFS / NOTES ({len(pdfs)})")
            lines.append("-" * 20)
            for p in pdfs: lines.append(f"{p['title']} : {p['url']}")
            lines.append("")

        if mocks:
            lines.append(f"📝 MOCK TESTS / QUIZZES ({len(mocks)})")
            lines.append("-" * 20)
            for m in mocks: lines.append(f"{m['title']} : {m['url']}")
            lines.append("")

        if images:
            lines.append(f"🖼 IMAGES ({len(images)})")
            for i in images: lines.append(f"{i['title']} : {i['url']}")
            lines.append("")
            
        if others:
            lines.append(f"🔗 OTHER LINKS ({len(others)})")
            for o in others: lines.append(f"{o['title']} : {o['url']}")
            
        return "\n".join(lines)

# ==================== BOT SETUP ====================
parser = UniversalParser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 **Universal Smart Bot**\nSupports: Videos, PDFs, Mock Tests.\nSend HTML file.")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(('.html', '.htm', '.txt')):
        await update.message.reply_text("❌ Send HTML file only.")
        return

    msg = await update.message.reply_text("⚡ **Parsing & Categorizing...**")
    
    try:
        f = await context.bot.get_file(doc.file_id)
        c = await f.download_as_bytearray()
        content = c.decode('utf-8', errors='ignore')
        
        links = parser.parse(content)
        
        if not links:
            await msg.edit_text("❌ No links found in this file.")
            return
            
        out_txt = parser.generate_txt(doc.file_name, links)
        out_name = f"{doc.file_name}_Smart.txt"
        
        with open(out_name, "w", encoding="utf-8") as f:
            f.write(out_txt)
            
        stats = (f"✅ **Done!**\n"
                 f"🎬 Videos: {len([x for x in links if x['type']=='video'])}\n"
                 f"📚 PDFs: {len([x for x in links if x['type']=='pdf'])}\n"
                 f"📝 Mocks: {len([x for x in links if x['type']=='mock'])}")
                 
        with open(out_name, "rb") as f:
            await update.message.reply_document(document=f, caption=stats, parse_mode=ParseMode.MARKDOWN)
            
        os.remove(out_name)
        await msg.delete()
        
    except Exception as e:
        logger.error(e)
        await msg.edit_text("❌ Error processing file.")

# ==================== SERVER ====================
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
        
