import os
import sys
import html2text
from pathlib import Path

# Add the parent directory to the path so we can import the ChromeHistoryViewer modules
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from ChromeHistoryViewer.core.page_downloader import WebPageDownloader

def test_html_to_markdown_conversion():
    """Test the HTML to Markdown conversion functionality"""
    print("=== HTML to Markdown Conversion Test ===")
    
    # Create a test directory
    test_dir = os.path.join(current_dir, 'test_markdown_output')
    os.makedirs(test_dir, exist_ok=True)
    
    # Sample HTML content
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Page</title>
    </head>
    <body>
        <h1>Test Heading</h1>
        <p>This is a <strong>test</strong> paragraph with <a href="https://example.com">a link</a>.</p>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
            <li>Item 3</li>
        </ul>
        <pre><code>
        def hello_world():
            print("Hello, World!")
        </code></pre>
        <table>
            <tr>
                <th>Header 1</th>
                <th>Header 2</th>
            </tr>
            <tr>
                <td>Cell 1</td>
                <td>Cell 2</td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    # Create a converter instance directly
    print("\n=== Direct Converter Test ===")
    converter = html2text.HTML2Text()
    configure_converter(converter)
    
    # Convert HTML to Markdown
    markdown = converter.handle(sample_html)
    print("Converted Markdown:")
    print(markdown)
    
    # Save to file
    direct_file = os.path.join(test_dir, 'direct_conversion.md')
    with open(direct_file, 'w', encoding='utf-8') as f:
        f.write(markdown)
    print(f"Saved to: {direct_file}")
    
    # Test using the WebPageDownloader class
    print("\n=== WebPageDownloader Test ===")
    
    # Create a minimal downloader instance
    downloader = WebPageDownloader([], test_dir)
    
    # Use the save_as_markdown method
    test_url = "https://example.com/test"
    test_title = "Test Page"
    
    try:
        downloader.save_as_markdown(0, test_title, test_url, sample_html, "test")
        print("Successfully saved using WebPageDownloader")
        
        # Check the file
        expected_file = os.path.join(test_dir, f"{test_title}.md")
        if os.path.exists(expected_file):
            print(f"File created: {expected_file}")
            print(f"File size: {os.path.getsize(expected_file)} bytes")
            
            # Read and print the content
            with open(expected_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print("\nFile content:")
            print(content[:500] + "..." if len(content) > 500 else content)
        else:
            print(f"File not created: {expected_file}")
    except Exception as e:
        print(f"Error saving markdown: {str(e)}")
    
    print("\n=== Test Complete ===")

def configure_converter(converter):
    """Configure the HTML to Markdown converter with the same settings as in the app"""
    converter.unicode_snob = True
    converter.body_width = 0
    converter.ignore_images = False
    converter.ignore_emphasis = False
    converter.ignore_links = False
    converter.protect_links = True
    converter.mark_code = True

if __name__ == "__main__":
    test_html_to_markdown_conversion() 