"""Calculation rules and report options, saved to settings.json next to the app."""
import json, os
from dataclasses import dataclass, field, asdict

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# user data (settings + parse cache) lives in the home folder so it survives updates and packaged builds
DATA_DIR = os.environ.get('FLET_APP_STORAGE_DATA') or os.path.join(os.path.expanduser('~'), '.attendance_reports')
os.makedirs(DATA_DIR, exist_ok=True)
SETTINGS_PATH = os.path.join(DATA_DIR, 'settings.json')
WEEKDAY_NAMES = {6: 'الأحد', 0: 'الاثنين', 1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس', 4: 'الجمعة', 5: 'السبت'}


def to_min(hhmm: str) -> int:
    h, m = str(hhmm).strip().split(':')
    return int(h) * 60 + int(m)


def fmt_min(m: int) -> str:
    return f'{int(m) // 60:02d}:{int(m) % 60:02d}'


@dataclass
class Settings:
    # identity
    school_name: str = 'ثانوية عبد اللطيف ثنيان الغانم للبنين'
    org_line: str = 'وزارة التربية • الإدارة العامة لمنطقة الفروانية التعليمية • مراقبة التعليم الثانوي'
    signatures: list = field(default_factory=lambda: ['مُعدّ التقرير', 'رئيس قسم شؤون الموظفين', 'مدير المدرسة'])
    # period
    start_date: str = ''          # 'YYYY-MM-DD' or '' for the first date in the file
    end_date: str = ''            # 'YYYY-MM-DD' or '' for the last date in the file
    excluded_dates: list = field(default_factory=list)   # ['YYYY-MM-DD', ...]
    workdays: list = field(default_factory=lambda: [6, 0, 1, 2, 3])  # python weekday numbers (Sun..Thu)
    # rules
    late_from: str = '07:55'      # arrival at or after this time = late
    early_before: str = '13:20'   # leaving before this time = early leave
    day_start: str = '07:10'      # quota counted from max(day_start, T1)
    full_minutes: int = 370       # full-shift quota in minutes
    t2_min: int = 121             # T2 window starts T1 + t2_min minutes
    t2_max: int = 181             # T2 window ends T1 + t2_max minutes
    repeat_threshold: int = 6     # chronic late / recurring early / repeated unexcused absence
    trend_delta: float = 0.10     # change in full-shift ratio that counts as improving/declining

    # derived helpers
    @property
    def late_min(self): return to_min(self.late_from)
    @property
    def early_min(self): return to_min(self.early_before)
    @property
    def start_min(self): return to_min(self.day_start)

    def save(self, path=SETTINGS_PATH):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=1)

    @classmethod
    def load(cls, path=SETTINGS_PATH):
        s = cls()
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
                for k, v in data.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
            except Exception:
                pass
        return s

    def validate(self):
        """Return a list of problems (empty when valid)."""
        errs = []
        for k in ('late_from', 'early_before', 'day_start'):
            try:
                m = to_min(getattr(self, k))
                assert 0 <= m < 24 * 60
            except Exception:
                errs.append(f'{k}: الوقت يجب أن يكون بصيغة HH:MM')
        if not (0 < int(self.full_minutes) < 24 * 60): errs.append('full_minutes غير صالح')
        if not (0 <= int(self.t2_min) < int(self.t2_max)): errs.append('نافذة T2: البداية يجب أن تسبق النهاية')
        if int(self.repeat_threshold) < 2: errs.append('حد التكرار يجب أن يكون 2 فأكثر')
        if not self.workdays: errs.append('اختر يوم عمل واحداً على الأقل')
        return errs
