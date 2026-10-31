"""Pure-Python PDF reports (reportlab) for Android/iOS, where Chromium/Playwright is unavailable.

Produces the same reports as report.py / infographic.py with simpler styling:
full report, single-employee report, people list and a one-page infographic.
"""
import math, os, re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Flowable, KeepTogether, PageBreak, SimpleDocTemplate, Spacer, Table, TableStyle)

from .arabic import shape, visual, wrap
from .report import DEFAULT_OPTIONS, findings, recommendations
from .stats import filters

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'fonts')
_REG = False
F, FB = 'DejaVuSans', 'DejaVuSans-Bold'
NAVY = colors.HexColor('#1F3864'); BLUE = colors.HexColor('#2A78D6'); ORANGE = colors.HexColor('#EB6834')
AQUA = colors.HexColor('#1BAF7A'); RED = colors.HexColor('#B3261E'); GREEN = colors.HexColor('#1B7F3B')
INK = colors.HexColor('#1D2433'); MUTED = colors.HexColor('#5A6474'); GRID = colors.HexColor('#D8DBE0')
LIGHT = colors.HexColor('#F5F6F8'); TILE = colors.HexColor('#FCFCFB'); HEAD_BG = colors.HexColor('#EAF1F8')
SERIES = [BLUE, ORANGE, AQUA]
P = lambda x: f'{x * 100:.1f}%'
_TAGS = re.compile(r'<[^>]+>')


