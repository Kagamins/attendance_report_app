"""Printable reports: the full people-based report, a single employee report, and a people list."""
import html
import pandas as pd

from .charts import C, grouped_bars, hbars, line, stacked
from .render import FONT_STACK, html_to_pdf
from .settings import Settings
from .stats import filters, PERSON_COLUMNS

esc = lambda s: html.escape(str(s))
P = lambda x: f'{x * 100:.1f}%'

DEFAULT_OPTIONS = dict(findings=True, weekly=True, justified=True, latest=True, distribution=True, weekday=True,
                       recommendations=True, app_chronic=True, app_unx=True, app_relief=True, app_roster=True,
                       show_names=True, signatures=True, extra_lists=[])
OPTION_LABELS = [('findings', 'أبرز النتائج'), ('weekly', 'المسار الأسبوعي'), ('justified', 'المبرر وغير المبرر'),
                 ('latest', 'الأسبوع الأحدث'), ('distribution', 'توزيع الموظفين والأسباب'), ('weekday', 'أيام الأسبوع'),
                 ('recommendations', 'التوصيات'), ('app_chronic', 'ملحق: المتأخرون باستمرار'),
                 ('app_unx', 'ملحق: الغياب دون عذر'), ('app_relief', 'ملحق: الانصراف المبكر المتكرر'),
                 ('app_roster', 'ملحق: سجل جميع الموظفين'), ('show_names', 'إظهار أسماء الموظفين'),
                 ('signatures', 'خانات التوقيع')]

CSS = '''@page{size:A4;margin:13mm 12mm 15mm 12mm}
body{font-family:%s;color:#1d2433;font-size:10.5px;line-height:1.6;margin:0;direction:rtl;background:#fff}
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.cover{background:#1F3864;color:#fff;border-radius:10px;padding:18px 22px;margin-bottom:12px}
.cover h1{font-size:21px;margin:4px 0}.cover .s{font-size:11px;opacity:.9}
.pill{display:inline-block;background:#ffffff22;border-radius:12px;padding:2px 10px;margin-top:6px;font-size:10.5px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:10px 0}
.tile{border:1px solid #d8dbe0;border-radius:8px;padding:8px;text-align:center;background:#fcfcfb}
.tl{font-size:9.5px;color:#52514e}.tv{font-size:24px;font-weight:bold;color:#1F3864;line-height:1.25}.ts{font-size:9px;color:#6b6a66}
h2{font-size:15px;color:#1F3864;border-right:5px solid #2a78d6;padding-right:9px;margin:16px 0 8px;page-break-after:avoid}
.box{border:1px solid #e6e5e0;border-radius:8px;padding:6px 8px;margin:6px 0;page-break-inside:avoid;background:#fff}
table{width:100%%;border-collapse:collapse;font-size:9.4px;margin:5px 0 9px}
thead{display:table-header-group} tr{page-break-inside:avoid}
th{background:#1F3864;color:#fff;padding:4px 3px;border:1px solid #9aa3ad}
td{border:1px solid #d8dbe0;padding:3px;text-align:center}
tbody tr:nth-child(even) td{background:#f5f6f8}
td.n{text-align:right}
table.sm{font-size:8.4px}
.good{color:#1b7f3b;font-weight:bold}.bad{color:#b3261e;font-weight:bold}.eq{color:#666}
ul.f li{margin:3px 0}
.note{font-size:9px;color:#52514e}
.pb{page-break-before:always}
.sign{display:flex;justify-content:space-between;margin-top:36px}.sign div{width:30%%;text-align:center;border-top:1px solid #555;padding-top:5px}''' % FONT_STACK


def tbl(head, rows, cls='', name_col=1):
    out = [f'<table class="{cls}"><thead><tr>' + ''.join(f'<th>{esc(h)}</th>' for h in head) + '</tr></thead><tbody>']
    for row in rows:
        cells = []
        for i, c in enumerate(row):
            k = ' class="n"' if i == name_col else ''
            cells.append(f'<td{k}>{c}</td>' if str(c).startswith('<') else f'<td{k}>{esc(c)}</td>')
        out.append('<tr>' + ''.join(cells) + '</tr>')
    return ''.join(out) + '</tbody></table>'


