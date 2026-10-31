"""Reads the 'تقرير حركة موظف (مختصر)' PDF exported by the fingerprint system.

Returns {'emps': {cid: {cid,name,fileno,job}}, 'recs': [daily rows]}.
The PDF stores Arabic text in visual order, so words are reversed back to logical order.
Parsing a 400-page file takes a minute or two, so results are cached by file content hash.
"""
import hashlib, json, os, re, unicodedata
from collections import defaultdict

import sys as _sys
_VENDOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vendor')
if _VENDOR not in _sys.path:
    _sys.path.insert(0, _VENDOR)   # bundled pure-Python pdfplumber + pdfminer (no binary deps, works on Android)
import pdfplumber  # noqa: E402

from .settings import DATA_DIR

CACHE_DIR = os.path.join(DATA_DIR, 'cache')
PARSER_VERSION = 2
_AR = re.compile(r'[؀-ۿﭐ-﻿]')
TIME = re.compile(r'^\d{2}:\d{2}$')
DATE = re.compile(r'^\d{4}/\d{2}/\d{2}$')


class ParseError(Exception):
    pass


def _fix(t):
    if _AR.search(t):
        t = t[::-1]
    t = unicodedata.normalize('NFKC', t)
    if re.search(r'[؀-ۿ]', t):  # mirrored brackets after reversal
        t = t.replace('(', '\x00').replace(')', '(').replace('\x00', ')')
    return re.sub('ـ+', '', t)


def file_hash(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_pdf(path, progress=None, use_cache=True):
    """progress(done_pages, total_pages) is called while parsing."""
    if not os.path.exists(path):
        raise ParseError(f'الملف غير موجود: {path}')
    key = file_hash(path)
    cache = os.path.join(CACHE_DIR, f'{key}_v{PARSER_VERSION}.json')
    if use_cache and os.path.exists(cache):
        with open(cache, encoding='utf-8') as f:
            data = json.load(f)
        if progress: progress(1, 1)
        return data

    recs, emps = [], {}
    cur = None
    try:
        pdf = pdfplumber.open(path)
    except Exception as e:
        raise ParseError(f'تعذر فتح ملف PDF: {e}')
    with pdf:
        total = len(pdf.pages)
        for pi, pg in enumerate(pdf.pages):
            ws = pg.extract_words(keep_blank_chars=False)
            for w in ws:
                w['t'] = _fix(w['text'])
            # ---- employee header (civil id is a 12-digit number near the top)
            cid = [w for w in ws if re.fullmatch(r'\d{12}', w['t']) and w['top'] < 130]
            if cid:
                c = cid[0]
                line = [w for w in ws if abs(w['top'] - c['top']) < 5]
                dash = [w for w in line if w['t'] == '-']
                jl = [w for w in line if 'الوظيفة' in w['t']]
                xmax = dash[0]['x0'] if dash else c['x0']
                xmin = jl[0]['x1'] if jl else 300
                name = ' '.join(w['t'] for w in sorted([w for w in line if xmin < w['x0'] < xmax], key=lambda w: -w['x0']))
                l2 = [w for w in ws if 3 <= w['top'] - c['top'] <= 14 and 320 < w['x0'] < 525 and w['t'] not in ('.', ':')]
                if l2:
                    name += ' ' + ' '.join(w['t'] for w in sorted(l2, key=lambda w: -w['x0']))
                name = re.sub(r'\s*\.\s*', ' ', name).strip()
                name = re.sub(r'\s+', ' ', name)
                fileno = [w['t'] for w in ws if re.fullmatch(r'\d{5,9}', w['t']) and w['top'] < 130 and w['x0'] < 110]
                jobw = [w for w in ws if 150 < w['x0'] < 275 and 85 < w['top'] < 115]
                job = ' '.join(w['t'] for w in sorted(jobw, key=lambda w: (round(w['top']), -w['x0'])))
                cur = dict(cid=c['t'], name=name or c['t'], fileno=fileno[0] if fileno else '', job=job)
                emps.setdefault(cur['cid'], cur)
            # ---- daily rows, anchored on the date column at the right edge
            anchors = sorted([w for w in ws if DATE.match(w['t']) and w['x0'] > 470], key=lambda w: w['top'])
            if anchors and cur is not None:
                cells = defaultdict(lambda: defaultdict(list))
                for w in ws:
                    if w['top'] < (165 if cid else 60) or w in anchors:
                        continue
                    cand = [i for i in range(len(anchors)) if anchors[i]['top'] <= w['top'] + 4]
                    if not cand:
                        continue
                    a = cand[-1]
                    if w['top'] - anchors[a]['top'] > 90:
                        continue
                    x = w['x0']
                    if x >= 470: col = 'day'
                    elif TIME.match(w['t']) and x >= 400: col = 't1'
                    elif TIME.match(w['t']) and x >= 330: col = 'out'
                    elif TIME.match(w['t']) and x >= 250: col = 't2'
                    elif TIME.match(w['t']) and x >= 180: col = 'late'
                    elif x < 100: col = 'note'
                    elif 100 <= x < 175 and not TIME.match(w['t']): col = 'shift'
                    else: col = 'mid'
                    cells[a][col].append(w)
                for i, a in enumerate(anchors):
                    g = cells[i]
                    j = lambda col: ' '.join(w['t'] for w in sorted(g[col], key=lambda w: (round(w['top'] / 4), -w['x0'])))
                    recs.append(dict(page=pi + 1, cid=cur['cid'], date=a['t'], day=j('day'), t1=j('t1'), out=j('out'),
                                     t2=j('t2'), late=j('late'), shift=j('shift'), mid=j('mid'), note=j('note')))
            if progress and (pi % 5 == 0 or pi == total - 1):
                progress(pi + 1, total)

    if not emps or not recs:
        raise ParseError('لم يُعثر على موظفين أو سجلات. تأكد أن الملف هو «تقرير حركة موظف (مختصر)» من نظام البصمة.')
    data = dict(emps=emps, recs=recs, source=os.path.basename(path), pages=total)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return data
