import os
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename, Message, MessageMediaPhoto
from telethon.errors import FloodWaitError

from utils.download_manager import DownloadManager
from utils.file_manager import FileManager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = int(os.getenv('API_ID'))
API_HASH = os.getenv('API_HASH')
ALLOWED_USERS = list(map(int, filter(None, os.getenv('ALLOWED_USERS', '').split(','))))

# Initialize the client
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Initialize managers
download_manager = DownloadManager()
file_manager = FileManager()

def is_user_allowed(user_id):
    """Check if user is allowed to use the bot."""
    return len(ALLOWED_USERS) == 0 or user_id in ALLOWED_USERS

def create_command_handler(pattern):
    """Factory function for command handlers with error handling."""
    def decorator(handler_func):
        @bot.on(events.NewMessage(pattern=pattern))
        async def command_handler(event):
            # Check if user is allowed
            if not is_user_allowed(event.sender_id):
                await event.respond("⛔ You are not authorized to use this bot.")
                return
            
            try:
                return await handler_func(event)
            except Exception as e:
                logger.error(f"Command error: {str(e)}")
                await event.respond(f"❌ Error: {str(e)}")
            raise events.StopPropagation
        return command_handler
    return decorator

# Command handlers
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    if not is_user_allowed(event.sender_id):
        await event.respond("⛔ You are not authorized to use this bot.")
        return
        
    help_text = """
📥 **Telegram File Manager Bot** 📥

This bot helps you manage file downloads:

Commands:
- /start - Show this help message
- /list [page] - List downloaded files (paginated)
- /rename <index> <new name> - Rename a file
- /delete <index> - Delete a file
- /cancel <download_id> - Cancel an active download
- /active - View active downloads

You can:
- Send files directly to download
- Forward messages with files or images
- Send Telegram links to download files

Files are stored by date (YYYYMMDD/filename)
    """
    await event.respond(help_text)
    raise events.StopPropagation

@create_command_handler(r'/list(?: (\d+))?')
async def list_command(event):
    page = int(event.pattern_match.group(1) or 1)
    page_size = 10
    start_idx = (page - 1) * page_size
    
    files = file_manager.list_files()
    
    if not files:
        await event.respond("No files have been downloaded yet.")
        return
    
    total_pages = (len(files) + page_size - 1) // page_size
    paged_files = files[start_idx:start_idx + page_size]
    
    response = f"📂 **Downloaded Files** (Page {page}/{total_pages}):\n\n"
    for idx, file_info in enumerate(paged_files, start_idx + 1):
        response += f"{idx}. `{file_info['relative_path']}`\n"
        response += f"   Size: {file_info['size']}\n\n"
    
    if page < total_pages:
        response += f"Use `/list {page+1}` to see the next page."
    
    await event.respond(response)

@create_command_handler(r'/rename (\d+) (.+)')
async def rename_command(event):
    index = int(event.pattern_match.group(1))
    new_name = event.pattern_match.group(2)
    
    result = file_manager.rename_file(index - 1, new_name)
    if result['success']:
        await event.respond(f"✅ File renamed to: `{result['new_relative_path']}`")
    else:
        await event.respond(f"❌ Error: {result['message']}")

@create_command_handler(r'/delete (\d+)')
async def delete_command(event):
    index = int(event.pattern_match.group(1))
    
    result = file_manager.delete_file(index - 1)
    if result['success']:
        await event.respond(f"✅ File deleted: `{result['deleted_path']}`")
    else:
        await event.respond(f"❌ Error: {result['message']}")

@create_command_handler(r'/cancel (\S+)')
async def cancel_command(event):
    download_id = event.pattern_match.group(1)
    
    result = download_manager.cancel_download(download_id)
    if result['success']:
        await event.respond(f"✅ Download cancelled: `{result['filename']}`")
    else:
        await event.respond(f"❌ Error: {result['message']}")

@create_command_handler(r'/active')
async def active_downloads_command(event):
    downloads = download_manager.list_active_downloads()
    
    if not downloads:
        await event.respond("No active downloads.")
        return
    
    response = "📥 **Active Downloads**:\n\n"
    for idx, (download_id, info) in enumerate(downloads.items(), 1):
        percentage = int(info['downloaded'] * 100 / max(info['size'], 1))
        response += f"{idx}. `{info['filename']}`\n"
        response += f"   Progress: {percentage}%, ID: `{download_id}`\n\n"
    
    response += "To cancel a download, use `/cancel <download_id>`"
    
    await event.respond(response)

# Handle direct file uploads and forwarded messages
@bot.on(events.NewMessage)
async def handle_message(event):
    # Check if user is allowed
    if not is_user_allowed(event.sender_id):
        await event.respond("⛔ You are not authorized to use this bot.")
        return
        
    # Debug logging
    logger.debug(f"Received message with media type: {type(event.message.media) if event.message.media else 'None'}")
    
    # Check if message has any media content
    if event.message.media:
        await download_from_message(event)
        return
    
    # Check for Telegram links
    message_text = event.message.text
    if message_text and ("t.me/" in message_text or "telegram.me/" in message_text):
        status_message = await event.respond("⏳ Processing Telegram link...")
        try:
            await download_manager.process_telegram_link(
                bot, message_text, event.chat_id, status_message.id
            )
        except Exception as e:
            await bot.edit_message(
                event.chat_id, status_message.id, f"❌ Error processing link: {str(e)}"
            )
        return

async def download_from_message(event):
    """Handle downloads from any message with media content"""
    status_message = await event.respond("⏳ Starting download...")
    
    try:
        # Define a default filename based on current timestamp
        default_filename = f"file_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        filename = default_filename
        
        # Check if it's a photo
        if isinstance(event.message.media, MessageMediaPhoto):
            filename = f"photo_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        
        # Or check for document attributes 
        elif hasattr(event.message.media, 'document') and event.message.media.document:
            for attribute in event.message.media.document.attributes:
                if isinstance(attribute, DocumentAttributeFilename) and attribute.file_name:
                    filename = attribute.file_name
                    break
        
        # Start download process
        download_id = await download_manager.download_telegram_file(
            bot, event.message, event.chat_id, status_message.id, filename
        )
        
        # Inform user about cancellation option
        if download_id:
            # Check if the download is still active before adding cancellation info
            active_downloads = download_manager.list_active_downloads()
            if download_id in active_downloads:
                current_message = await bot.get_messages(event.chat_id, ids=status_message.id)
                await bot.edit_message(
                    event.chat_id, 
                    status_message.id,
                    f"{current_message.text}\n\nTo cancel this download use: `/cancel {download_id}`"
                )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        await bot.edit_message(
            event.chat_id, status_message.id, f"❌ Download failed: {str(e)}"
        )

# Main function
def main():
    """Start the bot."""
    logger.info("Starting bot...")
    
    # Create downloads directory if it doesn't exist
    os.makedirs('downloads', exist_ok=True)
    
    # Start the client
    bot.run_until_disconnected()

if __name__ == '__main__':
    main()