def delta(a, b, good):
    d = round(b - a, 1)
    if d == 0: return '<span class="eq">═ 0</span>'
    up = d > 0; cls = 'good' if (up and good > 0) or (not up and good < 0) else 'bad'
    return f'<span class="{cls}">{"▲" if up else "▼"} {d:+g}</span>'


def _head(cfg, title, sub):
    return (f'<div class="cover"><div class="s">{esc(cfg.org_line)}</div><h1>{esc(title)}</h1><div class="s">{sub}</div>'
            '<span class="pill">جميع الأعداد بعدد الموظفين (أفراد)، لا بعدد البصمات أو الحالات</span></div>')


def _sign(cfg):
    return '<div class="sign">' + ''.join(f'<div>{esc(s)}</div>' for s in cfg.signatures) + '</div>'


def _method(S):
    ru = S['rules']
    return (f'<p class="note">المنهجية: التأخير = الحضور {ru["late"]} فأكثر؛ الانصراف المبكر = قبل {ru["early"]}؛ '
            f'الدوام الكامل = {ru["quota"]} دقيقة من max({ru["start"]}، T1)؛ نافذة T2 = T1+{ru["t2"][0]} إلى T1+{ru["t2"][1]} دقيقة؛ '
            'الغياب دون عذر = «غياب» أو «منقطع عن العمل» في النظام؛ «دون إذن» = لا يوجد إذن مسجل يغطي الحالة.</p>')


def _wrap(title, body):
    return f'<html><head><meta charset="utf-8"><title>{esc(title)}</title><style>{CSS}</style></head><body>{body}</body></html>'


def _person_rows(E, show_names):
    nm = (lambda x: x.name) if show_names else (lambda x: f'موظف {x.cid[-4:]}')
    return nm


def findings(S):
    """Key findings as HTML strings (also used, tag-stripped, by the mobile PDF renderer)."""
    A = S['ALL']; WK = S['WK']; LW = S['LW']; PW = S['PW']; wr = S['wr']; REP = S['rep']; D = S['DAY']
    f = [f"<b>{A['late']}</b> موظفاً من أصل {A['emp']} ({P(A['late'] / max(A['emp'], 1))}) تأخروا صباحاً مرة واحدة على الأقل، بإجمالي {A['late_inst']} حالة تأخير؛ <b>{A['lu']}</b> منهم تأخروا دون إذن مسجل، و<b>{A['emp'] - A['late']}</b> لم يتأخروا إطلاقاً.",
         f"<b>{A['absent']}</b> موظفاً غابوا يوماً واحداً على الأقل ({A['abs_days']} يوم غياب)، منهم <b>{A['unx']}</b> سُجل لهم غياب دون عذر؛ والباقون إجازات وأعذار رسمية.",
         f"<b>{A['early']}</b> موظفاً انصرفوا قبل {S['rules']['early']} مرة على الأقل، و<b>{A['eu']}</b> منهم دون إذن مسجل؛ و<b>{S['n_relief']}</b> تكرر انصرافهم المبكر {REP} مرات فأكثر.",
         f"<b>{A['allabs']}</b> موظفين غائبون طوال الفترة: {S['n_discon']} منقطعون و{S['n_onleave']} في إجازة. يحضر يومياً في المتوسط <b>{A['avg_pres']:.0f}</b> موظفاً."]
    if PW:
        a, b = WK[PW], WK[LW]
        f.append(f"الأسبوع {LW} ({wr[LW][0]}–{wr[LW][1]}) مقارنة بالأسبوع {PW}: الغائبون {a['absent']}←{b['absent']}، والمتأخرون {a['late']}←{b['late']} (دون إذن {a['lu']}←{b['lu']})، والمنصرفون مبكراً {a['early']}←{b['early']} (دون إذن {a['eu']}←{b['eu']}).")
    if S['worst_day']:
        w, bd = S['worst_day'], S['best_day']
        f.append(f"يوم <b>{w}</b> الأعلى: في المتوسط {D[w]['absent']:.0f} غائباً و{D[w]['early']:.0f} منصرفاً مبكراً، مقابل {D[bd]['absent']:.0f} و{D[bd]['early']:.0f} يوم {bd}.")
    f.append(f"<b>{A['clean']}</b> موظفاً منضبطون تماماً: لم يتأخروا ولم يغيبوا دون عذر ولم ينصرفوا دون إذن طوال {A['days']} يوم عمل.")
    return f


