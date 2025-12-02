#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter - VISUAL BLOCK PARSER (FINAL)
✨ Logic: Identifies 'Cards', Extracts Pure Titles, Removes ALL Duplicates
🚀 Fixes: Garbage Titles, Repeating Links, Mixed Categories
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

class VisualBlockParser:
    def __init__(self):
        # Strictly ignore these words to clean titles
        self.junk_words = [
            'view', 'play', 'download', 'watch', 'pdf', 'notes', 'video', 
            'click here', 'open', 'original', 'quality', '360p', '480p', '720p', '1080p',
            'class png', 'live', 'read online', 'attempt', 'start', 'test', 'discussion',
            'quality', 'hls', 'media'
        ]
        
    def clean_url(self, url):
        if not url: return None
        # Fix Wrapper Links
        if "video=" in url:
            try:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                if 'video' in qs: return qs['video'][0]
            except: pass
        
        # Remove Double Extensions
        if '.m3u8' in url: url = url.split('.m3u8')[0] + '.m3u8'
        if '.pdf' in url: url = url.split('.pdf')[0] + '.pdf'
        return url.strip()

    def clean_name(self, text):
        """Ultra-Strict Cleaner to get ONLY the topic name"""
        if not text: return ""
        
        # 1. Remove Button Words (Case Insensitive)
        for word in self.junk_words:
            text = re.sub(f'(?i)\\b{word}\\b', '', text)
            
        # 2. Remove Symbols & weird chars
        text = text.replace('|', ' ').replace('_', ' ').replace(':', ' - ')
        
        # 3. Remove Starting Numbers/Dots (e.g. "1.", "01", "23.")
        # Only if they are at the very start
        text = re.sub(r'^\s*\d+[\.\-\)]\s*', '', text)
        
        # 4. Collapse multiple spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def get_card_title(self, element):
        """
        🔍 Looks for the Container (Card) holding the link.
        It scans the Parent Div to find the longest non-junk text.
        """
        # First, try JS Title (Most Accurate)
        if element.has_attr('onclick'):
            matches = re.findall(r"['\"]([^'\"]+)['\"]", element['onclick'])
            if len(matches) >= 3:
                js_title = matches[-1].strip()
                if len(js_title) > 3 and "http" not in js_title:
                    return self.clean_name(js_title)

        # Fallback: Parent Div Analysis
        current = element
        btn_text = element.get_text(" ", strip=True)
        
        # Go up to finding a Block (div/li)
        for _ in range(3):
            parent = current.parent
            if not parent: break
            
            # Get all text in this block
            block_text = parent.get_text(" ", strip=True)
            
            # Remove the button text itself from block text
            clean_block = block_text.replace(btn_text, "").strip()
            
            # Split lines and find the most 'Title-like' line
            # We reject lines that are just numbers or junk
            candidates = re.split(r'[\n•]+', clean_block)
            best_candidate = ""
            
            for part in candidates:
                cleaned = self.clean_name(part)
                if len(cleaned) > 4: # Must be at least 4 chars to be a topic
                    # If this looks like a valid title, take it
                    if not best_candidate or len(cleaned) > len(best_candidate):
                        best_candidate = cleaned
            
            if best_candidate:
                return best_candidate
                
            current = parent
            
        return "Untitled Topic"

    def parse(self, html_content):
        # Decode if needed
        if "encodedContent" in html_content:
            try: pass 
            except: pass

        soup = BeautifulSoup(html_content, 'lxml')
        links_data = []
        
        # DEDUPLICATION SETS
        # We store titles we've already processed to avoid adding 360p/720p duplicates
        seen_titles = {'video': set(), 'pdf': set(), 'mock': set(), 'image': set(), 'other': set()}
        seen_urls = set()

        # Find all link elements
        targets = soup.find_all(lambda tag: tag.has_attr('href') or tag.has_attr('onclick'))

        for tag in targets:
            url = None
            if tag.has_attr('href'): url = tag['href']
            elif tag.has_attr('onclick'):
                m = re.search(r"['\"](https?://[^'\"]+)['\"]", tag['onclick'])
                if m: url = m.group(1)

            if url and "http" in url:
                clean_url = self.clean_url(url)
                
                # Filter Technical Junk
                if any(x in clean_url for x in ['w3.org', 'javascript:', 'jquery', 'google.com']):
                    continue

                if clean_url in seen_urls: continue
                
                # Get Title using Visual Block Logic
                title = self.get_card_title(tag)
                
                # CATEGORIZE
                l_type = 'other'
                u_low = clean_url.lower()
                t_low = title.lower()
                
                # 1. Video (Strict)
                if any(x in u_low for x in ['.mp4', '.m3u8', 'youtu', 'vimeo', 'manifest']):
                    l_type = 'video'
                # 2. PDF (Strict)
                elif any(x in u_low for x in ['.pdf', 'drive.google', 'doc', 'notes']):
                    l_type = 'pdf'
                # 3. Mock (Only if URL contains test/quiz AND not video)
                elif ('test' in u_low or 'quiz' in u_low or 'attempt' in u_low):
                    l_type = 'mock'
                # 4. Image
                elif any(x in u_low for x in ['.jpg', '.png', '.jpeg']):
                    l_type = 'image'
                
                # DUPLICATE CHECK
                # If we already have a VIDEO with this Exact Title, Skip this one (it's likely a lower quality link)
                if title in seen_titles[l_type]:
                    continue
                
                # Add to list
                seen_titles[l_type].add(title)
                seen_urls.add(clean_url)
                
                links_data.append({'title': title, 'url': clean_url, 'type': l_type})
        
        return links_data

    def generate_txt(self, filename, links):
        lines = [f"📂 Source: {filename}", "="*50, ""]
        
        # Order: Video -> PDF -> Mock -> Image -> Other
        cats = ['video', 'pdf', 'mock', 'image', 'other']
        headers = ['🎬 VIDEOS', '📚 PDFS / NOTES', '📝 MOCK TESTS', '🖼 IMAGES', '🔗 OTHERS']
        
        for c, h in zip(cats, headers):
            items = [x for x in links if x['type'] == c]
            if items:
                lines.append(h + f" ({len(items)})")
                lines.append("-" * 20)
                for item in items:
                    lines.append(f"{item['title']} : {item['url']}")
                lines.append("")
        
        return "\n".join(lines)

# ==================== BOT SETUP ====================
parser = VisualBlockParser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 **Visual Parser Active**\nSend HTML. I will extract clean titles and remove duplicates.")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(('.html', '.htm', '.txt')):
        await update.message.reply_text("❌ Send HTML file.")
        return

    msg = await update.message.reply_text("👁️ **Visualizing & Cleaning...**")
    
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
            
        stats = []
        for t in ['video', 'pdf', 'mock']:
            count = len([x for x in links if x['type'] == t])
            stats.append(f"{t.title()}: {count}")
            
        caption = f"✅ **Extraction Perfected**\n" + " | ".join(stats)
                 
        with open(out_name, "rb") as f:
            await update.message.reply_document(document=f, caption=caption, parse_mode=ParseMode.MARKDOWN)
            
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
        
