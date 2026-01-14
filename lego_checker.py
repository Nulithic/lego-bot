"""LEGO.com stock checking module."""
import cloudscraper
from bs4 import BeautifulSoup
import logging
import time
import re
from typing import Optional, Dict
from config import RATE_LIMIT_DELAY_SECONDS

logger = logging.getLogger(__name__)


class LEGOChecker:
    """Handles checking stock status on LEGO.com."""
    
    BASE_URL = "https://www.lego.com"
    
    def __init__(self, rate_limit_delay: float = RATE_LIMIT_DELAY_SECONDS):
        """Initialize the LEGO checker.
        
        Args:
            rate_limit_delay: Seconds to wait between requests
        """
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
        # Use cloudscraper to bypass Cloudflare protection
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        # Visit homepage first to establish session and get cookies
        self._initialize_session()
    
    def _initialize_session(self):
        """Initialize session by visiting the homepage to get cookies."""
        try:
            self.session.get(self.BASE_URL, timeout=15)
            logger.debug("Session initialized with homepage visit")
        except Exception as e:
            logger.warning(f"Could not initialize session: {e}")
    
    def _rate_limit(self):
        """Ensure we don't make requests too quickly."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        self.last_request_time = time.time()
    
    def _get_product_urls(self, set_code: str) -> list:
        """Get multiple possible product URLs for a set code.
        
        Args:
            set_code: The LEGO set code (e.g., "10312")
            
        Returns:
            List of possible product page URLs to try
        """
        # LEGO.com product URLs can vary - try multiple formats
        urls = [
            f"{self.BASE_URL}/en-us/product/{set_code}",  # Direct product code
            f"{self.BASE_URL}/en-us/product/lego-set-{set_code}",  # With prefix
            f"{self.BASE_URL}/product/{set_code}",  # Without locale
        ]
        return urls
    
    def _search_for_set(self, set_code: str) -> Optional[str]:
        """Search for a set by code and return the product URL if found.
        
        Args:
            set_code: The LEGO set code
            
        Returns:
            Product URL if found, None otherwise
        """
        self._rate_limit()
        search_url = f"{self.BASE_URL}/en-us/search?q={set_code}"
        
        try:
            response = self.session.get(search_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for product links in search results
            # LEGO.com search results typically have links with /en-us/product/ in them
            product_links = soup.find_all('a', href=True)
            for link in product_links:
                href = link.get('href', '')
                if '/en-us/product/' in href and set_code in href:
                    if href.startswith('/'):
                        return f"{self.BASE_URL}{href}"
                    return href
            
            return None
        except Exception as e:
            logger.error(f"Error searching for set {set_code}: {e}")
            return None
    
    def check_stock(self, set_code: str) -> Dict[str, any]:
        """Check the stock status of a LEGO set.
        
        Args:
            set_code: The LEGO set code (e.g., "10312")
            
        Returns:
            Dictionary with stock information:
            {
                'available': bool,
                'status': str,  # 'in_stock', 'out_of_stock', 'pre_order', 'unknown', 'error'
                'set_name': str,
                'price': Optional[str],
                'url': str,
                'message': str
            }
        """
        set_code = str(set_code).strip()
        
        # Try multiple URL formats
        urls = self._get_product_urls(set_code)
        for product_url in urls:
            result = self._fetch_product_page(product_url, set_code)
            # If we got a successful response (not error), use it
            if result['status'] != 'error':
                return result
            # If 403, try next URL format
            if '403' in result['message'] or 'Forbidden' in result['message']:
                logger.debug(f"403 for {product_url}, trying next format...")
                continue
        
        # If all direct URLs failed, try searching
        logger.info(f"All direct URLs failed for {set_code}, trying search...")
        search_url = self._search_for_set(set_code)
        if search_url:
            result = self._fetch_product_page(search_url, set_code)
            if result['status'] != 'error':
                return result
        
        # If everything failed, return the last error result
        return {
            'available': False,
            'status': 'error',
            'set_name': f"Set {set_code}",
            'price': None,
            'url': urls[0] if urls else f"{self.BASE_URL}/en-us/product/{set_code}",
            'message': 'Unable to access LEGO.com. The site may be blocking automated requests. Please try again later or check the set code.',
            'button_detected': None
        }
    
    def _fetch_product_page(self, url: str, set_code: str) -> Dict[str, any]:
        """Fetch and parse a product page.
        
        Args:
            url: The product page URL
            set_code: The set code for reference
            
        Returns:
            Dictionary with stock information
        """
        self._rate_limit()
        
        try:
            response = self.session.get(url, timeout=15)
            
            # Handle 403 errors specifically - cloudscraper should handle this, but just in case
            if response.status_code == 403:
                logger.warning(f"403 Forbidden for {url}, trying with fresh session...")
                # Recreate scraper and try again
                self.session = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'desktop': True
                    }
                )
                self._initialize_session()
                response = self.session.get(url, timeout=15)
            
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract set name
            set_name = self._extract_set_name(soup, set_code)
            
            # Extract price
            price = self._extract_price(soup)
            
            # Check stock status
            stock_status = self._check_stock_status(soup)
            
            # Determine availability
            available = stock_status['available']
            status = stock_status['status']
            message = stock_status['message']
            button_detected = stock_status.get('button_detected')
            
            return {
                'available': available,
                'status': status,
                'set_name': set_name,
                'price': price,
                'url': url,
                'message': message,
                'button_detected': button_detected
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error checking {set_code}: {error_msg}")
            
            # Check for 403 specifically
            if '403' in error_msg or 'Forbidden' in error_msg:
                return {
                    'available': False,
                    'status': 'error',
                    'set_name': f"Set {set_code}",
                    'price': None,
                    'url': url,
                    'message': f"403 Forbidden: LEGO.com is blocking automated requests. Please try again later.",
                    'button_detected': None
                }
            
            return {
                'available': False,
                'status': 'error',
                'set_name': f"Set {set_code}",
                'price': None,
                'url': url,
                'message': f"Error fetching product page: {error_msg}",
                'button_detected': None
            }
    
    def _extract_set_name(self, soup: BeautifulSoup, set_code: str) -> str:
        """Extract the set name from the product page.
        
        Args:
            soup: BeautifulSoup object of the product page
            set_code: Fallback set code if name not found
            
        Returns:
            The set name or fallback
        """
        # Try multiple selectors for the product name
        selectors = [
            'h1[data-test="product-overview-name"]',
            'h1.product-overview__name',
            'h1',
            '[data-test="product-title"]',
            '.product-title',
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                name = element.get_text(strip=True)
                if name and len(name) > 0:
                    return name
        
        return f"LEGO Set {set_code}"
    
    def _extract_price(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the price from the product page.
        
        Args:
            soup: BeautifulSoup object of the product page
            
        Returns:
            Price string or None
        """
        # Try multiple selectors for price
        selectors = [
            '[data-test="product-price"]',
            '.product-price',
            '.price',
            '[class*="price"]',
        ]
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                price = element.get_text(strip=True)
                if price and ('$' in price or '€' in price or '£' in price):
                    return price
        
        return None
    
    def _detect_button(self, soup: BeautifulSoup) -> Optional[str]:
        """Detect if there's a relevant button on the page (for informational purposes only).
        Only checks buttons within the add-to-bag-sticky-container class.
        
        Args:
            soup: BeautifulSoup object of the product page
            
        Returns:
            Button text if found, None otherwise
        """
        # Only look for buttons within add-to-bag-sticky-container
        sticky_container = soup.find('div', {'data-test': 'add-to-bag-sticky-container'})
        if not sticky_container:
            return None
        
        # Find button within this container
        buttons = sticky_container.find_all('button')
        if not buttons:
            return None
        
        # Look for the main purchase button (not close, wishlist, etc.)
        for button in buttons:
            button_text = button.get_text(separator=' ', strip=True)
            button_aria = button.get('aria-label', '')
            button_data_test = button.get('data-test', '')
            
            button_text_lower = button_text.lower() if button_text else ''
            button_aria_lower = button_aria.lower() if button_aria else ''
            button_data_test_lower = button_data_test.lower() if button_data_test else ''
            
            # Skip non-purchase buttons
            skip_keywords = ['wishlist', 'close', 'cancel', 'dismiss', 'x']
            if any(keyword in button_text_lower or keyword in button_aria_lower for keyword in skip_keywords):
                continue  # Skip this button
            
            # Look for purchase-related buttons
            purchase_keywords = ['add to bag', 'add to cart', 'pre-order', 'preorder', 'buy', 'purchase']
            if (any(keyword in button_text_lower for keyword in purchase_keywords) or
                any(keyword in button_aria_lower for keyword in purchase_keywords) or
                'add-to-cart' in button_data_test_lower):
                # This is a purchase button - return it
                if button_text and len(button_text) > 0:
                    return button_text
                elif button_aria:
                    return button_aria
        
        # If no purchase button found, return None
        return None
    
    def _check_stock_status(self, soup: BeautifulSoup) -> Dict[str, any]:
        """Check the stock status from the product page using meta tags and text-based detection.
        
        Args:
            soup: BeautifulSoup object of the product page
            
        Returns:
            Dictionary with available, status, message, and button_detected
        """
        page_text = soup.get_text().lower()
        
        # Detect button separately (for informational purposes only)
        button_detected = self._detect_button(soup)
        
        # First, check meta property="product:availability" (most reliable)
        availability_meta = soup.find('meta', {'property': 'product:availability'})
        if availability_meta:
            availability_content = availability_meta.get('content', '').lower()
            logger.debug(f"Found product:availability meta tag: {availability_content}")
            
            if 'in stock' in availability_content or 'instock' in availability_content:
                return {
                    'available': True,
                    'status': 'in_stock',
                    'message': 'In Stock',
                    'button_detected': button_detected
                }
            elif 'out of stock' in availability_content or 'outofstock' in availability_content or 'oos' in availability_content:
                return {
                    'available': False,
                    'status': 'out_of_stock',
                    'message': 'Out of Stock',
                    'button_detected': button_detected
                }
            elif 'preorder' in availability_content or 'pre-order' in availability_content or 'preorder' in availability_content:
                shipping_info = self._extract_shipping_date(soup)
                message = 'Pre-Order Available'
                if shipping_info:
                    message = f'Pre-Order - {shipping_info}'
                return {
                    'available': False,
                    'status': 'pre_order',
                    'message': message,
                    'button_detected': button_detected
                }
            elif 'backorder' in availability_content:
                return {
                    'available': False,
                    'status': 'out_of_stock',
                    'message': 'Backorder',
                    'button_detected': button_detected
                }
        
        # Fallback: Check page text for stock status indicators
        # Check for "Pre-order" text patterns first
        if 'pre-order' in page_text or 'preorder' in page_text:
            shipping_info = self._extract_shipping_date(soup)
            message = 'Pre-Order Available'
            if shipping_info:
                message = f'Pre-Order - {shipping_info}'
            elif 'ship from' in page_text or 'ships from' in page_text:
                date_match = re.search(r'(?:ship|ships)\s+from\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})', page_text, re.IGNORECASE)
                if date_match:
                    message = f'Pre-Order - Ships from {date_match.group(1)}'
            
            return {
                'available': False,
                'status': 'pre_order',
                'message': message,
                'button_detected': button_detected
            }
        
        # Check for "Coming Soon" text (usually means pre-order or not yet available)
        if 'coming soon' in page_text:
            shipping_info = self._extract_shipping_date(soup)
            message = 'Coming Soon'
            if shipping_info:
                message = f'Coming Soon - {shipping_info}'
            return {
                'available': False,
                'status': 'pre_order',
                'message': message,
                'button_detected': button_detected
            }
        
        # Check for "Available now" (in stock)
        if 'available now' in page_text:
            return {
                'available': True,
                'status': 'in_stock',
                'message': 'In Stock',
                'button_detected': button_detected
            }
        
        # Check for out of stock indicators
        out_of_stock_keywords = ['out of stock', 'sold out', 'unavailable', 'temporarily out of stock']
        for keyword in out_of_stock_keywords:
            if keyword in page_text:
                return {
                    'available': False,
                    'status': 'out_of_stock',
                    'message': 'Out of Stock',
                    'button_detected': button_detected
                }
        
        # Check for in stock indicators
        if any(keyword in page_text for keyword in ['in stock', 'add to cart', 'add to bag']):
            return {
                'available': True,
                'status': 'in_stock',
                'message': 'In Stock',
                'button_detected': button_detected
            }
        
        # Default to unknown
        return {
            'available': False,
            'status': 'unknown',
            'message': 'Status Unknown',
            'button_detected': button_detected
        }
    
    def _extract_shipping_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract shipping/availability date from the product page.
        
        Args:
            soup: BeautifulSoup object of the product page
            
        Returns:
            Shipping date string or None
        """
        page_text = soup.get_text()
        
        # Look for patterns like "ship from February 27, 2026" or "Coming Soon on February 27, 2026"
        # Pattern for "ship from [date]"
        ship_pattern = r'ship\s+from\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})'
        match = re.search(ship_pattern, page_text, re.IGNORECASE)
        if match:
            return f"Ships from {match.group(1)}"
        
        # Pattern for "Coming Soon on [date]"
        coming_pattern = r'coming\s+soon\s+on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})'
        match = re.search(coming_pattern, page_text, re.IGNORECASE)
        if match:
            return f"Available {match.group(1)}"
        
        # Pattern for "Available [date]"
        available_pattern = r'available\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})'
        match = re.search(available_pattern, page_text, re.IGNORECASE)
        if match:
            return f"Available {match.group(1)}"
        
        return None