def recommendations(S):
    A = S['ALL']; REP = S['rep']
    recs = [f"<b>المنقطعون كلياً ({S['n_discon']}):</b> التحقق من وضعهم الوظيفي وتحديث نظام البصمة والمشغول الفعلي.",
            f"<b>الغياب دون عذر ({A['unx']}):</b> متابعة فردية، والبدء بمن تكرر غيابه دون عذر {REP} أيام فأكثر ({S['n_unx_rep']}).",
            f"<b>المتأخرون باستمرار ({S['n_chronic']}):</b> لقاء فردي وتنبيه كتابي لمن لديه تأخير دون إذن ({A['lu']}).",
            f"<b>الانصراف المبكر:</b> {A['early'] - A['eu']} من {A['early']} انصرافهم مغطى بأذونات؛ تُراجع حالات {A['eu']} دون إذن، ويُتأكد من قرارات تخفيف العمل للمتكررين ({S['n_relief']}).",
            f"<b>التعزيز الإيجابي:</b> تكريم {A['clean']} موظفاً منضبطين تماماً طوال الفترة."]
    if S['worst_day']:
        recs.insert(4, f"<b>يوم {S['worst_day']}:</b> الأعلى غياباً وانصرافاً مبكراً؛ يُوصى بضبط الاستئذانات المسبقة وتوزيع المناوبات.")
    return recs


