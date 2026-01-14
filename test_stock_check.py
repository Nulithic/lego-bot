"""Test script for LEGO stock checking functionality."""
import asyncio
from lego_checker import LEGOChecker
from bs4 import BeautifulSoup

def test_with_html_file(filename: str, set_code: str):
    """Test stock checking with a local HTML file."""
    print(f"\n{'='*60}")
    print(f"Testing: {filename} (Set {set_code})")
    print('='*60)
    
    checker = LEGOChecker()
    
    # Read the HTML file
    with open(filename, 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Test button detection
    button_detected = checker._detect_button(soup)
    print(f"\nButton Detected: {button_detected}")
    
    # Test stock status
    stock_status = checker._check_stock_status(soup)
    print(f"\nStock Status:")
    print(f"  Available: {stock_status['available']}")
    print(f"  Status: {stock_status['status']}")
    print(f"  Message: {stock_status['message']}")
    print(f"  Button: {stock_status.get('button_detected', 'None')}")
    
    # Test meta tag detection
    availability_meta = soup.find('meta', {'property': 'product:availability'})
    if availability_meta:
        print(f"\nMeta Tag (product:availability): {availability_meta.get('content', 'Not found')}")
    else:
        print("\nMeta Tag (product:availability): Not found")
    
    return stock_status

def test_live_check(set_code: str):
    """Test live stock checking (requires internet connection)."""
    print(f"\n{'='*60}")
    print(f"Testing Live Check: Set {set_code}")
    print('='*60)
    
    checker = LEGOChecker()
    
    try:
        result = checker.check_stock(set_code)
        print(f"\nResult:")
        print(f"  Set Name: {result['set_name']}")
        print(f"  Available: {result['available']}")
        print(f"  Status: {result['status']}")
        print(f"  Message: {result['message']}")
        print(f"  Price: {result.get('price', 'N/A')}")
        print(f"  Button Detected: {result.get('button_detected', 'None')}")
        print(f"  URL: {result['url']}")
        return result
    except Exception as e:
        print(f"\nError: {e}")
        return None

if __name__ == '__main__':
    print("LEGO Stock Checker - Test Script")
    print("=" * 60)
    
    # Test with HTML files
    print("\n1. Testing with HTML files...")
    test_with_html_file('in_stock.html', '11371')
    test_with_html_file('preorder.html', '72153')
    test_with_html_file('preorder_no_button.html', '72152')
    
    # Test live check (optional - uncomment to test)
    print("\n2. Testing live check (optional)...")
    print("   Uncomment the line below to test live checking")
    # test_live_check('11371')  # Shopping Street
    # test_live_check('72152')  # Pikachu

