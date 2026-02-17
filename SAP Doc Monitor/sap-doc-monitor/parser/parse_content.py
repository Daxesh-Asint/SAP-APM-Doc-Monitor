from bs4 import BeautifulSoup
import re

def extract_text(html):
    """
    Technical documentation cleaner for SAP Help Portal.
    
    Extracts ONLY actual documentation content by removing:
    - Navigation menus, headers, footers
    - Search UI, cookie banners, icons
    - Duplicated content and broken line breaks
    - UI elements (breadcrumbs, buttons, etc.)
    
    Preserves:
    - Logical headings (H1, H2, H3) without duplication
    - Original wording and meaning
    - Documentation structure
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Check if this is a synthetic HTML wrapper around an API/JSON response
    # created by fetch_page.py (where <pre> is the sole child of <body>).
    # Do NOT short-circuit for real documentation pages that contain code samples.
    pre_tag = soup.find('pre')
    if pre_tag:
        body = soup.find('body')
        if body:
            body_children = [c for c in body.children
                             if hasattr(c, 'name') and c.name is not None]
            if len(body_children) == 1 and body_children[0].name == 'pre':
                return pre_tag.get_text(strip=True)
    
    # Step 1: Remove non-content elements
    for element in soup(['script', 'style', 'meta', 'link', 'noscript', 'iframe', 'svg', 'path']):
        element.decompose()
    
    # Step 2: Target the main content area FIRST (SAP Help Portal uses div#page)
    main_content = soup.find('div', id='page')
    
    # Fallback to other content selectors if div#page not found
    if not main_content:
        content_selectors = [
            '[role="main"]',
            'main',
            'article',
            '[class*="content-main"]',
            '[class*="main-content"]',
            '[id*="main"]'
        ]
        
        for selector in content_selectors:
            main_content = soup.select_one(selector)
            if main_content:
                break
    
    # Final fallback to body
    if not main_content:
        main_content = soup.find('body')
    
    if not main_content:
        return ""
    
    # Step 3: Pre-process menu cascades FIRST (before removing UI elements)
    for menucascade in main_content.find_all('span', class_=lambda x: x and 'menucascade' in x):
        # Find all uicontrol elements within this menucascade
        uicontrols = menucascade.find_all('span', class_=lambda x: x and 'uicontrol' in x)
        if len(uicontrols) > 1:
            # Create menu path with > separator
            menu_texts = [ui.get_text(strip=True) for ui in uicontrols if ui.get_text(strip=True)]
            menu_path = ' > '.join(menu_texts)
            
            # Clear all children and set new text
            menucascade.clear()
            menucascade.string = menu_path
    
    # Step 4: Now remove UI elements FROM the main content (excluding note blocks)
    ui_selectors = [
        'nav', 'header', 'footer',
        '[class*="navigation"]', '[class*="nav-"]', '[class*="breadcrumb"]',
        '[class*="search"]', '[class*="cookie"]', '[class*="banner"]',
        '[class*="toolbar"]',
        '[class*="feedback"]',
        '[class*="hero"]',
        'button', '[role="button"]'
    ]
    
    for selector in ui_selectors:
        for element in main_content.select(selector):
            element.decompose()
    
    # Remove aside elements that are NOT notes
    for aside in main_content.find_all('aside'):
        if 'note' not in aside.get('class', []):
            aside.decompose()
    
    if not main_content:
        return ""
    
    # Step 4b: Wrap bare inline content inside <section> elements into <p> tags.
    #   SAP DITA rendering sometimes places content as direct NavigableString
    #   children of <section> mixed with inline elements (<a>, <span>, etc.)
    #   instead of wrapping them in <p>.  The main extraction loop only sees
    #   real block elements, so these text nodes would be silently dropped.
    #
    #   Strategy: walk the direct children of each <section>, group runs of
    #   consecutive inline content (text nodes + inline tags like <a>, <span>,
    #   <em>, <strong>) and wrap each run in a synthetic <p>.
    from bs4 import NavigableString, Tag
    _INLINE_TAGS = frozenset([
        'a', 'abbr', 'b', 'bdo', 'br', 'cite', 'code', 'dfn', 'em', 'i',
        'kbd', 'mark', 'q', 's', 'samp', 'small', 'span', 'strong', 'sub',
        'sup', 'u', 'var', 'wbr',
    ])
    for section in main_content.find_all('section'):
        runs = []           # list of lists; each inner list is one inline run
        current_run = []
        for child in list(section.children):
            is_inline = (
                isinstance(child, NavigableString) and child.strip()
            ) or (
                isinstance(child, Tag) and child.name in _INLINE_TAGS
            )
            if is_inline:
                current_run.append(child)
            else:
                if current_run:
                    runs.append(current_run)
                    current_run = []
        if current_run:
            runs.append(current_run)

        for run in runs:
            # Build combined text, normalising internal whitespace
            parts = []
            for node in run:
                if isinstance(node, NavigableString):
                    parts.append(node.strip())
                else:
                    parts.append(node.get_text(strip=True))
            combined = ' '.join(p for p in parts if p)
            combined = re.sub(r'\s+', ' ', combined).strip()
            if not combined:
                continue
            # Replace the run with a single synthetic <p>
            new_p = soup.new_tag('p')
            new_p.string = combined
            run[0].insert_before(new_p)
            for node in run:
                node.extract()
    
    # Step 5: Extract text with structure preservation
    lines = []
    seen_content = set()  # For deduplication
    seen_hashes = set()  # For fuzzy deduplication
    
    # Process main elements in order
    for element in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ol', 'ul', 'aside', 'pre', 'code', 'blockquote', 'table', 'dl'], recursive=True):
        
        # Skip if this element is nested inside another we'll process
        if element.find_parent(['li', 'aside', 'pre']):
            if element.name not in ['aside', 'pre', 'table', 'dl']:  # Process these even if nested
                continue
        
        # Handle headings
        if element.name.startswith('h'):
            text = element.get_text(separator=' ', strip=True)
            if text and len(text) > 2 and not _is_ui_text(text) and text not in seen_content:
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(text)
                lines.append("")
                seen_content.add(text)
                
                # For Results heading, check for content in parent div.section.result
                if text == "Results":
                    # Find the parent div with class "section result"
                    parent_div = element.find_parent('div', class_='result')
                    if not parent_div:
                        parent_div = element.find_parent('div', class_='section')
                    
                    if parent_div:
                        # Get text from the div, excluding the heading itself
                        for child in parent_div.children:
                            if hasattr(child, 'name'):
                                # Skip the heading and anchor
                                if child.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span']:
                                    continue
                                # Skip div.tasklabel (contains the heading)
                                if child.name == 'div' and 'tasklabel' in child.get('class', []):
                                    continue
                                # Get text from remaining elements
                                child_text = child.get_text(separator=' ', strip=True)
                                if child_text and len(child_text) > 2 and not _is_ui_text(child_text):
                                    if child_text not in seen_content:
                                        lines.append(child_text)
                                        seen_content.add(child_text)
                                        lines.append("")
                                        break
        
        # Handle ordered lists (numbered steps)
        elif element.name == 'ol':
            li_items = element.find_all('li', recursive=False)  # Direct children only
            for idx, li in enumerate(li_items, 1):
                text = _extract_list_item_text(li)
                if text and text not in seen_content:
                    lines.append(f"{idx}. {text}")
                    seen_content.add(text)
                    
                    # Check for note blocks within this step
                    for note in li.find_all('aside', class_='note'):
                        note_text = _extract_note_text(note)
                        if note_text and note_text not in seen_content:
                            lines.append("")
                            lines.append(f"Note: {note_text}")
                            lines.append("")
                            seen_content.add(note_text)
        
        # Handle unordered lists
        elif element.name == 'ul':
            # Skip if inside an ordered list item (already processed)
            if element.find_parent('ol'):
                continue
            li_items = element.find_all('li', recursive=False)
            for li in li_items:
                text = _extract_list_item_text(li)
                if text and text not in seen_content:
                    lines.append(f"• {text}")
                    seen_content.add(text)
                    
                    # Check for note blocks within this list item
                    for note in li.find_all('aside', class_='note'):
                        note_text = _extract_note_text(note)
                        if note_text and note_text not in seen_content:
                            lines.append("")
                            lines.append(f"Note: {note_text}")
                            lines.append("")
                            seen_content.add(note_text)
        
        # Handle note blocks (aside elements)
        elif element.name == 'aside' and 'note' in element.get('class', []):
            # Skip if already processed within a list item
            if element.find_parent('li'):
                continue
            note_text = _extract_note_text(element)
            if note_text and note_text not in seen_content:
                lines.append("")
                lines.append(f"Note: {note_text}")
                lines.append("")
                seen_content.add(note_text)
        
        # Handle paragraphs (only top-level ones)
        elif element.name == 'p':
            # Skip paragraphs inside lists, notes, or table cells
            # (table cells are handled by the table branch to avoid duplication)
            if element.find_parent(['li', 'aside', 'ol', 'ul', 'table']):
                continue
            text = element.get_text(separator=' ', strip=True)
            if text and len(text) > 2 and not _is_ui_text(text):
                if not _is_duplicate_paragraph(text, seen_content):
                    lines.append(text)
                    lines.append("")  # blank line after each paragraph
                    seen_content.add(text)
        
        # Handle code blocks
        elif element.name in ['pre', 'code'] and element.parent.name != 'pre':
            text = element.get_text(separator=' ', strip=True)
            if text and len(text) > 2 and text not in seen_content:
                lines.append(f"```\n{text}\n```")
                seen_content.add(text)
        
        # Handle blockquotes
        elif element.name == 'blockquote':
            text = element.get_text(separator=' ', strip=True)
            if text and len(text) > 2 and text not in seen_content:
                lines.append(f"> {text}")
                seen_content.add(text)
        
        # Handle tables (role collections, parameters, API fields, etc.)
        elif element.name == 'table':
            if element.find_parent('table'):
                continue  # Skip nested tables — outer table already captures rows
            # Skip SAP floating-headers tables (duplicated headers for
            # sticky row rendering; the real data is in dynamic-table
            # or simpletable).
            table_classes = element.get('class', [])
            if 'floating-headers' in table_classes:
                continue
            table_lines = _format_table(element)
            # Deduplicate: build a fingerprint from all cell text
            table_fingerprint = '\n'.join(table_lines)
            if table_fingerprint and table_fingerprint not in seen_content:
                lines.append("")   # blank before table
                lines.extend(table_lines)
                lines.append("")   # blank after table
                seen_content.add(table_fingerprint)
        
        # Handle definition lists (field descriptions, glossaries)
        elif element.name == 'dl':
            for child in element.find_all(['dt', 'dd'], recursive=False):
                text = child.get_text(separator=' ', strip=True)
                if text and len(text) > 2 and text not in seen_content:
                    if child.name == 'dt':
                        lines.append(text)
                    else:
                        lines.append(f"  {text}")
                    seen_content.add(text)
    
    # Step 6: Join and clean up
    result = '\n'.join(lines)
    
    # Step 7: Fix formatting issues
    result = _fix_formatting(result)
    
    # Debug output
    if len(result) > 0:
        preview = result[:200].replace('\n', ' ')
        print(f"Cleaned documentation preview: {preview}...")
        print(f"Total cleaned content: {len(result)} characters, {len(result.split())} words")
    
    return result


def _extract_list_item_text(li_element):
    """
    Extract text from a list item, properly handling nested elements.
    Excludes note blocks which are handled separately.
    Note: Works with the already-modified DOM (after menucascade processing).
    """
    # Simply get the text directly from the modified element
    text = li_element.get_text(separator=' ', strip=True)
    
    # If there are note blocks, we need to remove their text
    for note in li_element.find_all('aside', class_='note'):
        note_text = note.get_text(separator=' ', strip=True)
        text = text.replace(note_text, '')
    
    # Clean up multiple spaces
    import re
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def _extract_note_text(note_element):
    """
    Extract text from a note block (aside element).
    Removes the "Note" title if present.
    """
    # Clone to avoid modifications
    note_copy = BeautifulSoup(str(note_element), 'html.parser').find('aside')
    
    # Remove the title div if present
    title_div = note_copy.find('div', class_='title')
    if title_div:
        title_div.decompose()
    
    # Get the actual note content
    text = note_copy.get_text(separator=' ', strip=True)
    
    # Remove "Note" prefix if it exists
    if text.lower().startswith('note'):
        text = text[4:].strip()
        if text.startswith(':'):
            text = text[1:].strip()
    
    return text


def _is_ui_text(text):
    """
    Detect if text is UI/navigation element rather than documentation.
    Returns True if text should be filtered out.
    """
    text_lower = text.lower().strip()
    
    # Short UI elements
    if len(text) < 3:
        return True
    
    # Common UI/navigation patterns
    ui_patterns = [
        # Buttons and actions
        r'^(yes|no|ok|cancel|close|back|next|previous|submit|search|filter|sort)$',
        r'^(save|edit|delete|remove|add|create|update|share|print|download|upload)$',
        r'^(send feedback|feedback|send|view|show|hide|expand|collapse)$',
        
        # Navigation
        r'^(home|menu|navigation|breadcrumb|table of contents|contents)$',
        r'^(previous|next|page \d+|go to|skip to)$',
        
        # Cookie/Privacy/Legal
        r'cookie|privacy policy|terms of use|legal|copyright|all rights reserved',
        r'accept cookies|manage cookies|cookie consent',
        r'©.*\d{4}',  # Copyright notices
        
        # Search UI
        r'^search$|^filter by\b|^sort by\b',
        r'^search through this document$|^search scope$|^provide feedback$',
        
        # Social/Share
        r'^share on\b|^follow us\b|^social media$',
        
        # Icons and symbols (common Unicode symbols used as icons)
        r'^[▼▲►◄★☆♥♡✓✔✗✘←→↑↓⋮⋯]+$',
        
        # Favorites/bookmarks
        r'^add to favorites$|^bookmark$|^favorite$',
        r'^pdf$|^share$|^favorites$',  # Single-word UI buttons
        
        # PDF/Export
        r'^export to pdf$|^download pdf$|^print page$',
        
        # SAP-specific UI elements (anchored to avoid matching real content)
        r'^on this page$|^was this page helpful',
        r'^explore sap$|^what\'s new$',
        r'^(products|help portal)$',
        r'^overview of getting started steps$',  # TOC headers
        r'^table of contents$',
    ]
    
    for pattern in ui_patterns:
        if re.search(pattern, text_lower):
            return True
    
    # Filter very short single-word items (likely UI labels)
    if len(text.split()) == 1 and len(text) < 15:
        common_ui_words = ['home', 'menu', 'help', 'about', 'contact', 'login', 'logout', 
                          'settings', 'profile', 'account', 'dashboard', 'admin']
        if text_lower in common_ui_words:
            return True
    
    return False


def _is_duplicate_paragraph(text, seen_content):
    """
    Check if paragraph is a duplicate with fuzzy matching.
    Sometimes content appears with slight variations (extra spaces, etc.)
    """
    normalized = ' '.join(text.split())  # Normalize whitespace
    
    if normalized in seen_content:
        return True
    
    # Check for substring duplicates (one might be truncated version)
    for seen in seen_content:
        seen_normalized = ' '.join(seen.split())
        # If texts are very similar in length and one contains the other
        if len(normalized) > 50 and len(seen_normalized) > 50:
            if normalized in seen_normalized or seen_normalized in normalized:
                return True
    
    return False


def _format_table(table_element):
    """
    Render an HTML <table> as column-aligned plain text.

    Returns a list of strings (one per output line) including a
    dash-separator line under the header row.
    """
    # 1. Collect raw cell text per row
    raw_rows = []
    is_header_row = []
    for tr in table_element.find_all('tr'):
        cells = tr.find_all(['th', 'td'])
        texts = [cell.get_text(separator=' ', strip=True) for cell in cells]
        # Skip completely empty rows (e.g. floating-headers ghost row)
        if not any(t for t in texts):
            continue
        raw_rows.append(texts)
        is_header_row.append(all(c.name == 'th' for c in cells))

    if not raw_rows:
        return []

    # 2. Normalise column count (pad short rows)
    num_cols = max(len(r) for r in raw_rows)
    for row in raw_rows:
        while len(row) < num_cols:
            row.append('')

    # 3. Calculate column widths
    col_widths = [0] * num_cols
    for row in raw_rows:
        for ci, cell in enumerate(row):
            col_widths[ci] = max(col_widths[ci], len(cell))

    # 4. Build formatted lines
    def _pad_row(row):
        parts = []
        for ci, cell in enumerate(row):
            parts.append(cell.ljust(col_widths[ci]))
        return '  '.join(parts).rstrip()

    out_lines = []
    for ri, row in enumerate(raw_rows):
        out_lines.append(_pad_row(row))
        # Add separator after header row(s)
        if is_header_row[ri] and (ri + 1 >= len(raw_rows) or not is_header_row[ri + 1]):
            sep = '  '.join('-' * w for w in col_widths)
            out_lines.append(sep)

    return out_lines


def _fix_formatting(text):
    """
    Fix common formatting issues:
    - Merge broken lines into proper paragraphs
    - Normalize whitespace (but preserve intentional column padding)
    - Remove excessive blank lines
    """
    # Remove lines with only whitespace
    lines = [line.rstrip() for line in text.split('\n')]
    
    # Remove excessive blank lines (max 2 consecutive)
    cleaned_lines = []
    blank_count = 0
    
    for line in lines:
        if line == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned_lines.append(line)
        else:
            blank_count = 0
            cleaned_lines.append(line)
    
    # Collapse multiple spaces ONLY on non-table lines.
    # Table lines use intentional padding and are identifiable by
    # having 2+ consecutive spaces as column separators.
    final_lines = []
    for line in cleaned_lines:
        # A table row has at least two cells separated by 2+ spaces
        if re.search(r'\S  +\S', line):
            final_lines.append(line)          # preserve padding
        else:
            final_lines.append(re.sub(r' +', ' ', line))
    
    result = '\n'.join(final_lines)
    
    # Remove leading/trailing whitespace
    result = result.strip()
    
    return result
