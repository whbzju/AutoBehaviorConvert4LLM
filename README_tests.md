# Chrome History Viewer Test Suite

This directory contains test scripts to validate the functionality of the Chrome History Viewer application, specifically focusing on the cache monitor and page downloader components.

## Test Scripts

1. **test_html_to_markdown.py** - Tests the HTML to Markdown conversion functionality
2. **test_cache_extraction.py** - Tests the cache extraction functionality by analyzing Chrome's cache files
3. **test_cache_monitor.py** - Full integration test of the cache monitor and page downloader components
4. **run_tests.py** - Script to run all tests and provide a summary

## Running the Tests

### Prerequisites

- Python 3.6 or higher
- PySide6
- html2text
- watchdog

Make sure you have Chrome installed and have browsed some websites recently to ensure there's content in the cache.

### Basic Tests

To run the basic tests (HTML to Markdown conversion and cache extraction):

```bash
python run_tests.py
```

### Full Integration Test

To run all tests including the full integration test:

```bash
python run_tests.py --full
```

Note: The full integration test requires Chrome to be running and may take longer to complete.

### Individual Tests

You can also run individual tests directly:

```bash
python test_html_to_markdown.py
python test_cache_extraction.py
python test_cache_monitor.py
```

## Test Output

The tests will create a directory called `test_markdown_output` to store the converted Markdown files. You can examine these files to verify the conversion quality.

## Troubleshooting

If the tests fail, check the following:

1. Make sure Chrome is installed and you have browsed some websites recently
2. Verify that the cache directories exist and are accessible
3. Check that all required dependencies are installed
4. Ensure you have the necessary permissions to access Chrome's files

## Understanding the Results

- **HTML to Markdown Test**: Validates that the HTML to Markdown conversion works correctly
- **Cache Extraction Test**: Checks if the application can find and extract HTML content from Chrome's cache
- **Full Integration Test**: Verifies that the cache monitor can detect changes in the cache and trigger the conversion process

If all tests pass, the application should be able to successfully convert Chrome history to Markdown files. 