def full_report_html(S, cfg: Settings, options=None):
    o = dict(DEFAULT_OPTIONS); o.update(options or {})
    E = S['E']; A = S['ALL']; WK = S['WK']; LW = S['LW']; PW = S['PW']; wr = S['wr']; weeks = S['weeks']
    REP = S['rep']; D = S['DAY']; DAYS = S['DAYS']; nm = _person_rows(E, o['show_names'])
    cats = [f'أ{w}' for w in weeks]
    parts = []
    tiles = [('إجمالي الموظفين', A['emp'], 'موظفاً في تقرير البصمة'),
             ('يحضرون يومياً في المتوسط', f"{A['avg_pres']:.0f}", f"نسبة الحضور {P(A['att'])}"),
             ('تأخروا مرة على الأقل', A['late'], f"منهم {A['lu']} دون إذن"),
             ('انصرفوا مبكراً مرة على الأقل', A['early'], f"منهم {A['eu']} دون إذن"),
             ('غابوا يوماً على الأقل', A['absent'], f"منهم {A['unx']} دون عذر"),
             ('غائبون طوال الفترة', A['allabs'], f"{S['n_discon']} منقطعون • {S['n_onleave']} في إجازة"),
             ('منضبطون تماماً', A['clean'], 'بلا تأخير ولا غياب أو انصراف دون إذن'),
             ('متأخرون باستمرار', S['n_chronic'], f'{REP} مرات تأخير فأكثر')]
    parts.append(_head(cfg, f'تقرير الحضور والانصراف: {cfg.school_name}',
                       f"الفترة {S['period']} • {A['days']} يوم عمل في {len(weeks)} أسابيع • {A['emp']} موظفاً"))
    parts.append('<div class="tiles">' + ''.join(f'<div class="tile"><div class="tl">{esc(a)}</div><div class="tv">{esc(b)}</div><div class="ts">{esc(c)}</div></div>' for a, b, c in tiles) + '</div>')
    sec = 1
    if o['findings']:
        f = findings(S)
        parts.append(f'<h2>{sec}. أبرز النتائج</h2><ul class="f">' + ''.join(f'<li>{x}</li>' for x in f) + '</ul>'); sec += 1
        if S['has_prev']:
            li = lambda L: ''.join(f'<li>{esc(n) if o["show_names"] else "موظف " + c[-4:]} • {esc(j)}</li>' for c, n, j in L) or '<li>لا أحد</li>'
            parts.append(f'<p class="note">مقارنة بالتقرير السابق: ظهر {len(S["new_people"])} موظفاً جديداً، وغاب {len(S["gone"])} عن هذا التقرير.</p>'
                         f'<div class="note"><b>الجدد:</b><ul>{li(S["new_people"])}</ul><b>غير الموجودين في هذا التقرير:</b><ul>{li(S["gone"])}</ul></div>')
    if o['weekly']:
        att = [WK[w]['att'] * 100 for w in weeks]
        parts.append(f'<h2 class="pb">{sec}. المسار الأسبوعي بعدد الموظفين</h2>'); sec += 1
        parts.append('<div class="box">' + grouped_bars(cats, [('غابوا', [WK[w]['absent'] for w in weeks], C['blue']), ('تأخروا', [WK[w]['late'] for w in weeks], C['orange']), ('انصرفوا مبكراً', [WK[w]['early'] for w in weeks], C['aqua'])], title='عدد الموظفين أسبوعياً') + '</div>')
        if len(weeks) > 1:
            parts.append('<div class="box">' + line(cats, att, title='نسبة الحضور الأسبوعية', ymin=max(0, int(min(att)) - 3), ymax=min(100, int(max(att)) + 3), h=230) + '</div>')
        rows = [[f'الأسبوع {w}', f'{wr[w][0]}–{wr[w][1]}', f"{WK[w]['avg_pres']:.0f}", P(WK[w]['att']), WK[w]['absent'], WK[w]['unx'], WK[w]['late'], WK[w]['lu'], WK[w]['early'], WK[w]['eu'], WK[w]['inc'], WK[w]['fullall']] for w in weeks]
        rows.append(['الإجمالي (أفراد مختلفون)', S['period_short'], f"{A['avg_pres']:.0f}", P(A['att']), A['absent'], A['unx'], A['late'], A['lu'], A['early'], A['eu'], A['inc'], A['fullall']])
        parts.append(tbl(['الأسبوع', 'الفترة', 'متوسط الحاضرين', 'نسبة الحضور', 'غابوا', 'منهم دون عذر', 'تأخروا', 'منهم دون إذن', 'انصرفوا مبكراً', 'منهم دون إذن', 'بصمة ناقصة', 'دوام كامل كل أيامهم'], rows, name_col=-1))
        parts.append('<p class="note">كل خانة = عدد الموظفين المختلفين الذين ينطبق عليهم الوصف مرة واحدة على الأقل. صف الإجمالي يعدّ الشخص مرة واحدة مهما تكرر، لذا لا يساوي مجموع الأسابيع.</p>')
    if o['justified']:
        parts.append(f'<h2 class="pb">{sec}. المبرر وغير المبرر</h2>'); sec += 1
        parts.append('<div class="box">' + stacked(cats, [('تأخروا بإذن فقط', [WK[w]['late'] - WK[w]['lu'] for w in weeks], C['blue']), ('تأخروا دون إذن', [WK[w]['lu'] for w in weeks], C['orange'])], title='المتأخرون أسبوعياً: بإذن مقابل دون إذن (أفراد)') + '</div>')
        parts.append('<div class="box">' + stacked(cats, [('غابوا بعذر فقط', [WK[w]['absent'] - WK[w]['unx'] for w in weeks], C['blue']), ('غابوا دون عذر', [WK[w]['unx'] for w in weeks], C['orange'])], title='الغائبون أسبوعياً: بعذر مقابل دون عذر (أفراد)') + '</div>')
    if o['latest']:
        parts.append(f'<h2 class="pb">{sec}. الأسبوع الأحدث: الأسبوع {LW} ({wr[LW][0]}–{wr[LW][1]})</h2>'); sec += 1
        b = WK[LW]
        if PW:
            a = WK[PW]
            cmp = [('غابوا', a['absent'], b['absent'], -1), ('منهم دون عذر', a['unx'], b['unx'], -1), ('غائبون طوال الأسبوع', a['allabs'], b['allabs'], -1),
                   ('تأخروا', a['late'], b['late'], -1), ('منهم دون إذن', a['lu'], b['lu'], -1), ('انصرفوا مبكراً', a['early'], b['early'], -1),
                   ('منهم دون إذن', a['eu'], b['eu'], -1), ('بصمة ناقصة', a['inc'], b['inc'], -1), ('دوام كامل كل أيامهم', a['fullall'], b['fullall'], 1),
                   ('متوسط الحاضرين يومياً', round(a['avg_pres'], 1), round(b['avg_pres'], 1), 1)]
            parts.append(tbl(['المؤشر (عدد الموظفين)', f'الأسبوع {PW}', f'الأسبوع {LW}', 'التغير'], [[x, y, z, delta(y, z, g)] for x, y, z, g in cmp], name_col=0))
        ld = S['LWD']
        parts.append('<div class="box">' + grouped_bars([f'{d[1]} {d[0]}' for d in ld], [('غائبون', [d[2]['absent'] for d in ld], C['blue']), ('متأخرون', [d[2]['late'] for d in ld], C['orange']), ('منصرفون مبكراً', [d[2]['early'] for d in ld], C['aqua'])], title=f'الأسبوع {LW} يوماً بيوم (عدد الموظفين)') + '</div>')
        parts.append(tbl(['اليوم', 'الحاضرون', 'الغائبون', 'منهم دون عذر', 'المتأخرون', 'منهم دون إذن', 'المنصرفون مبكراً', 'منهم دون إذن', 'بصمة ناقصة'],
                         [[f'{d[1]} {d[0]}', d[2]['emp'] - d[2]['absent'], d[2]['absent'], d[2]['unx'], d[2]['late'], d[2]['lu'], d[2]['early'], d[2]['eu'], d[2]['inc']] for d in ld], name_col=-1))
        if PW:
            TR = S['TR']
            parts.append('<div class="box">' + hbars([('متحسن ↑', TR['متحسن']), ('مستقر ═', TR['مستقر']), ('متراجع ↓', TR['متراجع']), ('غائب طوال الأسبوع', TR['منقطع'])], title=f'مسار كل موظف في الأسبوع {LW} مقارنة بمعدله السابق', unit=' موظف', h=190) + '</div>')
    if o['distribution']:
        parts.append(f'<h2 class="pb">{sec}. توزيع الموظفين والأسباب</h2>'); sec += 1
        parts.append('<div class="box">' + hbars(S['LATE_B'], title='الموظفون حسب عدد مرات التأخير', color=C['orange'], unit=' موظف') + '</div>')
        parts.append('<div class="box">' + hbars(S['ABS_B'], title='الموظفون حسب عدد أيام الغياب', color=C['blue'], unit=' موظف') + '</div>')
        if S['ABS_P']: parts.append('<div class="box">' + hbars(S['ABS_P'], title='أسباب الغياب: عدد الموظفين لكل سبب', unit=' موظف') + '</div>')
        if S['PERM_P']: parts.append('<div class="box">' + hbars(S['PERM_P'], title='الأذونات المسجلة: عدد الموظفين المستفيدين', color=C['aqua'], unit=' موظف') + '</div>')
    if o['weekday'] and DAYS:
        parts.append(f'<h2 class="pb">{sec}. الأنماط حسب أيام الأسبوع</h2>'); sec += 1
        parts.append('<div class="box">' + grouped_bars(DAYS, [('غائبون', [round(D[d]['absent'], 1) for d in DAYS], C['blue']), ('متأخرون', [round(D[d]['late'], 1) for d in DAYS], C['orange']), ('منصرفون مبكراً', [round(D[d]['early'], 1) for d in DAYS], C['aqua'])], title='متوسط عدد الموظفين في اليوم حسب أيام الأسبوع') + '</div>')
        parts.append(tbl(['اليوم', 'متوسط الحاضرين', 'متوسط الغائبين', 'منهم دون عذر', 'متوسط المتأخرين', 'متوسط المنصرفين مبكراً', 'تأخروا في هذا اليوم (أفراد)', 'انصرفوا مبكراً في هذا اليوم (أفراد)'],
                         [[d, f"{D[d]['pres']:.0f}", f"{D[d]['absent']:.1f}", f"{D[d]['unx']:.1f}", f"{D[d]['late']:.1f}", f"{D[d]['early']:.1f}", S['DAYP'][d]['late'], S['DAYP'][d]['early']] for d in DAYS], name_col=-1))
    if o['recommendations']:
        recs = recommendations(S)
        parts.append(f'<h2>{sec}. التوصيات</h2><ol>' + ''.join(f'<li>{x}</li>' for x in recs) + '</ol>'); sec += 1
    # ---- appendices (people)
    first = True
    def app(title, head, rows):
        nonlocal first
        parts.append(f'<h2 class="{"pb" if first else ""}">{esc(title)} ({len(rows)} موظفاً)</h2>' + (tbl(head, rows, 'sm') if rows else '<p class="note">لا أحد.</p>'))
        first = False
    if o['app_chronic']:
        ch = E[E.chronic].sort_values(['late', 'lu'], ascending=False)
        app(f'ملحق: المتأخرون باستمرار ({REP} مرات فأكثر)', ['م', 'الاسم', 'الوظيفة', 'مرات التأخير', 'دون إذن', f'قبل الأسبوع {LW}', f'الأسبوع {LW}', 'إجمالي الدقائق'],
            [[i + 1, nm(x), x.job, x.late, x.lu, x.hlate, x.llate, x.lmin] for i, x in enumerate(ch.itertuples())])
    if o['app_unx']:
        ux = E[E.unx > 0].sort_values(['unx', 'absd'], ascending=False)
        app('ملحق: الموظفون الذين غابوا دون عذر', ['م', 'الاسم', 'الوظيفة', 'أيام الغياب', 'منها دون عذر', 'الحالة'],
            [[i + 1, nm(x), x.job, x.absd, x.unx, 'غائب طوال الفترة' if x.allabs else ('غياب متكرر' if x.unx >= REP else 'غياب متفرق')] for i, x in enumerate(ux.itertuples())])
    if o['app_relief']:
        rl = E[E.relief].sort_values(['early', 'eu'], ascending=False)
        app(f'ملحق: الانصراف المبكر المتكرر ({REP} مرات فأكثر)', ['م', 'الاسم', 'الوظيفة', 'مرات الانصراف المبكر', 'دون إذن', 'أيام الدوام الكامل'],
            [[i + 1, nm(x), x.job, x.early, x.eu, x.full] for i, x in enumerate(rl.itertuples())])
    F = filters(cfg)
    for key in o.get('extra_lists') or []:
        if key in F:
            lab, fn = F[key]; sub = E[fn(E)]
            app(f'ملحق: {lab}', ['م', 'الاسم', 'الوظيفة', 'الحضور', 'الغياب (دون عذر)', 'التأخير (دون إذن)', 'الانصراف المبكر (دون إذن)', 'دوام كامل'],
                [[i + 1, nm(x), x.job, f'{x.pres}/{x.days}', f'{x.absd} ({x.unx})', f'{x.late} ({x.lu})', f'{x.early} ({x.eu})', x.full] for i, x in enumerate(sub.itertuples())])
    if o['app_roster']:
        first = True
        app('ملحق: سجل جميع الموظفين', ['م', 'الاسم', 'الوظيفة', 'الحضور', 'الغياب (دون عذر)', 'التأخير (دون إذن)', 'الانصراف المبكر (دون إذن)', 'دوام كامل', 'المسار'],
            [[i + 1, nm(x), x.job, f'{x.pres}/{x.days}', f'{x.absd} ({x.unx})', f'{x.late} ({x.lu})', f'{x.early} ({x.eu})', x.full, x.tr] for i, x in enumerate(E.sort_values('name').itertuples())])
        parts.append('<p class="note">الأرقام بين القوسين: غير المبرر. المسار: الأسبوع الأحدث مقارنة بالمعدل السابق.</p>')
    if o['signatures']: parts.append(_sign(cfg))
    parts.append(_method(S))
    return _wrap('تقرير الحضور والانصراف', ''.join(parts))


