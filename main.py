#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 Telegram HTML to TXT Converter Bot - Ultra Powerful Edition
✨ Optimized for Render.com Free Tier (512MB RAM)
🚀 Deep Parsing | Smart URL Decoding | Memory Efficient
"""

import os
import re
import logging
import base64
import asyncio
from datetime import datetime
from urllib.parse import unquote, quote
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
import tempfile

# ==================== LOGGING SETUP ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit

# ==================== STATISTICS ====================
stats = {
    'total_conversions': 0,
    'total_videos': 0,
    'total_pdfs': 0,
    'total_links': 0,
    'start_time': datetime.now()
}


class AdvancedHTMLParser:
    """🔥 Ultra-Powerful HTML Parser with Deep Link Extraction"""
    
    def __init__(self):
        # Enhanced patterns for maximum coverage
        self.video_patterns = [
            # onclick patterns
            r'onclick\s*=\s*["\']playVideo\s*\(\s*["\']([^"\']+)["\']',
            r'playVideo\s*\(\s*["\']([^"\']+)["\']',
            r'loadVideo\s*\(\s*["\']([^"\']+)["\']',
            
            # Direct m3u8 links
            r'https?://[^\s<>"\']*\.m3u8[^\s<>"\']*',
            r'src\s*:\s*{?\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'source.*?src\s*=\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
            
            # YouTube patterns
            r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
            r'https?://(?:www\.)?youtube\.com/live/[\w-]+',
            r'https?://youtu\.be/[\w-]+',
            r'youtube\.com/embed/[\w-]+',
            
            # Video platforms
            r'https?://[^\s<>"\']*(?:vimeo|dailymotion|twitch)\.(?:com|tv)/[^\s<>"\']+',
            
            # Encoded video URLs
            r'video["\']?\s*:\s*["\']([^"\']+)["\']',
            r'videoUrl["\']?\s*:\s*["\']([^"\']+)["\']',
        ]
        
        self.pdf_patterns = [
            # onclick patterns
            r'onclick\s*=\s*["\'](?:viewPDF|downloadFile|openPDF)\s*\(\s*["\']([^"\']+)["\']',
            r'viewPDF\s*\(\s*["\']([^"\']+)["\']',
            r'downloadFile\s*\(\s*["\']([^"\']+)["\']',
            
            # Direct PDF links
            r'href\s*=\s*["\']([^"\']*\.pdf[^"\']*)["\']',
            r'https?://[^\s<>"\']+\.pdf[^\s<>"\']*',
            
            # PDF in data attributes
            r'data-pdf\s*=\s*["\']([^"\']+)["\']',
            r'data-file\s*=\s*["\']([^"\']*\.pdf[^"\']*)["\']',
        ]
        
        self.link_patterns = [
            r'href\s*=\s*["\']([^"\'#][^"\']*)["\']',
            r'https?://[^\s<>"\']+',
            r'data-url\s*=\s*["\']([^"\']+)["\']',
        ]
    
    def decode_url(self, encoded_url: str, depth: int = 0) -> str:
        """🔓 Multi-layer URL decoder with intelligence"""
        if depth > 5:  # Prevent infinite recursion
            return encoded_url
        
        try:
            original = encoded_url.strip()
            
            # Try Base64 decoding (single and double)
            if not original.startswith(('http://', 'https://', 'www.')):
                try:
                    # Double Base64 decode
                    decoded = base64.b64decode(original).decode('utf-8', errors='ignore')
                    decoded = base64.b64decode(decoded).decode('utf-8', errors='ignore')
                    
                    # Remove common prefixes (like "kvsKeGh" - 8 chars)
                    if len(decoded) > 8 and not decoded.startswith(('http://', 'https://')):
                        decoded = decoded[8:]
                    
                    if decoded.startswith(('http://', 'https://')):
                        return decoded
                except:
                    pass
                
                try:
                    # Single Base64 decode
                    decoded = base64.b64decode(original).decode('utf-8', errors='ignore')
                    if decoded.startswith(('http://', 'https://')):
                        return decoded
                    # Try removing prefix
                    if len(decoded) > 8:
                        decoded = decoded[8:]
                        if decoded.startswith(('http://', 'https://')):
                            return decoded
                except:
                    pass
            
            # URL decoding
            decoded = unquote(original)
            if decoded != original and not decoded.startswith(('http://', 'https://')):
                return self.decode_url(decoded, depth + 1)
            
            # Clean up URL
            if decoded.startswith(('http://', 'https://')):
                # Remove trailing garbage
                decoded = re.sub(r'["\'>]+$', '', decoded)
                return decoded
            
            return original
            
        except Exception as e:
            logger.debug(f"Decode error: {e}")
            return encoded_url
    
    def extract_title(self, element, default: str = "Untitled") -> str:
        """📝 Smart title extraction from HTML elements"""
        try:
            # Priority 1: Direct text in specific elements
            for tag in ['span', 'div', 'strong', 'b', 'p', 'h1', 'h2', 'h3', 'h4']:
                found = element.find(tag, class_=re.compile(r'(title|name|item-title)', re.I))
                if found and found.get_text(strip=True):
                    title = found.get_text(strip=True)
                    return self.clean_title(title)
            
            # Priority 2: Element with class containing 'title'
            title_elem = element.find(class_=re.compile(r'title', re.I))
            if title_elem:
                title = title_elem.get_text(strip=True)
                return self.clean_title(title)
            
            # Priority 3: Direct text content
            text = element.get_text(strip=True)
            if text:
                return self.clean_title(text)
            
            # Priority 4: Check attributes
            for attr in ['title', 'data-title', 'aria-label', 'alt']:
                if element.get(attr):
                    return self.clean_title(element.get(attr))
            
            return default
            
        except Exception as e:
            logger.debug(f"Title extraction error: {e}")
            return default
    
    def clean_title(self, title: str) -> str:
        """🧹 Clean and format title"""
        if not title:
            return "Untitled"
        
        # Remove common prefixes
        title = re.sub(r'^(𝙼𝚎𝚗𝚍𝚊𝚡|Watch|Download|View|Play|Click|Open)\s*', '', title, flags=re.I)
        
        # Remove timestamps
        title = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', '', title)
        
        # Remove file extensions from titles
        title = re.sub(r'\.(?:pdf|html|htm|txt)(?:\s*-\s*\d+)?$', '', title, flags=re.I)
        
        # Remove download/PDF indicators
        title = re.sub(r'(?:📥|🔥)\s*Download.*$', '', title, flags=re.I)
        title = re.sub(r'\s*@\w+\s*$', '', title)  # Remove usernames
        
        # Clean extra whitespace
        title = ' '.join(title.split())
        
        # Truncate if too long
        if len(title) > 200:
            title = title[:197] + "..."
        
        return title or "Untitled"
    
    def parse_html(self, html_content: str, progress_callback=None) -> dict:
        """🎯 Deep HTML parsing with comprehensive link extraction"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        results = {
            'title': 'Converted Document',
            'videos': [],
            'pdfs': [],
            'others': []
        }
        
        seen_urls = set()
        
        # Extract document title
        if progress_callback:
            asyncio.create_task(progress_callback("🔍 Extracting document title..."))
        
        title_tag = soup.find('title')
        if title_tag and title_tag.get_text(strip=True):
            results['title'] = self.clean_title(title_tag.get_text(strip=True))
        else:
            for tag in ['h1', 'h2', 'div']:
                header = soup.find(tag, class_=re.compile(r'(header|title|brand)', re.I))
                if header and header.get_text(strip=True):
                    results['title'] = self.clean_title(header.get_text(strip=True))
                    break
        
        # Phase 1: Extract Videos
        if progress_callback:
            asyncio.create_task(progress_callback("🎬 Extracting video links..."))
        
        video_containers = soup.find_all(['a', 'div', 'li', 'button'], 
                                         class_=re.compile(r'(video|play|watch|stream)', re.I))
        
        # Also check onclick attributes anywhere
        onclick_elements = soup.find_all(attrs={'onclick': re.compile(r'play|video|load', re.I)})
        video_containers.extend(onclick_elements)
        
        for container in video_containers:
            onclick = container.get('onclick', '')
            href = container.get('href', '')
            data_url = container.get('data-url', '')
            
            combined_text = str(container) + onclick + href + data_url
            
            for pattern in self.video_patterns:
                matches = re.findall(pattern, combined_text, re.I)
                for match in matches:
                    decoded_url = self.decode_url(match)
                    
                    # Validate video URL
                    if decoded_url.startswith(('http://', 'https://')) and decoded_url not in seen_urls:
                        if any(x in decoded_url.lower() for x in ['.m3u8', 'youtube.com', 'youtu.be', 'vimeo.com', 'twitch.tv']):
                            title = self.extract_title(container, f"Video {len(results['videos']) + 1}")
                            results['videos'].append({'title': title, 'url': decoded_url})
                            seen_urls.add(decoded_url)
                            break
        
        # Phase 2: Extract PDFs
        if progress_callback:
            asyncio.create_task(progress_callback("📚 Extracting PDF links..."))
        
        pdf_containers = soup.find_all(['a', 'div', 'li', 'button'], 
                                       class_=re.compile(r'(pdf|document|download|file)', re.I))
        
        onclick_pdf = soup.find_all(attrs={'onclick': re.compile(r'pdf|document|download', re.I)})
        pdf_containers.extend(onclick_pdf)
        
        for container in pdf_containers:
            onclick = container.get('onclick', '')
            href = container.get('href', '')
            data_url = container.get('data-url', '')
            
            combined_text = str(container) + onclick + href + data_url
            
            for pattern in self.pdf_patterns:
                matches = re.findall(pattern, combined_text, re.I)
                for match in matches:
                    decoded_url = self.decode_url(match)
                    
                    if decoded_url.startswith(('http://', 'https://')) and '.pdf' in decoded_url.lower() and decoded_url not in seen_urls:
                        title = self.extract_title(container, f"Document {len(results['pdfs']) + 1}")
                        results['pdfs'].append({'title': title, 'url': decoded_url})
                        seen_urls.add(decoded_url)
                        break
        
        # Phase 3: Extract Other Links
        if progress_callback:
            asyncio.create_task(progress_callback("🔗 Extracting other links..."))
        
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '').strip()
            
            # Skip anchors, javascript, and empty
            if not href or href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                continue
            
            decoded_url = href if href.startswith(('http://', 'https://')) else self.decode_url(href)
            
            # Skip if already added or is video/pdf
            if decoded_url in seen_urls:
                continue
            
            # Check if it's not a video or PDF
            is_media = any(x in decoded_url.lower() for x in [
                '.m3u8', '.pdf', 'youtube.com', 'youtu.be', 'vimeo.com'
            ])
            
            if decoded_url.startswith(('http://', 'https://')) and not is_media:
                title = self.extract_title(link, f"Link {len(results['others']) + 1}")
                results['others'].append({'title': title, 'url': decoded_url})
                seen_urls.add(decoded_url)
        
        return results
    
    def format_to_txt(self, parsed_data: dict) -> str:
        """📄 Format parsed data to beautiful TXT structure"""
        lines = []
        
        # Header
        lines.append("=" * 80)
        lines.append(f"📄 {parsed_data['title']}")
        lines.append("=" * 80)
        lines.append("")
        
        # Videos Section
        if parsed_data['videos']:
            lines.append(f"🎬 VIDEOS ({len(parsed_data['videos'])})")
            lines.append("-" * 80)
            for idx, item in enumerate(parsed_data['videos'], 1):
                lines.append(f"\n[{idx}] {item['title']}")
                lines.append(f"    🔗 {item['url']}")
            lines.append("\n")
        
        # PDFs Section
        if parsed_data['pdfs']:
            lines.append(f"📚 PDFs ({len(parsed_data['pdfs'])})")
            lines.append("-" * 80)
            for idx, item in enumerate(parsed_data['pdfs'], 1):
                lines.append(f"\n[{idx}] {item['title']}")
                lines.append(f"    🔗 {item['url']}")
            lines.append("\n")
        
        # Other Links Section
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
        lines.append("🤖 Powered by HTML2TXT Converter Bot")
        lines.append("=" * 80)
        
        return '\n'.join(lines)


