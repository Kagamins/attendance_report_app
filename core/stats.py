"""People-based statistics: every count is distinct employees, not fingerprint records."""
import numpy as np
import pandas as pd

from .settings import Settings, WEEKDAY_NAMES

TRENDS = ['متحسن', 'مستقر', 'متراجع', 'منقطع']


def people(d: pd.DataFrame) -> dict:
    """Distinct-employee counts for any slice of records (a week, a day, the whole period)."""
    g = d.groupby('name'); n = g.size(); pres = g.pres.sum()
    t2den = ((d.t1m > 0) & ~d.t2_exempt).sum()
    hrs = d.hours[d.hours > 0]
    return dict(
        emp=int(d.name.nunique()), days=int(d.date.nunique()),
        avg_pres=round(float(d.pres.sum() / max(d.date.nunique(), 1)), 1), att=float(d.pres.mean()) if len(d) else 0.0,
        absent=int((g['abs'].sum() > 0).sum()), unx=int((g.unx.sum() > 0).sum()), allabs=int((g['abs'].sum() == n).sum()),
        late=int((g.late.sum() > 0).sum()), lu=int((g.lu.sum() > 0).sum()),
        early=int((g.early.sum() > 0).sum()), eu=int((g.eu.sum() > 0).sum()),
        inc=int((g.inc.sum() > 0).sum()), fullall=int(((pres > 0) & (g.full.sum() == pres)).sum()),
        clean=int(((g.late.sum() == 0) & (g.unx.sum() == 0) & (g.eu.sum() == 0) & (pres > 0)).sum()),
        t2=float((d.t2s == 'ملتزم بالنافذة').sum() / t2den) if t2den else 0.0,
        hrs=float(hrs.mean()) if len(hrs) else 0.0,
        late_inst=int(d.late.sum()), early_inst=int(d.early.sum()), abs_days=int(d['abs'].sum()))


def daily_avg(d):
    g = d.groupby('date')
    return dict(absent=float(g['abs'].sum().mean()), late=float(g.late.sum().mean()), early=float(g.early.sum().mean()),
                unx=float(g.unx.sum().mean()), pres=float(g.pres.sum().mean()))


def person_table(r: pd.DataFrame, cfg: Settings) -> pd.DataFrame:
    """One row per employee with counts, flags and the latest-week trend."""
    REP = int(cfg.repeat_threshold); LW = int(r.week.max())
    g = r.groupby('name')
    E = pd.DataFrame(dict(cid=g.cid.first(), job=g.job.first(), fileno=g.fileno.first(), days=g.size(),
                          pres=g.pres.sum(), absd=g['abs'].sum(), unx=g.unx.sum(), late=g.late.sum(), lu=g.lu.sum(),
                          lmin=g.late_min.sum(), early=g.early.sum(), eu=g.eu.sum(), full=g.full.sum(), inc=g.inc.sum(),
                          hours=g.hours.apply(lambda h: h[h > 0].mean() if (h > 0).any() else 0.0))).reset_index()
    for c in ['days', 'pres', 'absd', 'unx', 'late', 'lu', 'lmin', 'early', 'eu', 'full', 'inc']:
        E[c] = E[c].astype(int)
    E['hours'] = E.hours.round(2)
    E['att'] = (E.pres / E.days).round(3)
    E['full_ratio'] = (E.full / E.days).round(3)
    h = r[r.week < LW].groupby('name'); l = r[r.week == LW].groupby('name')
    E['hi'] = E.name.map(h.full.sum() / h.size()); E['li'] = E.name.map(l.full.sum() / l.size())
    E['labs'] = E.name.map(l['abs'].sum()).fillna(0).astype(int); E['ldays'] = E.name.map(l.size()).fillna(0).astype(int)
    E['llate'] = E.name.map(l.late.sum()).fillna(0).astype(int); E['hlate'] = E.name.map(h.late.sum()).fillna(0).astype(int)
    E['labsd'] = E['labs']
    d = (E.li - E.hi).fillna(0); td = float(cfg.trend_delta)
    E['tr'] = np.where((E.ldays > 0) & (E.labs == E.ldays), 'منقطع', np.where(d >= td, 'متحسن', np.where(d <= -td, 'متراجع', 'مستقر')))
    E['allabs'] = E.absd == E.days
    E['discon'] = E.allabs & (E.unx > 0)
    E['onleave'] = E.allabs & (E.unx == 0)
    E['chronic'] = E.late >= REP
    E['relief'] = E.early >= REP
    E['clean'] = (E.late == 0) & (E.unx == 0) & (E.eu == 0) & (E.pres > 0)
    E['fullall'] = (E.pres > 0) & (E.full == E.pres)
    E['status'] = np.select(
        [E.discon, E.onleave, E.unx >= REP, E.relief, E.chronic, E.full_ratio >= 0.9],
        ['منقطع كلياً', 'إجازة/إعفاء طوال الفترة', 'غياب متكرر بدون عذر', 'تخفيف عمل / انصراف متكرر', 'متأخر باستمرار', 'ملتزم'],
        default='ملتزم جزئياً')
    # absence reasons per person
    ab = r[r['abs']].groupby('name').abs_type.agg(lambda s: '، '.join(f'{k} ({v})' for k, v in s.value_counts().items()))
    E['abs_reasons'] = E.name.map(ab).fillna('')
    return E.sort_values('name').reset_index(drop=True)


