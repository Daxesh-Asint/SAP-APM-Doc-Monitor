from config import settings
from fetcher.fetch_page import fetch_page, validate_content
from fetcher.discover_urls import discover_documentation_urls
from parser.parse_content import extract_text
from comparator.compare_content import compare
from notifier.send_email import send_email
from storage.gcs_storage import is_gcs_enabled, download_all_snapshots, upload_all_snapshots
import os
import logging
import datetime
from zoneinfo import ZoneInfo

import re
import traceback

logger = logging.getLogger(__name__)

# Minimum extracted-text length to consider content valid for snapshot saving.
# Pages with less text than this are treated as rendering failures.
MIN_SNAPSHOT_LENGTH = 100


def format_timestamp_readable(dt):
    """Format timestamp as 'Saturday, 15th Feb 2026 12:09 PM'"""
    day = dt.day
    # Add ordinal suffix
    if 10 <= day % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    
    return dt.strftime(f"%A, %d{suffix} %b %Y %I:%M %p").replace(dt.strftime("%d"), str(day), 1)


def sanitize_filename(page_name, page_number=None):
    """Convert page name to safe filename"""
    # Remove invalid characters and replace spaces with underscores
    safe_name = re.sub(r'[<>:"/\\|?*]', '', page_name)
    safe_name = safe_name.replace(' ', '_')
    safe_name = safe_name[:100]  # Limit length
    
    # Prepend page number if provided
    if page_number is not None:
        safe_name = f"{page_number}_{safe_name}"
    
    return safe_name