# ==================== BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command with beautiful UI"""
    keyboard = [
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats")],
        [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/YourUsername")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "🤖 <b>HTML to TXT Converter Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✨ <b>Features:</b>\n"
        "• 🔍 Deep HTML parsing\n"
        "• 🔓 Smart URL decoding (Base64, etc.)\n"
        "• 🎯 Extracts ALL links (videos, PDFs, others)\n"
        "• 📊 Real-time progress tracking\n"
        "• ⚡️ Lightning fast conversion\n"
        "• 💾 Memory optimized\n\n"
        "📝 <b>Usage:</b>\n"
        "Just send me any HTML file and I'll convert it to a clean, organized TXT format!\n\n"
        "🚀 Ready to convert? Send me a file!"
    )
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detailed help message"""
    help_text = (
        "📖 <b>HOW TO USE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Step 1:</b> Send me your HTML file\n"
        "<b>Step 2:</b> Wait for conversion (with progress)\n"
        "<b>Step 3:</b> Download your TXT file\n\n"
        "🎯 <b>SUPPORTED CONTENT:</b>\n"
        "• 🎬 Video links (.m3u8, YouTube, Vimeo, etc.)\n"
        "• 📚 PDF documents\n"
        "• 🔗 All other web links\n\n"
        "💡 <b>SMART FEATURES:</b>\n"
        "• Decodes obfuscated URLs automatically\n"
        "• Extracts titles intelligently\n"
        "• Organizes by content type\n"
        "• Handles large files efficiently\n"
        "• No link left behind!\n\n"
        "⚙️ <b>TECHNICAL SPECS:</b>\n"
        "• Max file size: 50MB\n"
        "• Supported formats: .html, .htm\n"
        "• Processing time: ~5-30 seconds\n\n"
        "❓ Need help? Contact @YourSupport"
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main document handler with progress tracking"""
    document = update.message.document
    user = update.effective_user
    
    # Validate file type
    if not (document.file_name.endswith('.html') or document.file_name.endswith('.htm')):
        await update.message.reply_text(
            "❌ <b>Invalid file type!</b>\n\n"
            "Please send an HTML file (.html or .htm)",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Validate file size
    if document.file_size > MAX_FILE_SIZE:
        await update.message.reply_text(
            f"❌ <b>File too large!</b>\n\n"
            f"Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB\n"
            f"Your file: {document.file_size // (1024*1024)}MB",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Progress message
    progress_msg = await update.message.reply_text(
        "⏳ <b>Processing...</b>\n\n"
        "📥 Downloading: <code>░░░░░░░░░░</code> 0%",
        parse_mode=ParseMode.HTML
    )
    
    temp_file = None
    output_file = None
    
    try:
        # Download phase
        file = await context.bot.get_file(document.file_id)
        
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.html') as tf:
            temp_file = tf.name
            await file.download_to_drive(temp_file)
        
        await progress_msg.edit_text(
            "⏳ <b>Processing...</b>\n\n"
            "📥 Downloading: <code>██████████</code> 100%\n"
            "🔍 Parsing HTML: <code>░░░░░░░░░░</code> 0%",
            parse_mode=ParseMode.HTML
        )
        
        # Read file
        with open(temp_file, 'r', encoding='utf-8', errors='ignore') as f:
            html_content = f.read()
        
        await progress_msg.edit_text(
            "⏳ <b>Processing...</b>\n\n"
            "📥 Downloading: <code>██████████</code> 100%\n"
            "🔍 Parsing HTML: <code>█████░░░░░</code> 50%",
            parse_mode=ParseMode.HTML
        )
        
        # Parse HTML
        parser = AdvancedHTMLParser()
        
        async def progress_callback(message):
            try:
                await progress_msg.edit_text(
                    f"⏳ <b>Processing...</b>\n\n"
                    f"📥 Downloading: <code>██████████</code> 100%\n"
                    f"{message}",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
        
        parsed_data = parser.parse_html(html_content, progress_callback)
        
        await progress_msg.edit_text(
            "⏳ <b>Processing...</b>\n\n"
            "📥 Downloading: <code>██████████</code> 100%\n"
            "🔍 Parsing HTML: <code>██████████</code> 100%\n"
            "💾 Generating TXT: <code>░░░░░░░░░░</code> 0%",
            parse_mode=ParseMode.HTML
        )
        
        # Generate TXT
        txt_content = parser.format_to_txt(parsed_data)
        
        # Save TXT
        txt_filename = os.path.splitext(document.file_name)[0] + '.txt'
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as tf:
            output_file = tf.name
            tf.write(txt_content)
        
        await progress_msg.edit_text(
            "⏳ <b>Processing...</b>\n\n"
            "📥 Downloading: <code>██████████</code> 100%\n"
            "🔍 Parsing HTML: <code>██████████</code> 100%\n"
            "💾 Generating TXT: <code>██████████</code> 100%\n"
            "✅ <b>Complete!</b>",
            parse_mode=ParseMode.HTML
        )
        
        # Update statistics
        stats['total_conversions'] += 1
        stats['total_videos'] += len(parsed_data['videos'])
        stats['total_pdfs'] += len(parsed_data['pdfs'])
        stats['total_links'] += len(parsed_data['others'])
        
        # Send file
        caption = (
            "✅ <b>Conversion Complete!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📄 <b>Original:</b> {document.file_name}\n"
            f"📝 <b>Converted:</b> {txt_filename}\n\n"
            f"📊 <b>Extracted:</b>\n"
            f"  • 🎬 Videos: {len(parsed_data['videos'])}\n"
            f"  • 📚 PDFs: {len(parsed_data['pdfs'])}\n"
            f"  • 🔗 Links: {len(parsed_data['others'])}\n"
            f"  • 📈 Total: {len(parsed_data['videos']) + len(parsed_data['pdfs']) + len(parsed_data['others'])}\n\n"
            f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        with open(output_file, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=txt_filename,
                caption=caption,
                parse_mode=ParseMode.HTML
            )
        
        await progress_msg.delete()
        
        logger.info(f"Conversion successful for user {user.id}: {document.file_name}")
        
    except Exception as e:
        logger.error(f"Conversion error for user {user.id}: {e}", exc_info=True)
        await progress_msg.edit_text(
            f"❌ <b>Error during conversion!</b>\n\n"
            f"<code>{str(e)[:200]}</code>\n\n"
            "Please try again or contact support if the issue persists.",
            parse_mode=ParseMode.HTML
        )
    
    finally:
        # Cleanup
        try:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            if output_file and os.path.exists(output_file):
                os.remove(output_file)
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "help":
        help_text = (
            "📖 <b>Quick Help</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send me an HTML file and I'll:\n"
            "• Extract all video links 🎬\n"
            "• Extract all PDF links 📚\n"
            "• Extract all other links 🔗\n"
            "• Organize everything beautifully ✨\n\n"
            "Use /help for detailed instructions!"
        )
        await query.edit_message_text(help_text, parse_mode=ParseMode.HTML)
    
    elif query.data == "stats":
        uptime = datetime.now() - stats['start_time']
        stats_text = (
            "📊 <b>Bot Statistics</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔄 Total Conversions: <b>{stats['total_conversions']}</b>\n"
            f"🎬 Videos Extracted: <b>{stats['total_videos']}</b>\n"
            f"📚 PDFs Extracted: <b>{stats['total_pdfs']}</b>\n"
            f"🔗 Links Extracted: <b>{stats['total_links']}</b>\n\n"
            f"⏱ Uptime: <b>{uptime.days}d {uptime.seconds//3600}h</b>\n"
            f"🚀 Status: <b>Online</b>\n"
            f"💾 Server: <b>Render.com Free Tier</b>\n\n"
            "Powered by Advanced HTML Parser 🔥"
        )
        await query.edit_message_text(stats_text, parse_mode=ParseMode.HTML)


def main():
    """Initialize and start the bot"""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not found in environment variables!")
        return
    
    logger.info("🚀 Starting HTML to TXT Converter Bot...")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Log startup
    logger.info("✅ Bot initialized successfully!")
    logger.info("📊 Statistics tracking enabled")
    logger.info("🔥 Advanced HTML parser loaded")
    logger.info("⚡️ Ready to convert HTML files!")
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
