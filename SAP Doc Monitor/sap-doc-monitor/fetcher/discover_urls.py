from bs4 import BeautifulSoup
from .fetch_page import _create_chrome_driver
import re
import logging
import time
from urllib.parse import urljoin, urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)

# The SAP sidebar TOC typically holds 20-30+ links.  We wait until the
# sidebar contains at least this many matching doc links before scraping.
MIN_EXPECTED_TOC_LINKS = 10

# Maximum seconds to wait for the sidebar to finish rendering its tree.
SIDEBAR_WAIT_TIMEOUT = 30


def _fetch_page_with_sidebar(base_url, timeout=SIDEBAR_WAIT_TIMEOUT):
    """
    Fetch the SAP Help page AND wait for the sidebar Table-of-Contents
    to be fully populated with documentation links.

    The generic fetch_page() waits for the *main content* area, but the
    sidebar is a separate JS-rendered component that loads its navigation
    tree asynchronously.  This function specifically waits for that tree.

    Returns:
        str: fully-rendered page HTML (including sidebar).

    Raises:
        RuntimeError: if the sidebar never populates.
    """
    # Extract the doc-prefix so we can count matching links inside the wait
    doc_match = re.search(r'/docs/[^/]+/[a-f0-9]+/', base_url)
    doc_prefix = doc_match.group(0) if doc_match else None

    driver = _create_chrome_driver()
    try:
        logger.info(f"Loading page for TOC discovery: {base_url}")
        driver.get(base_url)

        wait = WebDriverWait(driver, timeout)

        # --- 1. Wait for the sidebar container to appear ---
        sidebar_selectors = [
            '#d4h5-sidebar',
            'aside#d4h5-sidebar',
            '[class*="toc"]',
            'nav',
            'aside',
        ]
        sidebar_found = False
        for selector in sidebar_selectors:
            try:
                wait.until(
                    lambda d, s=selector: d.find_element(By.CSS_SELECTOR, s)
                )
                sidebar_found = True
                logger.info(f"Sidebar container appeared: '{selector}'")
                break
            except TimeoutException:
                continue

        if not sidebar_found:
            logger.warning(
                "No sidebar container found within timeout — "
                "will fall back to full-page link scan."
            )

        # --- 2. Wait for enough doc-pattern links to appear ---
        # SAP loads the tree progressively; we poll until the link count
        # stabilises or we hit the timeout.
        if doc_prefix:
            logger.info(
                f"Waiting for sidebar to populate ≥{MIN_EXPECTED_TOC_LINKS} "
                f"links matching '{doc_prefix}' …"
            )
            try:
                wait.until(
                    lambda d: len([
                        a for a in d.find_elements(By.TAG_NAME, 'a')
                        if doc_prefix in (a.get_attribute('href') or '')
                        and '.html' in (a.get_attribute('href') or '')
                    ]) >= MIN_EXPECTED_TOC_LINKS
                )
                link_count = len([
                    a for a in driver.find_elements(By.TAG_NAME, 'a')
                    if doc_prefix in (a.get_attribute('href') or '')
                    and '.html' in (a.get_attribute('href') or '')
                ])
                logger.info(
                    f"Sidebar now has {link_count} matching doc links — "
                    f"ready to scrape."
                )
            except TimeoutException:
                # Count what we have so far
                current = len([
                    a for a in driver.find_elements(By.TAG_NAME, 'a')
                    if doc_prefix in (a.get_attribute('href') or '')
                    and '.html' in (a.get_attribute('href') or '')
                ])
                logger.warning(
                    f"Sidebar only has {current} matching links after "
                    f"{timeout}s (wanted ≥{MIN_EXPECTED_TOC_LINKS}). "
                    f"Proceeding with what we have."
                )

            # --- 3. Stability check — wait until the link count
            #     stops changing for 2 seconds (tree fully expanded). ---
            prev_count = 0
            stable_ticks = 0
            for _ in range(10):
                curr = len([
                    a for a in driver.find_elements(By.TAG_NAME, 'a')
                    if doc_prefix in (a.get_attribute('href') or '')
                    and '.html' in (a.get_attribute('href') or '')
                ])
                if curr == prev_count:
                    stable_ticks += 1
                else:
                    stable_ticks = 0
                prev_count = curr
                if stable_ticks >= 2:
                    logger.info(
                        f"Link count stabilised at {curr} — sidebar ready."
                    )
                    break
                time.sleep(1)

        html = driver.page_source
        return html

    finally:
        driver.quit()


