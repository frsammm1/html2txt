#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram HTML to TXT Converter Bot
Optimized for Render.com Free Tier (512MB RAM)
Author: Your Name
"""

import os
import re
import logging
from datetime import datetime
from urllib.parse import unquote
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode
import asyncio
from collections import defaultdict

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

class HTMLToTXTConverter:
    """Advanced HTML to TXT converter with deep parsing capabilities"""
    
    def __init__(self):
        self.video_patterns = [
            r'onclick=["\']playVideo\(["\']([^"\']+)["\']',
            r'href=["\']#["\'][^>]*onclick=["\']playVideo\(["\']([^"\']+)["\']',
            r'<a[^>]*onclick=["\']playVideo\(["\']([^"\']+)["\']',
            r'playVideo\(["\']([^"\']+)["\']',
            r'src:\s*{?\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'source.*?src=["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'https?://[^\s<>"\']+\.m3u8[^\s<>"\']*',
            r'https?://[^\s<>"\']*youtube\.com/watch\?v=[^\s<>"\']+',
            r'https?://[^\s<>"\']*youtube\.com/live/[^\s<>"\']+',
        ]
        
        self.pdf_patterns = [
            r'onclick=["\']viewPDF\(["\']([^"\']+)["\']',
            r'href=["\']([^"\']*\.pdf[^"\']*)["\']',
            r'https?://[^\s<>"\']+\.pdf[^\s<>"\']*',
            r'viewPDF\(["\']([^"\']+)["\']',
            r'downloadFile\(["\']([^"\']+)["\']',
        ]
        
        self.other_patterns = [
            r'href=["\'](?!#)([^"\']+)["\']',
            r'https?://[^\s<>"\']+',
        ]

    def decode_url(self, encoded_url: str) -> str:
        """Decode obfuscated URLs with multiple encoding layers"""
        try:
            # Handle base64 encoded URLs
            import base64
            
            # Try double base64 decode (common pattern)
            try:
                decoded = base64.b64decode(encoded_url).decode('utf-8')
                decoded = base64.b64decode(decoded).decode('utf-8')
                # Remove prefix if present (like "kvsKeGh")
                if decoded.startswith(('http://', 'https://')):
                    return decoded
                # Try removing first 8 characters as mentioned in examples
                if len(decoded) > 8:
                    potential_url = decoded[8:]
                    if potential_url.startswith(('http://', 'https://')):
                        return potential_url
                return decoded
            except:
                pass
            
            # Try single base64 decode
            try:
                decoded = base64.b64decode(encoded_url).decode('utf-8')
                if decoded.startswith(('http://', 'https://')):
                    return decoded
            except:
                pass
            
            # URL decode
            decoded = unquote(encoded_url)
            if decoded != encoded_url:
                return self.decode_url(decoded)
            
            return encoded_url
        except:
            return encoded_url

    def extract_title_from_element(self, element) -> str:
        """Extract title/name from HTML element"""
        # Try multiple ways to get title
        title = None
        
        # Check for direct text content
        if element.string:
            title = element.string.strip()
        
        # Check nested spans/divs
        if not title:
            for tag in ['span', 'div', 'p']:
                nested = element.find(tag)
                if nested and nested.get_text(strip=True):
                    title = nested.get_text(strip=True)
                    break
        
        # Get all text if still no title
        if not title:
            title = element.get_text(strip=True)
        
        # Clean title
        if title:
            # Remove common prefixes
            title = re.sub(r'^(𝙼𝚎𝚗𝚍𝚊𝚡|Watch|Download|View|Play)\s*', '', title)
            # Remove timestamps
            title = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', '', title)
            # Remove extra whitespace
            title = ' '.join(title.split())
            # Remove PDF/Download suffixes
            title = re.sub(r'\.pdf(-\d+)?$', '', title)
            title = re.sub(r'📥\s*Download.*$', '', title)
        
        return title or "Untitled"

    def parse_html_deep(self, html_content: str) -> dict:
        """Deep parsing of HTML with comprehensive link extraction"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        results = {
            'videos': [],
            'pdfs': [],
            'others': [],
            'title': 'Untitled Document'
        }
        
        # Extract document title
        title_tag = soup.find('title')
        if title_tag:
            results['title'] = title_tag.get_text(strip=True)
        else:
            header = soup.find(['h1', 'h2', 'div'], class_=re.compile(r'(header|title)'))
            if header:
                results['title'] = header.get_text(strip=True)
        
        seen_urls = set()
        
        # Extract videos
        video_containers = soup.find_all(['a', 'div', 'li'], 
                                        class_=re.compile(r'(video|list-group-item)', re.I))
        
        for container in video_containers:
            # Try to find onclick with playVideo
            onclick = container.get('onclick', '')
            title = self.extract_title_from_element(container)
            url = None
            
            # Extract from onclick
            for pattern in self.video_patterns:
                matches = re.findall(pattern, str(container) + onclick)
                for match in matches:
                    decoded = self.decode_url(match)
                    if decoded.startswith(('http://', 'https://')) and decoded not in seen_urls:
                        url = decoded
                        seen_urls.add(decoded)
                        break
                if url:
                    break
            
            if url and ('m3u8' in url or 'youtube.com' in url or 'youtu.be' in url):
                results['videos'].append({'title': title, 'url': url})
        
        # Extract PDFs
        pdf_containers = soup.find_all(['a', 'div', 'li'], 
                                       class_=re.compile(r'(pdf|list-group-item)', re.I))
        
        for container in pdf_containers:
            onclick = container.get('onclick', '')
            href = container.get('href', '')
            title = self.extract_title_from_element(container)
            url = None
            
            # Extract from onclick/href
            for pattern in self.pdf_patterns:
                matches = re.findall(pattern, str(container) + onclick + href)
                for match in matches:
                    decoded = self.decode_url(match)
                    if decoded.startswith(('http://', 'https://')) and '.pdf' in decoded.lower() and decoded not in seen_urls:
                        url = decoded
                        seen_urls.add(decoded)
                        break
                if url:
                    break
            
            if url:
                results['pdfs'].append({'title': title, 'url': url})
        
        # Extract other links
        other_containers = soup.find_all('a', href=True)
        
        for link in other_containers:
            href = link.get('href', '')
            if href.startswith('#') or not href:
                continue
            
            title = self.extract_title_from_element(link)
            url = href
            
            # Decode if needed
            if not url.startswith(('http://', 'https://')):
                url = self.decode_url(url)
            
            # Skip if already added or is video/pdf
            if url in seen_urls:
                continue
            
            if not ('.m3u8' in url or '.pdf' in url or 'youtube.com' in url):
                if url.startswith(('http://', 'https://')):
                    results['others'].append({'title': title, 'url': url})
                    seen_urls.add(url)
        
        return results

    def format_to_txt(self, parsed_data: dict) -> str:
        """Format parsed data to structured TXT"""
        lines = []
        lines.append(f"📄 {parsed_data['title']}\n")
        lines.append("=" * 50 + "\n")
        
        # Videos section
        if parsed_data['videos']:
            lines.append(f"\n🎬 Videos ({len(parsed_data['videos'])})\n")
            lines.append("-" * 50 + "\n")
            for idx, item in enumerate(parsed_data['videos'], 1):
                lines.append(f"{idx}. {item['title']}\n")
                lines.append(f"   {item['url']}\n\n")
        
        # PDFs section
        if parsed_data['pdfs']:
            lines.append(f"\n📚 PDFs ({len(parsed_data['pdfs'])})\n")
            lines.append("-" * 50 + "\n")
            for idx, item in enumerate(parsed_data['pdfs'], 1):
                lines.append(f"{idx}. {item['title']}\n")
                lines.append(f"   {item['url']}\n\n")
        
        # Others section
        if parsed_data['others']:
            lines.append(f"\n🔗 Other Links ({len(parsed_data['others'])})\n")
            lines.append("-" * 50 + "\n")
            for idx, item in enumerate(parsed_data['others'], 1):
                lines.append(f"{idx}. {item['title']}\n")
                lines.append(f"   {item['url']}\n\n")
        
        # Summary
        lines.append("\n" + "=" * 50 + "\n")
        lines.append(f"📊 Total: {len(parsed_data['videos'])} videos, {len(parsed_data['pdfs'])} PDFs, {len(parsed_data['others'])} other links\n")
        lines.append(f"⏰ Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        return ''.join(lines)

    def convert(self, html_content: str) -> str:
        """Main conversion method"""
        parsed = self.parse_html_deep(html_content)
        return self.format_to_txt(parsed)


# Bot handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    keyboard = [
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "🤖 <b>HTML to TXT Converter Bot</b>\n\n"
        "📝 Send me an HTML file and I'll convert it to structured TXT format!\n\n"
        "<b>Features:</b>\n"
        "✅ Deep parsing of HTML structure\n"
        "✅ Automatic URL decoding\n"
        "✅ Organized categorization (Videos/PDFs/Others)\n"
        "✅ Progress tracking\n"
        "✅ Fast & accurate conversion\n\n"
        "Just send me your HTML file to get started! 🚀"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = (
        "📖 <b>How to Use:</b>\n\n"
        "1️⃣ Send me your HTML file\n"
        "2️⃣ Wait for conversion (with progress bar)\n"
        "3️⃣ Download the converted TXT file\n\n"
        "<b>Supported formats:</b>\n"
        "• Video links (.m3u8, YouTube)\n"
        "• PDF files\n"
        "• Other web links\n\n"
        "<b>Features:</b>\n"
        "• Decodes obfuscated URLs\n"
        "• Extracts titles automatically\n"
        "• Organizes by type\n"
        "• Shows detailed statistics\n\n"
        "Need help? Contact @YourSupport"
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle uploaded HTML files"""
    document = update.message.document
    
    # Check if it's an HTML file
    if not (document.file_name.endswith('.html') or document.file_name.endswith('.htm')):
        await update.message.reply_text(
            "❌ Please send an HTML file (.html or .htm)"
        )
        return
    
    # File size check (max 20MB)
    if document.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "❌ File too large! Maximum size is 20MB."
        )
        return
    
    # Send initial processing message
    status_msg = await update.message.reply_text(
        "⏳ <b>Processing your file...</b>\n\n"
        "📥 Downloading: ░░░░░░░░░░ 0%",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_path = f"temp_{update.effective_user.id}_{document.file_name}"
        await file.download_to_drive(file_path)
        
        # Update progress
        await status_msg.edit_text(
            "⏳ <b>Processing your file...</b>\n\n"
            "📥 Downloading: ██████████ 100%\n"
            "🔍 Parsing: ░░░░░░░░░░ 0%",
            parse_mode=ParseMode.HTML
        )
        
        # Read and convert
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        await status_msg.edit_text(
            "⏳ <b>Processing your file...</b>\n\n"
            "📥 Downloading: ██████████ 100%\n"
            "🔍 Parsing: █████░░░░░ 50%",
            parse_mode=ParseMode.HTML
        )
        
        # Convert
        converter = HTMLToTXTConverter()
        txt_content = converter.convert(html_content)
        
        await status_msg.edit_text(
            "⏳ <b>Processing your file...</b>\n\n"
            "📥 Downloading: ██████████ 100%\n"
            "🔍 Parsing: ██████████ 100%\n"
            "💾 Generating: ░░░░░░░░░░ 0%",
            parse_mode=ParseMode.HTML
        )
        
        # Save TXT file
        txt_filename = document.file_name.rsplit('.', 1)[0] + '.txt'
        txt_path = f"temp_{update.effective_user.id}_{txt_filename}"
        
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(txt_content)
        
        await status_msg.edit_text(
            "⏳ <b>Processing your file...</b>\n\n"
            "📥 Downloading: ██████████ 100%\n"
            "🔍 Parsing: ██████████ 100%\n"
            "💾 Generating: ██████████ 100%\n"
            "✅ <b>Complete!</b>",
            parse_mode=ParseMode.HTML
        )
        
        # Send file
        await update.message.reply_document(
            document=open(txt_path, 'rb'),
            filename=txt_filename,
            caption=(
                "✅ <b>Conversion Complete!</b>\n\n"
                f"📄 Original: {document.file_name}\n"
                f"📝 Converted: {txt_filename}\n"
                f"⏱ Time: {datetime.now().strftime('%H:%M:%S')}"
            ),
            parse_mode=ParseMode.HTML
        )
        
        # Cleanup
        os.remove(file_path)
        os.remove(txt_path)
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await status_msg.edit_text(
            f"❌ <b>Error during conversion:</b>\n\n{str(e)}\n\n"
            "Please try again or contact support.",
            parse_mode=ParseMode.HTML
        )
        # Cleanup on error
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(txt_path):
                os.remove(txt_path)
        except:
            pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        await help_command(update, context)
    elif query.data == "stats":
        stats_text = (
            "📊 <b>Bot Statistics</b>\n\n"
            "🚀 Status: Online\n"
            "⚡️ Speed: Ultra Fast\n"
            "💾 Storage: Optimized\n"
            "🔒 Security: High\n\n"
            "Powered by Render.com 🌐"
        )
        await query.edit_message_text(stats_text, parse_mode=ParseMode.HTML)

async def keep_alive(context: ContextTypes.DEFAULT_TYPE):
    """Keep bot alive with periodic ping"""
    logger.info("Bot is alive! ✅")

def main():
    """Start the bot"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not found in environment variables!")
        return
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add keep-alive job (every minute)
    application.job_queue.run_repeating(keep_alive, interval=60, first=10)
    
    # Start bot
    logger.info("Bot started! 🚀")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
