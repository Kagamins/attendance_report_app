"""Minimal Arabic shaping + right-to-left reordering for PDF libraries without a text shaper.

shape_rtl(text) returns a string in *visual* order using Arabic Presentation Forms-B, ready to be
drawn left-to-right by reportlab with a font that contains those forms (DejaVu Sans does).
"""
import re

# letter: (isolated, final, initial, medial); right-joining letters have only two forms
_F = {
    'ء': ('ﺀ',), 'آ': ('ﺁ', 'ﺂ'), 'أ': ('ﺃ', 'ﺄ'), 'ؤ': ('ﺅ', 'ﺆ'), 'إ': ('ﺇ', 'ﺈ'),
    'ئ': ('ﺉ', 'ﺊ', 'ﺋ', 'ﺌ'), 'ا': ('ﺍ', 'ﺎ'), 'ب': ('ﺏ', 'ﺐ', 'ﺑ', 'ﺒ'), 'ة': ('ﺓ', 'ﺔ'),
    'ت': ('ﺕ', 'ﺖ', 'ﺗ', 'ﺘ'), 'ث': ('ﺙ', 'ﺚ', 'ﺛ', 'ﺜ'), 'ج': ('ﺝ', 'ﺞ', 'ﺟ', 'ﺠ'),
    'ح': ('ﺡ', 'ﺢ', 'ﺣ', 'ﺤ'), 'خ': ('ﺥ', 'ﺦ', 'ﺧ', 'ﺨ'), 'د': ('ﺩ', 'ﺪ'), 'ذ': ('ﺫ', 'ﺬ'),
    'ر': ('ﺭ', 'ﺮ'), 'ز': ('ﺯ', 'ﺰ'), 'س': ('ﺱ', 'ﺲ', 'ﺳ', 'ﺴ'), 'ش': ('ﺵ', 'ﺶ', 'ﺷ', 'ﺸ'),
    'ص': ('ﺹ', 'ﺺ', 'ﺻ', 'ﺼ'), 'ض': ('ﺽ', 'ﺾ', 'ﺿ', 'ﻀ'), 'ط': ('ﻁ', 'ﻂ', 'ﻃ', 'ﻄ'),
    'ظ': ('ﻅ', 'ﻆ', 'ﻇ', 'ﻈ'), 'ع': ('ﻉ', 'ﻊ', 'ﻋ', 'ﻌ'), 'غ': ('ﻍ', 'ﻎ', 'ﻏ', 'ﻐ'),
    'ف': ('ﻑ', 'ﻒ', 'ﻓ', 'ﻔ'), 'ق': ('ﻕ', 'ﻖ', 'ﻗ', 'ﻘ'), 'ك': ('ﻙ', 'ﻚ', 'ﻛ', 'ﻜ'),
    'ل': ('ﻝ', 'ﻞ', 'ﻟ', 'ﻠ'), 'م': ('ﻡ', 'ﻢ', 'ﻣ', 'ﻤ'), 'ن': ('ﻥ', 'ﻦ', 'ﻧ', 'ﻨ'),
    'ه': ('ﻩ', 'ﻪ', 'ﻫ', 'ﻬ'), 'و': ('ﻭ', 'ﻮ'), 'ى': ('ﻯ', 'ﻰ'), 'ي': ('ﻱ', 'ﻲ', 'ﻳ', 'ﻴ'),
    'ـ': ('ـ', 'ـ', 'ـ', 'ـ'),
}
_LAM_ALEF = {'آ': ('ﻵ', 'ﻶ'), 'أ': ('ﻷ', 'ﻸ'), 'إ': ('ﻹ', 'ﻺ'), 'ا': ('ﻻ', 'ﻼ')}
_HARAKAT = re.compile('[ً-ٰٟۖ-ۭ]')
_MIRROR = str.maketrans('()[]{}<>«»', ')(][}{><»«')
_LTR = re.compile(r'[0-9A-Za-z٠-٩۰-۹]+(?:[.,:/%+\-−_@#×][0-9A-Za-z٠-٩۰-۹%]+)*%?'
                  r'|[+\-−][0-9]+(?:[.,][0-9]+)?%?')
_ARABIC = re.compile('[؀-ۿﭐ-﷿ﹰ-﻿]')


def _joins_next(ch):   # can connect to the following letter
    f = _F.get(ch)
    return f is not None and len(f) == 4


def _joinable(ch):
    f = _F.get(ch)
    return f is not None and len(f) >= 2


def _clusters(s):
    """Split into (base, marks) so diacritics stay attached to their letter."""
    out = []
    for ch in s:
        if _HARAKAT.match(ch) and out:
            out[-1][1] += ch
        else:
            out.append([ch, ''])
    return out


def shape(text):
    """Contextual letter forms, logical order kept (diacritics are transparent for joining)."""
    cl = _clusters(str(text)); out = []; i = 0; n = len(cl)
    while i < n:
        ch, marks = cl[i]
        prev = cl[i - 1][0] if i > 0 else ''
        connect_prev = i > 0 and _joins_next(prev) and _joinable(ch)
        if ch == 'ل' and i + 1 < n and cl[i + 1][0] in _LAM_ALEF:
            out.append(_LAM_ALEF[cl[i + 1][0]][1 if connect_prev else 0] + marks + cl[i + 1][1]); i += 2; continue
        f = _F.get(ch)
        if not f:
            out.append(ch + marks); i += 1; continue
        nxt = cl[i + 1][0] if i + 1 < n else ''
        connect_next = len(f) == 4 and _joinable(nxt)
        if len(f) == 1: form = f[0]
        elif connect_prev and connect_next: form = f[3]
        elif connect_prev: form = f[1]
        elif connect_next: form = f[2]
        else: form = f[0]
        out.append(form + marks); i += 1
    return ''.join(out)


def _rev(chunk):
    """Reverse an RTL run by letter clusters (marks stay after their base) and mirror brackets."""
    return ''.join(b + m for b, m in reversed(_clusters(chunk))).translate(_MIRROR)


def has_arabic(text):
    return bool(_ARABIC.search(str(text)))


def visual(text):
    """Logical text -> visual order for a right-to-left line (no wrapping)."""
    text = str(text)
    if not has_arabic(text):
        return text
    s = shape(text)
    runs = []; pos = 0
    for m in _LTR.finditer(s):
        if m.start() > pos: runs.append((False, s[pos:m.start()]))
        runs.append((True, m.group())); pos = m.end()
    if pos < len(s): runs.append((False, s[pos:]))
    out = []
    for ltr, chunk in reversed(runs):
        out.append(chunk if ltr else _rev(chunk))
    return ''.join(out)


def wrap(text, width, measure):
    """Split logical text into lines no wider than width (measure(str)->float works on shaped text)."""
    lines = []
    for para in str(text).split('\n'):
        words = para.split(' '); cur = ''
        for w in words:
            t = (cur + ' ' + w).strip() if cur else w
            if cur and measure(shape(t)) > width:
                lines.append(cur); cur = w
            else:
                cur = t
        lines.append(cur)
    return lines
