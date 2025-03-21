import os
import time
from datetime import datetime

class FileManager:
    def __init__(self):
        self.base_dir = 'downloads'
        self._files_cache = None
        self._cache_time = 0
        self._cache_ttl = 30  # Cache TTL in seconds
    
    def list_files(self, offset=0, limit=None):
        """List all downloaded files with optional pagination."""
        current_time = time.time()
        
        # Use cached results if available and fresh
        if self._files_cache and current_time - self._cache_time < self._cache_ttl:
            files = self._files_cache
        else:
            # Fetch and cache files
            files = self._scan_files()
            self._files_cache = files
            self._cache_time = current_time
        
        # Apply pagination
        if limit:
            return files[offset:offset+limit]
        elif offset:
            return files[offset:]
        return files
    
    def _scan_files(self):
        """Scan the downloads directory for files."""
        files = []
        
        # Walk through the downloads directory
        for root, _, filenames in os.walk(self.base_dir):
            for filename in filenames:
                # Construct the full path
                full_path = os.path.join(root, filename)
                
                # Skip partial downloads or non-files
                if not os.path.isfile(full_path) or filename.endswith('.partial'):
                    continue
                
                # Get relative path from downloads directory
                relative_path = os.path.relpath(full_path, self.base_dir)
                
                # Get file size and modified time efficiently
                try:
                    stat_info = os.stat(full_path)
                    size_bytes = stat_info.st_size
                    size = self._format_size(size_bytes)
                    modified_time = stat_info.st_mtime
                except Exception as e:
                    size = "Unknown"
                    size_bytes = 0
                    modified_time = 0
                
                # Add file info to list
                files.append({
                    'full_path': full_path,
                    'relative_path': relative_path,
                    'filename': filename,
                    'size': size,
                    'size_bytes': size_bytes,
                    'modified_time': modified_time
                })
        
        # Sort files by modification time (newest first)
        files.sort(key=lambda x: x['modified_time'], reverse=True)
        
        return files
    
    def rename_file(self, index, new_name):
        """Rename a file by its index."""
        files = self.list_files()
        
        if not files:
            return {'success': False, 'message': 'No files found'}
        
        if index < 0 or index >= len(files):
            return {'success': False, 'message': f'Invalid index: {index+1}'}
        
        file_info = files[index]
        dir_name = os.path.dirname(file_info['full_path'])
        new_full_path = os.path.join(dir_name, new_name)
        
        # Check if target already exists
        if os.path.exists(new_full_path):
            return {'success': False, 'message': f'Target file already exists: {new_name}'}
        
        try:
            os.rename(file_info['full_path'], new_full_path)
            new_relative_path = os.path.relpath(new_full_path, self.base_dir)
            
            # Invalidate cache
            self._files_cache = None
            
            return {
                'success': True, 
                'new_path': new_full_path, 
                'new_relative_path': new_relative_path
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def delete_file(self, index):
        """Delete a file by its index."""
        files = self.list_files()
        
        if not files:
            return {'success': False, 'message': 'No files found'}
        
        if index < 0 or index >= len(files):
            return {'success': False, 'message': f'Invalid index: {index+1}'}
        
        file_info = files[index]
        
        try:
            os.remove(file_info['full_path'])
            
            # Invalidate cache
            self._files_cache = None
            
            return {
                'success': True, 
                'deleted_path': file_info['relative_path']
            }
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
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