def compute(r: pd.DataFrame, cfg: Settings, prev_raw=None, current_raw=None) -> dict:
    """All figures used by the dashboard, reports and infographic."""
    REP = int(cfg.repeat_threshold)
    weeks = sorted(int(w) for w in r.week.unique()); LW = max(weeks); PW = LW - 1 if (LW - 1) in weeks else None
    wr = {int(w): (r[r.week == w].date.min().strftime('%d/%m'), r[r.week == w].date.max().strftime('%d/%m')) for w in weeks}
    days = [WEEKDAY_NAMES[d] for d in [6, 0, 1, 2, 3, 4, 5] if d in [int(x) for x in cfg.workdays] and WEEKDAY_NAMES[d] in set(r.day)]
    E = person_table(r, cfg)
    ALL = people(r)
    WK = {w: people(r[r.week == w]) for w in weeks}
    DAY = {dn: daily_avg(r[r.day == dn]) for dn in days}
    DAYP = {dn: people(r[r.day == dn]) for dn in days}
    LWD = [(d.strftime('%d/%m'), r[r.date == d].day.iloc[0], people(r[r.date == d])) for d in sorted(r[r.week == LW].date.unique())]
    worst = max(days, key=lambda dn: DAY[dn]['absent'] + DAY[dn]['early']) if days else ''
    best = min(days, key=lambda dn: DAY[dn]['absent'] + DAY[dn]['early']) if days else ''
    bins = [(0, 0, 'لم يتأخر'), (1, 2, '1–2 مرة'), (3, REP - 1, f'3–{REP - 1} مرات'), (REP, REP + 4, f'{REP}–{REP + 4} مرات'), (REP + 5, 10**6, f'أكثر من {REP + 4}')]
    bins = [b for b in bins if b[0] <= b[1]]
    LATE_B = [(lab, int(((E.late >= a) & (E.late <= b)).sum())) for a, b, lab in bins]
    ABS_B = [(lab, int(((E.absd >= a) & (E.absd <= b)).sum())) for a, b, lab in
             [(0, 0, 'لم يغب'), (1, 2, '1–2 يوم'), (3, 5, '3–5 أيام'), (6, 15, '6–15 يوماً'), (16, 10**6, 'أكثر من 15')]]
    ABS_P = r[r['abs']].groupby('abs_type').name.nunique().sort_values(ascending=False)
    PERM_P = r[r.perm != ''].groupby('perm').name.nunique().sort_values(ascending=False)
    new_people, gone = [], []
    if prev_raw is not None:
        prev_ids = set(prev_raw['emps']); cur_ids = set(r.cid)
        cid2 = r.drop_duplicates('cid').set_index('cid')
        new_people = [(c, cid2.loc[c, 'name'], cid2.loc[c, 'job']) for c in sorted(cur_ids - prev_ids)]
        gone = [(c, prev_raw['emps'][c]['name'], prev_raw['emps'][c].get('job', '')) for c in sorted(prev_ids - cur_ids)]
    dates = sorted(r.date.unique())
    return dict(
        period=f"{pd.Timestamp(dates[0]).strftime('%d/%m/%Y')} – {pd.Timestamp(dates[-1]).strftime('%d/%m/%Y')}",
        period_short=f"{pd.Timestamp(dates[0]).strftime('%d/%m')}–{pd.Timestamp(dates[-1]).strftime('%d/%m/%Y')}",
        weeks=weeks, LW=LW, PW=PW, wr=wr, DAYS=days, ALL=ALL, WK=WK, DAY=DAY, DAYP=DAYP, LWD=LWD, worst_day=worst, best_day=best,
        TR={k: int((E.tr == k).sum()) for k in TRENDS}, LATE_B=LATE_B, ABS_B=ABS_B,
        ABS_P=[(k, int(v)) for k, v in ABS_P.items()], PERM_P=[(k, int(v)) for k, v in PERM_P.items()],
        new_people=new_people, gone=gone, has_prev=prev_raw is not None,
        n_chronic=int(E.chronic.sum()), n_relief=int(E.relief.sum()), n_discon=int(E.discon.sum()),
        n_onleave=int(E.onleave.sum()), n_unx=int((E.unx > 0).sum()), n_unx_rep=int((E.unx >= REP).sum()),
        n_lw_allabs=int((E.tr == 'منقطع').sum()), n_90=int((E.full_ratio >= 0.9).sum()),
        rep=REP, rules=dict(late=cfg.late_from, early=cfg.early_before, start=cfg.day_start, quota=int(cfg.full_minutes),
                            t2=(int(cfg.t2_min), int(cfg.t2_max))),
        E=E)


