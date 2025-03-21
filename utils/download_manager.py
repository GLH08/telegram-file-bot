import os
import asyncio
import aiohttp
import time
import logging
import uuid
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetMessagesRequest
from telethon.errors import FloodWaitError
import re

# Configure logging
logger = logging.getLogger(__name__)

class DownloadManager:
    def __init__(self):
        self.active_downloads = {}
        self.update_interval = 1  # Update progress more frequently (every 1 second)
        self.max_concurrent_downloads = 5  # Allow up to 5 concurrent downloads
    
    async def _get_unique_filepath(self, directory, filename):
        """Generate a unique filename to avoid overwriting existing files."""
        original_filepath = os.path.join(directory, filename)
        
        # If file doesn't exist, use original name
        if not os.path.exists(original_filepath):
            return original_filepath
        
        # Split filename and extension
        name, ext = os.path.splitext(filename)
        
        # Try with numeric suffix
        counter = 1
        while True:
            new_filename = f"{name} ({counter}){ext}"
            new_filepath = os.path.join(directory, new_filename)
            
            if not os.path.exists(new_filepath):
                return new_filepath
            
            counter += 1
    
    async def download_telegram_file(self, client, message, chat_id, status_msg_id, filename):
        """Download a file from a Telegram message."""
        # Check concurrent download limit
        if len(self.active_downloads) >= self.max_concurrent_downloads:
            await client.edit_message(
                chat_id, status_msg_id, "❌ Maximum concurrent downloads reached. Try again later."
            )
            return None
            
        # Generate a unique download ID
        download_id = str(uuid.uuid4())[:8]
        
        today = datetime.now().strftime('%Y%m%d')
        download_path = os.path.join('downloads', today)
        os.makedirs(download_path, exist_ok=True)
        
        # Get unique file path to prevent overwriting
        file_path = await self._get_unique_filepath(download_path, filename)
        relative_path = os.path.relpath(file_path, 'downloads')
        
        # Extract just the filename without path
        filename = os.path.basename(file_path)
        
        download_info = {
            'download_id': download_id,
            'filename': filename,
            'path': file_path,
            'relative_path': relative_path,
            'size': 0,
            'downloaded': 0,
            'speed': 0,
            'status': 'downloading',
            'start_time': time.time(),
            'last_update_time': time.time(),
            'last_downloaded': 0,
            'last_message': '',  # Store the last message to prevent duplicate updates
            'task': None,  # Will store the download task for cancellation
            'initial_phase': True,  # Flag for initial download phase
        }
        
        key = f"{chat_id}_{status_msg_id}"
        self.active_downloads[key] = download_info
        
        # Create initial progress message immediately
        await client.edit_message(
            chat_id,
            status_msg_id,
            f"⏬ Downloading: `{download_info['filename']}`\n"
            f"🔄 Initializing download...\n"
            f"🔢 Download ID: `{download_id}`"
        )
        
        # Start progress updater
        update_task = asyncio.create_task(
            self._update_progress(client, chat_id, status_msg_id)
        )
        
        try:
            # Log before download
            logger.info(f"Starting download for {filename}, ID: {download_id}")
            
            # Create the actual download task
            download_task = asyncio.create_task(
                client.download_media(
                    message,
                    file_path,
                    progress_callback=lambda d, t: self._progress_callback(
                        d, t, chat_id, status_msg_id
                    )
                )
            )
            
            # Store the task for potential cancellation
            if key in self.active_downloads:
                self.active_downloads[key]['task'] = download_task
            
            # Await the download
            downloaded_file = await download_task
            
            # Check if download was successful
            if not downloaded_file or not os.path.exists(downloaded_file):
                raise Exception("Download failed - file not saved")
            
            # Only proceed if the download wasn't cancelled
            if key in self.active_downloads and self.active_downloads[key]['status'] != 'cancelled':
                # Get actual file size
                file_size = os.path.getsize(downloaded_file)
                
                # Mark download as complete
                download_info = self.active_downloads[key]
                download_info['status'] = 'completed'
                download_info['size'] = file_size
                download_info['downloaded'] = file_size
                
                # Final update with better formatting
                date_part = os.path.dirname(relative_path)
                filename_part = os.path.basename(relative_path)
                formatted_date = ""
                if date_part and len(date_part) == 8:
                    try:
                        year = date_part[0:4]
                        month = date_part[4:6]
                        day = date_part[6:8]
                        formatted_date = f"{year}-{month}-{day}"
                    except:
                        formatted_date = date_part

                await client.edit_message(
                    chat_id,
                    status_msg_id,
                    f"✅ **Download Complete**\n\n"
                    f"**File:** `{filename_part}`\n"
                    f"**Folder:** {formatted_date}\n"
                    f"**Size:** {self._format_size(file_size)}\n"
                    f"**Path:** `{relative_path}`"
                )
                
                logger.info(f"Download completed for {filename}, ID: {download_id}, size: {file_size} bytes")
            
            return download_id
            
        except asyncio.CancelledError:
            # Download was cancelled
            logger.info(f"Download cancelled for {filename}, ID: {download_id}")
            
            # Update status message
            await client.edit_message(
                chat_id,
                status_msg_id,
                f"🛑 Download cancelled: `{filename}`"
            )
            
            # Clean up partial file
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Removed partial file: {file_path}")
                except Exception as e:
                    logger.error(f"Error removing partial file: {str(e)}")
            
            return None
            
        except FloodWaitError as e:
            # Handle rate limits
            wait_time = e.seconds
            logger.warning(f"Rate limited for {wait_time} seconds")
            
            if key in self.active_downloads:
                self.active_downloads[key]['status'] = 'waiting'
            
            await client.edit_message(
                chat_id,
                status_msg_id,
                f"⏳ Rate limited by Telegram. Waiting {wait_time} seconds..."
            )
            
            await asyncio.sleep(wait_time)
            
            # Retry download
            await client.edit_message(
                chat_id,
                status_msg_id,
                f"🔄 Retrying download after rate limit..."
            )
            
            # Try again with recursion
            return await self.download_telegram_file(client, message, chat_id, status_msg_id, filename)
            
        except Exception as e:
            # Log the error
            logger.error(f"Download error: {str(e)}")
            
            # Mark download as failed
            if key in self.active_downloads:
                self.active_downloads[key]['status'] = 'failed'
            
            await client.edit_message(
                chat_id,
                status_msg_id,
                f"❌ Download failed: {str(e)}"
            )
            
            return None
            
        finally:
            # Clean up if not already cleaned
            if key in self.active_downloads and self.active_downloads[key]['status'] not in ['cancelled']:
                await asyncio.sleep(5)  # Keep info for a few seconds
                del self.active_downloads[key]
            
            # Cancel updater
            update_task.cancel()
    
    def cancel_download(self, download_id):
        """Cancel an active download by its ID."""
        for key, info in list(self.active_downloads.items()):
            if info.get('download_id') == download_id:
                # Cancel the download task
                if info.get('task') and not info['task'].done():
                    info['task'].cancel()
                
                # Mark as cancelled
                info['status'] = 'cancelled'
                
                # Clean up partial file if it exists
                if os.path.exists(info['path']):
                    try:
                        os.remove(info['path'])
                    except Exception as e:
                        logger.error(f"Error removing partial file: {str(e)}")
                
                # Return success
                return {
                    'success': True,
                    'filename': info['filename'],
                    'download_id': download_id
                }
        
        # Download ID not found
        return {
            'success': False,
            'message': f"No active download found with ID: {download_id}"
        }
    
    def list_active_downloads(self):
        """List all currently active downloads."""
        return {info.get('download_id'): {
            'filename': info['filename'],
            'downloaded': info['downloaded'],
            'size': info['size'],
            'status': info['status'],
            'speed': info['speed']
        } for key, info in self.active_downloads.items() 
          if info['status'] in ['downloading', 'waiting']}
    
    async def process_telegram_link(self, client, link, chat_id, status_msg_id):
        """Process a Telegram link to download its content."""
        # Parse message link
        match = re.search(r't\.me/(?:c/)?([a-zA-Z0-9_]+)/(\d+)', link)
        if not match:
            await client.edit_message(
                chat_id, status_msg_id, "❌ Invalid Telegram link format"
            )
            return
        
        channel, message_id = match.groups()
        message_id = int(message_id)
        
        try:
            # Get the message
            entity = await client.get_entity(channel)
            message = await client.get_messages(entity, ids=message_id)
            
            if not message or not message.media:
                await client.edit_message(
                    chat_id, status_msg_id, "❌ No media found in the linked message"
                )
                return
            
            # Get filename
            filename = f"file_from_link_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if hasattr(message.media, 'document'):
                for attribute in message.media.document.attributes:
                    if hasattr(attribute, 'file_name'):
                        filename = attribute.file_name
                        break
            
            # Download the file
            download_id = await self.download_telegram_file(
                client, message, chat_id, status_msg_id, filename
            )
            
            # Inform user about cancellation option
            if download_id:
                # Only add cancellation info if download is still active
                active_downloads = self.list_active_downloads()
                if download_id in active_downloads:
                    current_message = await client.get_messages(chat_id, ids=status_msg_id)
                    await client.edit_message(
                        chat_id, 
                        status_msg_id,
                        f"{current_message.text}\n\nTo cancel this download use: `/cancel {download_id}`"
                    )
            
        except Exception as e:
            logger.error(f"Link processing error: {str(e)}")
            await client.edit_message(
                chat_id, status_msg_id, f"❌ Error processing link: {str(e)}"
            )
    
    def _progress_callback(self, downloaded, total, chat_id, status_msg_id):
        """Callback to track download progress."""
        key = f"{chat_id}_{status_msg_id}"
        if key not in self.active_downloads:
            return
        
        # Get download info
        download_info = self.active_downloads[key]
        if download_info['status'] == 'cancelled':
            return
        
        # Always update progress in initial stages
        if download_info['downloaded'] < 1024 * 1024:  # First 1MB
            significant_change = True
            # After first data received, mark initial phase as done
            if downloaded > 0 and download_info['initial_phase']:
                download_info['initial_phase'] = False
        else:
            # Only update on significant changes to reduce processing overhead
            # Use a smaller threshold for updates - only 1% change or 256KB
            if total and total > 0:
                min_progress = min(256 * 1024, total * 0.01)
            else:
                min_progress = 256 * 1024  # 256KB if total unknown
            
            progress_since_last = abs(downloaded - download_info['last_downloaded'])
            significant_change = progress_since_last >= min_progress
        
        # Always update when reaching 100%
        if total and downloaded == total:
            significant_change = True
        
        if significant_change:
            # Update download info
            download_info['downloaded'] = downloaded
            
            # Get total size if available
            if total and total > 0:
                download_info['size'] = total
            
            # Calculate speed
            current_time = time.time()
            elapsed = current_time - download_info['last_update_time']
            if elapsed >= 0.1:  # Update speed more frequently
                downloaded_since_last = downloaded - download_info['last_downloaded']
                if elapsed > 0:  # Avoid division by zero
                    download_info['speed'] = downloaded_since_last / elapsed
                download_info['last_update_time'] = current_time
                download_info['last_downloaded'] = downloaded
    
    async def _update_progress(self, client, chat_id, status_msg_id):
        """Task to periodically update progress messages."""
        key = f"{chat_id}_{status_msg_id}"
        
        try:
            while key in self.active_downloads:
                download_info = self.active_downloads[key]
                
                if download_info['status'] == 'downloading':
                    # Calculate progress
                    if download_info['size'] > 0:
                        percentage = int(download_info['downloaded'] * 100 / download_info['size'])
                    else:
                        # If size unknown, show a waiting indicator
                        percentage = 0
                    
                    # Calculate speed and ETA
                    speed = download_info['speed']
                    speed_str = f"{self._format_size(speed)}/s"
                    
                    eta = "unknown"
                    if speed > 0 and download_info['size'] > download_info['downloaded']:
                        remaining_bytes = download_info['size'] - download_info['downloaded']
                        eta_seconds = remaining_bytes / speed
                        eta = self._format_time(eta_seconds)
                    
                    # Create progress bar
                    bar_length = 20
                    filled_length = int(bar_length * percentage / 100)
                    bar = '█' * filled_length + '░' * (bar_length - filled_length)
                    
                    # If in initial phase with no data, show special message
                    if download_info['initial_phase'] and download_info['downloaded'] == 0:
                        new_message = (
                            f"⏬ Downloading: `{download_info['filename']}`\n"
                            f"🔄 Establishing connection to Telegram servers...\n"
                            f"⏱️ This might take a moment for large files\n"
                            f"🔢 Download ID: `{download_info['download_id']}`"
                        )
                    else:
                        # Normal progress message
                        new_message = (
                            f"⏬ Downloading: `{download_info['filename']}`\n"
                            f"🔄 Progress: |{bar}| {percentage}%\n"
                            f"📊 {self._format_size(download_info['downloaded'])} "
                        )
                        
                        # Add size info if available
                        if download_info['size'] > 0:
                            new_message += f"of {self._format_size(download_info['size'])}\n"
                        else:
                            new_message += f"downloaded\n"
                        
                        # Add speed and ETA
                        new_message += f"🚀 Speed: {speed_str}"
                        if download_info['size'] > 0 and speed > 0:
                            new_message += f", ETA: {eta}\n"
                        else:
                            new_message += "\n"
                        
                        # Add download ID
                        new_message += f"🔢 Download ID: `{download_info['download_id']}`"
                    
                    # Only update if the message content has changed
                    if new_message != download_info['last_message']:
                        try:
                            await client.edit_message(chat_id, status_msg_id, new_message)
                            download_info['last_message'] = new_message
                        except Exception as e:
                            # Only log if it's not the "content not modified" error
                            if "Content of the message was not modified" not in str(e):
                                logger.error(f"Error updating progress message: {str(e)}")
                
                # Dynamic update interval based on download phase
                if download_info['initial_phase']:
                    await asyncio.sleep(1)  # Quick updates during initialization
                elif download_info['size'] > 500 * 1024 * 1024:  # >500MB
                    await asyncio.sleep(3)  # Slower updates for very large files
                elif download_info['size'] > 100 * 1024 * 1024:  # >100MB
                    await asyncio.sleep(2)  # Medium updates for large files
                else:
                    await asyncio.sleep(1)  # Quick updates for smaller files
                
        except asyncio.CancelledError:
            # Task was cancelled, just exit
            pass
        except Exception as e:
            # Log the error but don't crash
            logger.error(f"Error in progress updater: {str(e)}")
    
    def _format_size(self, size_bytes):
        """Format bytes to human-readable size."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"
    
    def _format_time(self, seconds):
        """Format seconds to readable time."""
        if seconds < 60:
            return f"{int(seconds)} sec"
        elif seconds < 3600:
            return f"{int(seconds/60)} min {int(seconds%60)} sec"
        else:
            return f"{int(seconds/3600)} hr {int((seconds%3600)/60)} min"