#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter Bot - GOD MODE
✨ Smart Context Extraction: Finds real titles even if link says "View PDF"
🚀 Deep Decryption for Encrypted Batches
"""

import os
import re
import logging
import base64
import asyncio
from bs4 import BeautifulSoup, NavigableString
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

class GodModeParser:
    """🧠 Smart Parser that understands HTML structure to find Names & Links"""
    
    def __init__(self):
        # Generic words to ignore in titles
        self.generic_keywords = [
            'view', 'play', 'download', 'watch', 'pdf', 'notes', 'video', 
            'click here', 'open', 'attachment', 'class png', 'live'
        ]
        
    def xor_decrypt(self, encoded_b64, key):
        """Standard XOR Decryption for Selection Batch & others"""
        try:
            encrypted_data = base64.b64decode(encoded_b64).decode('latin1')
            result = []
            key_len = len(key)
            for i in range(len(encrypted_data)):
                char_code = ord(encrypted_data[i]) ^ ord(key[i % key_len])
                result.append(chr(char_code))
            return base64.b64decode("".join(result)).decode('utf-8')
        except Exception as e:
            return None

    def extract_secret_key(self, html_content):
        """Extracts secret key components from JS"""
        default_key = "TusharSuperSecreT2025!"
        try:
            p1 = re.search(r'let\s+P1\s*=\s*["\']([^"\']+)["\']', html_content)
            p2 = re.search(r'let\s+P2\s*=\s*["\']([^"\']+)["\']', html_content)
            p3 = re.search(r'let\s+P3_Reversed\s*=\s*["\']([^"\']+)["\']', html_content)
            p4 = re.search(r'let\s+P4\s*=\s*["\']([^"\']+)["\']', html_content)
            
            if p1 and p2 and p3 and p4:
                return f"{p4.group(1)}{p1.group(1)}{p2.group(1)}{p3.group(1)[::-1]}"
            return default_key
        except:
            return default_key

    def get_smart_title(self, element, default_text="Untitled"):
        """
        🚀 The Magic Function:
        Looks at the element, then its neighbors, then its parent to find the REAL name.
        """
        # 1. Get own text
        text = element.get_text(" ", strip=True)
        
        # 2. Check if text is 'Generic' (like "View PDF") or empty
        is_generic = False
        if not text or len(text) < 4:
            is_generic = True
        else:
            if any(kw in text.lower() for kw in self.generic_keywords):
                # But allow if it has numbers or specific details (e.g. "Class 5 PDF")
                if len(text) < 20: 
                    is_generic = True

        if not is_generic:
            return self.clean_text(text)

        # 3. Context Search (If generic)
        
        # A) Look for previous sibling (often <strong>Name</strong> <a...>View</a>)
        prev = element.find_previous_sibling()
        if prev:
            prev_text = prev.get_text(" ", strip=True)
            if len(prev_text) > 3:
                return self.clean_text(prev_text)

        # B) Look at Parent's text (ignoring the button text itself)
        parent = element.parent
        if parent:
            # Get parent text but remove the link's own text from it to avoid duplication
            full_parent_text = parent.get_text(" ", strip=True)
            # Simple heuristic: If parent text is longer, use it
            if len(full_parent_text) > len(text) + 3:
                # Remove the generic word from parent text
                clean_parent = full_parent_text.replace(text, "").strip()
                if len(clean_parent) > 3:
                    return self.clean_text(clean_parent)
        
        # C) Look for nearest Header/Strong preceding the element
        nearest_strong = element.find_previous(['strong', 'h3', 'h4', 'h5', 'b', 'span'])
        if nearest_strong:
            return self.clean_text(nearest_strong.get_text(" ", strip=True))

        return default_text

    def clean_text(self, text):
        # Basic cleanup
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove trailing colons or dashes
        text = text.strip(':-| ')
        return text

    def parse(self, html_content):
        # 1. Decrypt Loop (Handle multiple layers if needed, but usually 1)
        if "encodedContent" in html_content:
            key = self.extract_secret_key(html_content)
            match = re.search(r"encodedContent\s*=\s*['\"]([^'\"]+)['\"]", html_content)
            if match:
                decrypted = self.xor_decrypt(match.group(1), key)
                if decrypted: html_content = decrypted

        soup = BeautifulSoup(html_content, 'lxml') # or 'html.parser'
        
        links_data = [] # List of dicts: {'title':..., 'url':..., 'type':...}
        seen_urls = set()

        # 2. Universal Element Scanner
        # We look for ANY element that might have a link
        targets = soup.find_all(['a', 'button', 'div', 'li', 'span'])
        
        for tag in targets:
            url = None
            
            # A) Check href
            if tag.name == 'a' and tag.get('href'):
                url = tag.get('href')
            
            # B) Check onclick (The juicy stuff for encrypted batches)
            elif tag.get('onclick'):
                # Extract URL from onclick="...('URL')..."
                # Supports single/double quotes, http/https
                onclick_match = re.search(r"['\"](https?://[^'\"]+)['\"]", tag.get('onclick'))
                if onclick_match:
                    url = onclick_match.group(1)
            
            # Process if URL found
            if url and url.startswith('http') and url not in seen_urls:
                seen_urls.add(url)
                
                # SMART TITLE EXTRACTION
                title = self.get_smart_title(tag)
                
                # Determine Type
                l_type = "other"
                u_lower = url.lower()
                if any(x in u_lower for x in ['.pdf', 'drive.google', 'doc', 'ppt']):
                    l_type = "pdf"
                elif any(x in u_lower for x in ['.mp4', '.m3u8', 'youtube', 'youtu.be', 'vimeo', 'playlist']):
                    l_type = "video"
                # If title contains keywords, override type
                elif 'pdf' in title.lower() or 'notes' in title.lower():
                    l_type = "pdf"
                
                links_data.append({'title': title, 'url': url, 'type': l_type})

        # 3. Fallback: Regex for loose strings (Only if soup failed for a URL)
        # Sometimes URLs are just in script tags
        raw_urls = re.findall(r'(https?://[^\s<>"\';]+)', html_content)
        for r_url in raw_urls:
            if r_url not in seen_urls:
                # Basic filter to avoid garbage JS urls
                if not any(x in r_url for x in ['.js', '.css', 'w3.org']):
                    seen_urls.add(r_url)
                    links_data.append({'title': "Hidden Link (Regex)", 'url': r_url, 'type': "other"})

        return links_data

    def generate_output(self, file_name, links):
        lines = [f"📂 Source: {file_name}", "="*40, ""]
        
        # Categorize for display
        videos = [x for x in links if x['type'] == 'video']
        pdfs = [x for x in links if x['type'] == 'pdf']
        others = [x for x in links if x['type'] == 'other']
        
        if videos:
            lines.append(f"🎬 VIDEOS ({len(videos)})")
            for v in videos: lines.append(f"{v['title']} : {v['url']}")
            lines.append("")
            
        if pdfs:
            lines.append(f"📚 PDFS / NOTES ({len(pdfs)})")
            for p in pdfs: lines.append(f"{p['title']} : {p['url']}")
            lines.append("")
            
        if others:
            lines.append(f"🔗 OTHERS ({len(others)})")
            for o in others: lines.append(f"{o['title']} : {o['url']}")
            
        return "\n".join(lines)

# ==================== BOT HANDLERS ====================
parser = GodModeParser()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("😎 **God Mode Active**\nSend HTML. I will find real names and ALL links.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.file_name.lower().endswith(('.html', '.htm', '.txt')):
        await update.message.reply_text("❌ Send HTML file.")
        return

    status = await update.message.reply_text("🔍 **Analyzing Structure...**")
    
    try:
        f = await context.bot.get_file(doc.file_id)
        content = await f.download_as_bytearray()
        html_text = content.decode('utf-8', errors='ignore')
        
        links = parser.parse(html_text)
        
        if not links:
            await status.edit_text("❌ No links found.")
            return
            
        output = parser.generate_output(doc.file_name, links)
        
        out_name = f"{doc.file_name}_Fixed.txt"
        with open(out_name, "w", encoding="utf-8") as f:
            f.write(output)
            
        with open(out_name, "rb") as f:
            await update.message.reply_document(
                document=f,
                caption=f"✅ **Extracted Successfully**\nTotal: {len(links)}",
                parse_mode=ParseMode.MARKDOWN
            )
        os.remove(out_name)
        await status.delete()
        
    except Exception as e:
        logger.error(e)
        await status.edit_text("❌ Error processing file.")

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
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    if WEBHOOK_URL:
        await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
                