def save_snapshot(snapshot_file, content):
    """
    Save content to a snapshot file ONLY if the content passes validation.

    Returns:
        bool: True if saved, False if rejected.
    """
    if not content or len(content.strip()) < MIN_SNAPSHOT_LENGTH:
        logger.warning(
            f"Snapshot NOT saved — content too short "
            f"({len(content.strip()) if content else 0} chars, "
            f"minimum {MIN_SNAPSHOT_LENGTH}): {snapshot_file}"
        )
        return False

    os.makedirs(os.path.dirname(snapshot_file) or '.', exist_ok=True)
    with open(snapshot_file, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Snapshot saved ({len(content)} chars): {snapshot_file}")
    return True


def extract_page_name_from_filename(filename):
    """Extract normalised page name from a snapshot filename.

    E.g. '9.1_Standard_Role_Collections.txt' → 'standard role collections'
    """
    name = filename
    if name.endswith('.txt'):
        name = name[:-4]
    # Strip leading page-number prefix  (e.g. '9.1_', '12_', '14.1_')
    name = re.sub(r'^\d+(\.\d+)*_', '', name)
    return name.replace('_', ' ').strip().lower()


def normalize_page_name(page_name):
    """Normalise a page name for snapshot matching."""
    return page_name.strip().lower()


def load_previous_snapshots(snapshots_dir):
    """Read all .txt snapshots into a dict keyed by normalised page name."""
    previous = {}
    if not os.path.isdir(snapshots_dir):
        return previous
    for fname in os.listdir(snapshots_dir):
        if not fname.endswith('.txt'):
            continue
        norm = extract_page_name_from_filename(fname)
        try:
            with open(os.path.join(snapshots_dir, fname), 'r',
                       encoding='utf-8') as fh:
                previous[norm] = fh.read()
        except Exception as exc:
            logger.warning("Could not read snapshot %s: %s", fname, exc)
    return previous


def fetch_page_content(page_name, url, page_number=None):
    """Fetch a single page and return extracted text (or *None*).

    Does **not** compare or save — fetch + extract only.
    """
    print(f"\n{'='*80}")
    label = f"{page_number}. {page_name}" if page_number else page_name
    print(f"Fetching: {label}")
    print(f"{'='*80}")
    try:
        print(f"Fetching {url}...")
        try:
            html = fetch_page(url)
        except RuntimeError as err:
            print(f"[X] Fetch failed for '{page_name}': {err}")
            logger.warning("Skipping '%s' — fetch failed: %s", page_name, err)
            return None

        print(f"Fetched {len(html)} characters of HTML")
        print("Extracting text content...")
        text = extract_text(html)
        print(f"Extracted {len(text)} characters of text")

        if not text or len(text.strip()) < MIN_SNAPSHOT_LENGTH:
            print(f"[X] Content too short for '{page_name}' — skipped")
            return None

        return text
    except Exception as exc:
        print(f"[X] Error fetching '{page_name}': {exc}")
        traceback.print_exc()
        return None


def process_page(page_name, url, page_number=None):
    """Process a single documentation page with content validation."""
    print(f"\n{'='*80}")
    if page_number:
        print(f"Processing: {page_number}. {page_name}")
    else:
        print(f"Processing: {page_name}")
    print(f"{'='*80}")
    
    # Create snapshot filename
    snapshot_file = os.path.join(settings.SNAPSHOTS_DIR, f"{sanitize_filename(page_name, page_number)}.txt")
    
    try:
        # ---- Fetch & extract ----
        print(f"Fetching {url}...")
        try:
            html = fetch_page(url)
        except RuntimeError as fetch_err:
            # fetch_page exhausted all retries — skip this page entirely,
            # do NOT touch the existing snapshot.
            print(f"[X] Fetch failed after retries for '{page_name}': {fetch_err}")
            logger.warning(f"Skipping '{page_name}' — fetch failed: {fetch_err}")
            return None

        print(f"Fetched {len(html)} characters of HTML")
        
        print("Extracting text content...")
        current_text = extract_text(html)
        print(f"Extracted {len(current_text)} characters of text")

        # ---- Content validation gate ----
        if not current_text or len(current_text.strip()) < MIN_SNAPSHOT_LENGTH:
            print(
                f"[X] Content validation FAILED for '{page_name}' — "
                f"extracted text too short ({len(current_text.strip()) if current_text else 0} chars). "
                f"Snapshot will NOT be overwritten."
            )
            logger.warning(
                f"Skipping '{page_name}': extracted content below "
                f"{MIN_SNAPSHOT_LENGTH}-char threshold. "
                f"Existing snapshot preserved."
            )
            return None

        # ---- First-time snapshot (no previous file) ----
        if not os.path.exists(snapshot_file):
            saved = save_snapshot(snapshot_file, current_text)
            if saved:
                print(f"[+] Initial snapshot saved for '{page_name}'")
                # Report this as a NEW PAGE so it triggers an email notification
                content_lines = [line.strip() for line in current_text.splitlines() if line.strip()]
                print(f"[NEW PAGE] '{page_name}' — {len(content_lines)} lines of content discovered")
                return {
                    'page_name': page_name,
                    'url': url,
                    'is_new_page': True,
                    'content_preview': content_lines[:15],
                    'total_lines': len(content_lines),
                }
            else:
                print(f"[X] Initial snapshot rejected for '{page_name}'")
            return None

        # ---- Compare with previous snapshot ----
        with open(snapshot_file, "r", encoding="utf-8") as f:
            old_text = f.read()

        result = compare(old_text, current_text)

        if result['has_changes']:
            added = result['added']
            removed = result['removed']
            warnings = result['structural_warnings']
            severity = result['max_severity']
            
            # ---- Snapshot integrity check ----
            # If the new content is drastically shorter than the old snapshot
            # (>70 % shrinkage) AND there are zero additions, this is almost
            # certainly a rendering failure, not a real change.
            old_len = len(old_text.strip())
            new_len = len(current_text.strip())
            shrinkage = (old_len - new_len) / old_len if old_len > 0 else 0

            if shrinkage > 0.7 and len(added) == 0:
                print(
                    f"[!] Suspicious shrinkage ({shrinkage:.0%}) with no "
                    f"additions for '{page_name}' — likely rendering failure. "
                    f"Snapshot NOT overwritten."
                )
                logger.warning(
                    f"Blocked snapshot overwrite for '{page_name}': "
                    f"old={old_len} chars, new={new_len} chars, "
                    f"shrinkage={shrinkage:.0%}"
                )
                return None

            # Safe to save — content is validated
            save_snapshot(snapshot_file, current_text)
            
            warn_msg = f", {len(warnings)} warnings" if warnings else ""
            print(f"[+] Changes detected [{severity}]: {len(added)} additions, {len(removed)} removals{warn_msg}")
            
            return {
                'page_name': page_name,
                'url': url,
                'added': added,
                'removed': removed,
                'structural_warnings': warnings,
                'max_severity': severity,
            }
        else:
            print(f"[+] No changes detected for '{page_name}'")
            return None
            
    except Exception as e:
        print(f"[X] Error processing '{page_name}': {e}")
        traceback.print_exc()
        # Do NOT return an error dict that triggers a false email.
        # The page simply couldn't be checked this run.
        logger.error(f"Unhandled error for '{page_name}', snapshot preserved: {e}")
        return None

def build_notification(all_changes, page_names, run_timestamp, run_status="Success", urls_dict=None, numbers_dict=None):
    """
    Build email subject and body for the monitoring run.
    Always produces output — whether changes were detected or not.

    Args:
        all_changes:   list of change dicts returned by process_page()
        page_names:    list of all monitored page names
        run_timestamp: datetime of this run
        run_status:    "Success" or brief error description
        urls_dict:     dict mapping page names to URLs (optional)
        numbers_dict:  dict mapping page names to hierarchical numbers (optional)

    Returns:
        (subject, body) tuple
    """
    if urls_dict is None:
        urls_dict = {}
    if numbers_dict is None:
        numbers_dict = {}
    total_pages = len(page_names)
    ts = format_timestamp_readable(run_timestamp)

    # Calculate next scheduled run (daily at 10:00 AM and 6:00 PM IST)
    current_hour = run_timestamp.hour
    if current_hour < 10:
        next_run = run_timestamp.replace(hour=10, minute=0, second=0, microsecond=0)
    elif current_hour < 18:
        next_run = run_timestamp.replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        next_run = (run_timestamp + datetime.timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    next_run_ts = format_timestamp_readable(next_run)

    new_pages = [c for c in all_changes if c.get('is_new_page')]
    modified_pages = [c for c in all_changes if not c.get('is_new_page') and not c.get('is_removed_page')]
    removed_pages_list = [c for c in all_changes if c.get('is_removed_page')]
    unchanged_count = total_pages - len(new_pages) - len(modified_pages)

    total_additions = sum(len(c.get('added', [])) for c in modified_pages)
    total_removals = sum(len(c.get('removed', [])) for c in modified_pages)
    total_warnings = sum(len(c.get('structural_warnings', [])) for c in modified_pages)

    # Compute overall severity across all modified pages
    _sev_order = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
    overall_severity = None
    if modified_pages:
        _sevs = [c.get('max_severity', 'LOW') for c in modified_pages if c.get('max_severity')]
        if _sevs:
            overall_severity = max(_sevs, key=lambda s: _sev_order.get(s, 0))

    has_changes = len(all_changes) > 0

    # ── Subject ──────────────────────────────────────────────────────────
    if has_changes:
        parts = []
        if new_pages:
            parts.append(f"{len(new_pages)} New")
        if modified_pages:
            parts.append(f"{len(modified_pages)} Modified")
        if removed_pages_list:
            parts.append(f"{len(removed_pages_list)} Removed")
        sev_tag = f" [{overall_severity}]" if overall_severity else ""
        subject = f"SAP APM Doc Monitor — Changes Detected{sev_tag}: {', '.join(parts)}"
    else:
        subject = "SAP APM Doc Monitor — No Changes Detected"

    # ── Body ─────────────────────────────────────────────────────────────
    lines = []

    # Header
    lines.append("SAP APM Documentation Monitor — Run Report")
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"  Timestamp           : {ts}")
    lines.append(f"  Next Scheduled Run  : {next_run_ts}")
    lines.append(f"  Run Status          : {run_status}")
    lines.append(f"  Pages Checked       : {total_pages}")
    lines.append(f"  New Pages Added     : {len(new_pages)}")
    lines.append(f"  Modified Pages      : {len(modified_pages)}")
    lines.append(f"  Unchanged Pages     : {unchanged_count}")
    if removed_pages_list:
        lines.append(f"  Removed Pages       : {len(removed_pages_list)}")
    if modified_pages:
        lines.append(f"  Additions           : {total_additions}")
        lines.append(f"  Removals            : {total_removals}")
        if total_warnings:
            lines.append(f"  Struct. Warnings    : {total_warnings}")
        if overall_severity:
            lines.append(f"  Overall Severity    : {overall_severity}")
    lines.append("")

    # ── Changes detail ───────────────────────────────────────────────────
    if has_changes:
        # New pages
        if new_pages:
            lines.append("=" * 60)
            lines.append(f"  NEW PAGES ADDED: {len(new_pages)}")
            lines.append("=" * 60)
            for idx, pg in enumerate(new_pages, 1):
                lines.append("")
                lines.append(f"  {idx}. {pg['page_name']}")
                lines.append(f"     URL: {pg['url']}")
                lines.append(f"     Content: {pg.get('total_lines', 0)} lines")
                preview = pg.get('content_preview', [])
                if preview:
                    lines.append("")
                    lines.append("     Preview:")
                    for i, ln in enumerate(preview[:10], 1):
                        wrapped = [ln[j:j+65] for j in range(0, max(len(ln), 1), 65)]
                        lines.append(f"       {i}. " + "\n          ".join(wrapped))
                    remaining = pg.get('total_lines', 0) - min(len(preview), 10)
                    if remaining > 0:
                        lines.append(f"       ... and {remaining} more lines")
            lines.append("")

        # Modified pages
        if modified_pages:
            lines.append("=" * 60)
            lines.append(f"  MODIFIED PAGES: {len(modified_pages)}")
            lines.append("=" * 60)
            for idx, ci in enumerate(modified_pages, 1):
                added = ci.get('added', [])
                removed = ci.get('removed', [])
                warnings = ci.get('structural_warnings', [])
                sev = ci.get('max_severity', '')
                lines.append("")
                lines.append(f"  {idx}. {ci['page_name']}")
                lines.append(f"     URL: {ci['url']}")
                sev_tag = f"  |  Severity: {sev}" if sev else ""
                lines.append(f"     Additions: {len(added)}  |  Removals: {len(removed)}{sev_tag}")

                if warnings:
                    lines.append("")
                    lines.append("     [!] Structural Warnings:")
                    for w in warnings:
                        lines.append(f"       [{w['severity']}] {w['message']}")

                if added:
                    lines.append("")
                    lines.append("     [+] New content:")
                    for i, item in enumerate(added[:5], 1):
                        txt = item['text'] if isinstance(item, dict) else item
                        s = item.get('severity', '') if isinstance(item, dict) else ''
                        prefix = f"[{s}] " if s else ""
                        wrapped = [txt[j:j+60] for j in range(0, max(len(txt), 1), 60)]
                        lines.append(f"       {i}. {prefix}" + "\n          ".join(wrapped))
                    if len(added) > 5:
                        lines.append(f"       ... and {len(added) - 5} more")

                if removed:
                    lines.append("")
                    lines.append("     [-] Removed content:")
                    for i, item in enumerate(removed[:5], 1):
                        txt = item['text'] if isinstance(item, dict) else item
                        s = item.get('severity', '') if isinstance(item, dict) else ''
                        prefix = f"[{s}] " if s else ""
                        wrapped = [txt[j:j+60] for j in range(0, max(len(txt), 1), 60)]
                        lines.append(f"       {i}. {prefix}" + "\n          ".join(wrapped))
                    if len(removed) > 5:
                        lines.append(f"       ... and {len(removed) - 5} more")
            lines.append("")

        # Removed pages
        if removed_pages_list:
            lines.append("=" * 60)
            lines.append(f"  REMOVED PAGES: {len(removed_pages_list)}")
            lines.append("=" * 60)
            for idx, pg in enumerate(removed_pages_list, 1):
                lines.append("")
                lines.append(f"  {idx}. {pg['page_name']}")
                lines.append(f"     Previously had {pg.get('total_lines', 0)} lines of content")
                lines.append(f"     No longer found in the documentation table of contents")
            lines.append("")

    # ── No-change body ───────────────────────────────────────────────────
    else:
        lines.append("=" * 60)
        lines.append("  ALL PAGES UNCHANGED")
        lines.append("=" * 60)
        lines.append("")
        lines.append("  No additions, removals, or new pages were detected")
        lines.append("  in this monitoring run. All snapshots match the")
        lines.append("  current live documentation.")
        lines.append("")

    # ── Pages list ───────────────────────────────────────────────────────
    pages_monitored_start_index = len(lines)
    lines.append("-" * 120)
    lines.append("  Pages Monitored:")
    lines.append("-" * 120)
    lines.append("")
    
    # Table header
    lines.append(f"  {'S.No.':<6}  {'Page No.':<10}  {'Status':<9}  {'Page Name':<60}  {'URL'}")
    lines.append(f"  {'-'*6}  {'-'*10}  {'-'*9}  {'-'*60}  {'-'*80}")
    
    # Table rows (plain text version with full URLs)
    for i, name in enumerate(page_names, 1):
        # Mark status
        status_tag = "OK"
        for c in new_pages:
            if c['page_name'] == name:
                status_tag = "NEW"
                break
        for c in modified_pages:
            if c['page_name'] == name:
                status_tag = "CHANGED"
                break
        
        # Display full page names and URLs without truncation
        num = numbers_dict.get(name, str(i))
        url = urls_dict.get(name, '')
        lines.append(f"  {i:<6}  {num:<10}  {status_tag:<9}  {name:<60}  {url}")
    
    lines.append("")

    # Footer
    lines.append("-" * 60)
    lines.append("  This is an automated notification from")
    lines.append("  SAP Documentation Monitor.")
    lines.append("-" * 60)

    # ── Build premium HTML email ─────────────────────────────────────
    def _esc(text):
        """HTML-escape a string."""
        return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

    # Status banner configuration
    if has_changes:
        _parts = []
        if new_pages:
            _parts.append(f"{len(new_pages)} new")
        if modified_pages:
            _parts.append(f"{len(modified_pages)} modified")
        if removed_pages_list:
            _parts.append(f"{len(removed_pages_list)} removed")
        status_sub = ', '.join(_parts) + ' page(s) found. Review details below.'

        # Severity-aware colours
        if overall_severity == 'HIGH':
            status_text = 'Changes Detected [HIGH]'
            status_bg = '#FEF2F2'
            status_border = '#DC2626'
            status_color = '#991B1B'
            status_icon_bg = '#FECACA'
            status_icon = '&#9888;'
        else:
            sev_label = f' [{overall_severity}]' if overall_severity else ''
            status_text = f'Changes Detected{sev_label}'
            status_bg = '#FFFAEB'
            status_border = '#F59E0B'
            status_color = '#92400E'
            status_icon_bg = '#FEF3C7'
            status_icon = '&#9888;'
    else:
        status_text = 'No Changes Detected'
        status_sub = 'All snapshots match the current live documentation.'
        status_bg = '#ECFDF3'
        status_border = '#34D399'
        status_color = '#065F46'
        status_icon_bg = '#D1FAE5'
        status_icon = '&#10003;'

    # Metric cards data
    metrics = [
        ('Pages Checked', total_pages, '#0070F2', '#EFF6FF'),
        ('New Pages Added', len(new_pages), '#2563EB' if new_pages else '#6B7280', '#EFF6FF' if new_pages else '#F9FAFB'),
        ('Modified Pages', len(modified_pages), '#DC6803' if modified_pages else '#6B7280', '#FFFAEB' if modified_pages else '#F9FAFB'),
        ('Unchanged Pages', unchanged_count, '#059669', '#ECFDF3'),
    ]

    run_status_color = '#059669' if run_status == 'Success' else '#DC2626'

    html_lines = []
    html_lines.append('<!DOCTYPE html>')
    html_lines.append('<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">')
    # Responsive styles – Gmail, Apple Mail, iOS Mail, Outlook.com, Yahoo, Samsung Mail, Android Gmail
    html_lines.append('<style type="text/css">')

    # ── Tablet / small laptop (≤ 660px) ─────────────────────────
    html_lines.append('  @media only screen and (max-width:660px) {')
    html_lines.append('    .outer-pad  { padding:20px 10px !important; }')
    html_lines.append('    .sec-pad    { padding-left:20px !important; padding-right:20px !important; }')
    html_lines.append('    .hdr-pad    { padding:22px 20px !important; }')
    html_lines.append('    .hdr-title  { font-size:17px !important; }')
    html_lines.append('    .metric-cell { display:inline-block !important; width:48% !important; box-sizing:border-box !important; padding:3px !important; }')
    html_lines.append('    .metric-num  { font-size:24px !important; }')
    html_lines.append('    .metric-lbl  { font-size:9px !important; }')
    html_lines.append('    .tile-cell   { display:block !important; width:100% !important; box-sizing:border-box !important; padding:3px 0 !important; }')
    html_lines.append('    .tile-val    { font-size:11px !important; }')
    html_lines.append('    .detail-td   { display:block !important; width:100% !important; text-align:left !important; padding:4px 12px !important; }')
    html_lines.append('    .pg-name     { max-width:220px !important; word-break:break-word !important; }')
    html_lines.append('    .tbl-wrap    { overflow-x:auto !important; -webkit-overflow-scrolling:touch !important; }')
    html_lines.append('    .status-icon { width:30px !important; height:30px !important; line-height:30px !important; font-size:15px !important; }')
    html_lines.append('    .status-title { font-size:14px !important; }')
    html_lines.append('  }')

    # ── Phone landscape / large phone (≤ 480px) ────────────────
    html_lines.append('  @media only screen and (max-width:480px) {')
    html_lines.append('    .outer-pad  { padding:12px 4px !important; }')
    html_lines.append('    .sec-pad    { padding-left:14px !important; padding-right:14px !important; }')
    html_lines.append('    .hdr-pad    { padding:18px 14px !important; }')
    html_lines.append('    .hdr-title  { font-size:15px !important; }')
    html_lines.append('    .hdr-ts     { display:none !important; }')
    html_lines.append('    .metric-cell { width:48% !important; padding:3px !important; }')
    html_lines.append('    .metric-num  { font-size:22px !important; }')
    html_lines.append('    .tile-cell   { display:block !important; width:100% !important; padding:3px 0 !important; }')
    html_lines.append('    .tile-lbl    { font-size:8px !important; }')
    html_lines.append('    .tile-val    { font-size:10px !important; }')
    html_lines.append('    .pg-name     { max-width:180px !important; font-size:11px !important; }')
    html_lines.append('    .status-icon { width:26px !important; height:26px !important; line-height:26px !important; font-size:13px !important; }')
    html_lines.append('    .status-title { font-size:13px !important; }')
    html_lines.append('  }')

    # ── Small phone / iPhone SE / Android compact (≤ 375px) ────
    html_lines.append('  @media only screen and (max-width:375px) {')
    html_lines.append('    .outer-pad  { padding:8px 2px !important; }')
    html_lines.append('    .sec-pad    { padding-left:10px !important; padding-right:10px !important; }')
    html_lines.append('    .hdr-pad    { padding:14px 10px !important; }')
    html_lines.append('    .hdr-title  { font-size:13px !important; }')
    html_lines.append('    .metric-cell { width:47% !important; padding:2px !important; }')
    html_lines.append('    .metric-num  { font-size:18px !important; }')
    html_lines.append('    .metric-lbl  { font-size:8px !important; letter-spacing:0.2px !important; }')
    html_lines.append('    .tile-cell   { display:block !important; width:100% !important; padding:2px 0 !important; }')
    html_lines.append('    .tile-lbl    { font-size:8px !important; }')
    html_lines.append('    .tile-val    { font-size:10px !important; }')
    html_lines.append('    .pg-name     { max-width:130px !important; font-size:10px !important; }')
    html_lines.append('  }')

    html_lines.append('</style>')
    html_lines.append('</head>')
    html_lines.append('<body style="margin:0;padding:0;background-color:#F1F5F9;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;-webkit-font-smoothing:antialiased;">')

    # Outer wrapper (email-client compat)
    html_lines.append('<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F1F5F9;">')
    html_lines.append('<tr><td align="center" class="outer-pad" style="padding:32px 16px;">')

    # Main container
    html_lines.append('<table cellpadding="0" cellspacing="0" border="0" style="max-width:660px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;">')

    # ── HEADER ──────────────────────────────────────────────────────
    html_lines.append('<tr><td class="hdr-pad" style="background-color:#0F172A;padding:28px 36px;">')
    html_lines.append('  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')
    html_lines.append('    <td style="vertical-align:middle;">')
    html_lines.append('      <div class="hdr-title" style="font-size:19px;font-weight:700;color:#ffffff;letter-spacing:0.2px;">SAP APM Documentation Monitor</div>')
    html_lines.append('      <div style="font-size:11px;color:#94A3B8;margin-top:4px;text-transform:uppercase;letter-spacing:1.2px;font-weight:500;">Run Report</div>')
    html_lines.append('    </td>')
    html_lines.append(f'    <td class="hdr-ts" align="right" style="vertical-align:top;"><div style="font-size:12px;color:#94A3B8;white-space:nowrap;">{_esc(ts)}</div></td>')
    html_lines.append('  </tr></table>')
    html_lines.append('</td></tr>')

    # ── STATUS BANNER ───────────────────────────────────────────────
    html_lines.append(f'<tr><td class="sec-pad" style="padding:20px 36px;background-color:{status_bg};border-left:4px solid {status_border};">')
    html_lines.append('  <table cellpadding="0" cellspacing="0" border="0"><tr>')
    html_lines.append(f'    <td style="vertical-align:middle;padding-right:14px;"><div class="status-icon" style="width:36px;height:36px;border-radius:50%;background-color:{status_icon_bg};text-align:center;line-height:36px;font-size:18px;color:{status_color};">{status_icon}</div></td>')
    html_lines.append(f'    <td style="vertical-align:middle;">')
    html_lines.append(f'      <div class="status-title" style="font-size:16px;font-weight:700;color:{status_color};">{status_text}</div>')
    html_lines.append(f'      <div style="font-size:12px;color:{status_color};opacity:0.75;margin-top:2px;">{status_sub}</div>')
    html_lines.append('    </td>')
    html_lines.append('  </tr></table>')
    html_lines.append('</td></tr>')

    # ── METRIC CARDS ────────────────────────────────────────────────
    # Table-based layout so all 4 cards share equal height on desktop;
    # .metric-cell gets display:inline-block at ≤660px for 2×2 reflow
    html_lines.append('<tr><td class="sec-pad" style="padding:24px 32px 16px 32px;">')
    html_lines.append('  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')
    for m_idx, (m_label, m_value, m_color, m_bg) in enumerate(metrics):
        html_lines.append(f'    <td class="metric-cell" width="25%" style="vertical-align:top;padding:4px;">')
        html_lines.append(f'      <table width="100%" height="100%" cellpadding="0" cellspacing="0" border="0" style="height:100%;"><tr>')
        html_lines.append(f'        <td style="background-color:{m_bg};border-radius:8px;padding:14px 6px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.04);vertical-align:middle;">')
        html_lines.append(f'          <div class="metric-num" style="font-size:28px;font-weight:800;color:{m_color};line-height:1;">{m_value}</div>')
        html_lines.append(f'          <div class="metric-lbl" style="font-size:10px;color:#64748B;margin-top:6px;text-transform:uppercase;letter-spacing:0.4px;font-weight:600;">{m_label}</div>')
        html_lines.append(f'        </td>')
        html_lines.append(f'      </tr></table>')
        html_lines.append('    </td>')
    html_lines.append('  </tr></table>')
    html_lines.append('</td></tr>')

    # ── RUN DETAILS TILES (2×2 grid) ────────────────────────────────
    run_status_msg = 'Monitoring completed without errors' if run_status == 'Success' else 'Monitoring encountered errors'
    tile_inner = 'background-color:#F8FAFC;border-radius:8px;border:1px solid #E2E8F0;padding:14px 12px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.04);'
    tile_lbl = 'font-size:10px;color:#94A3B8;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;margin-bottom:6px;'
    tile_val = 'font-size:12px;color:#1E293B;font-weight:600;'

    html_lines.append('<tr><td class="sec-pad" style="padding:0 36px 24px 36px;">')

    # Table-based grid so cells in the same row always share equal height
    html_lines.append('  <table width="100%" cellpadding="0" cellspacing="0" border="0">')

    # Row 1: Timestamp | Run Status
    html_lines.append('    <tr>')
    html_lines.append(f'      <td class="tile-cell" width="50%" style="vertical-align:top;padding:4px;">')
    html_lines.append(f'        <table width="100%" height="100%" cellpadding="0" cellspacing="0" border="0" style="height:100%;"><tr>')
    html_lines.append(f'          <td style="{tile_inner}vertical-align:middle;">')
    html_lines.append(f'            <div class="tile-lbl" style="{tile_lbl}">Timestamp</div>')
    html_lines.append(f'            <div class="tile-val" style="{tile_val}">{_esc(ts)}</div>')
    html_lines.append(f'            <div style="font-size:10px;color:#94A3B8;margin-top:3px;">IST (Asia/Kolkata)</div>')
    html_lines.append(f'          </td>')
    html_lines.append(f'        </tr></table>')
    html_lines.append('      </td>')

    html_lines.append(f'      <td class="tile-cell" width="50%" style="vertical-align:top;padding:4px;">')
    html_lines.append(f'        <table width="100%" height="100%" cellpadding="0" cellspacing="0" border="0" style="height:100%;"><tr>')
    html_lines.append(f'          <td style="{tile_inner}vertical-align:middle;">')
    html_lines.append(f'            <div class="tile-lbl" style="{tile_lbl}">Run Status</div>')
    html_lines.append(f'            <div class="tile-val" style="font-size:12px;font-weight:700;color:{run_status_color};">{_esc(run_status)}</div>')
    html_lines.append(f'            <div style="font-size:10px;color:#94A3B8;margin-top:3px;">{run_status_msg}</div>')
    html_lines.append(f'          </td>')
    html_lines.append(f'        </tr></table>')
    html_lines.append('      </td>')
    html_lines.append('    </tr>')

    # Row 2: Next Run | Changes Summary  (or full-width Next Run)
    html_lines.append('    <tr>')
    if modified_pages:
        html_lines.append(f'      <td class="tile-cell" width="50%" style="vertical-align:top;padding:4px;">')
        html_lines.append(f'        <table width="100%" height="100%" cellpadding="0" cellspacing="0" border="0" style="height:100%;"><tr>')
        html_lines.append(f'          <td style="{tile_inner}vertical-align:middle;">')
        html_lines.append(f'            <div class="tile-lbl" style="{tile_lbl}">Next Scheduled Run</div>')
        html_lines.append(f'            <div class="tile-val" style="{tile_val}">{_esc(next_run_ts)}</div>')
        html_lines.append(f'            <div style="font-size:10px;color:#94A3B8;margin-top:3px;">Daily at 10:00 AM &amp; 6:00 PM</div>')
        html_lines.append(f'          </td>')
        html_lines.append(f'        </tr></table>')
        html_lines.append('      </td>')

        html_lines.append(f'      <td class="tile-cell" width="50%" style="vertical-align:top;padding:4px;">')
        html_lines.append(f'        <table width="100%" height="100%" cellpadding="0" cellspacing="0" border="0" style="height:100%;"><tr>')
        html_lines.append(f'          <td style="{tile_inner}vertical-align:middle;">')
        html_lines.append(f'            <div class="tile-lbl" style="{tile_lbl}">Changes Summary</div>')
        sev_color = {'HIGH': '#DC2626', 'MEDIUM': '#D97706', 'LOW': '#6B7280'}.get(overall_severity or '', '#D97706')
        sev_html = f' &nbsp;&middot;&nbsp; <span style="color:{sev_color};font-weight:700;">Severity: {overall_severity or "N/A"}</span>' if overall_severity else ''
        html_lines.append(f'            <div style="font-size:12px;font-weight:700;margin-top:2px;"><span style="color:#059669;">+{total_additions} additions</span> &nbsp;&middot;&nbsp; <span style="color:#DC2626;">-{total_removals} removals</span>{sev_html}</div>')
        warn_html = f' &middot; {total_warnings} structural warning(s)' if total_warnings else ''
        html_lines.append(f'            <div style="font-size:10px;color:#94A3B8;margin-top:3px;">Content-level differences{warn_html}</div>')
        html_lines.append(f'          </td>')
        html_lines.append(f'        </tr></table>')
        html_lines.append('      </td>')
    else:
        html_lines.append(f'      <td class="tile-cell" colspan="2" style="vertical-align:top;padding:4px;">')
        html_lines.append(f'        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')
        html_lines.append(f'          <td style="{tile_inner}vertical-align:middle;">')
        html_lines.append(f'            <div class="tile-lbl" style="{tile_lbl}">Next Scheduled Run</div>')
        html_lines.append(f'            <div class="tile-val" style="{tile_val}">{_esc(next_run_ts)}</div>')
        html_lines.append(f'            <div style="font-size:10px;color:#94A3B8;margin-top:3px;">Daily at 10:00 AM &amp; 6:00 PM</div>')
        html_lines.append(f'          </td>')
        html_lines.append(f'        </tr></table>')
        html_lines.append('      </td>')
    html_lines.append('    </tr>')

    html_lines.append('  </table>')
    html_lines.append('</td></tr>')

    # ── CHANGES DETAIL ──────────────────────────────────────────────
    if has_changes:
        # New Pages section
        if new_pages:
            html_lines.append('<tr><td class="sec-pad" style="padding:0 36px 20px 36px;">')
            html_lines.append(f'  <div style="font-size:13px;font-weight:700;color:#1E293B;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #3B82F6;">New Pages Added: {len(new_pages)}</div>')
            for idx, pg in enumerate(new_pages, 1):
                html_lines.append('  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#EFF6FF;border-radius:8px;border-left:3px solid #3B82F6;margin-bottom:8px;"><tr>')
                html_lines.append('    <td style="padding:14px 16px;">')
                html_lines.append(f'      <div style="font-size:13px;font-weight:600;color:#1E293B;">{idx}. {_esc(pg["page_name"])}</div>')
                pg_url = pg.get('url', '')
                if pg_url:
                    html_lines.append(f'      <div style="margin-top:4px;"><a href="{pg_url}" style="font-size:11px;color:#3B82F6;text-decoration:none;font-weight:500;">Click here to view page &#8594;</a></div>')
                html_lines.append(f'      <div style="font-size:11px;color:#64748B;margin-top:4px;">{pg.get("total_lines", 0)} lines of content discovered</div>')
                preview = pg.get('content_preview', [])
                if preview:
                    html_lines.append('      <div style="margin-top:10px;padding:10px 12px;background-color:#ffffff;border-radius:6px;border:1px solid #DBEAFE;font-size:11px;color:#374151;line-height:1.6;">')
                    for ln_i, ln in enumerate(preview[:5], 1):
                        html_lines.append(f'        <div style="margin-bottom:2px;"><span style="color:#94A3B8;margin-right:4px;">{ln_i}.</span> {_esc(ln[:90])}</div>')
                    remaining = pg.get('total_lines', 0) - min(len(preview), 5)
                    if remaining > 0:
                        html_lines.append(f'        <div style="color:#94A3B8;font-style:italic;margin-top:4px;">... and {remaining} more lines</div>')
                    html_lines.append('      </div>')
                html_lines.append('    </td>')
                html_lines.append('  </tr></table>')
            html_lines.append('</td></tr>')

        # Modified Pages section
        if modified_pages:
            html_lines.append('<tr><td class="sec-pad" style="padding:0 36px 20px 36px;">')
            html_lines.append(f'  <div style="font-size:13px;font-weight:700;color:#1E293B;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #F59E0B;">Modified Pages: {len(modified_pages)}</div>')
            for idx, ci in enumerate(modified_pages, 1):
                added = ci.get('added', [])
                removed = ci.get('removed', [])
                warnings = ci.get('structural_warnings', [])
                sev = ci.get('max_severity', '')

                # Card border colour based on severity
                card_border = '#DC2626' if sev == 'HIGH' else '#F59E0B'
                card_bg = '#FEF2F2' if sev == 'HIGH' else '#FFFBEB'

                html_lines.append(f'  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{card_bg};border-radius:8px;border-left:3px solid {card_border};margin-bottom:8px;"><tr>')
                html_lines.append('    <td style="padding:14px 16px;">')
                # Title + severity badge
                sev_badge = ''
                if sev:
                    sev_colors = {'HIGH': ('#991B1B', '#FECACA'), 'MEDIUM': ('#92400E', '#FEF3C7'), 'LOW': ('#6B7280', '#F3F4F6')}
                    sb_color, sb_bg = sev_colors.get(sev, ('#6B7280', '#F3F4F6'))
                    sev_badge = f' <span style="display:inline-block;padding:1px 8px;border-radius:10px;font-size:9px;font-weight:700;background-color:{sb_bg};color:{sb_color};vertical-align:middle;margin-left:6px;">{sev}</span>'
                html_lines.append(f'      <div style="font-size:13px;font-weight:600;color:#1E293B;">{idx}. {_esc(ci["page_name"])}{sev_badge}</div>')
                ci_url = ci.get('url', '')
                if ci_url:
                    html_lines.append(f'      <div style="margin-top:4px;"><a href="{ci_url}" style="font-size:11px;color:#3B82F6;text-decoration:none;font-weight:500;">Click here to view page &#8594;</a></div>')
                html_lines.append(f'      <div style="font-size:11px;color:#64748B;margin-top:4px;"><span style="color:#059669;font-weight:600;">+{len(added)} additions</span> &middot; <span style="color:#DC2626;font-weight:600;">-{len(removed)} removals</span></div>')

                # Structural warnings
                if warnings:
                    html_lines.append('      <div style="margin-top:8px;padding:8px 12px;background-color:#FEF2F2;border-radius:6px;border:1px solid #FECACA;font-size:11px;color:#991B1B;line-height:1.6;">')
                    html_lines.append('        <div style="font-weight:700;margin-bottom:3px;">&#9888; Structural Warnings</div>')
                    for w in warnings:
                        html_lines.append(f'        <div style="margin-left:8px;">[{w["severity"]}] {_esc(w["message"])}</div>')
                    html_lines.append('      </div>')

                # Additions
                if added:
                    html_lines.append('      <div style="margin-top:10px;padding:10px 12px;background-color:#F0FDF4;border-radius:6px;border:1px solid #BBF7D0;font-size:11px;color:#166534;line-height:1.6;">')
                    for a_i, item in enumerate(added[:3], 1):
                        txt = item['text'] if isinstance(item, dict) else item
                        s = item.get('severity', '') if isinstance(item, dict) else ''
                        sev_lbl = f'<span style="font-weight:700;color:#059669;">[{s}]</span> ' if s else ''
                        html_lines.append(f'        <div>+ {sev_lbl}{_esc(txt[:90])}</div>')
                    if len(added) > 3:
                        html_lines.append(f'        <div style="color:#86EFAC;font-style:italic;margin-top:2px;">... and {len(added) - 3} more additions</div>')
                    html_lines.append('      </div>')

                # Removals
                if removed:
                    html_lines.append('      <div style="margin-top:6px;padding:10px 12px;background-color:#FEF2F2;border-radius:6px;border:1px solid #FECACA;font-size:11px;color:#991B1B;line-height:1.6;">')
                    for r_i, item in enumerate(removed[:3], 1):
                        txt = item['text'] if isinstance(item, dict) else item
                        s = item.get('severity', '') if isinstance(item, dict) else ''
                        sev_lbl = f'<span style="font-weight:700;color:#DC2626;">[{s}]</span> ' if s else ''
                        html_lines.append(f'        <div>- {sev_lbl}{_esc(txt[:90])}</div>')
                    if len(removed) > 3:
                        html_lines.append(f'        <div style="color:#FCA5A5;font-style:italic;margin-top:2px;">... and {len(removed) - 3} more removals</div>')
                    html_lines.append('      </div>')
                html_lines.append('    </td>')
                html_lines.append('  </tr></table>')
            html_lines.append('</td></tr>')

        # Removed Pages section
        if removed_pages_list:
            html_lines.append('<tr><td class="sec-pad" style="padding:0 36px 20px 36px;">')
            html_lines.append(f'  <div style="font-size:13px;font-weight:700;color:#1E293B;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #DC2626;">Removed Pages: {len(removed_pages_list)}</div>')
            for idx, pg in enumerate(removed_pages_list, 1):
                html_lines.append('  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#FEF2F2;border-radius:8px;border-left:3px solid #DC2626;margin-bottom:8px;"><tr>')
                html_lines.append('    <td style="padding:14px 16px;">')
                html_lines.append(f'      <div style="font-size:13px;font-weight:600;color:#991B1B;">{idx}. {_esc(pg["page_name"])}</div>')
                html_lines.append(f'      <div style="font-size:11px;color:#DC2626;margin-top:4px;">This page is no longer found in the documentation table of contents</div>')
                html_lines.append(f'      <div style="font-size:11px;color:#64748B;margin-top:4px;">{pg.get("total_lines", 0)} lines were in previous snapshot</div>')
                html_lines.append('    </td>')
                html_lines.append('  </tr></table>')
            html_lines.append('</td></tr>')

    # ── PAGES MONITORED TABLE ───────────────────────────────────────
    html_lines.append('<tr><td class="sec-pad" style="padding:4px 36px 28px 36px;">')
    html_lines.append(f'  <div style="font-size:13px;font-weight:700;color:#1E293B;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid #E2E8F0;">Pages Monitored: {total_pages}</div>')
    html_lines.append('  <div class="tbl-wrap" style="overflow-x:auto;-webkit-overflow-scrolling:touch;">')
    html_lines.append('  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border:1px solid #E2E8F0;border-radius:8px;min-width:420px;">')

    # Table header
    th = 'font-size:10px;font-weight:600;color:#64748B;text-transform:uppercase;letter-spacing:0.6px;padding:10px 8px;background-color:#F8FAFC;border-bottom:2px solid #E2E8F0;'
    html_lines.append('    <tr>')
    html_lines.append(f'      <th style="text-align:center;{th}width:6%;white-space:nowrap;">S.No.</th>')
    html_lines.append(f'      <th style="text-align:center;{th}width:10%;white-space:nowrap;">Page No.</th>')
    html_lines.append(f'      <th style="text-align:center;{th}width:12%;white-space:nowrap;">Status</th>')
    html_lines.append(f'      <th style="text-align:left;{th}padding-left:14px;">Page Name</th>')
    html_lines.append(f'      <th style="text-align:center;{th}width:10%;white-space:nowrap;">Link</th>')
    html_lines.append('    </tr>')

    # Table rows
    for i, name in enumerate(page_names, 1):
        status_tag = "OK"
        for c in new_pages:
            if c['page_name'] == name:
                status_tag = "NEW"
                break
        for c in modified_pages:
            if c['page_name'] == name:
                status_tag = "CHANGED"
                break

        # Badge colors
        if status_tag == "OK":
            b_bg, b_color = '#ECFDF3', '#059669'
        elif status_tag == "NEW":
            b_bg, b_color = '#EFF6FF', '#2563EB'
        else:
            b_bg, b_color = '#FFFAEB', '#D97706'

        num = numbers_dict.get(name, str(i))
        row_bg = '#ffffff' if i % 2 == 1 else '#F8FAFC'
        bd = 'border-bottom:1px solid #F1F5F9;' if i < len(page_names) else ''
        url = urls_dict.get(name, '')
        link_html = f'<a href="{url}" style="display:inline-block;padding:3px 10px;background-color:#EFF6FF;color:#2563EB;border-radius:4px;font-size:11px;font-weight:500;text-decoration:none;white-space:nowrap;">Open</a>' if url else ''

        # Indent sub-sections visually
        indent_px = (num.count('.') * 18)
        name_style = f'padding-left:{indent_px}px;' if indent_px else ''

        html_lines.append(f'    <tr style="background-color:{row_bg};">')
        html_lines.append(f'      <td style="padding:9px 8px;text-align:center;font-size:12px;color:#64748B;font-weight:600;{bd}white-space:nowrap;">{i}</td>')
        html_lines.append(f'      <td style="padding:9px 8px;text-align:center;font-size:12px;color:#94A3B8;{bd}white-space:nowrap;">{num}</td>')
        html_lines.append(f'      <td style="padding:9px 8px;text-align:center;{bd}white-space:nowrap;">')
        html_lines.append(f'        <span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;letter-spacing:0.3px;white-space:nowrap;background-color:{b_bg};color:{b_color};">&#9679; {status_tag}</span>')
        html_lines.append(f'      </td>')
        html_lines.append(f'      <td class="pg-name" style="padding:9px 14px;font-size:12px;color:#1E293B;{bd}{name_style}">{_esc(name)}</td>')
        html_lines.append(f'      <td style="padding:9px 8px;text-align:center;{bd}white-space:nowrap;">{link_html}</td>')
        html_lines.append(f'    </tr>')

    html_lines.append('  </table>')
    html_lines.append('  </div>')
    html_lines.append('</td></tr>')

    # ── FOOTER ──────────────────────────────────────────────────────
    html_lines.append('<tr><td class="sec-pad" style="padding:20px 36px;background-color:#F8FAFC;border-top:1px solid #E2E8F0;">')
    html_lines.append('  <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>')
    html_lines.append('    <td class="detail-td" style="font-size:11px;color:#94A3B8;">SAP Documentation Monitor &mdash; Automated Notification</td>')
    html_lines.append(f'    <td class="detail-td" align="right" style="font-size:11px;color:#94A3B8;">{_esc(ts)}</td>')
    html_lines.append('  </tr></table>')
    html_lines.append('</td></tr>')

    # Close containers
    html_lines.append('</table>')
    html_lines.append('</td></tr></table>')
    html_lines.append('</body></html>')

    html_body = '\n'.join(html_lines)

    body = "\n".join(lines)
    return subject, body, html_body


def main():
    run_timestamp = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
    run_status = "Success"
    page_names = []

    try:
        print("\n" + "="*80)
        print("SAP Documentation Monitor - Multi-Page Change Detection")
        print("="*80)

        os.makedirs(settings.SNAPSHOTS_DIR, exist_ok=True)

        # ═══ Phase 1: Download previous snapshots & build index ══════
        if is_gcs_enabled():
            print("\n[*] Cloud Storage enabled — downloading previous snapshots...")
            # Wipe any pre-existing local snapshots (e.g. baked into the
            # Docker image) so GCS is the single source of truth.
            for _fname in os.listdir(settings.SNAPSHOTS_DIR):
                if _fname.endswith('.txt'):
                    os.remove(os.path.join(settings.SNAPSHOTS_DIR, _fname))
            download_all_snapshots(settings.SNAPSHOTS_DIR)
        else:
            print("\n[*] Using local filesystem for snapshots")

        previous_snapshots = load_previous_snapshots(settings.SNAPSHOTS_DIR)
        print(f"[*] Loaded {len(previous_snapshots)} previous snapshot(s)")

        # ═══ Phase 2: Discover pages & fetch ALL current content ═════
        urls_to_monitor = settings.DOCUMENT_URLS

        if not urls_to_monitor:
            print("\n[*] Auto-discovery mode enabled")
            print(f"Discovering pages from: {settings.BASE_DOCUMENTATION_URL}\n")
            page_list = discover_documentation_urls(settings.BASE_DOCUMENTATION_URL)
            if not page_list:
                print("[X] No pages discovered. Check BASE_DOCUMENTATION_URL.")
                return
        else:
            print(f"\n[*] Manual mode: Monitoring {len(urls_to_monitor)} specified pages\n")
            page_list = [
                (str(i), name, url)
                for i, (name, url) in enumerate(urls_to_monitor.items(), 1)
            ]

        page_names = [name for _, name, _ in page_list]
        urls_dict  = {name: url for _, name, url in page_list}
        numbers_dict = {name: num for num, name, _ in page_list}

        # Fetch all current page content (NO comparison or saving yet)
        current_content = {}   # page_name → extracted text
        for page_number, page_name, url in page_list:
            text = fetch_page_content(page_name, url, page_number)
            if text is not None:
                current_content[page_name] = text

        print(f"\n[*] Successfully fetched {len(current_content)}/{len(page_list)} pages")

        # ═══ Phase 3: Compare previous vs current snapshots ══════════
        print(f"\n{'='*80}")
        print("Comparing previous snapshots with current content...")
        print(f"{'='*80}")

        all_changes = []
        matched_previous = set()   # normalised names matched to current pages

        for page_name in page_names:
            norm = normalize_page_name(page_name)
            current_text = current_content.get(page_name)

            if current_text is None:
                print(f"  [~] '{page_name}' — skipped (fetch failed)")
                continue

            old_text = previous_snapshots.get(norm)

            if old_text is None:
                # ── NEW page ─────────────────────────────────────────
                content_lines = [l.strip() for l in current_text.splitlines() if l.strip()]
                print(f"  [NEW]     '{page_name}' — {len(content_lines)} lines")
                all_changes.append({
                    'page_name': page_name,
                    'url': urls_dict.get(page_name, ''),
                    'is_new_page': True,
                    'content_preview': content_lines[:15],
                    'total_lines': len(content_lines),
                })
            else:
                matched_previous.add(norm)
                # ── Compare content ──────────────────────────────────
                result = compare(old_text, current_text)
                if result['has_changes']:
                    added    = result['added']
                    removed  = result['removed']
                    warnings = result['structural_warnings']
                    severity = result['max_severity']

                    # Integrity check — extreme shrinkage is likely a
                    # rendering failure, not a real change.
                    old_len = len(old_text.strip())
                    new_len = len(current_text.strip())
                    shrinkage = (old_len - new_len) / old_len if old_len else 0
                    if shrinkage > 0.7 and len(added) == 0:
                        print(f"  [!]       '{page_name}' — suspicious shrinkage, skipped")
                        continue

                    warn_msg = f", {len(warnings)} warning(s)" if warnings else ""
                    print(f"  [CHANGED] '{page_name}' — +{len(added)} / -{len(removed)}{warn_msg}")

                    all_changes.append({
                        'page_name': page_name,
                        'url': urls_dict.get(page_name, ''),
                        'added': added,
                        'removed': removed,
                        'structural_warnings': warnings,
                        'max_severity': severity,
                    })
                else:
                    print(f"  [OK]      '{page_name}'")

        # ── Detect removed pages ─────────────────────────────────────
        current_norms = {normalize_page_name(n) for _, n, _ in page_list}
        for norm, old_content in previous_snapshots.items():
            if norm not in current_norms:
                display_name = norm.title()
                content_lines = [l.strip() for l in old_content.splitlines() if l.strip()]
                print(f"  [REMOVED] '{display_name}' — {len(content_lines)} lines (no longer in TOC)")
                all_changes.append({
                    'page_name': display_name,
                    'url': '',
                    'is_removed_page': True,
                    'total_lines': len(content_lines),
                })

        # ── Summary ──────────────────────────────────────────────────
        new_pages      = [c for c in all_changes if c.get('is_new_page')]
        modified_pages = [c for c in all_changes
                          if not c.get('is_new_page') and not c.get('is_removed_page')]
        removed_pages  = [c for c in all_changes if c.get('is_removed_page')]

        print(f"\n{'='*80}")
        if all_changes:
            parts = []
            if new_pages:      parts.append(f"{len(new_pages)} new")
            if modified_pages: parts.append(f"{len(modified_pages)} modified")
            if removed_pages:  parts.append(f"{len(removed_pages)} removed")
            print(f"SUMMARY: {', '.join(parts)} page(s)")
        else:
            print(f"[+] No changes detected in any of the {len(page_names)} monitored pages")
        print(f"{'='*80}\n")

        # ═══ Phase 4: Save current snapshots & upload to GCS ═════════
        # Clear old local snapshots so stale filenames don't persist
        for fname in os.listdir(settings.SNAPSHOTS_DIR):
            if fname.endswith('.txt'):
                os.remove(os.path.join(settings.SNAPSHOTS_DIR, fname))

        saved = 0
        for page_number, page_name, url in page_list:
            content = current_content.get(page_name)
            if content is None:
                # Fetch failed — preserve previous snapshot if available
                norm = normalize_page_name(page_name)
                content = previous_snapshots.get(norm)
                if content:
                    print(f"  [~] Preserving previous snapshot for '{page_name}'")
            if content:
                path = os.path.join(
                    settings.SNAPSHOTS_DIR,
                    f"{sanitize_filename(page_name, page_number)}.txt",
                )
                if save_snapshot(path, content):
                    saved += 1

        print(f"[*] Saved {saved} snapshot(s) to local directory")

        if is_gcs_enabled():
            print("[*] Uploading snapshots to Cloud Storage...")
            upload_all_snapshots(settings.SNAPSHOTS_DIR)

        # ═══ Phase 5: Send email notification ════════════════════════
        subject, body, html_body = build_notification(
            all_changes, page_names, run_timestamp, run_status,
            urls_dict, numbers_dict,
        )

        if settings.EMAIL_SENDER != "yourgmail@gmail.com":
            try:
                send_email(subject, body, settings, html_body)
                print("[+] Email notification sent successfully")
            except Exception as e:
                print(f"[X] Email failed: {e}")
                traceback.print_exc()
        else:
            print("\nEmail not configured. Notification preview:")
            print(body)

    except Exception as e:
        run_status = f"Error: {type(e).__name__}: {e}"
        print(f"\n[X] {run_status}")
        traceback.print_exc()

        # Attempt to send a failure notification even on crash
        try:
            subject, body, html_body = build_notification(
                [], page_names, run_timestamp, run_status,
                urls_dict if 'urls_dict' in locals() else None,
                numbers_dict if 'numbers_dict' in locals() else None,
            )
            if settings.EMAIL_SENDER != "yourgmail@gmail.com":
                send_email(subject, body, settings, html_body)
                print("[+] Failure notification email sent")
        except Exception:
            print("[X] Could not send failure notification email")

        raise

if __name__ == "__main__":
    main()
