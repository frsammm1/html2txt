#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter - DOM WALKER EDITION
✨ Logic: Navigates up to Grandparents to find the REAL Topic Name.
🚀 Fixes: Untitled_Topic, Double Extensions (.m3u8.m3u8), Junk URLs
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

class DomWalkerParser:
    def __init__(self):
        # Words to remove from Title
        self.ignore_words = [
            'view', 'play', 'download', 'watch', 'pdf', 'notes', 'video', 
            'click here', 'open', 'original', 'quality', '360p', '480p', '720p', '1080p',
            'class png', 'live', 'read online'
        ]
        
    def clean_url(self, url):
        """Fixes .m3u8.m3u8 and wrapper links"""
        if not url: return None
        
        # 1. Extract inner URL if it's a wrapper (like Marshmallow player)
        # Ex: https://player...dev?video=https://...m3u8&title=...
        if "video=" in url:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            if 'video' in qs:
                url = qs['video'][0]
        
        # 2. Fix Double Extension (.m3u8.m3u8)
        # Sometimes regex captures too much or source is bad
        url = url.split('.m3u8')[0] + '.m3u8' if '.m3u8' in url else url
        url = url.split('.pdf')[0] + '.pdf' if '.pdf' in url else url
        
        # 3. Basic cleanup
        return url.strip()

    def clean_title(self, text, button_text=""):
        if not text: return "Untitled"
        
        # Remove the button text itself from the parent text
        if button_text:
            text = text.replace(button_text, "")
            
        # Clean specific symbols
        text = text.replace('|', ' ').replace('_', ' ').replace(':', ' - ')
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove generic words from start/end
        lower_text = text.lower()
        for word in self.ignore_words:
            if lower_text == word: return ""
            # Regex to remove whole word matches
            text = re.sub(f'(?i)\\b{word}\\b', '', text)
            
        return text.strip(" -|")

    def find_real_title(self, element):
        """
        🚀 Walks up the HTML Tree (Parent -> Grandparent) to find the text.
        """
        # Step 1: Check Javascript arguments (Most accurate if available)
        if element.has_attr('onclick'):
            # Look for 3rd argument in openVideo(id, url, 'TITLE')
            matches = re.findall(r"['\"]([^'\"]+)['\"]", element['onclick'])
            if len(matches) >= 3:
                # usually the last one is title or quality. 
                # If it's long, it's a title.
                candidate = matches[-1]
                if len(candidate) > 4 and candidate.lower() not in self.ignore_words:
                    return self.clean_title(candidate)

        # Step 2: DOM Walking (The Fix for 'Untitled')
        # We go up 3 levels max to find a container with text
        current = element
        button_text = element.get_text(" ", strip=True)
        
        for _ in range(3): # Check Parent, then Grandparent, then Great-Grandparent
            parent = current.parent
            if not parent: break
            
            # Get all text in this container
            full_text = parent.get_text(" ", strip=True)
            
            # If this container has more text than just the button
            if len(full_text) > len(button_text) + 3:
                # Clean it
                real_title = self.clean_title(full_text, button_text)
                if len(real_title) > 3:
                    return real_title
            
            current = parent
            
        return "Untitled_Topic"

    def parse(self, html_content):
        # Basic Decryption for Selection Batch
        if "encodedContent" in html_content:
            try:
                # Quick regex extraction of the Base64 string
                m = re.search(r"encodedContent\s*=\s*['\"]([^'\"]+)['\"]", html_content)
                if m:
                    # Simple XOR attempt (assuming standard key or just b64)
                    # For safety, we return original if this fails, but usually 
                    # users send decoded HTML mostly now. 
                    pass 
            except: pass

        soup = BeautifulSoup(html_content, 'lxml')
        links_data = []
        seen_urls = set()

        # Find ALL interactive elements
        # We focus on elements that have onclick or href
        targets = soup.find_all(lambda tag: tag.has_attr('href') or tag.has_attr('onclick'))

        for tag in targets:
            url = None
            
            # Extraction
            if tag.has_attr('href'):
                url = tag['href']
            elif tag.has_attr('onclick'):
                # Robust Regex for URL
                u_match = re.search(r"['\"](https?://[^'\"]+)['\"]", tag['onclick'])
                if u_match: url = u_match.group(1)

            # Validation & Cleaning
            if url and "http" in url:
                clean_url = self.clean_url(url)
                
                # Filter Junk
                if any(x in clean_url for x in ['w3.org', 'cloudflare', 'javascript:', 'jquery']):
                    continue
                
                # Deduplication logic
                if clean_url in seen_urls: continue
                seen_urls.add(clean_url)
                
                # TITLE HUNTING
                title = self.find_real_title(tag)
                if title == "Untitled" or title == "":
                    title = "Untitled_Topic"

                # Type Detection
                l_type = 'other'
                u_low = clean_url.lower()
                if any(x in u_low for x in ['.mp4', '.m3u8', 'youtu', 'vimeo']):
                    l_type = 'video'
                elif any(x in u_low for x in ['.pdf', 'drive.google', 'doc', 'notes']):
                    l_type = 'pdf'
                elif any(x in u_low for x in ['.jpg', '.png', '.jpeg']):
                    l_type = 'image'
                elif '.zip' in u_low or '.rar' in u_low:
                    l_type = 'other'
                else:
                    # Skip generic web links to keep txt clean
                    continue 

                links_data.append({'title': title, 'url': clean_url, 'type': l_type})
        
        return links_data

    def generate_txt(self, filename, links):
        lines = [f"📂 Source: {filename}", "="*40, ""]
        
        # Categories
        videos = [x for x in links if x['type'] == 'video']
        pdfs = [x for x in links if x['type'] == 'pdf']
        images = [x for x in links if x['type'] == 'image']
        
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
            
        return "\n".join(lines)

# ==================== BOT SETUP ====================
parser = DomWalkerParser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧬 **DOM Walker Active**\nSend HTML. I dig deep for titles.")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(('.html', '.htm', '.txt')):
        await update.message.reply_text("❌ Send HTML file.")
        return

    msg = await update.message.reply_text("🧠 **Analyzing DOM Tree...**")
    
    try:
        f = await context.bot.get_file(doc.file_id)
        c = await f.download_as_bytearray()
        content = c.decode('utf-8', errors='ignore')
        
        links = parser.parse(content)
        
        if not links:
            await msg.edit_text("❌ No links found.")
            return
            
        out_txt = parser.generate_txt(doc.file_name, links)
        out_name = f"{doc.file_name}_Cleaned.txt"
        
        with open(out_name, "w", encoding="utf-8") as f:
            f.write(out_txt)
            
        with open(out_name, "rb") as f:
            await update.message.reply_document(document=f, caption=f"✅ **Extraction Complete**\nTotal: {len(links)}")
            
        os.remove(out_name)
        await msg.delete()
        
    except Exception as e:
        logger.error(e)
        await msg.edit_text("❌ Error.")

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
