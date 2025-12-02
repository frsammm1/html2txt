#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter - FINAL STABLE
✨ Fixes: Removes Duplicate Links (360p/480p/720p), Fixes Bad PDF Names
🚀 Logic: Aggressive Context Merging & Title Deduplication
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

class FinalParser:
    def __init__(self):
        self.ignore_words = [
            'view', 'play', 'download', 'watch', 'pdf', 'notes', 'video', 
            'click here', 'open', 'original', 'quality', '360p', '480p', '720p', '1080p',
            'class png', 'live', 'read online', 'attempt', 'start', 'test', 'discussion'
        ]
        
    def clean_url(self, url):
        if not url: return None
        # Marshmallow fix
        if "video=" in url:
            try:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                if 'video' in qs: return qs['video'][0]
            except: pass
        
        # Double extension fix
        if '.m3u8' in url: url = url.split('.m3u8')[0] + '.m3u8'
        if '.pdf' in url: url = url.split('.pdf')[0] + '.pdf'
        return url.strip()

    def clean_title(self, text):
        if not text: return ""
        # Remove unwanted characters
        text = text.replace('|', ' ').replace('_', ' ').replace(':', ' - ')
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Remove starting numbers (e.g. "1.", "01") ONLY if followed by generic text
        # But for "Class 01", we keep it.
        # This regex removes standalone numbers at start: "1. "
        text = re.sub(r'^\d+[\.\-\)]\s*', '', text)
        
        return text.strip()

    def is_generic(self, text):
        """Checks if title is too generic (like 'View PDF')"""
        if not text or len(text) < 3: return True
        t_low = text.lower()
        if t_low in self.ignore_words: return True
        # If text is just "Discussion" or "Solution"
        if t_low in ['discussion', 'solution', 'paper', 'class']: return True
        return False

    def get_context_title(self, element):
        """
        🧬 MERGES context from Parent and Grandparent to form a full title.
        Example: Parent="Mock 1", Element="Discussion" -> Result="Mock 1 Discussion"
        """
        # 1. Start with the element's own text (or JS title)
        title_parts = []
        
        # Check JS
        if element.has_attr('onclick'):
            matches = re.findall(r"['\"]([^'\"]+)['\"]", element['onclick'])
            if len(matches) >= 3:
                js_title = matches[-1].strip()
                if not js_title.startswith('http'): title_parts.append(js_title)

        # Check Button Text
        btn_text = element.get_text(" ", strip=True)
        if btn_text and not self.is_generic(btn_text):
            title_parts.append(btn_text)

        # 2. Walk Up (Parent -> Grandparent)
        current = element
        for _ in range(3):
            parent = current.parent
            if not parent: break
            
            # Get parent text, but exclude the text of the child we just came from
            parent_text = parent.get_text(" ", strip=True)
            
            # Simple heuristic: If parent text contains the child text, try to subtract it
            # But safer is just to grab the longest meaningful line in parent
            
            # Split parent text by newlines/separators
            lines = re.split(r'[\n•|]+', parent_text)
            for line in lines:
                line = self.clean_title(line)
                # If this line is unique and substantial, add it
                if len(line) > 4 and line not in title_parts and not self.is_generic(line):
                    # Prepend parent text (Topic) before Child text (Sub-topic)
                    title_parts.insert(0, line)
                    break # Only take the main heading from parent
            
            current = parent
            
        # 3. Join parts
        if not title_parts: return "Untitled_Resource"
        
        # Deduplicate parts if "Mock 1" appears twice
        seen = set()
        final_parts = []
        for p in title_parts:
            if p.lower() not in seen:
                final_parts.append(p)
                seen.add(p.lower())
                
        return " ".join(final_parts)

    def parse(self, html_content):
        if "encodedContent" in html_content:
            try: pass # Add decryption if needed, usually decoded content works
            except: pass

        soup = BeautifulSoup(html_content, 'lxml')
        links_data = []
        
        # Track seen titles per category to prevent duplicates (360p vs 720p)
        # Structure: {'video': {'noun class 1'}, 'pdf': set()}
        seen_titles = {'video': set(), 'pdf': set(), 'mock': set(), 'other': set(), 'image': set()}
        seen_urls = set()

        targets = soup.find_all(lambda tag: tag.has_attr('href') or tag.has_attr('onclick'))

        for tag in targets:
            url = None
            if tag.has_attr('href'): url = tag['href']
            elif tag.has_attr('onclick'):
                m = re.search(r"['\"](https?://[^'\"]+)['\"]", tag['onclick'])
                if m: url = m.group(1)

            if url and "http" in url:
                clean_url = self.clean_url(url)
                if any(x in clean_url for x in ['w3.org', 'javascript:', 'jquery']): continue
                
                # Check URL duplication
                if clean_url in seen_urls: continue
                
                # Title Extraction
                raw_title = self.get_context_title(tag)
                title = self.clean_title(raw_title)
                
                # CATEGORIZATION
                l_type = 'other'
                u_low = clean_url.lower()
                t_low = title.lower()
                
                # Video
                if any(x in u_low for x in ['.mp4', '.m3u8', 'youtu', 'vimeo', 'manifest']):
                    l_type = 'video'
                # PDF
                elif any(x in u_low for x in ['.pdf', 'drive.google', 'doc', 'notes']):
                    l_type = 'pdf'
                # Mock (Strict: Must imply a test platform or quiz)
                elif ('test' in u_low or 'quiz' in u_low) and not ('.mp4' in u_low or '.m3u8' in u_low):
                    l_type = 'mock'
                elif 'attempt' in t_low:
                    l_type = 'mock'
                # Image
                elif any(x in u_low for x in ['.jpg', '.png', '.jpeg']):
                    l_type = 'image'
                
                # DEDUPLICATION LOGIC (The Fix)
                # If we have already seen this TITLE in this CATEGORY, skip it!
                # This drops the 2nd, 3rd links (lower quality duplicates)
                if title in seen_titles[l_type]:
                    continue
                
                # Register
                seen_titles[l_type].add(title)
                seen_urls.add(clean_url)
                
                links_data.append({'title': title, 'url': clean_url, 'type': l_type})
        
        return links_data

    def generate_txt(self, filename, links):
        lines = [f"📂 Source: {filename}", "="*50, ""]
        
        cats = ['video', 'pdf', 'mock', 'image', 'other']
        names = ['🎬 VIDEOS', '📚 PDFS / NOTES', '📝 MOCK TESTS', '🖼 IMAGES', '🔗 OTHERS']
        
        for cat, name in zip(cats, names):
            items = [x for x in links if x['type'] == cat]
            if items:
                lines.append(f"{name} ({len(items)})")
                lines.append("-" * 20)
                for item in items:
                    lines.append(f"{item['title']} : {item['url']}")
                lines.append("")
            
        return "\n".join(lines)

# ==================== BOT SETUP ====================
parser = FinalParser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛡️ **Anti-Dupe Bot**\nSend HTML. I remove duplicates & fix names.")

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(('.html', '.htm', '.txt')):
        await update.message.reply_text("❌ Send HTML file.")
        return

    msg = await update.message.reply_text("♻️ **Filtering Duplicates...**")
    
    try:
        f = await context.bot.get_file(doc.file_id)
        c = await f.download_as_bytearray()
        content = c.decode('utf-8', errors='ignore')
        
        links = parser.parse(content)
        
        if not links:
            await msg.edit_text("❌ No links found.")
            return
            
        out_txt = parser.generate_txt(doc.file_name, links)
        out_name = f"{doc.file_name}_Final.txt"
        
        with open(out_name, "w", encoding="utf-8") as f:
            f.write(out_txt)
            
        stats = []
        for t in ['video', 'pdf', 'mock']:
            count = len([x for x in links if x['type'] == t])
            stats.append(f"{t.title()}: {count}")
            
        caption = f"✅ **Cleaned & Fixed**\n" + " | ".join(stats)
                 
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
    