def _extract_toc_hierarchy(toc_container, doc_prefix, base_domain, base_url):
    """
    Walk the TOC sidebar tree (nested <ul>/<li>) and extract pages
    with hierarchical numbering based on actual DOM nesting.

    Handles both linked pages and non-link group headers (collapsible
    sections in the SAP sidebar that have children but no page of their own).

    Returns:
        list of (hierarchical_number_str, page_title, url)
        e.g. [('1', 'Overview', 'https://...'),
              ('9', 'Creating...', 'https://...'),
              ('9.1', 'Standard...', 'https://...')]
    """
    results = []
    seen_urls = set()

    # Find the top-level <ul> in the TOC container
    top_ul = toc_container.find('ul')
    if not top_ul:
        return results

    def _find_own_link(li_element):
        """
        Find the <a> that belongs directly to this <li>, NOT to a nested
        child <li>.  In the SAP sidebar, group headers may have no <a> of
        their own while their children do; a naive li.find('a') would
        incorrectly steal a child's link.
        """
        for a_tag in li_element.find_all('a', href=True):
            # Walk up from the <a> to the <li> — if we pass through
            # another <ul> on the way, this <a> belongs to a child.
            parent = a_tag.parent
            nested = False
            while parent and parent != li_element:
                if parent.name == 'ul':
                    nested = True
                    break
                parent = parent.parent
            if not nested:
                return a_tag
        return None

    def _validate_url(href):
        """Build full URL from href and check if it's a valid doc link."""
        if not href or href.startswith('javascript:') or href == '#':
            return None
        if href.startswith('http'):
            full_url = href
        elif href.startswith('/'):
            full_url = base_domain + href
        else:
            full_url = urljoin(base_url, href)
        clean_url = full_url.split('#')[0].split('?')[0]
        if doc_prefix:
            if doc_prefix in clean_url and '.html' in clean_url:
                return clean_url
        else:
            if '.html' in clean_url:
                return clean_url
        return None

    def _walk_list(ul_element, parent_number=''):
        """Recursively walk <ul>/<li> tree assigning hierarchical numbers."""
        counter = 0
        for li in ul_element.find_all('li', recursive=False):
            nested_ul = li.find('ul', recursive=False)

            # Find the <a> that belongs to THIS <li> (not a child's)
            link = _find_own_link(li)

            if link:
                href = link.get('href', '').strip()
                clean_url = _validate_url(href)

                if not clean_url or clean_url in seen_urls:
                    # Invalid or duplicate link — still recurse if children exist
                    if nested_ul:
                        counter += 1
                        number = f"{parent_number}.{counter}" if parent_number else str(counter)
                        _walk_list(nested_ul, number)
                    continue

                seen_urls.add(clean_url)
                counter += 1
                number = f"{parent_number}.{counter}" if parent_number else str(counter)

                page_title = link.get_text(strip=True)
                page_title = re.sub(r'\s+', ' ', page_title)[:200]

                if page_title:
                    results.append((number, page_title, clean_url))
                    print(f"  [+] Added: {number}. {page_title}")

                # Recurse into nested <ul> (sub-pages)
                if nested_ul:
                    _walk_list(nested_ul, number)

            elif nested_ul:
                # Non-link group header with children — increment counter
                # for proper hierarchical numbering, then recurse.
                counter += 1
                number = f"{parent_number}.{counter}" if parent_number else str(counter)

                # Extract group header text (first text node in <li>, not children)
                group_text = ''
                for child in li.children:
                    if hasattr(child, 'name') and child.name == 'ul':
                        break
                    text = child.get_text(strip=True) if hasattr(child, 'get_text') else str(child).strip()
                    if text:
                        group_text = text
                        break
                if group_text:
                    group_text = re.sub(r'\s+', ' ', group_text)[:200]
                    print(f"  [~] Group header: {number}. {group_text}")
                    logger.info(f"Non-link group header: {number}. {group_text}")

                _walk_list(nested_ul, number)

    _walk_list(top_ul)
    return results


