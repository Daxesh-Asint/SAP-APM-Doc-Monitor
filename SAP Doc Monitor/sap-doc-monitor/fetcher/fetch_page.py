from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import logging
import time
import requests

logger = logging.getLogger(__name__)

# Minimum characters of visible text to consider a page successfully rendered
MIN_CONTENT_LENGTH = 100

# Known error markers that indicate a failed or incomplete page load
ERROR_MARKERS = [
    "this page isn't working",
    "err_connection",
    "page not found",
    "404 not found",
    "access denied",
    "503 service unavailable",
]


def _create_chrome_driver():
    """Create and return a configured headless Chrome WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def validate_content(html, url=""):
    """
    Validate that fetched HTML contains real, rendered page content.

    Returns:
        (bool, str): (is_valid, reason)
    """
    if html is None:
        return False, "HTML is None"

    if len(html.strip()) == 0:
        return False, "HTML is empty"

    # Check for known error markers in the raw HTML
    html_lower = html.lower()
    for marker in ERROR_MARKERS:
        if marker in html_lower:
            return False, f"Error marker detected: '{marker}'"

    # Extract visible text length to ensure JS actually rendered content
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')

    # Remove script/style so we only measure visible text
    for tag in soup(['script', 'style', 'meta', 'link', 'noscript']):
        tag.decompose()

    visible_text = soup.get_text(separator=' ', strip=True)

    if len(visible_text) < MIN_CONTENT_LENGTH:
        return False, (
            f"Visible text too short ({len(visible_text)} chars, "
            f"minimum {MIN_CONTENT_LENGTH})"
        )

    return True, "OK"


def _fetch_with_selenium(url, timeout=20):
    """
    Fetch a single page using Selenium with explicit waits.

    Waits for actual SAP content elements to appear in the DOM rather than
    relying on a fixed sleep.  Falls back to a generic body-text check for
    non-SAP pages.

    Returns:
        str: page HTML source

    Raises:
        RuntimeError: if the page fails to render meaningful content.
    """
    driver = _create_chrome_driver()
    try:
        logger.info(f"Loading page with Selenium: {url}")
        driver.get(url)

        wait = WebDriverWait(driver, timeout)

        # --- Explicit wait for real content ---
        if 'help.sap.com' in url:
            # SAP Help Portal: wait until the main content div is present
            # and contains substantial text (not just a loading spinner)
            sap_content_selectors = [
                (By.CSS_SELECTOR, 'div#page'),
                (By.CSS_SELECTOR, '[role="main"]'),
                (By.TAG_NAME, 'article'),
            ]
            content_found = False
            for by, selector in sap_content_selectors:
                try:
                    element = wait.until(
                        EC.presence_of_element_located((by, selector))
                    )
                    # Make sure the element actually has rendered text
                    wait.until(
                        lambda d: len(
                            d.find_element(by, selector).text.strip()
                        ) > MIN_CONTENT_LENGTH
                    )
                    content_found = True
                    logger.info(
                        f"Content element located via '{selector}' "
                        f"with {len(element.text.strip())} chars"
                    )
                    break
                except TimeoutException:
                    logger.warning(
                        f"Selector '{selector}' did not yield content "
                        f"within {timeout}s, trying next..."
                    )

            if not content_found:
                raise RuntimeError(
                    f"No SAP content element rendered within {timeout}s "
                    f"for {url}"
                )
        else:
            # Generic page: just wait for body to have some text
            try:
                wait.until(
                    lambda d: len(
                        d.find_element(By.TAG_NAME, 'body').text.strip()
                    ) > MIN_CONTENT_LENGTH
                )
            except TimeoutException:
                raise RuntimeError(
                    f"Page body did not render enough content within "
                    f"{timeout}s for {url}"
                )

        # Content stabilisation: wait until visible text length stops
        # growing, so dynamically-loaded sections have fully rendered.
        _prev = 0
        for _ in range(10):                          # max ~5 s extra
            _cur = len(driver.find_element(By.TAG_NAME, 'body').text)
            if _cur == _prev:
                break
            _prev = _cur
            time.sleep(0.5)

        html = driver.page_source
        return html

    finally:
        driver.quit()


def fetch_page(url, max_retries=3):
    """
    Fetch webpage content with retry logic and content validation.

    Uses requests for simple URLs/APIs, Selenium for JavaScript-heavy
    pages like SAP Help Portal.  Retries up to *max_retries* times with
    exponential back-off when rendering or validation fails.

    Returns:
        str: validated HTML content

    Raises:
        RuntimeError: after all retries are exhausted.
    """
    # ---- Non-Selenium path (simple HTTP) ----
    if 'help.sap.com' not in url:
        try:
            logger.info(f"Loading page via HTTP: {url}")
            response = requests.get(
                url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'}
            )
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'json' in content_type or 'text/plain' in content_type:
                    logger.info("Fetched API response successfully")
                    return (
                        f"<html><body><pre>{response.text}</pre></body></html>"
                    )
                logger.info("Fetched HTML response successfully")
                return response.text
        except Exception as e:
            logger.warning(f"HTTP request failed: {e}, falling back to Selenium...")
    else:
        logger.info(f"SAP Help Portal detected — using Selenium for {url}")

    # ---- Selenium path with retries ----
    import time

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Selenium attempt {attempt}/{max_retries} for {url}")
            html = _fetch_with_selenium(url)

            # Validate before returning
            is_valid, reason = validate_content(html, url)
            if is_valid:
                logger.info(
                    f"Content validated successfully on attempt {attempt}"
                )
                return html
            else:
                last_error = RuntimeError(
                    f"Content validation failed: {reason}"
                )
                logger.warning(
                    f"Attempt {attempt}/{max_retries} — validation failed: "
                    f"{reason}"
                )

        except Exception as e:
            last_error = e
            logger.warning(
                f"Attempt {attempt}/{max_retries} — error: {e}"
            )

        # Exponential back-off: 2s, 4s, 8s …
        if attempt < max_retries:
            backoff = 2 ** attempt
            logger.info(f"Retrying in {backoff}s...")
            time.sleep(backoff)

    raise RuntimeError(
        f"Failed to fetch valid content from {url} after {max_retries} "
        f"attempts. Last error: {last_error}"
    )
