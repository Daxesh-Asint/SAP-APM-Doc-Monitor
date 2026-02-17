"""
Smart document comparison engine for SAP documentation monitoring.

Provides:
  - Deep normalization to ignore formatting noise (whitespace, bullets,
    line breaks, arrow symbols, UI separators, step numbers).
  - Semantic change classification with severity levels
    (HIGH / MEDIUM / LOW).
  - Structural validation (numbering gaps, missing sections, removed
    prerequisite lines).
"""

import re
from collections import Counter

# ────────────────────────────────────────────────────────────────────
# Normalization helpers
# ────────────────────────────────────────────────────────────────────

_BULLET_RE = re.compile(
    r'^[\s]*[•·\-\*\u2022\u2023\u25E6\u2043\u2219]\s*'
)
_STEP_NUMBER_RE = re.compile(r'^[\s]*(\d+)[\.\)]\s*')
_SEPARATOR_RE = re.compile(r'^[\s]*[-=*_─]{3,}\s*$')
_ARROW_RE = re.compile(r'\s*[→►▶➜➤»]\s*')
_TABLE_SEP_RE = re.compile(r'^[\s]*[-─]+(\s{2,}[-─]+)+\s*$')


def _normalize_line(line):
    """
    Deep normalization of a single line for comparison.

    Strips bullets, step numbers, arrows, and collapses whitespace so
    that purely cosmetic differences are invisible to the diff engine.
    """
    if not line or not line.strip():
        return ''
    s = line.strip()

    # Strip leading bullet characters
    s = _BULLET_RE.sub('', s)

    # Strip leading step numbers  (e.g. "3. Choose …" → "Choose …")
    s = _STEP_NUMBER_RE.sub('', s)

    # Normalize arrow variants  (→ ► ▶ ➜ ») → " > "
    s = _ARROW_RE.sub(' > ', s)

    # Collapse whitespace and lowercase
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def _is_noise(line):
    """Return True when *line* carries no semantic content."""
    stripped = line.strip()
    if not stripped:
        return True
    if _SEPARATOR_RE.match(stripped):
        return True
    if _TABLE_SEP_RE.match(stripped):
        return True
    return False


# ────────────────────────────────────────────────────────────────────
# Semantic line classification
# ────────────────────────────────────────────────────────────────────

_ACTION_VERBS = frozenset([
    'choose', 'select', 'click', 'enter', 'navigate', 'open', 'upload',
    'download', 'save', 'add', 'remove', 'delete', 'create', 'configure',
    'check', 'verify', 'confirm', 'submit', 'type', 'drag', 'drop',
    'browse', 'expand', 'collapse', 'go', 'log', 'sign', 'press',
    'enable', 'disable', 'set', 'change', 'update', 'assign', 'map',
    'register', 'subscribe', 'search', 'copy', 'paste', 'refresh',
])

_SECTION_KEYWORDS = frozenset([
    'prerequisites', 'prerequisite', 'procedure', 'results', 'result',
    'context', 'steps', 'next steps', 'related information',
])


def _classify_line(line):
    """
    Classify a line into a semantic category.

    Returns one of:
      ``'section_header'`` | ``'instruction'`` | ``'prerequisite'``
      | ``'note'`` | ``'content'`` | ``'noise'``
    """
    stripped = line.strip()
    if not stripped or _is_noise(stripped):
        return 'noise'

    norm = _normalize_line(stripped)
    if not norm:
        return 'noise'

    # Section headers  ("Prerequisites", "Procedure", "Results", …)
    clean = norm.rstrip(':').strip()
    if clean in _SECTION_KEYWORDS:
        return 'section_header'

    # Step-group sub-headers  ("Steps in the SAP BTP cockpit:")
    if norm.startswith('steps in') or norm.startswith('steps for'):
        return 'section_header'

    # Procedural instructions (first meaningful word is an action verb)
    first_word = norm.split()[0] if norm.split() else ''
    if first_word in _ACTION_VERBS:
        return 'instruction'

    # Prerequisite bullets
    if any(stripped.lstrip('•·-* ').lower().startswith(p)
           for p in ("you've", "you're", "you need", "you must",
                     "you have", "you should")):
        return 'prerequisite'

    # Note blocks
    if norm.startswith('note:') or norm.startswith('note ') or norm == 'note':
        return 'note'

    return 'content'


_SEVERITY_MAP = {
    'instruction':    'HIGH',
    'section_header': 'HIGH',
    'prerequisite':   'HIGH',
    'note':           'MEDIUM',
    'content':        'MEDIUM',
    'noise':          'LOW',
}


def _severity_for(category):
    """Map a line category to a severity level."""
    return _SEVERITY_MAP.get(category, 'MEDIUM')


# ────────────────────────────────────────────────────────────────────
# Structural validation
# ────────────────────────────────────────────────────────────────────

def _detect_numbering_gaps(text):
    """
    Detect gaps in step numbering.

    E.g. steps 11 → 13 means step 12 is missing.
    Resets the counter when the numbers restart from 1.
    """
    warnings = []
    prev_num = None

    for line in text.splitlines():
        m = _STEP_NUMBER_RE.match(line.strip())
        if m:
            num = int(m.group(1))
            # Reset when numbering restarts (new sub-procedure)
            if num == 1:
                prev_num = 1
                continue
            if prev_num is not None and num > prev_num + 1:
                for missing in range(prev_num + 1, num):
                    warnings.append({
                        'type': 'NUMBERING_GAP',
                        'severity': 'HIGH',
                        'message': (
                            f'Step {missing} is missing '
                            f'(numbering jumps from {prev_num} to {num})'
                        ),
                    })
            prev_num = num

    return warnings