def person_report_html(r, S, cfg: Settings, name):
    E = S['E']; x = E[E.name == name].iloc[0]; d = r[r.name == name].sort_values('date')
    tiles = [('أيام الحضور', f'{x.pres} من {x.days}', f'نسبة الحضور {P(x.att)}'), ('الغياب', x.absd, f'منه دون عذر {x.unx}'),
             ('التأخير الصباحي', x.late, f'منه دون إذن {x.lu} • {x.lmin} دقيقة'), ('الانصراف المبكر', x.early, f'منه دون إذن {x.eu}'),
             ('دوام كامل', x.full, f'من {x.days} يوماً'), ('بصمة ناقصة', x.inc, ''), ('متوسط ساعات العمل', f'{x.hours:.2f}', ''),
             ('التصنيف', x.status, f'المسار: {x.tr}')]
    wk = d.groupby('week').agg(days=('date', 'size'), pres=('pres', 'sum'), absd=('abs', 'sum'), late=('late', 'sum'),
                               early=('early', 'sum'), full=('full', 'sum'), hrs=('hours', 'sum')).reset_index()
    tm = lambda m: f'{int(m) // 60:02d}:{int(m) % 60:02d}' if m else '—'
    rows = [[row.date.strftime('%d/%m/%Y'), row.day, tm(row.t1m), tm(row.t2m), tm(row.outm), row.status,
             ('تأخير' + (' (دون إذن)' if row.lu else ' (بإذن)')) if row.late else '', ('مبكر' + (' (دون إذن)' if row.eu else ' (بإذن)')) if row.early else '',
             'نعم' if row.full else '', f'{row.hours:.2f}' if row.hours else '', ' '.join(x for x in [row.abs_type, row.perm] if x)] for row in d.itertuples()]
    body = (_head(cfg, f'تقرير موظف: {name}', f"{esc(x.job)} • الرقم المدني {x.cid} • الفترة {S['period']}") +
            '<div class="tiles">' + ''.join(f'<div class="tile"><div class="tl">{esc(a)}</div><div class="tv" style="font-size:18px">{esc(b)}</div><div class="ts">{esc(c)}</div></div>' for a, b, c in tiles) + '</div>' +
            '<h2>الملخص الأسبوعي</h2>' + tbl(['الأسبوع', 'أيام العمل', 'الحضور', 'الغياب', 'التأخير', 'الانصراف المبكر', 'دوام كامل', 'ساعات العمل'],
                                            [[f'الأسبوع {w.week} ({S["wr"][int(w.week)][0]}–{S["wr"][int(w.week)][1]})', w.days, int(w.pres), int(w.absd), int(w.late), int(w.early), int(w.full), f'{w.hrs:.1f}'] for w in wk.itertuples()], name_col=-1) +
            '<h2>السجل اليومي</h2>' + tbl(['التاريخ', 'اليوم', 'الحضور', 'التواجد T2', 'الانصراف', 'الحالة', 'التأخير', 'الانصراف المبكر', 'دوام كامل', 'الساعات', 'ملاحظة النظام'], rows, 'sm', name_col=10) +
            (f'<p class="note">أسباب الغياب: {esc(x.abs_reasons)}</p>' if x.abs_reasons else '') + _sign(cfg) + _method(S))
    return _wrap(f'تقرير موظف {name}', body)


