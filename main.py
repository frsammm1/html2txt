#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter Bot - HARDCORE Edition
✨ Multi-Strategy Parser | No Link Left Behind
🚀 Optimized for Render.com with Health Check
"""

import os
import re
import logging
import base64
import asyncio
from datetime import datetime
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode
import tempfile
from aiohttp import web
import json

# ==================== LOGGING ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== CONFIG ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
MAX_FILE_SIZE = 50 * 1024 * 1024

# ==================== STATS ====================
stats = {
    'total_conversions': 0,
    'total_videos': 0,
    'total_pdfs': 0,
    'total_links': 0,
    'start_time': datetime.now()
}


class HardcoreHTMLParser:
    """🔥 Multi-Strategy HTML Parser - Koi link nahi bachegi"""
    
    def __init__(self):
        self.video_extensions = ['.m3u8', '.mp4', '.avi', '.mkv', '.mov', '.flv', '.wmv', '.webm']
        self.video_platforms = ['youtube.com', 'youtu.be', 'vimeo.com', 'dailymotion.com', 
                               'twitch.tv', 'livelearn.in', 'hranker.com']
        self.pdf_extensions = ['.pdf']
        
    def decode_url_aggressive(self, encoded: str) -> str:
        """🔓 Aggressive multi-layer URL decoder"""
        try:
            original = encoded.strip()
            
            # Skip if already valid URL
            if original.startswith(('http://', 'https://', 'www.')):
                return original
            
            # Try URL decode multiple times
            decoded = original
            for _ in range(5):
                temp = unquote(decoded)
                if temp == decoded:
                    break
                decoded = temp
            
            if decoded.startswith(('http://', 'https://')):
                return decoded
            
            # Try Base64 decode (single and double)
            try:
                # Try double base64
                b64_decoded = base64.b64decode(original).decode('utf-8', errors='ignore')
                b64_decoded = base64.b64decode(b64_decoded).decode('utf-8', errors='ignore')
                
                # Remove common prefixes
                if len(b64_decoded) > 8 and not b64_decoded.startswith(('http://', 'https://')):
                    b64_decoded = b64_decoded[8:]
                
                if b64_decoded.startswith(('http://', 'https://')):
                    return b64_decoded
            except:
                pass
            
            try:
                # Try single base64
                b64_decoded = base64.b64decode(original).decode('utf-8', errors='ignore')
                if b64_decoded.startswith(('http://', 'https://')):
                    return b64_decoded
                
                # Try removing prefix
                if len(b64_decoded) > 8:
                    b64_decoded = b64_decoded[8:]
                    if b64_decoded.startswith(('http://', 'https://')):
                        return b64_decoded
            except:
                pass
            
            return original
        except:
            return encoded
    
    def extract_title_smart(self, element, default: str) -> str:
        """📝 Smart title extraction with multiple strategies"""
        try:
            # Strategy 1: Direct text in element
            text = element.get_text(strip=True)
            if text and len(text) < 300:
                title = self.clean_title(text)
                if title and title != "Untitled":
                    return title
            
            # Strategy 2: Check parent element
            if element.parent:
                parent_text = element.parent.get_text(strip=True)
                if parent_text and len(parent_text) < 300:
                    title = self.clean_title(parent_text)
                    if title and title != "Untitled":
                        return title
            
            # Strategy 3: Attributes
            for attr in ['title', 'data-title', 'aria-label', 'alt', 'data-name']:
                if element.get(attr):
                    title = self.clean_title(element.get(attr))
                    if title and title != "Untitled":
                        return title
            
            # Strategy 4: Previous sibling
            prev = element.find_previous_sibling()
            if prev:
                prev_text = prev.get_text(strip=True)
                if prev_text and len(prev_text) < 300:
                    title = self.clean_title(prev_text)
                    if title and title != "Untitled":
                        return title
            
            return default
        except:
            return default
    
    def clean_title(self, title: str) -> str:
        """🧹 Clean and format title"""
        if not title:
            return "Untitled"
        
        # Remove common prefixes/suffixes
        title = re.sub(r'^(𝙼𝚎𝚗𝚍𝚊𝚡|Mendax|Watch|Download|View|Play|Click|Open|ð™¼ðšŽðš—ðšðšŠðš¡)\s*', '', title, flags=re.I)
        title = re.sub(r'(📥|🔥)\s*Download.*$', '', title, flags=re.I)
        title = re.sub(r'\s*@\w+\s*$', '', title)
        title = re.sub(r'\.(?:pdf|html|htm|txt)(?:\s*-\s*\d+)?$', '', title, flags=re.I)
        title = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', '', title)
        
        # Clean whitespace
        title = ' '.join(title.split())
        
        # Truncate if too long
        if len(title) > 200:
            title = title[:197] + "..."
        
        return title or "Untitled"
    
    def is_video_url(self, url: str) -> bool:
        """Check if URL is a video"""
        url_lower = url.lower()
        return (any(ext in url_lower for ext in self.video_extensions) or 
                any(platform in url_lower for platform in self.video_platforms))
    
    def is_pdf_url(self, url: str) -> bool:
        """Check if URL is a PDF"""
        return '.pdf' in url.lower()
    
    def strategy_1_onclick_extraction(self, html_content: str) -> dict:
        """Strategy 1: Extract from onclick attributes"""
        results = {'videos': [], 'pdfs': []}
        
        # Find all onclick patterns
        onclick_patterns = [
            r'onclick\s*=\s*["\']playVideo\s*\(\s*["\']([^"\']+)["\']',
            r'onclick\s*=\s*["\']loadVideo\s*\(\s*["\']([^"\']+)["\']',
            r'onclick\s*=\s*["\'](?:viewPDF|downloadFile|openPDF)\s*\(\s*["\']([^"\']+)["\']',
            r'playVideo\s*\(\s*["\']([^"\']+)["\']',
            r'viewPDF\s*\(\s*["\']([^"\']+)["\']',
        ]
        
        for pattern in onclick_patterns:
            matches = re.finditer(pattern, html_content, re.I)
            for match in matches:
                url = self.decode_url_aggressive(match.group(1))
                if url.startswith(('http://', 'https://')):
                    if self.is_video_url(url):
                        results['videos'].append(url)
                    elif self.is_pdf_url(url):
                        results['pdfs'].append(url)
        
        return results
    
    def strategy_2_href_extraction(self, soup: BeautifulSoup) -> dict:
        """Strategy 2: Extract from href attributes"""
        results = {'videos': [], 'pdfs': [], 'others': []}
        
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '').strip()
            
            # Skip invalid
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            
            url = self.decode_url_aggressive(href)
            
            if url.startswith(('http://', 'https://')):
                if self.is_video_url(url):
                    results['videos'].append({'url': url, 'element': link})
                elif self.is_pdf_url(url):
                    results['pdfs'].append({'url': url, 'element': link})
                else:
                    results['others'].append({'url': url, 'element': link})
        
        return results
    
    def strategy_3_regex_scan(self, html_content: str) -> dict:
        """Strategy 3: Raw regex scan for URLs"""
        results = {'videos': [], 'pdfs': [], 'others': []}
        
        # All URLs pattern
        url_pattern = r'https?://[^\s<>"\']+(?:\.m3u8|\.pdf|\.mp4|[^\s<>"\']{10,})'
        
        matches = re.finditer(url_pattern, html_content, re.I)
        
        for match in matches:
            url = match.group(0)
            # Clean trailing garbage
            url = re.sub(r'["\',;)}\]]+$', '', url)
            
            if self.is_video_url(url):
                results['videos'].append(url)
            elif self.is_pdf_url(url):
                results['pdfs'].append(url)
            else:
                results['others'].append(url)
        
        return results
    
    def strategy_4_data_attributes(self, soup: BeautifulSoup) -> dict:
        """Strategy 4: Extract from data-* attributes"""
        results = {'videos': [], 'pdfs': []}
        
        # Find all elements with data attributes
        all_elements = soup.find_all(attrs={'data-url': True})
        all_elements.extend(soup.find_all(attrs={'data-src': True}))
        all_elements.extend(soup.find_all(attrs={'data-video': True}))
        all_elements.extend(soup.find_all(attrs={'data-pdf': True}))
        all_elements.extend(soup.find_all(attrs={'data-file': True}))
        
        for elem in all_elements:
            for attr in ['data-url', 'data-src', 'data-video', 'data-pdf', 'data-file']:
                value = elem.get(attr, '').strip()
                if value:
                    url = self.decode_url_aggressive(value)
                    if url.startswith(('http://', 'https://')):
                        if self.is_video_url(url):
                            results['videos'].append(url)
                        elif self.is_pdf_url(url):
                            results['pdfs'].append(url)
        
        return results
    
    def parse_html_hardcore(self, html_content: str) -> dict:
        """🔥 Multi-strategy hardcore parsing"""
        logger.info("🔍 Starting multi-strategy parsing...")
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract title
        title = "Converted Document"
        title_tag = soup.find('title')
        if title_tag:
            title = self.clean_title(title_tag.get_text(strip=True))
        else:
            for tag in ['h1', 'h2', 'div']:
                header = soup.find(tag, class_=re.compile(r'(header|title|brand)', re.I))
                if header:
                    title = self.clean_title(header.get_text(strip=True))
                    break
        
        # Collect URLs from all strategies
        all_videos = set()
        all_pdfs = set()
        all_others = set()
        video_titles = {}
        pdf_titles = {}
        other_titles = {}
        
        # Strategy 1: onclick extraction
        logger.info("📍 Strategy 1: onclick extraction")
        onclick_results = self.strategy_1_onclick_extraction(html_content)
        all_videos.update(onclick_results['videos'])
        all_pdfs.update(onclick_results['pdfs'])
        
        # Strategy 2: href extraction
        logger.info("📍 Strategy 2: href extraction")
        href_results = self.strategy_2_href_extraction(soup)
        for item in href_results['videos']:
            url = item['url']
            all_videos.add(url)
            if url not in video_titles:
                video_titles[url] = self.extract_title_smart(item['element'], f"Video {len(all_videos)}")
        
        for item in href_results['pdfs']:
            url = item['url']
            all_pdfs.add(url)
            if url not in pdf_titles:
                pdf_titles[url] = self.extract_title_smart(item['element'], f"Document {len(all_pdfs)}")
        
        for item in href_results['others']:
            url = item['url']
            all_others.add(url)
            if url not in other_titles:
                other_titles[url] = self.extract_title_smart(item['element'], f"Link {len(all_others)}")
        
        # Strategy 3: regex scan
        logger.info("📍 Strategy 3: regex scan")
        regex_results = self.strategy_3_regex_scan(html_content)
        all_videos.update(regex_results['videos'])
        all_pdfs.update(regex_results['pdfs'])
        all_others.update(regex_results['others'])
        
        # Strategy 4: data attributes
        logger.info("📍 Strategy 4: data attributes")
        data_results = self.strategy_4_data_attributes(soup)
        all_videos.update(data_results['videos'])
        all_pdfs.update(data_results['pdfs'])
        
        # Build final results
        videos = []
        for idx, url in enumerate(sorted(all_videos), 1):
            videos.append({
                'title': video_titles.get(url, f"Video {idx}"),
                'url': url
            })
        
        pdfs = []
        for idx, url in enumerate(sorted(all_pdfs), 1):
            pdfs.append({
                'title': pdf_titles.get(url, f"Document {idx}"),
                'url': url
            })
        
        others = []
        for idx, url in enumerate(sorted(all_others), 1):
            others.append({
                'title': other_titles.get(url, f"Link {idx}"),
                'url': url
            })
        
        logger.info(f"✅ Extraction complete: {len(videos)} videos, {len(pdfs)} PDFs, {len(others)} links")
        
        return {
            'title': title,
            'videos': videos,
            'pdfs': pdfs,
            'others': others
        }
    
    def format_to_txt(self, parsed_data: dict) -> str:
        """📄 Format to beautiful TXT"""
        lines = []
        
        # Header
        lines.append("=" * 80)
        lines.append(f"📄 {parsed_data['title']}")
        lines.append("=" * 80)
        lines.append("")
        
        # Videos
        if parsed_data['videos']:
            lines.append(f"🎬 VIDEOS ({len(parsed_data['videos'])})")
            lines.append("-" * 80)
            for idx, item in enumerate(parsed_data['videos'], 1):
                lines.append(f"\n[{idx}] {item['title']}")
                lines.append(f"    🔗 {item['url']}")
            lines.append("\n")
        
        # PDFs
        if parsed_data['pdfs']:
            lines.append(f"📚 PDFs ({len(parsed_data['pdfs'])})")
            lines.append("-" * 80)
            for idx, item in enumerate(parsed_data['pdfs'], 1):
                lines.append(f"\n[{idx}] {item['title']}")
                lines.append(f"    🔗 {item['url']}")
            lines.append("\n")
        
        # Others
        if parsed_data['others']:
            lines.append(f"🔗 OTHER LINKS ({len(parsed_data['others'])})")
            lines.append("-" * 80)
            for idx, item in enumerate(parsed_data['others'], 1):
                lines.append(f"\n[{idx}] {item['title']}")
                lines.append(f"    🔗 {item['url']}")
            lines.append("\n")
        
        # Summary
        lines.append("=" * 80)
        lines.append("📊 SUMMARY")
        lines.append("-" * 80)
        lines.append(f"Total Videos: {len(parsed_data['videos'])}")
        lines.append(f"Total PDFs: {len(parsed_data['pdfs'])}")
        lines.append(f"Total Other Links: {len(parsed_data['others'])}")
        lines.append(f"Grand Total: {len(parsed_data['videos']) + len(parsed_data['pdfs']) + len(parsed_data['others'])}")
        lines.append(f"\n⏰ Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("🤖 Powered by Hardcore HTML Parser")
        lines.append("=" * 80)
        
        return '\n'.join(lines)


# ==================== BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command"""
    keyboard = [
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🤖 <b>HTML to TXT Converter - Hardcore Edition</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ <b>Features:</b>\n"
        "• 🔥 Multi-strategy parsing\n"
        "• 🎯 Extracts ALL links (no exceptions)\n"
        "• 🔓 Aggressive URL decoding\n"
        "• ⚡️ Lightning fast\n\n"
        "📝 Send me any HTML file!",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Document handler"""
    document = update.message.document
    
    if not (document.file_name.endswith('.html') or document.file_name.endswith('.htm')):
        await update.message.reply_text("❌ Please send HTML file only!")
        return
    
    if document.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(f"❌ File too large! Max: {MAX_FILE_SIZE // (1024*1024)}MB")
        return
    
    progress_msg = await update.message.reply_text("⏳ Processing...", parse_mode=ParseMode.HTML)
    
    temp_file = None
    output_file = None
    
    try:
        # Download
        file = await context.bot.get_file(document.file_id)
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.html') as tf:
            temp_file = tf.name
            await file.download_to_drive(temp_file)
        
        await progress_msg.edit_text("⏳ Parsing HTML with 4 strategies...")
        
        # Read & Parse
        with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()
        
        parser = HardcoreHTMLParser()
        parsed_data = parser.parse_html_hardcore(html_content)
        
        await progress_msg.edit_text("⏳ Generating TXT...")
        
        # Generate TXT
        txt_content = parser.format_to_txt(parsed_data)
        txt_filename = os.path.splitext(document.file_name)[0] + '.txt'
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tf:
            output_file = tf.name
            tf.write(txt_content)
        
        # Update stats
        stats['total_conversions'] += 1
        stats['total_videos'] += len(parsed_data['videos'])
        stats['total_pdfs'] += len(parsed_data['pdfs'])
        stats['total_links'] += len(parsed_data['others'])
        
        # Send
        caption = (
            f"✅ <b>Conversion Complete!</b>\n\n"
            f"📊 <b>Extracted:</b>\n"
            f"  • 🎬 Videos: {len(parsed_data['videos'])}\n"
            f"  • 📚 PDFs: {len(parsed_data['pdfs'])}\n"
            f"  • 🔗 Links: {len(parsed_data['others'])}\n"
            f"  • 📈 Total: {len(parsed_data['videos']) + len(parsed_data['pdfs']) + len(parsed_data['others'])}"
        )
        
        with open(output_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=txt_filename,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        
        await progress_msg.delete()
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await progress_msg.edit_text(f"❌ Error: {str(e)[:200]}")
    
    finally:
        try:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            if output_file and os.path.exists(output_file):
                os.remove(output_file)
        except:
            pass


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Button handler"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "stats":
        uptime = datetime.now() - stats['start_time']
        text = (
            f"📊 <b>Statistics</b>\n\n"
            f"🔄 Conversions: {stats['total_conversions']}\n"
            f"🎬 Videos: {stats['total_videos']}\n"
            f"📚 PDFs: {stats['total_pdfs']}\n"
            f"🔗 Links: {stats['total_links']}\n\n"
            f"⏱ Uptime: {uptime.days}d {uptime.seconds//3600}h"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML)


# ==================== WEB SERVER FOR RENDER ====================

async def health_check(request):
    """Health check endpoint for Render"""
    return web.json_response({
        'status': 'healthy',
        'uptime': str(datetime.now() - stats['start_time']),
        'conversions': stats['total_conversions']
    })


async def start_web_server():
    """Start web server for health checks"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Web server started on port {PORT}")


async def start_bot():
    """Initialize bot"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not found!")
        return
    
    logger.info("🚀 Starting bot...")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start web server for Render health check
    await start_web_server()
    
    # Use webhook if URL provided, else polling
    if WEBHOOK_URL:
        logger.info(f"🔗 Using webhook: {WEBHOOK_URL}")
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        await application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/webhook",
            webhook_url=f"{WEBHOOK_URL}/webhook"
        )
    else:
        logger.info("📡 Using polling mode")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        
        # Keep running
        while True:
            await asyncio.sleep(1)


def main():
    """Main entry point"""
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped")


if __name__ == "__main__":
    main()