def _detect_missing_sections(text):
    """
    Warn when a procedural document is missing expected sections.

    Only checks documents that *look like* procedures (contain action
    verbs).
    """
    warnings = []
    norm = text.lower()

    # Only validate docs that contain procedural instructions
    has_procedures = any(
        verb in norm for verb in ('choose ', 'select ', 'navigate ')
    )
    if not has_procedures:
        return warnings

    expected = [
        ('prerequisites', 'Prerequisites section'),
        ('procedure',     'Procedure section'),
    ]
    for keyword, label in expected:
        if keyword not in norm:
            warnings.append({
                'type': 'MISSING_SECTION',
                'severity': 'HIGH',
                'message': f'{label} may be missing from the document',
            })

    return warnings


def _detect_missing_prerequisites(old_text, new_text):
    """
    Detect prerequisite lines present in old text but missing from new.
    """
    warnings = []

    def _prereq_lines(text):
        out = set()
        for line in text.splitlines():
            if _classify_line(line) == 'prerequisite':
                out.add(_normalize_line(line))
        return out

    old_prereqs = _prereq_lines(old_text)
    new_prereqs = _prereq_lines(new_text)

    for missing in old_prereqs - new_prereqs:
        warnings.append({
            'type': 'MISSING_PREREQUISITE',
            'severity': 'HIGH',
            'message': f'Prerequisite removed: "{missing}"',
        })

    return warnings


def _validate_structure(old_text, new_text):
    """
    Run all structural validations.

    Only reports *new* issues (not already present in the old text) so
    the monitor does not re-alert on pre-existing gaps every run.
    """
    old_warnings = (
        _detect_numbering_gaps(old_text)
        + _detect_missing_sections(old_text)
    )
    new_warnings = (
        _detect_numbering_gaps(new_text)
        + _detect_missing_sections(new_text)
    )

    old_msgs = {w['message'] for w in old_warnings}
    new_only = [w for w in new_warnings if w['message'] not in old_msgs]

    # Missing prerequisite comparison (always "new")
    new_only.extend(_detect_missing_prerequisites(old_text, new_text))

    return new_only


# ────────────────────────────────────────────────────────────────────
# Main comparison engine
# ────────────────────────────────────────────────────────────────────

_SEVERITY_ORDER = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}


def compare(old_text, new_text):
    """
    Compare old and new documentation text with semantic awareness.

    1. Normalizes both texts to strip formatting noise.
    2. Performs a count-aware semantic diff on meaningful content
       (handles duplicate lines like repeated "Choose Save" correctly).
    3. Classifies every change by severity (HIGH / MEDIUM / LOW).
    4. Runs structural validation for numbering gaps, missing sections,
       and removed prerequisite lines.

    Returns
    -------
    dict
        ``has_changes``          – bool
        ``added``                – list of {text, severity, category}
        ``removed``              – list of {text, severity, category}
        ``structural_warnings``  – list of {type, severity, message}
        ``max_severity``         – 'HIGH' | 'MEDIUM' | 'LOW' | None
    """
    result = {
        'has_changes': False,
        'added': [],
        'removed': [],
        'structural_warnings': [],
        'max_severity': None,
    }

    # ── Build normalized lists (preserving duplicates) ─────────────
    old_norm_map = {}   # normalized → first original line (stripped)
    new_norm_map = {}
    old_norm_list = []
    new_norm_list = []

    for line in old_text.splitlines():
        if _is_noise(line):
            continue
        n = _normalize_line(line)
        if n:
            old_norm_map.setdefault(n, line.strip())
            old_norm_list.append(n)

    for line in new_text.splitlines():
        if _is_noise(line):
            continue
        n = _normalize_line(line)
        if n:
            new_norm_map.setdefault(n, line.strip())
            new_norm_list.append(n)

    # Count-aware comparison: handles duplicate lines correctly
    # e.g. 3× "Choose Save ." in old, 1× in new → 2 removals
    old_counts = Counter(old_norm_list)
    new_counts = Counter(new_norm_list)

    # ── Semantic additions & removals ──────────────────────────────
    all_norms = set(old_norm_list) | set(new_norm_list)

    for norm in sorted(all_norms):
        old_c = old_counts.get(norm, 0)
        new_c = new_counts.get(norm, 0)

        if old_c > new_c:
            # Removed lines
            original = old_norm_map.get(norm, norm)
            cat = _classify_line(original)
            if cat == 'noise':
                continue
            for _ in range(old_c - new_c):
                result['removed'].append({
                    'text': original,
                    'severity': _severity_for(cat),
                    'category': cat,
                })

        elif new_c > old_c:
            # Added lines
            original = new_norm_map.get(norm, norm)
            cat = _classify_line(original)
            if cat == 'noise':
                continue
            for _ in range(new_c - old_c):
                result['added'].append({
                    'text': original,
                    'severity': _severity_for(cat),
                    'category': cat,
                })

    # ── Structural validation ──────────────────────────────────────
    result['structural_warnings'] = _validate_structure(old_text, new_text)

    # ── Determine flags ────────────────────────────────────────────
    if result['added'] or result['removed']:
        result['has_changes'] = True

    all_sevs = (
        [c['severity'] for c in result['added']]
        + [c['severity'] for c in result['removed']]
        + [w['severity'] for w in result['structural_warnings']]
    )
    if all_sevs:
        result['max_severity'] = max(
            all_sevs, key=lambda s: _SEVERITY_ORDER.get(s, 0)
        )

    # Sort each list: HIGH first
    _skey = lambda item: _SEVERITY_ORDER.get(item.get('severity'), 0) * -1
    result['added'].sort(key=_skey)
    result['removed'].sort(key=_skey)
    result['structural_warnings'].sort(key=_skey)

    return result
