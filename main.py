#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter - DEEP DOM TREE TRAVERSAL
✨ Fixes: Finds real titles hidden in parent divs (e.g. Aman Vashisth Batch)
🚀 Logic: Treats Mock Test VIDEOS as VIDEOS, not Quizzes.
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

class DeepDomParser:
    def __init__(self):
        # Words that are NOT titles
        self.ignore_list = [
            'view', 'play', 'download', 'watch', 'pdf', 'notes', 'video', 
            'click here', 'open', 'original', 'quality', '360p', '480p', '720p', '1080p',
            'class png', 'live', 'read online', 'attempt', 'start'
        ]
        
    def clean_url(self, url):
        if not url: return None
        # Fix Marshmallow wrappers
        if "video=" in url:
            try:
                parsed = urllib.parse.urlparse(url)
                qs = urllib.parse.parse_qs(parsed.query)
                if 'video' in qs: return qs['video'][0]
            except: pass
        
        # Remove double extensions
        if '.m3u8' in url: url = url.split('.m3u8')[0] + '.m3u8'
        return url.strip()

    def clean_title(self, text):
        """Cleans garbage from titles"""
        if not text: return "Untitled"
        
        # 1. Remove generic words (Case insensitive)
        for word in self.ignore_list:
            text = re.sub(f'(?i)\\b{word}\\b', '', text)
            
        # 2. Fix Symbols
        text = text.replace('|', ' ').replace('_', ' ').replace(':', ' - ')
        
        # 3. Remove leading/trailing numbers/dots (e.g. "1. " or "02.")
        # But keep them if they are part of "Class 01"
        text = re.sub(r'^\s*\d+[\.\-\)]\s*', '', text) 
        
        return text.strip()

    def get_real_title(self, element):
        """
        🌳 Tree Traversal:
        Looks for the title in this order:
        1. Onclick JS Argument (Most accurate)
        2. Previous Sibling Element (Usually lists have Title then Button)
        3. Parent Container Text (Grandparent logic)
        """
        # Strategy 1: JS Arguments (openVideo('id', 'url', 'REAL NAME'))
        if element.has_attr('onclick'):
            matches = re.findall(r"['\"]([^'\"]+)['\"]", element['onclick'])
            if len(matches) >= 3:
                candidate = matches[-1].strip()
                if len(candidate) > 3 and "http" not in candidate:
                    return self.clean_title(candidate)

        # Strategy 2: Look at Previous Sibling (e.g. <span>Title</span> <a>Link</a>)
        prev = element.find_previous_sibling()
        if prev:
            prev_text = prev.get_text(" ", strip=True)
            if len(prev_text) > 4:
                return self.clean_title(prev_text)

        # Strategy 3: Parent/Grandparent Text Analysis
        # This is for Aman Vashisth files where structure is nested
        current = element
        button_text = element.get_text(" ", strip=True)
        
        for _ in range(3): # Go up 3 levels
            parent = current.parent
            if not parent: break
            
            full_text = parent.get_text(" ", strip=True)
            # Subtract the button text ("Original") from full text
            remaining_text = full_text.replace(button_text, "").strip()
            
            # If we have substantial text left, that's likely the title
            if len(remaining_text) > 4:
                # Split by newlines to avoid merging multiple lines
                lines = [line.strip() for line in remaining_text.splitlines() if line.strip()]
                # Find the longest line that isn't a number
                for line in lines:
                    if len(line) > 4 and not line.isdigit():
                        return self.clean_title(line)
            
            current = parent

        return "Untitled_Topic"

    def parse(self, html_content):
        # Decryption Check
        if "encodedContent" in html_content:
            try:
                # Keep simple check to not break flow
                pass 
            except: pass

        soup = BeautifulSoup(html_content, 'lxml')
        links_data = []
        seen_urls = set()

        # Find interactive elements
        targets = soup.find_all(lambda tag: tag.has_attr('href') or tag.has_attr('onclick'))

        for tag in targets:
            url = None
            if tag.has_attr('href'): url = tag['href']
            elif tag.has_attr('onclick'):
                m = re.search(r"['\"](https?://[^'\"]+)['\"]", tag['onclick'])
                if m: url = m.group(1)

            if url and "http" in url:
                clean_url = self.clean_url(url)
                
                # Filter Junk
                if any(x in clean_url for x in ['w3.org', 'javascript:', 'jquery', 'google.com/search']):
                    continue
                
                # Deduplicate: Skip if URL already exists
                if clean_url in seen_urls: continue
                seen_urls.add(clean_url)
                
                # Get Title
                title = self.get_real_title(tag)
                if title == "Untitled" or len(title) < 2:
                    continue # Skip garbage links with no title
                
                # CATEGORIZATION
                l_type = 'other'
                u_low = clean_url.lower()
                t_low = title.lower()
                
                # 1. VIDEO Check (Highest Priority)
                # Even if title says "Mock Test Discussion", if it's .m3u8, IT IS A VIDEO.
                if any(x in u_low for x in ['.mp4', '.m3u8', 'youtu', 'vimeo', 'manifest']):
                    l_type = 'video'
                    
                # 2. PDF Check
                elif any(x in u_low for x in ['.pdf', 'drive.google', 'doc', 'notes']):
                    l_type = 'pdf'
                    
                # 3. MOCK TEST (Only if it's NOT a video/pdf)
                # This catches actual online quiz links, not discussion videos
                elif any(x in t_low for x in ['mock test', 'quiz', 'attempt']) or 'test' in u_low:
                    l_type = 'mock'
                
                # 4. Images
                elif any(x in u_low for x in ['.jpg', '.png', '.jpeg']):
                    l_type = 'image'

                links_data.append({'title': title, 'url': clean_url, 'type': l_type})
        
        return links_data

    def generate_txt(self, filename, links):
        lines = [f"📂 Source: {filename}", "="*50, ""]
        
        videos = [x for x in links if x['type'] == 'video']
        pdfs = [x for x in links if x['type'] == 'pdf']
        mocks = [x for x in links if x['type'] == 'mock']
        others = [x for x in links if x['type'] == 'other'] # Images usually not needed in txt unless requested
        
        if videos:
            lines.append(f"🎬 VIDEOS ({len(videos)})")
            lines.append("-" * 20)
            for v in videos: 
                lines.append(f"{v['title']} : {v['url']}")
            lines.append("")
            
        if pdfs:
            lines.append(f"📚 PDFS / NOTES ({len(pdfs)})")
            lines.append("-" * 20)
            for p in pdfs: 
                lines.append(f"{p['title']} : {p['url']}")
            lines.append("")

        if mocks:
            lines.append(f"📝 ONLINE TESTS / QUIZZES ({len(mocks)})")
            lines.append("-" * 20)
            for m in mocks: 
                lines.append(f"{m['title']} : {m['url']}")
            lines.append("")
            
        if others:
            lines.append(f"🔗 OTHERS ({len(others)})")
            for o in others: 
                lines.append(f"{o['title']} : {o['url']}")
            
        return "\n".join(lines)

# ==================== BOT SETUP ====================
parser = DeepDomParser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ **Bot Online**\nSend HTML file. I will extract REAL titles.")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(('.html', '.htm', '.txt')):
        await update.message.reply_text("❌ Send HTML file.")
        return

    msg = await update.message.reply_text("🔄 **Extracting & Structuring...**")
    
    try:
        f = await context.bot.get_file(doc.file_id)
        c = await f.download_as_bytearray()
        content = c.decode('utf-8', errors='ignore')
        
        links = parser.parse(content)
        
        if not links:
            await msg.edit_text("❌ No content found.")
            return
            
        out_txt = parser.generate_txt(doc.file_name, links)
        out_name = f"{doc.file_name}_Fixed.txt"
        
        with open(out_name, "w", encoding="utf-8") as f:
            f.write(out_txt)
            
        stats = (f"✅ **Extraction Complete**\n"
                 f"📹 Videos: {len([x for x in links if x['type']=='video'])}\n"
                 f"📚 PDFs: {len([x for x in links if x['type']=='pdf'])}\n"
                 f"📝 Tests: {len([x for x in links if x['type']=='mock'])}")
                 
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
       
