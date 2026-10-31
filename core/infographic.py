"""One-page people-based infographic (PNG + PDF)."""
import html, math

from .charts import C, grouped_bars, svg
from .render import FONT_STACK, html_to_image_and_pdf
from .settings import Settings

esc = lambda s: html.escape(str(s))
P = lambda x: f'{x * 100:.1f}%'


def _people_grid(n_total, groups):
    cols = 27 if n_total > 120 else 20; s = 14; seq = []
    for c, col in groups: seq += [col] * max(int(c), 0)
    seq += ['#d8dbe0'] * max(n_total - len(seq), 0)
    rows = -(-n_total // cols); w = cols * s + 4; h = rows * s + 4; out = ''
    for k, col in enumerate(seq[:n_total]):
        r, cc = divmod(k, cols); x = w - 2 - (cc + 1) * s + s / 2; y = 2 + r * s + s / 2
        out += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.2" fill="{col}"/>'
    return svg(w, h, out, 'كل نقطة موظف')


def _ring(v, tot, col, lab):
    f = v / tot if tot else 0; R = 46; c = 2 * math.pi * R
    return (f'<div class="ring"><svg viewBox="0 0 120 120" width="118"><circle cx="60" cy="60" r="{R}" fill="none" stroke="#e6e5e0" stroke-width="13"/>'
            f'<circle cx="60" cy="60" r="{R}" fill="none" stroke="{col}" stroke-width="13" stroke-dasharray="{c * f:.1f} {c:.1f}" stroke-linecap="round" transform="rotate(-90 60 60)"/>'
            f'<text x="60" y="58" text-anchor="middle" font-size="25" font-weight="bold" fill="#1F3864" direction="ltr">{v}</text>'
            f'<text x="60" y="78" text-anchor="middle" font-size="11" fill="#52514e" direction="ltr">من {tot}</text></svg><div class="rl">{lab}</div></div>')


def infographic_html(S, cfg: Settings):
    A = S['ALL']; WK = S['WK']; LW = S['LW']; PW = S['PW']; wr = S['wr']; weeks = S['weeks']; D = S['DAY']; DAYS = S['DAYS']; REP = S['rep']
    cats = [f'أ{w}' for w in weeks]
    other = A['emp'] - A['clean'] - A['allabs']
    grid = _people_grid(A['emp'], [(A['clean'], C['aqua']), (other, C['blue']), (A['allabs'], C['orange'])])
    ch_week = grouped_bars(cats, [('غابوا', [WK[w]['absent'] for w in weeks], C['blue']), ('تأخروا', [WK[w]['late'] for w in weeks], C['orange']), ('انصرفوا مبكراً', [WK[w]['early'] for w in weeks], C['aqua'])], w=540, h=300, title='عدد الموظفين أسبوعياً')
    ch_day = grouped_bars(DAYS, [('غائبون', [round(D[d]['absent']) for d in DAYS], C['blue']), ('متأخرون', [round(D[d]['late']) for d in DAYS], C['orange']), ('منصرفون مبكراً', [round(D[d]['early']) for d in DAYS], C['aqua'])], w=540, h=270, title='متوسط الموظفين يومياً حسب اليوم') if DAYS else ''

    def chg(lab, a, b, good=-1):
        d = b - a; cls = 'g' if d * good > 0 else ('b' if d != 0 else 'n'); ar = '▲' if d > 0 else ('▼' if d < 0 else '═')
        return f'<div class="cg"><div class="cl">{lab}</div><div class="cv">{a} → <b>{b}</b></div><div class="{cls}">{ar} {abs(d)}</div></div>'
    if PW:
        a, b = WK[PW], WK[LW]
        cmp = (f'<h3>الأسبوع {LW} ({wr[LW][0]}–{wr[LW][1]}) مقارنة بالأسبوع {PW} (عدد الموظفين)</h3>' +
               chg('غابوا', a['absent'], b['absent']) + chg('غابوا دون عذر', a['unx'], b['unx']) + chg('تأخروا', a['late'], b['late']) +
               chg('تأخروا دون إذن', a['lu'], b['lu']) + chg('انصرفوا مبكراً', a['early'], b['early']) + chg('انصرفوا دون إذن', a['eu'], b['eu']) +
               chg('بصمة ناقصة', a['inc'], b['inc']) + '<div class="ft">الأخضر = تحسن • الأحمر = تراجع</div>')
    else:
        cmp = '<h3>أسبوع واحد فقط في الفترة</h3><p>لا توجد مقارنة أسبوعية.</p>'
    many = sum(v for lab, v in S['LATE_B'][3:])
    bullets = [f"<b>{A['emp'] - A['late']}</b> موظفاً لم يتأخروا أبداً، و<b>{many}</b> تأخروا {REP} مرات فأكثر.",
               f"من <b>{A['absent']}</b> غابوا، <b>{A['absent'] - A['unx']}</b> غيابهم بعذر أو إجازة مسجلة.",
               f"من <b>{A['early']}</b> انصرفوا مبكراً، <b>{A['early'] - A['eu']}</b> لديهم إذن مسجل."]
    if S['worst_day']: bullets.append(f"<b>{S['worst_day']}</b> أعلى أيام الأسبوع غياباً وانصرافاً مبكراً.")
    if PW: bullets.append(f"مسار الأسبوع {LW}: <b>{S['TR']['متحسن']}</b> متحسن • <b>{S['TR']['مستقر']}</b> مستقر • <b>{S['TR']['متراجع']}</b> متراجع.")
    ru = S['rules']
    css = f'''*{{-webkit-print-color-adjust:exact;print-color-adjust:exact;box-sizing:border-box}}
body{{margin:0;font-family:{FONT_STACK};direction:rtl;background:#f3f4f6;color:#1d2433;width:1123px}}
.wrap{{padding:26px 30px}}
.hd{{background:#1F3864;color:#fff;border-radius:14px;padding:22px 28px;display:flex;justify-content:space-between;align-items:center}}
.hd h1{{margin:4px 0;font-size:30px}}.hd .s{{font-size:14px;opacity:.88}}
.big{{text-align:center}}.big b{{font-size:58px;display:block;line-height:1}}.big span{{font-size:13px}}
.note{{background:#fff;border:2px dashed #2a78d6;border-radius:10px;padding:8px 14px;margin:14px 0;font-size:15px;text-align:center;color:#1F3864}}
.row{{display:grid;gap:14px;margin-bottom:14px}}.r4{{grid-template-columns:repeat(4,1fr)}}.r2{{grid-template-columns:1fr 1fr}}.r3{{grid-template-columns:repeat(3,1fr)}}
.card{{background:#fff;border-radius:12px;padding:14px;box-shadow:0 1px 3px #0001}}
.card h3{{margin:0 0 8px;font-size:17px;color:#1F3864}}
.k{{text-align:center}}.k .v{{font-size:46px;font-weight:bold;color:#1F3864;line-height:1.1}}.k .l{{font-size:15px;margin-top:2px}}.k .sub{{font-size:13px;color:#52514e;margin-top:6px}}
.ring{{text-align:center}}.rl{{font-size:13.5px;margin-top:4px;line-height:1.4}}
.lg span{{display:inline-block;margin-left:14px;font-size:13px}}.lg i{{display:inline-block;width:12px;height:12px;border-radius:50%;margin-left:5px;vertical-align:-1px}}
.cg{{display:grid;grid-template-columns:1.6fr 1fr .6fr;padding:6px 4px;border-bottom:1px solid #eee;font-size:14px;align-items:center}}
.cv{{direction:ltr;text-align:center}}.g{{color:#1b7f3b;font-weight:bold}}.b{{color:#b3261e;font-weight:bold}}.n{{color:#777}}
.ft{{font-size:12px;color:#52514e;text-align:center;margin-top:6px}}
ul{{margin:4px 0;padding-right:20px;font-size:14.5px;line-height:1.75}}'''
    body = f'''<div class="wrap">
<div class="hd"><div><div class="s">{esc(cfg.school_name)}</div><h1>الحضور والانصراف بالأرقام</h1><div class="s">{S['period']} • {A['days']} يوم عمل • {len(weeks)} أسابيع</div></div>
<div class="big"><b>{A['emp']}</b><span>موظفاً</span></div></div>
<div class="note">كل رقم هنا = عدد <b>أشخاص</b> مختلفين، وليس عدد البصمات أو الحالات</div>
<div class="row r4">
<div class="card k"><div class="v">{A['avg_pres']:.0f}</div><div class="l">يحضرون في اليوم الواحد (متوسط)</div><div class="sub">نسبة الحضور {P(A['att'])}</div></div>
<div class="card k"><div class="v" style="color:#178f65">{A['clean']}</div><div class="l">منضبطون تماماً</div><div class="sub">بلا تأخير ولا غياب أو انصراف دون إذن</div></div>
<div class="card k"><div class="v" style="color:#c9521f">{S['n_chronic']}</div><div class="l">متأخرون باستمرار</div><div class="sub">{REP} مرات تأخير فأكثر</div></div>
<div class="card k"><div class="v" style="color:#b3261e">{A['allabs']}</div><div class="l">غائبون طوال الفترة</div><div class="sub">{S['n_discon']} منقطعون • {S['n_onleave']} في إجازة</div></div></div>
<div class="row r2">
<div class="card"><h3>كم موظفاً… مرة واحدة على الأقل؟</h3><div class="row r3" style="margin:0">
{_ring(A['late'], A['emp'], C['orange'], f"تأخروا<br><b>{A['lu']}</b> منهم دون إذن")}
{_ring(A['absent'], A['emp'], C['blue'], f"غابوا<br><b>{A['unx']}</b> منهم دون عذر")}
{_ring(A['early'], A['emp'], C['aqua'], f"انصرفوا مبكراً<br><b>{A['eu']}</b> منهم دون إذن")}</div></div>
<div class="card"><h3>كل نقطة = موظف واحد</h3>{grid}
<div class="lg"><span><i style="background:{C['aqua']}"></i>منضبط تماماً ({A['clean']})</span><span><i style="background:{C['blue']}"></i>مخالفة واحدة على الأقل ({other})</span><span><i style="background:{C['orange']}"></i>غائب طوال الفترة ({A['allabs']})</span></div></div></div>
<div class="row r2"><div class="card">{ch_week}</div><div class="card">{cmp}</div></div>
<div class="row r2"><div class="card">{ch_day}</div>
<div class="card"><h3>ما الذي يعنيه ذلك؟</h3><ul>{''.join(f'<li>{x}</li>' for x in bullets)}</ul></div></div>
<div class="ft">التأخير: {ru['late']} فأكثر • الانصراف المبكر: قبل {ru['early']} • «دون إذن»: لا يوجد إذن مسجل في النظام</div>
</div>'''
    return f'<html><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'


def save_infographic(S, cfg, png_path=None, pdf_path=None):
    return html_to_image_and_pdf(infographic_html(S, cfg), png_path, pdf_path)
