import os
import sys
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, Slot, QTimer

# Add the parent directory to the path so we can import the ChromeHistoryViewer modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from ChromeHistoryViewer.core.cache_monitor import ChromeCacheMonitor
from ChromeHistoryViewer.core.page_downloader import WebPageDownloader
from ChromeHistoryViewer.config import DEFAULT_SAVE_DIR, CHROME_CACHE, CHROME_NETWORK

class TestHandler(QObject):
    """Handler for testing the cache monitor and page downloader"""
    
    def __init__(self):
        super().__init__()
        self.cache_monitor = None
        self.downloader = None
        self.test_urls = [
            # Add some test URLs here - these should be URLs you've recently visited in Chrome
            (0, "Google", "https://www.google.com"),
            (1, "GitHub", "https://github.com"),
            (2, "Stack Overflow", "https://stackoverflow.com")
        ]
        self.found_content = {}
        self.save_dir = os.path.join(current_dir, 'test_markdown_output')
        os.makedirs(self.save_dir, exist_ok=True)
        
        # Initialize the cache monitor
        self.init_cache_monitor()
        
    def init_cache_monitor(self):
        """Initialize the cache monitor"""
        print("Initializing cache monitor...")
        self.cache_monitor = ChromeCacheMonitor()
        self.cache_monitor.content_ready.connect(self.handle_cache_content)
        self.cache_monitor.start()
        
        # Wait for the cache monitor to initialize
        time.sleep(2)
        
        print("Cache monitor initialized")
        print(f"Cache directory exists: {os.path.exists(CHROME_CACHE)}")
        print(f"Network directory exists: {os.path.exists(CHROME_NETWORK)}")
        
    def start_test(self):
        """Start the test process"""
        print("\n=== Starting Test ===")
        print(f"Testing with URLs: {[url for _, _, url in self.test_urls]}")
        print(f"Save directory: {self.save_dir}")
        
        # Initialize the downloader
        self.downloader = WebPageDownloader(self.test_urls, self.save_dir, self.cache_monitor)
        self.downloader.progress.connect(self.update_progress)
        self.downloader.page_finished.connect(self.page_finished)
        self.downloader.finished.connect(self.test_finished)
        
        # Start the downloader
        print("\nStarting downloader...")
        self.downloader.start()
    
    @Slot(str, str)
    def handle_cache_content(self, url, content):
        """Handle content found in the cache"""
        print(f"\n=== Content found for URL: {url} ===")
        print(f"Content length: {len(content)}")
        print(f"Content preview: {content[:100]}...")
        
        self.found_content[url] = content
        
        if self.downloader:
            print("Forwarding content to downloader...")
            self.downloader.handle_cache_content(url, content)
    
    @Slot(int, str)
    def update_progress(self, value, status):
        """Update progress information"""
        print(f"Progress: {value}% - {status}")
    
    @Slot(int, bool, str)
    def page_finished(self, row, success, message):
        """Handle page finished event"""
        url = self.test_urls[row][2]
        print(f"\nPage finished: Row {row}, URL: {url}")
        print(f"Success: {success}, Message: {message}")
        
        # Check if the file was created
        title = self.test_urls[row][1]
        from ChromeHistoryViewer.core.utils import get_safe_title
        filename = f"{get_safe_title(title, url)}.md"
        filepath = os.path.join(self.save_dir, filename)
        
        if os.path.exists(filepath):
            print(f"File created: {filepath}")
            print(f"File size: {os.path.getsize(filepath)} bytes")
        else:
            print(f"File not created: {filepath}")
    
    @Slot(bool)
    def test_finished(self, normal_completion):
        """Handle test finished event"""
        print("\n=== Test Finished ===")
        print(f"Normal completion: {normal_completion}")
        print(f"URLs found in cache: {len(self.found_content)}/{len(self.test_urls)}")
        
        # List created files
        print("\nCreated files:")
        for filename in os.listdir(self.save_dir):
            filepath = os.path.join(self.save_dir, filename)
            print(f"- {filename} ({os.path.getsize(filepath)} bytes)")
        
        # Schedule application exit
        QTimer.singleShot(1000, self.cleanup_and_exit)
    
    def cleanup_and_exit(self):
        """Clean up resources and exit"""
        print("\nCleaning up...")
        
        if self.downloader and self.downloader.isRunning():
            print("Stopping downloader...")
            self.downloader.stop()
        
        if self.cache_monitor and self.cache_monitor.isRunning():
            print("Stopping cache monitor...")
            self.cache_monitor.stop()
        
        print("Exiting application")
        QApplication.quit()

def main():
    """Main function"""
    app = QApplication(sys.argv)
    
    # Create and start the test handler
    test_handler = TestHandler()
    
    # Start the test after a short delay
    QTimer.singleShot(1000, test_handler.start_test)
    
    # Run the application
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 