# ---- people filters shared by the UI, the report and the exports
def filters(cfg: Settings):
    REP = int(cfg.repeat_threshold)
    return {
        'all': ('جميع الموظفين', lambda E: E.index == E.index),
        'late': ('تأخروا مرة على الأقل', lambda E: E.late > 0),
        'lu': ('تأخروا دون إذن', lambda E: E.lu > 0),
        'chronic': (f'متأخرون باستمرار ({REP}+)', lambda E: E.chronic),
        'never_late': ('لم يتأخروا أبداً', lambda E: E.late == 0),
        'absent': ('غابوا يوماً على الأقل', lambda E: E.absd > 0),
        'unx': ('غابوا دون عذر', lambda E: E.unx > 0),
        'unx_rep': (f'غياب دون عذر متكرر ({REP}+)', lambda E: E.unx >= REP),
        'allabs': ('غائبون طوال الفترة', lambda E: E.allabs),
        'discon': ('منقطعون كلياً', lambda E: E.discon),
        'onleave': ('في إجازة طوال الفترة', lambda E: E.onleave),
        'early': ('انصرفوا مبكراً', lambda E: E.early > 0),
        'eu': ('انصرفوا دون إذن', lambda E: E.eu > 0),
        'relief': (f'انصراف مبكر متكرر ({REP}+)', lambda E: E.relief),
        'inc': ('لديهم بصمة ناقصة', lambda E: E.inc > 0),
        'clean': ('منضبطون تماماً', lambda E: E.clean),
        'fullall': ('دوام كامل في كل أيام حضورهم', lambda E: E.fullall),
        'improving': ('متحسن في الأسبوع الأحدث', lambda E: E.tr == 'متحسن'),
        'declining': ('متراجع في الأسبوع الأحدث', lambda E: E.tr == 'متراجع'),
        'lw_absent': ('غائب طوال الأسبوع الأحدث', lambda E: E.tr == 'منقطع'),
    }


PERSON_COLUMNS = [  # (key, Arabic header) for tables and exports
    ('name', 'الاسم'), ('cid', 'الرقم المدني'), ('job', 'الوظيفة'), ('days', 'أيام العمل'), ('pres', 'الحضور'),
    ('absd', 'الغياب'), ('unx', 'منه دون عذر'), ('late', 'التأخير'), ('lu', 'منه دون إذن'), ('lmin', 'دقائق التأخير'),
    ('early', 'الانصراف المبكر'), ('eu', 'منه دون إذن'), ('inc', 'بصمة ناقصة'), ('full', 'دوام كامل'),
    ('hours', 'متوسط الساعات'), ('tr', 'المسار'), ('status', 'التصنيف'), ('abs_reasons', 'أسباب الغياب')]


def export_people(E: pd.DataFrame, path: str):
    """Write a people list to .xlsx (right-to-left) or .csv."""
    cols = [c for c, _ in PERSON_COLUMNS]
    df = E[cols].rename(columns=dict(PERSON_COLUMNS))
    if path.lower().endswith('.csv'):
        df.to_csv(path, index=False, encoding='utf-8-sig')
        return path
    with pd.ExcelWriter(path, engine='openpyxl') as xw:
        df.to_excel(xw, index=False, sheet_name='الموظفون')
        ws = xw.sheets['الموظفون']; ws.sheet_view.rightToLeft = True; ws.freeze_panes = 'B2'
        for i, w in enumerate([32, 14, 26, 9, 8, 8, 9, 8, 9, 10, 10, 9, 9, 9, 10, 10, 22, 40], 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    return path
