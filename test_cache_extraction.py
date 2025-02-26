import os
import sys
import time
from pathlib import Path

# Add the parent directory to the path so we can import the ChromeHistoryViewer modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from ChromeHistoryViewer.config import CHROME_CACHE, CHROME_NETWORK

def scan_cache_directories():
    """Scan Chrome cache directories and print statistics"""
    print("\n=== Chrome Cache Directories ===")
    
    # Check if directories exist
    print(f"Main cache directory: {CHROME_CACHE}")
    print(f"  - Exists: {os.path.exists(CHROME_CACHE)}")
    
    print(f"Network cache directory: {CHROME_NETWORK}")
    print(f"  - Exists: {os.path.exists(CHROME_NETWORK)}")
    
    # Count files in each directory
    cache_files = []
    network_files = []
    
    if os.path.exists(CHROME_CACHE):
        for root, _, files in os.walk(CHROME_CACHE):
            for file in files:
                cache_files.append(os.path.join(root, file))
    
    if os.path.exists(CHROME_NETWORK):
        for root, _, files in os.walk(CHROME_NETWORK):
            for file in files:
                network_files.append(os.path.join(root, file))
    
    print(f"\nFiles in main cache: {len(cache_files)}")
    print(f"Files in network cache: {len(network_files)}")
    
    # Print some statistics about file sizes
    if cache_files:
        cache_sizes = [os.path.getsize(f) for f in cache_files]
        print(f"Main cache file sizes: min={min(cache_sizes)}, max={max(cache_sizes)}, avg={sum(cache_sizes)/len(cache_sizes):.2f}")
    
    if network_files:
        network_sizes = [os.path.getsize(f) for f in network_files]
        print(f"Network cache file sizes: min={min(network_sizes)}, max={max(network_sizes)}, avg={sum(network_sizes)/len(network_sizes):.2f}")
    
    return cache_files, network_files

def analyze_cache_file(file_path):
    """Analyze a single cache file for HTML content"""
    print(f"\n=== Analyzing Cache File: {os.path.basename(file_path)} ===")
    print(f"File size: {os.path.getsize(file_path)} bytes")
    
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        # Try different encodings
        for encoding in ['utf-8', 'latin1', 'gbk', 'gb2312']:
            try:
                content_str = content.decode(encoding, errors='ignore')
                
                # Look for HTML tags
                html_start = content_str.find('<html')
                html_end = content_str.rfind('</html>')
                
                if html_start >= 0 and html_end >= 0:
                    html_content = content_str[html_start:html_end + 7]
                    print(f"Found HTML content using {encoding} encoding")
                    print(f"HTML content length: {len(html_content)}")
                    print(f"HTML content preview: {html_content[:100]}...")
                    
                    # Look for URLs in the content
                    urls = find_urls(content_str)
                    if urls:
                        print(f"Found {len(urls)} URLs in content:")
                        for url in urls[:5]:  # Show first 5 URLs
                            print(f"  - {url}")
                        if len(urls) > 5:
                            print(f"  - ... and {len(urls) - 5} more")
                    
                    return True
                
                # Look for other HTML indicators
                body_start = content_str.find('<body')
                if body_start >= 0:
                    print(f"Found <body> tag but no complete HTML using {encoding} encoding")
                    
                    # Look for URLs in the content
                    urls = find_urls(content_str)
                    if urls:
                        print(f"Found {len(urls)} URLs in content:")
                        for url in urls[:5]:  # Show first 5 URLs
                            print(f"  - {url}")
                        if len(urls) > 5:
                            print(f"  - ... and {len(urls) - 5} more")
                    
                    return True
                
            except Exception as e:
                print(f"Error decoding with {encoding}: {str(e)}")
        
        print("No HTML content found in file")
        return False
        
    except Exception as e:
        print(f"Error analyzing file: {str(e)}")
        return False

def find_urls(content):
    """Find URLs in content"""
    import re
    url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+\.[^\s<>"\']+'
    return re.findall(url_pattern, content)

def main():
    """Main function"""
    print("=== Chrome Cache Analysis Tool ===")
    
    # Scan cache directories
    cache_files, network_files = scan_cache_directories()
    
    # Analyze some random files from each directory
    print("\n=== Sample Analysis ===")
    
    # Analyze up to 5 files from main cache
    if cache_files:
        print("\nAnalyzing files from main cache:")
        for i, file in enumerate(sorted(cache_files, key=os.path.getsize, reverse=True)[:5]):
            print(f"\nFile {i+1}/{min(5, len(cache_files))}")
            analyze_cache_file(file)
    
    # Analyze up to 5 files from network cache
    if network_files:
        print("\nAnalyzing files from network cache:")
        for i, file in enumerate(sorted(network_files, key=os.path.getsize, reverse=True)[:5]):
            print(f"\nFile {i+1}/{min(5, len(network_files))}")
            analyze_cache_file(file)
    
    print("\n=== Analysis Complete ===")

if __name__ == "__main__":
    main() 