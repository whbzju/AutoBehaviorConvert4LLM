#!/usr/bin/env python3
import os
import sys
import subprocess
import time

def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 80)
    print(f" {title} ".center(80, "="))
    print("=" * 80 + "\n")

def run_test(test_script, description):
    """Run a test script and return the result"""
    print_header(description)
    
    try:
        # Run the test script
        result = subprocess.run(
            [sys.executable, test_script],
            capture_output=True,
            text=True,
            check=False
        )
        
        # Print the output
        print(result.stdout)
        
        if result.stderr:
            print("ERRORS:")
            print(result.stderr)
        
        # Return success/failure
        return result.returncode == 0
    except Exception as e:
        print(f"Error running test: {str(e)}")
        return False

def main():
    """Run all tests"""
    print_header("CHROME HISTORY VIEWER TEST SUITE")
    
    # Get the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define the tests to run
    tests = [
        ("test_html_to_markdown.py", "HTML to Markdown Conversion Test"),
        ("test_cache_extraction.py", "Cache Extraction Test")
    ]
    
    # Optional: Run the full integration test if specified
    if "--full" in sys.argv:
        tests.append(("test_cache_monitor.py", "Full Cache Monitor Integration Test"))
    
    # Run the tests
    results = {}
    for test_script, description in tests:
        script_path = os.path.join(current_dir, test_script)
        if os.path.exists(script_path):
            print(f"Running {test_script}...")
            success = run_test(script_path, description)
            results[test_script] = success
        else:
            print(f"Test script not found: {script_path}")
            results[test_script] = False
    
    # Print summary
    print_header("TEST SUMMARY")
    
    all_passed = True
    for test_script, success in results.items():
        status = "PASSED" if success else "FAILED"
        print(f"{test_script}: {status}")
        all_passed = all_passed and success
    
    print("\nOverall result:", "PASSED" if all_passed else "FAILED")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main()) 