def _fonts():
    global _REG
    if not _REG:
        pdfmetrics.registerFont(TTFont(F, os.path.join(_FONT_DIR, 'DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont(FB, os.path.join(_FONT_DIR, 'DejaVuSans-Bold.ttf')))
        _REG = True


def plain(html):
    return _TAGS.sub('', html).replace('&amp;', '&')


def width_of(text, font=F, size=10):
    return pdfmetrics.stringWidth(shape(str(text)), font, size)


# ---------------------------------------------------------------- flowables
class RTLText(Flowable):
    """Right-aligned wrapped Arabic paragraph (optionally a bullet)."""
    def __init__(self, text, size=10, font=F, color=INK, bullet='', leading=1.55, bg=None, pad=0, align='right'):
        super().__init__(); self.t = plain(str(text)); self.size = size; self.font = font; self.color = color
        self.bullet = bullet; self.lead = size * leading; self.bg = bg; self.pad = pad; self.align = align

    def wrap(self, aw, ah):
        self.w = aw; inner = aw - 2 * self.pad - (14 if self.bullet else 0)
        self.lines = wrap(self.t, inner, lambda s: pdfmetrics.stringWidth(s, self.font, self.size))
        self.h = len(self.lines) * self.lead + 2 * self.pad + 2
        return aw, self.h

    def draw(self):
        c = self.canv
        if self.bg is not None:
            c.setFillColor(self.bg); c.roundRect(0, 0, self.w, self.h, 6, stroke=0, fill=1)
        c.setFillColor(self.color); c.setFont(self.font, self.size)
        x = self.w - self.pad; y = self.h - self.pad - self.size
        if self.bullet:
            c.drawRightString(x, y, self.bullet); x -= 14
        for ln in self.lines:
            v = visual(ln)
            if self.align == 'center': c.drawCentredString(self.w / 2, y, v)
            else: c.drawRightString(x, y, v)
            y -= self.lead


class Heading(Flowable):
    def __init__(self, text, size=14):
        super().__init__(); self.t = text; self.size = size

    def wrap(self, aw, ah):
        self.w = aw; return aw, self.size + 12

    def draw(self):
        c = self.canv; c.setFillColor(BLUE); c.rect(self.w - 4, 2, 4, self.size + 4, stroke=0, fill=1)
        c.setFillColor(NAVY); c.setFont(FB, self.size); c.drawRightString(self.w - 10, 5, visual(self.t))


class Cover(Flowable):
    def __init__(self, org, title, sub):
        super().__init__(); self.org, self.title, self.sub = org, title, sub

    def wrap(self, aw, ah):
        self.w = aw
        self.tl = wrap(self.title, aw - 30, lambda s: pdfmetrics.stringWidth(s, FB, 17))
        self.h = 70 + 22 * len(self.tl); return aw, self.h

    def draw(self):
        c = self.canv; c.setFillColor(NAVY); c.roundRect(0, 0, self.w, self.h, 8, stroke=0, fill=1)
        c.setFillColor(colors.white); x = self.w - 15; y = self.h - 20
        c.setFont(F, 9); c.drawRightString(x, y, visual(self.org)); y -= 24
        c.setFont(FB, 17)
        for ln in self.tl: c.drawRightString(x, y, visual(ln)); y -= 22
        c.setFont(F, 9.5); c.drawRightString(x, y, visual(self.sub)); y -= 16
        c.setFont(F, 9); c.drawRightString(x, y, visual('جميع الأعداد بعدد الموظفين (أفراد)، لا بعدد البصمات أو الحالات'))


class Tiles(Flowable):
    """Grid of KPI tiles laid out right-to-left."""
    def __init__(self, tiles, cols=4, h=58, value_size=20):
        super().__init__(); self.tiles = tiles; self.cols = cols; self.th = h; self.vs = value_size

    def wrap(self, aw, ah):
        self.w = aw; rows = math.ceil(len(self.tiles) / self.cols); self.h = rows * (self.th + 6); return aw, self.h

    def draw(self):
        c = self.canv; gap = 6; tw = (self.w - gap * (self.cols - 1)) / self.cols
        for i, t in enumerate(self.tiles):
            lab, val, sub = t[:3]; col = t[3] if len(t) > 3 else NAVY
            r, k = divmod(i, self.cols)
            x = self.w - (k + 1) * tw - k * gap; y = self.h - (r + 1) * (self.th + 6) + 6
            c.setFillColor(TILE); c.setStrokeColor(GRID); c.roundRect(x, y, tw, self.th, 6, stroke=1, fill=1)
            cx = x + tw / 2
            c.setFillColor(MUTED); c.setFont(F, 7.5); c.drawCentredString(cx, y + self.th - 12, visual(lab))
            vs = self.vs
            while vs > 7 and width_of(val, FB, vs) > tw - 8: vs -= 1
            c.setFillColor(col); c.setFont(FB, vs); c.drawCentredString(cx, y + self.th - 14 - (self.vs + vs) / 2, visual(val))
            c.setFillColor(MUTED); c.setFont(F, 7)
            s = str(sub)
            while s and width_of(s, F, 7) > tw - 6: s = s[:-2]
            c.drawCentredString(cx, y + 6, visual(s))


class BarChart(Flowable):
    """Grouped vertical bars, first category on the right."""
    def __init__(self, cats, series, title='', h=190, labels=True):
        super().__init__(); self.cats = cats; self.series = series; self.title = title; self.ch = h; self.labels = labels

    def wrap(self, aw, ah):
        self.w = aw; return aw, self.ch

    def draw(self):
        c = self.canv; L, R, T, B = 28, 8, 26, 34
        pw = self.w - L - R; ph = self.ch - T - B
        m = max([max(v) for _, v, _ in self.series] + [1])
        step = next((s for s in [1, 2, 5, 10, 20, 25, 50, 100, 200, 500] if m / s <= 6), 1000); top = step * math.ceil(m / step)
        c.setFont(FB, 10); c.setFillColor(INK); c.drawRightString(self.w - R, self.ch - 14, visual(self.title))
        c.setFont(F, 7); c.setStrokeColor(GRID)
        for gv in range(0, top + 1, step):
            y = B + ph * gv / top; c.line(L, y, self.w - R, y); c.setFillColor(MUTED); c.drawRightString(L - 4, y - 2, str(gv))
        n = len(self.cats); k = len(self.series); gw = pw / max(n, 1); bw = min(16, gw * 0.75 / k)
        for i, cat in enumerate(self.cats):
            gi = n - 1 - i; gx = L + gi * gw + (gw - bw * k - 2 * (k - 1)) / 2
            for j, (nm, vals, col) in enumerate(self.series):
                v = vals[i]; bh = ph * v / top; x = gx + j * (bw + 2)
                c.setFillColor(col); c.rect(x, B, bw, bh, stroke=0, fill=1)
                if self.labels:
                    c.setFillColor(MUTED); c.setFont(F, 6.5); c.drawCentredString(x + bw / 2, B + bh + 2, f'{v:g}')
            c.setFillColor(MUTED); c.setFont(F, 7.5); c.drawCentredString(L + gi * gw + gw / 2, B - 11, visual(cat))
        x = self.w - R; c.setFont(F, 8)
        for nm, _, col in self.series:
            c.setFillColor(col); c.rect(x - 9, 5, 9, 9, stroke=0, fill=1)
            c.setFillColor(INK); v = visual(nm); c.drawRightString(x - 13, 6, v); x -= 26 + pdfmetrics.stringWidth(v, F, 8)


class HBars(Flowable):
    def __init__(self, items, title='', color=BLUE):
        super().__init__(); self.items = items; self.title = title; self.color = color

    def wrap(self, aw, ah):
        self.w = aw; self.h = 26 + 17 * len(self.items); return aw, self.h

    def draw(self):
        c = self.canv; lab_w = 150; m = max([v for _, v in self.items] + [1]); pw = self.w - lab_w - 40
        c.setFont(FB, 10); c.setFillColor(INK); c.drawRightString(self.w, self.h - 13, visual(self.title))
        for i, (lab, v) in enumerate(self.items):
            y = self.h - 34 - i * 17; x0 = self.w - lab_w; bw = pw * v / m
            c.setFillColor(INK); c.setFont(F, 8); c.drawRightString(self.w, y + 2, visual(lab))
            c.setFillColor(self.color); c.rect(x0 - 6 - bw, y, bw, 11, stroke=0, fill=1)
            c.setFillColor(INK); c.setFont(FB, 8); c.drawRightString(x0 - 10 - bw, y + 2, str(v))


class DotGrid(Flowable):
    def __init__(self, n, groups, cols=27):
        super().__init__(); self.n = n; self.groups = groups; self.cols = cols

    def wrap(self, aw, ah):
        self.w = aw; self.s = min(12, aw / self.cols); self.h = math.ceil(self.n / self.cols) * self.s + 4; return aw, self.h

    def draw(self):
        c = self.canv; seq = []
        for cnt, col in self.groups: seq += [col] * int(cnt)
        seq += [GRID] * max(self.n - len(seq), 0)
        for k, col in enumerate(seq[:self.n]):
            r, cc = divmod(k, self.cols)
            c.setFillColor(col); c.circle(self.w - (cc + 0.5) * self.s, self.h - (r + 0.5) * self.s - 2, self.s * 0.38, stroke=0, fill=1)


def table(head, rows, widths, avail, size=7.5, name_cols=(1,), zebra=True, colored=None):
    """RTL table: columns are given right-to-left (first = rightmost) and reversed for reportlab."""
    tot = sum(widths); cw = [avail * w / tot for w in widths]
    def cell(v, i, bold=False):
        s = str(v); font = FB if bold else F
        lines = wrap(s, cw[i] - 6, lambda t: pdfmetrics.stringWidth(t, font, size)) if width_of(s, font, size) > cw[i] - 6 else [s]
        return '\n'.join(visual(x) for x in lines)
    data = [[cell(h, i, True) for i, h in enumerate(head)]] + [[cell(v, i) for i, v in enumerate(r)] for r in rows]
    data = [list(reversed(r)) for r in data]; cwr = list(reversed(cw)); n = len(head)
    st = [('FONT', (0, 0), (-1, -1), F, size), ('FONT', (0, 0), (-1, 0), FB, size), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
          ('BACKGROUND', (0, 0), (-1, 0), NAVY), ('GRID', (0, 0), (-1, -1), 0.4, GRID), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
          ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
          ('LEADING', (0, 0), (-1, -1), size * 1.35)]
    for i in name_cols:
        if 0 <= i < n: st.append(('ALIGN', (n - 1 - i, 1), (n - 1 - i, -1), 'RIGHT'))
    if zebra:
        for r in range(2, len(data), 2): st.append(('BACKGROUND', (0, r), (-1, r), LIGHT))
    for (r, i, col) in (colored or []):
        st.append(('TEXTCOLOR', (n - 1 - i, r + 1), (n - 1 - i, r + 1), col))
    t = Table(data, colWidths=cwr, repeatRows=1); t.setStyle(TableStyle(st)); return t


def _doc(path, footer, land=False):
    _fonts()
    ps = landscape(A4) if land else A4
    doc = SimpleDocTemplate(path, pagesize=ps, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
                            title='تقرير الحضور والانصراف')
    def on_page(c, d):
        c.saveState(); c.setFont(F, 7); c.setFillColor(MUTED)
        c.drawCentredString(ps[0] / 2, 7 * mm, visual(f'{footer} • صفحة {d.page}')); c.restoreState()
    return doc, on_page, ps[0] - 24 * mm


def _method(S):
    ru = S['rules']
    return RTLText(f'المنهجية: التأخير = الحضور {ru["late"]} فأكثر؛ الانصراف المبكر = قبل {ru["early"]}؛ الدوام الكامل = {ru["quota"]} دقيقة من '
                   f'بداية النصاب {ru["start"]} أو الحضور أيهما أبعد؛ الغياب دون عذر = «غياب» أو «منقطع عن العمل» في النظام؛ '
                   '«دون إذن» = لا يوجد إذن مسجل يغطي الحالة.', size=7.5, color=MUTED)


def _sign(cfg, avail):
    sigs = list(cfg.signatures) or ['']
    t = Table([[visual(s) for s in reversed(sigs)]], colWidths=[avail / len(sigs)] * len(sigs))
    t.setStyle(TableStyle([('FONT', (0, 0), (-1, -1), F, 9), ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), 30),
                           ('LINEABOVE', (0, 0), (-1, 0), 0.6, MUTED)]))
    return t


# ---------------------------------------------------------------- documents
def save_full_report(S, cfg, path, options=None):
    o = dict(DEFAULT_OPTIONS); o.update(options or {})
    E = S['E']; A = S['ALL']; WK = S['WK']; LW = S['LW']; PW = S['PW']; wr = S['wr']; weeks = S['weeks']; REP = S['rep']
    D = S['DAY']; DAYS = S['DAYS']; cats = [f'أ{w}' for w in weeks]
    nm = (lambda x: x.name) if o['show_names'] else (lambda x: f'موظف {x.cid[-4:]}')
    doc, on_page, W = _doc(path, f'{cfg.school_name} • تقرير الحضور والانصراف {S["period_short"]}')
    st = [Cover(cfg.org_line, f'تقرير الحضور والانصراف: {cfg.school_name}', f"الفترة {S['period']} • {A['days']} يوم عمل في {len(weeks)} أسابيع • {A['emp']} موظفاً"),
          Spacer(1, 8),
          Tiles([('إجمالي الموظفين', A['emp'], 'موظفاً في تقرير البصمة'), ('يحضرون يومياً في المتوسط', f"{A['avg_pres']:.0f}", f"نسبة الحضور {P(A['att'])}"),
                 ('تأخروا مرة على الأقل', A['late'], f"منهم {A['lu']} دون إذن", ORANGE), ('انصرفوا مبكراً مرة على الأقل', A['early'], f"منهم {A['eu']} دون إذن", AQUA),
                 ('غابوا يوماً على الأقل', A['absent'], f"منهم {A['unx']} دون عذر", BLUE), ('غائبون طوال الفترة', A['allabs'], f"{S['n_discon']} منقطعون • {S['n_onleave']} في إجازة", RED),
                 ('منضبطون تماماً', A['clean'], 'بلا تأخير ولا غياب أو انصراف دون إذن', GREEN), ('متأخرون باستمرار', S['n_chronic'], f'{REP} مرات تأخير فأكثر', ORANGE)])]
    sec = 1
    def h(t):
        nonlocal sec
        st.append(Spacer(1, 6)); st.append(Heading(f'{sec}. {t}')); st.append(Spacer(1, 4)); sec += 1
    if o['findings']:
        h('أبرز النتائج')
        st += [RTLText(x, bullet='•') for x in findings(S)]
        if S['has_prev']:
            st.append(RTLText(f'مقارنة بالتقرير السابق: {len(S["new_people"])} موظفاً جديداً، و{len(S["gone"])} غير موجودين في هذا التقرير.', size=8.5, color=MUTED))
            for c_, n_, j_ in S['new_people']: st.append(RTLText(f'جديد: {n_ if o["show_names"] else c_[-4:]} • {j_}', size=8, bullet='+'))
            for c_, n_, j_ in S['gone']: st.append(RTLText(f'غير موجود: {n_ if o["show_names"] else c_[-4:]} • {j_}', size=8, bullet='−'))
    if o['weekly']:
        st.append(PageBreak()); h('المسار الأسبوعي بعدد الموظفين')
        st.append(BarChart(cats, [('غابوا', [WK[w]['absent'] for w in weeks], BLUE), ('تأخروا', [WK[w]['late'] for w in weeks], ORANGE), ('انصرفوا مبكراً', [WK[w]['early'] for w in weeks], AQUA)], 'عدد الموظفين أسبوعياً'))
        rows = [[f'الأسبوع {w}', f'{wr[w][0]}–{wr[w][1]}', f"{WK[w]['avg_pres']:.0f}", P(WK[w]['att']), WK[w]['absent'], WK[w]['unx'], WK[w]['late'], WK[w]['lu'], WK[w]['early'], WK[w]['eu'], WK[w]['inc'], WK[w]['fullall']] for w in weeks]
        rows.append(['الإجمالي (أفراد)', S['period_short'], f"{A['avg_pres']:.0f}", P(A['att']), A['absent'], A['unx'], A['late'], A['lu'], A['early'], A['eu'], A['inc'], A['fullall']])
        st += [Spacer(1, 6), table(['الأسبوع', 'الفترة', 'متوسط الحاضرين', 'نسبة الحضور', 'غابوا', 'دون عذر', 'تأخروا', 'دون إذن', 'مبكراً', 'دون إذن', 'بصمة ناقصة', 'دوام كامل'], rows,
                                   [11, 12, 8, 8, 6, 6, 6, 6, 6, 6, 7, 7], W, name_cols=(0,)),
               RTLText('كل خانة = عدد الموظفين المختلفين؛ صف الإجمالي يعدّ الشخص مرة واحدة لذا لا يساوي مجموع الأسابيع.', size=7.5, color=MUTED)]
    if o['justified']:
        h('المبرر وغير المبرر')
        st.append(BarChart(cats, [('تأخروا بإذن فقط', [WK[w]['late'] - WK[w]['lu'] for w in weeks], BLUE), ('تأخروا دون إذن', [WK[w]['lu'] for w in weeks], ORANGE)], 'المتأخرون أسبوعياً (أفراد)', h=170))
        st.append(BarChart(cats, [('غابوا بعذر فقط', [WK[w]['absent'] - WK[w]['unx'] for w in weeks], BLUE), ('غابوا دون عذر', [WK[w]['unx'] for w in weeks], ORANGE)], 'الغائبون أسبوعياً (أفراد)', h=170))
    if o['latest']:
        st.append(PageBreak()); h(f'الأسبوع الأحدث: الأسبوع {LW} ({wr[LW][0]}–{wr[LW][1]})')
        b = WK[LW]
        if PW:
            a = WK[PW]; cmp = [('غابوا', a['absent'], b['absent'], -1), ('منهم دون عذر', a['unx'], b['unx'], -1), ('غائبون طوال الأسبوع', a['allabs'], b['allabs'], -1),
                               ('تأخروا', a['late'], b['late'], -1), ('منهم دون إذن', a['lu'], b['lu'], -1), ('انصرفوا مبكراً', a['early'], b['early'], -1),
                               ('منهم دون إذن', a['eu'], b['eu'], -1), ('بصمة ناقصة', a['inc'], b['inc'], -1), ('دوام كامل كل أيامهم', a['fullall'], b['fullall'], 1)]
            rows, col = [], []
            for i, (lab, x, y, g) in enumerate(cmp):
                d = y - x; rows.append([lab, x, y, f"{'▲' if d > 0 else '▼' if d < 0 else '═'} {d:+g}" + (' (أفضل)' if d * g > 0 else ' (أسوأ)' if d else '')])
                if d: col.append((i, 3, GREEN if d * g > 0 else RED))
            st.append(table(['المؤشر (عدد الموظفين)', f'الأسبوع {PW}', f'الأسبوع {LW}', 'التغير'], rows, [40, 15, 15, 20], W, name_cols=(0,), colored=col))
        ld = S['LWD']
        st.append(BarChart([f'{d[1]} {d[0]}' for d in ld], [('غائبون', [d[2]['absent'] for d in ld], BLUE), ('متأخرون', [d[2]['late'] for d in ld], ORANGE), ('منصرفون مبكراً', [d[2]['early'] for d in ld], AQUA)], f'الأسبوع {LW} يوماً بيوم', h=170))
        if PW:
            TR = S['TR']; st.append(HBars([('متحسن', TR['متحسن']), ('مستقر', TR['مستقر']), ('متراجع', TR['متراجع']), ('غائب طوال الأسبوع', TR['منقطع'])], f'مسار الموظفين في الأسبوع {LW}'))
    if o['distribution']:
        st.append(PageBreak()); h('توزيع الموظفين والأسباب')
        st += [HBars(S['LATE_B'], 'الموظفون حسب عدد مرات التأخير', ORANGE), Spacer(1, 6), HBars(S['ABS_B'], 'الموظفون حسب عدد أيام الغياب', BLUE), Spacer(1, 6)]
        if S['ABS_P']: st += [HBars(S['ABS_P'], 'أسباب الغياب: عدد الموظفين لكل سبب', BLUE), Spacer(1, 6)]
        if S['PERM_P']: st.append(HBars(S['PERM_P'], 'الأذونات المسجلة: عدد الموظفين', AQUA))
    if o['weekday'] and DAYS:
        h('الأنماط حسب أيام الأسبوع')
        st.append(BarChart(DAYS, [('غائبون', [round(D[d]['absent'], 1) for d in DAYS], BLUE), ('متأخرون', [round(D[d]['late'], 1) for d in DAYS], ORANGE), ('منصرفون مبكراً', [round(D[d]['early'], 1) for d in DAYS], AQUA)], 'متوسط عدد الموظفين في اليوم', h=170))
    if o['recommendations']:
        h('التوصيات'); st += [RTLText(x, bullet=f'{i + 1}.') for i, x in enumerate(recommendations(S))]
    first = [True]
    def app(title, head, rows, widths):
        st.append(PageBreak() if first[0] else Spacer(1, 10)); first[0] = False
        st.append(Heading(f'{title} ({len(rows)} موظفاً)', 12)); st.append(Spacer(1, 4))
        st.append(table(head, rows, widths, W, size=7) if rows else RTLText('لا أحد.', color=MUTED))
    if o['app_chronic']:
        ch = E[E.chronic].sort_values(['late', 'lu'], ascending=False)
        app(f'ملحق: المتأخرون باستمرار ({REP}+)', ['م', 'الاسم', 'الوظيفة', 'مرات التأخير', 'دون إذن', f'قبل الأسبوع {LW}', f'الأسبوع {LW}', 'الدقائق'],
            [[i + 1, nm(x), x.job, x.late, x.lu, x.hlate, x.llate, x.lmin] for i, x in enumerate(ch.itertuples())], [4, 28, 22, 8, 7, 8, 8, 8])
    if o['app_unx']:
        ux = E[E.unx > 0].sort_values(['unx', 'absd'], ascending=False)
        app('ملحق: الغياب دون عذر', ['م', 'الاسم', 'الوظيفة', 'أيام الغياب', 'دون عذر', 'الحالة'],
            [[i + 1, nm(x), x.job, x.absd, x.unx, 'غائب طوال الفترة' if x.allabs else ('غياب متكرر' if x.unx >= REP else 'غياب متفرق')] for i, x in enumerate(ux.itertuples())], [4, 30, 24, 9, 9, 15])
    if o['app_relief']:
        rl = E[E.relief].sort_values(['early', 'eu'], ascending=False)
        app(f'ملحق: الانصراف المبكر المتكرر ({REP}+)', ['م', 'الاسم', 'الوظيفة', 'مرات الانصراف المبكر', 'دون إذن', 'دوام كامل'],
            [[i + 1, nm(x), x.job, x.early, x.eu, x.full] for i, x in enumerate(rl.itertuples())], [4, 30, 26, 12, 9, 9])
    F_ = filters(cfg)
    for key in o.get('extra_lists') or []:
        if key in F_:
            lab, fn = F_[key]; sub = E[fn(E)]
            app(f'ملحق: {lab}', ['م', 'الاسم', 'الوظيفة', 'الحضور', 'الغياب (دون عذر)', 'التأخير (دون إذن)', 'المبكر (دون إذن)', 'دوام كامل'],
                [[i + 1, nm(x), x.job, f'{x.pres}/{x.days}', f'{x.absd} ({x.unx})', f'{x.late} ({x.lu})', f'{x.early} ({x.eu})', x.full] for i, x in enumerate(sub.itertuples())], [4, 28, 22, 8, 10, 10, 10, 8])
    if o['app_roster']:
        first[0] = True
        app('ملحق: سجل جميع الموظفين', ['م', 'الاسم', 'الوظيفة', 'الحضور', 'الغياب (دون عذر)', 'التأخير (دون إذن)', 'المبكر (دون إذن)', 'دوام كامل', 'المسار'],
            [[i + 1, nm(x), x.job, f'{x.pres}/{x.days}', f'{x.absd} ({x.unx})', f'{x.late} ({x.lu})', f'{x.early} ({x.eu})', x.full, x.tr] for i, x in enumerate(E.sort_values('name').itertuples())],
            [4, 26, 20, 7, 9, 9, 9, 7, 8])
    if o['signatures']: st += [Spacer(1, 16), _sign(cfg, W)]
    st += [Spacer(1, 8), _method(S)]
    doc.build(st, onFirstPage=on_page, onLaterPages=on_page)
    return path


def save_person_report(r, S, cfg, name, path):
    E = S['E']; x = E[E.name == name].iloc[0]; d = r[r.name == name].sort_values('date')
    doc, on_page, W = _doc(path, f'{cfg.school_name} • تقرير موظف {S["period_short"]}')
    tm = lambda m: f'{int(m) // 60:02d}:{int(m) % 60:02d}' if m else '—'
    wk = d.groupby('week').agg(days=('date', 'size'), pres=('pres', 'sum'), absd=('abs', 'sum'), late=('late', 'sum'), early=('early', 'sum'), full=('full', 'sum'), hrs=('hours', 'sum')).reset_index()
    rows = [[row.date.strftime('%d/%m/%Y'), row.day, tm(row.t1m), tm(row.t2m), tm(row.outm), row.status,
             ('تأخير' + (' دون إذن' if row.lu else ' بإذن')) if row.late else '', ('مبكر' + (' دون إذن' if row.eu else ' بإذن')) if row.early else '',
             'نعم' if row.full else '', ' '.join(s for s in [row.abs_type, row.perm] if s)] for row in d.itertuples()]
    st = [Cover(cfg.org_line, f'تقرير موظف: {name}', f'{x.job} • الرقم المدني {x.cid} • الفترة {S["period"]}'), Spacer(1, 8),
          Tiles([('أيام الحضور', f'{x.pres} من {x.days}', f'نسبة الحضور {P(x.att)}'), ('الغياب', x.absd, f'منه دون عذر {x.unx}', BLUE),
                 ('التأخير الصباحي', x.late, f'دون إذن {x.lu} • {x.lmin} دقيقة', ORANGE), ('الانصراف المبكر', x.early, f'دون إذن {x.eu}', AQUA),
                 ('دوام كامل', x.full, f'من {x.days} يوماً', GREEN), ('بصمة ناقصة', x.inc, ''), ('متوسط ساعات العمل', f'{x.hours:.2f}', ''),
                 ('التصنيف', x.status, f'المسار: {x.tr}')], value_size=13),
          Spacer(1, 6), Heading('الملخص الأسبوعي', 12), Spacer(1, 4),
          table(['الأسبوع', 'أيام العمل', 'الحضور', 'الغياب', 'التأخير', 'المبكر', 'دوام كامل', 'الساعات'],
                [[f'الأسبوع {w.week} ({S["wr"][int(w.week)][0]}–{S["wr"][int(w.week)][1]})', w.days, int(w.pres), int(w.absd), int(w.late), int(w.early), int(w.full), f'{w.hrs:.1f}'] for w in wk.itertuples()],
                [22, 9, 9, 9, 9, 9, 9, 9], W, name_cols=(0,)),
          Spacer(1, 6), Heading('السجل اليومي', 12), Spacer(1, 4),
          table(['التاريخ', 'اليوم', 'الحضور', 'T2', 'الانصراف', 'الحالة', 'التأخير', 'المبكر', 'دوام كامل', 'ملاحظة النظام'], rows, [11, 8, 7, 7, 8, 11, 11, 11, 7, 22], W, size=7, name_cols=(9,))]
    if x.abs_reasons: st.append(RTLText(f'أسباب الغياب: {x.abs_reasons}', size=8, color=MUTED))
    st += [Spacer(1, 14), _sign(cfg, W), Spacer(1, 6), _method(S)]
    doc.build(st, onFirstPage=on_page, onLaterPages=on_page)
    return path


def save_people_list(E_sub, title, S, cfg, path, show_names=True):
    nm = (lambda x: x.name) if show_names else (lambda x: f'موظف {x.cid[-4:]}')
    doc, on_page, W = _doc(path, f'{cfg.school_name} • {title} {S["period_short"]}', land=True)
    rows = [[i + 1, nm(x), x.job, f'{x.pres}/{x.days}', f'{x.absd} ({x.unx})', f'{x.late} ({x.lu})', x.lmin, f'{x.early} ({x.eu})', x.inc, x.full, x.tr, x.status]
            for i, x in enumerate(E_sub.itertuples())]
    st = [Cover(cfg.org_line, title, f'{cfg.school_name} • الفترة {S["period"]} • {len(rows)} موظفاً'), Spacer(1, 8),
          table(['م', 'الاسم', 'الوظيفة', 'الحضور', 'الغياب (دون عذر)', 'التأخير (دون إذن)', 'دقائق التأخير', 'المبكر (دون إذن)', 'بصمة ناقصة', 'دوام كامل', 'المسار', 'التصنيف'], rows,
                [4, 24, 18, 7, 9, 9, 8, 9, 7, 7, 7, 15], W, size=7.5),
          RTLText('الأرقام بين القوسين: غير المبرر.', size=7.5, color=MUTED), _method(S)]
    doc.build(st, onFirstPage=on_page, onLaterPages=on_page)
    return path


def save_infographic(S, cfg, png_path=None, pdf_path=None):
    """One-page infographic as PDF (no PNG on mobile)."""
    A = S['ALL']; WK = S['WK']; LW = S['LW']; PW = S['PW']; wr = S['wr']; weeks = S['weeks']; D = S['DAY']; DAYS = S['DAYS']; REP = S['rep']
    doc, on_page, W = _doc(pdf_path, f'{cfg.school_name} • الحضور والانصراف بالأرقام')
    other = A['emp'] - A['clean'] - A['allabs']
    st = [Cover(cfg.org_line, f'الحضور والانصراف بالأرقام: {cfg.school_name}', f"{S['period']} • {A['days']} يوم عمل • {A['emp']} موظفاً"), Spacer(1, 6),
          Tiles([('يحضرون في اليوم (متوسط)', f"{A['avg_pres']:.0f}", f"نسبة الحضور {P(A['att'])}"), ('منضبطون تماماً', A['clean'], 'بلا تأخير ولا غياب/انصراف دون إذن', GREEN),
                 ('متأخرون باستمرار', S['n_chronic'], f'{REP} مرات فأكثر', ORANGE), ('غائبون طوال الفترة', A['allabs'], f"{S['n_discon']} منقطعون • {S['n_onleave']} إجازة", RED),
                 ('تأخروا مرة على الأقل', A['late'], f"منهم {A['lu']} دون إذن", ORANGE), ('غابوا يوماً على الأقل', A['absent'], f"منهم {A['unx']} دون عذر", BLUE),
                 ('انصرفوا مبكراً', A['early'], f"منهم {A['eu']} دون إذن", AQUA), ('إجمالي الموظفين', A['emp'], 'كل نقطة أدناه = موظف')], h=54, value_size=19),
          Spacer(1, 4), DotGrid(A['emp'], [(A['clean'], AQUA), (other, BLUE), (A['allabs'], ORANGE)]),
          RTLText(f'الأخضر: منضبط تماماً ({A["clean"]}) • الأزرق: مخالفة واحدة على الأقل ({other}) • البرتقالي: غائب طوال الفترة ({A["allabs"]})', size=8, color=MUTED, align='center'),
          BarChart([f'أ{w}' for w in weeks], [('غابوا', [WK[w]['absent'] for w in weeks], BLUE), ('تأخروا', [WK[w]['late'] for w in weeks], ORANGE), ('انصرفوا مبكراً', [WK[w]['early'] for w in weeks], AQUA)], 'عدد الموظفين أسبوعياً', h=165)]
    if DAYS:
        st.append(BarChart(DAYS, [('غائبون', [round(D[d]['absent']) for d in DAYS], BLUE), ('متأخرون', [round(D[d]['late']) for d in DAYS], ORANGE), ('منصرفون مبكراً', [round(D[d]['early']) for d in DAYS], AQUA)], 'متوسط الموظفين يومياً حسب اليوم', h=150))
    if PW:
        a, b = WK[PW], WK[LW]
        st.append(RTLText(f"الأسبوع {LW} مقارنة بالأسبوع {PW}: الغائبون {a['absent']}←{b['absent']} • المتأخرون {a['late']}←{b['late']} (دون إذن {a['lu']}←{b['lu']}) • المنصرفون مبكراً {a['early']}←{b['early']} (دون إذن {a['eu']}←{b['eu']})", size=8.5, bg=HEAD_BG, pad=5))
    doc.build(st, onFirstPage=on_page, onLaterPages=on_page)
    return None, pdf_path