def discover_documentation_urls(base_url, max_retries=3):
    """
    Automatically discover all documentation pages from the table of contents.

    Uses a dedicated Selenium session that waits for the sidebar navigation
    tree to be fully rendered before extracting links.  Retries with
    exponential back-off if too few pages are found.

    The TOC tree structure (nested <ul>/<li>) is used to determine
    hierarchical numbering (e.g. 9, 9.1, 9.2, 12, 12.1).

    Args:
        base_url: The main documentation page URL containing the TOC
        max_retries: number of attempts before giving up

    Returns:
        list of (number_str, page_name, url) tuples with hierarchical numbering
    """
    print(f"\n{'='*80}")
    print(f"Auto-discovering documentation pages from: {base_url}")
    print(f"{'='*80}\n")

    last_result = []

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                f"Discovery attempt {attempt}/{max_retries}"
            )

            # Fetch page with sidebar-aware wait
            html = _fetch_page_with_sidebar(base_url)
            soup = BeautifulSoup(html, 'html.parser')

            # --- Locate the TOC container ---
            toc_selectors = [
                '#d4h5-sidebar',
                'aside#d4h5-sidebar',
                'div.toc',
                'nav.toc',
                '[class*="table-of-contents"]',
                '[class*="toc"]',
                'aside.toc',
                '#toc',
                '[role="navigation"]',
                'nav',
                'aside',
            ]

            toc_container = None
            for selector in toc_selectors:
                toc_container = soup.select_one(selector)
                if toc_container and len(toc_container.find_all('a', href=True)) > 0:
                    print(f"[+] Found TOC using selector: {selector}")
                    break
                else:
                    toc_container = None

            if not toc_container:
                print("[!] No TOC container with links found, searching entire page")
                toc_container = soup

            # --- Extract links with hierarchy ---
            all_links = toc_container.find_all('a', href=True)
            print(f"[+] Found {len(all_links)} total links in TOC area")

            if all_links:
                print(f"\nFirst 3 links found:")
                for link in all_links[:3]:
                    print(f"  - Text: '{link.get_text(strip=True)}'")
                    print(f"    Href: {link.get('href')}")

            parsed_base = urlparse(base_url)
            base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"

            doc_pattern = re.search(r'/docs/[^/]+/[a-f0-9]+/', base_url)
            doc_prefix = doc_pattern.group(0) if doc_pattern else None

            print(
                f"\nLooking for URLs matching pattern: "
                f"{doc_prefix if doc_prefix else 'any .html files'}"
            )

            # Walk the tree to get hierarchical numbering
            discovered = _extract_toc_hierarchy(
                toc_container, doc_prefix, base_domain, base_url
            )

            print(f"\n{'='*80}")
            print(
                f"[+] Attempt {attempt}: discovered "
                f"{len(discovered)} documentation pages"
            )
            print(f"{'='*80}\n")

            # Keep the best result across retries
            if len(discovered) > len(last_result):
                last_result = discovered

            # Success threshold — we expect ~25 pages
            if len(discovered) >= MIN_EXPECTED_TOC_LINKS:
                print("Discovered pages:")
                for number, title, url in discovered:
                    print(f"  {number}. {title}")
                return discovered

            # Not enough pages — retry
            logger.warning(
                f"Only {len(discovered)} pages found "
                f"(need ≥{MIN_EXPECTED_TOC_LINKS}). Retrying..."
            )

        except Exception as e:
            logger.warning(f"Discovery attempt {attempt} error: {e}")
            import traceback
            traceback.print_exc()

        if attempt < max_retries:
            backoff = 3 * attempt
            logger.info(f"Retrying discovery in {backoff}s...")
            time.sleep(backoff)

    # Return best result even if below threshold
    if last_result:
        print(
            f"\n[!] WARNING: Only discovered {len(last_result)} pages "
            f"after {max_retries} attempts "
            f"(expected ≥{MIN_EXPECTED_TOC_LINKS})."
        )
        print("Discovered pages:")
        for number, title, url in last_result:
            print(f"  {number}. {title}")
        return last_result

    print(f"[X] Failed to discover any pages after {max_retries} attempts")
    return []


def get_toc_links_only(base_url):
    """
    Extract only the table of contents structure without fetching all pages.
    Useful for initial setup and verification.
    
    Args:
        base_url: The main documentation page URL
        
    Returns:
        list: List of tuples (title, url) for TOC items
    """
    try:
        html = _fetch_page_with_sidebar(base_url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find TOC container
        toc_container = (
            soup.find('nav')
            or soup.find('aside')
            or soup.find('div', class_=re.compile(r'toc|nav', re.I))
        )
        
        if not toc_container:
            toc_container = soup
        
        links = []
        for link in toc_container.find_all('a', href=True):
            title = link.get_text(strip=True)
            href = link.get('href')
            
            if title and href and not href.startswith('#'):
                full_url = urljoin(base_url, href)
                if full_url.endswith('.html'):
                    links.append((title, full_url))
        
        return links
        
    except Exception as e:
        print(f"Error extracting TOC links: {e}")
        return []