def people_list_html(E_sub, title, S, cfg: Settings, show_names=True):
    nm = _person_rows(E_sub, show_names)
    rows = [[i + 1, nm(x), x.job, f'{x.pres}/{x.days}', f'{x.absd} ({x.unx})', f'{x.late} ({x.lu})', x.lmin, f'{x.early} ({x.eu})', x.inc, x.full, x.tr, x.status]
            for i, x in enumerate(E_sub.itertuples())]
    body = (_head(cfg, title, f"{cfg.school_name} • الفترة {S['period']} • {len(rows)} موظفاً") +
            tbl(['م', 'الاسم', 'الوظيفة', 'الحضور', 'الغياب (دون عذر)', 'التأخير (دون إذن)', 'دقائق التأخير', 'الانصراف المبكر (دون إذن)', 'بصمة ناقصة', 'دوام كامل', 'المسار', 'التصنيف'], rows, 'sm') +
            '<p class="note">الأرقام بين القوسين: غير المبرر.</p>' + _method(S))
    return _wrap(title, body)


def footer(cfg, S, what='تقرير الحضور والانصراف'):
    return f"{esc(cfg.school_name)} • {what} {S['period_short']}"


def save_full_report(S, cfg, path, options=None):
    return html_to_pdf(full_report_html(S, cfg, options), path, footer(cfg, S))


def save_person_report(r, S, cfg, name, path):
    return html_to_pdf(person_report_html(r, S, cfg, name), path, footer(cfg, S, 'تقرير موظف'), landscape=False)


def save_people_list(E_sub, title, S, cfg, path, show_names=True):
    return html_to_pdf(people_list_html(E_sub, title, S, cfg, show_names), path, footer(cfg, S, title), landscape=True)
