"""Turns parsed rows into one classified record per employee per working day."""
import numpy as np
import pandas as pd

from .settings import Settings, WEEKDAY_NAMES

ABS_TYPES = [('منقطع', 'منقطع عن العمل'), ('مرضيه بنصف', 'إجازة مرضية بنصف راتب'), ('مرضيه بربع', 'إجازة مرضية بربع راتب'),
             ('مرضية مستثناة', 'إجازة مرضية مستثناة'), ('مرضيه', 'إجازة مرضية براتب'), ('طارئه', 'إجازة طارئة'),
             ('دراسية', 'إجازة دراسية'), ('بعثة', 'بعثة دراسية'), ('خاصه بدون', 'إجازة خاصة بدون راتب'),
             ('إعفاء كلي', 'إعفاء كلي (دورات/مهمة رسمية)'), ('غياب', 'غياب')]
UNEXCUSED_PREFIXES = ('غياب', 'منقطع')   # 'غياب (بدون بصمات)' counts as unexcused too
UNJUST = 'غير مبرر بالنظام'
JUST = 'مبرر بإذن مسجل'


def _abstype(s):
    for k, v in ABS_TYPES:
        if k in s:
            return v
    return ''


def _perm(s):
    s = s or ''
    if 'اذن خاص فى الحضور و' in s: return 'إذن خاص في الحضور والانصراف'
    if 'مراجعة طبية فى الحضور' in s: return 'إذن مراجعة طبية في الحضور'
    if 'مراجعة طبية فى الانصراف' in s: return 'إذن مراجعة طبية في الانصراف'
    if 'اذن خاص فى الحضور' in s: return 'إذن خاص في الحضور'
    if 'اذن خاص فى الانصراف' in s: return 'إذن خاص في الانصراف'
    if 'تخفيف' in s or s == 'العمل فى': return 'تخفيف ساعات العمل'
    if 'إعفاء جزئي' in s: return 'إعفاء جزئي في الانصراف'
    if 'لا يوجد بصمة' in s: return 'لا يوجد بصمة انصراف'
    return ''


def _m(t):
    t = (t or '').split()
    if not t:
        return 0
    h, mi = map(int, t[0].split(':'))
    return h * 60 + mi


def available_dates(raw):
    d = pd.to_datetime(pd.Series([x['date'] for x in raw['recs']]), format='%Y/%m/%d')
    return d.min().date(), d.max().date()


def build_records(raw, cfg: Settings) -> pd.DataFrame:
    E = raw['emps']
    R = pd.DataFrame(raw['recs'])
    R['date'] = pd.to_datetime(R.date, format='%Y/%m/%d')
    keep = R.date.dt.weekday.isin([int(x) for x in cfg.workdays])
    if cfg.start_date: keep &= R.date >= pd.Timestamp(cfg.start_date)
    if cfg.end_date: keep &= R.date <= pd.Timestamp(cfg.end_date)
    if cfg.excluded_dates:
        keep &= ~R.date.isin(pd.to_datetime(list(cfg.excluded_dates)))
    R = R[keep].copy()
    if R.empty:
        raise ValueError('لا توجد سجلات ضمن الفترة والأيام المختارة.')
    R = R.drop_duplicates(['cid', 'date'])

    for c in ['t1', 't2', 'out']:
        R[c + 'm'] = R[c].map(_m)
    R['sys_late'] = R.late.map(_m)
    R['mid'] = R.mid.str.replace(r'\s*\d*:?\d*\s*إجمالى الخصم بالايام :', '', regex=True).str.strip()
    R['abs_type'] = R.mid.map(_abstype)
    R['t2_exempt'] = R.mid.str.contains('غير ملزم')
    R['perm'] = R.note.map(_perm)
    R['name'] = R.cid.map(lambda c: E[c]['name'])
    R['fileno'] = R.cid.map(lambda c: E[c].get('fileno', ''))
    R['job'] = R.cid.map(lambda c: E[c].get('job', ''))
    # same name for two civil ids would merge people: make names unique
    dup = R.drop_duplicates('cid').groupby('name').cid.nunique()
    for nm in dup[dup > 1].index:
        for c in R[R.name == nm].cid.unique():
            R.loc[R.cid == c, 'name'] = f'{nm} ({c[-4:]})'

    r = R
    first = r.date.min()
    anchor = first - pd.Timedelta(days=(first.weekday() + 1) % 7)   # Sunday on/before the first day
    r['week'] = ((r.date - anchor).dt.days // 7) + 1
    r['day'] = r.date.dt.weekday.map(WEEKDAY_NAMES)
    z = (r.t1m == 0) & (r.t2m == 0) & (r.outm == 0)
    absent = (r.abs_type != '') | z
    r['abs_type'] = np.where(absent & (r.abs_type == ''), 'غياب (بدون بصمات)', r.abs_type)
    r['status'] = np.where(absent, 'غياب كامل', np.where((r.t1m > 0) & (r.outm > 0), 'حضور مكتمل', 'بصمة ناقصة'))
    p = r.t1m > 0
    LT = cfg.late_min
    r['late'] = (p & (r.t1m >= LT)).astype(int)
    r['late_min'] = np.where(r.late == 1, r.t1m - (LT - 1), 0)
    r['gap'] = np.where(p & (r.t2m > 0), r.t2m - r.t1m, np.nan)
    a, b = int(cfg.t2_min), int(cfg.t2_max)
    r['t2s'] = np.where(~p, np.where(r.t2m > 0, 'بلا بصمة دخول', '—'),
               np.where(r.t2_exempt, 'غير ملزم ببصمة التواجد',
               np.where(r.t2m == 0, 'لم تسجل بصمة تواجد',
               np.where(r.gap < a, 'مبكر عن النافذة', np.where(r.gap > b, 'متأخر عن النافذة', 'ملتزم بالنافذة')))))
    r['req'] = np.where(p, np.maximum(r.t1m, cfg.start_min) + int(cfg.full_minutes), np.nan)
    r['hours'] = np.where(p & (r.outm > 0), ((r.outm - r.t1m) / 60).round(2), 0)
    r['early'] = ((r.outm > 0) & (r.outm < cfg.early_min)).astype(int)
    r['full'] = (p & (r.outm > 0) & (r.outm >= r.req)).astype(int)
    r['cat'] = np.where(r.status == 'غياب كامل', 'غياب', np.where(r.late == 1, 'تأخير صباحي',
               np.where(r.early == 1, 'انصراف مبكر / استئذان', np.where(r.full == 1, 'دوام كامل مكتمل', 'بصمة ناقصة / نقص نصاب'))))
    pa = r.perm.str.contains('الحضور') | r.perm.str.contains('تخفيف')
    pl = r.perm.str.contains('الانصراف') | r.perm.str.contains('تخفيف') | r.perm.str.contains('إعفاء جزئي')
    r['late_just'] = np.where(r.late == 1, np.where(pa, JUST, UNJUST), '')
    r['early_just'] = np.where(r.early == 1, np.where(pl, JUST, UNJUST), '')
    # convenience flags used by the people statistics
    r['abs'] = r.status == 'غياب كامل'
    r['pres'] = ~r['abs']
    r['unx'] = r.abs_type.str.startswith(UNEXCUSED_PREFIXES)
    r['lu'] = r.late_just == UNJUST
    r['eu'] = r.early_just == UNJUST
    r['inc'] = r.status == 'بصمة ناقصة'
    return r.sort_values(['name', 'date']).reset_index(drop=True)
