"""Attendance reports - Flet desktop app (Arabic, right-to-left).

Run:  python main.py
Built for flet==0.28.3 (see requirements.txt).
"""
import os, sys, threading, traceback, subprocess, datetime as dt

import flet as ft

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.settings import Settings, WEEKDAY_NAMES, to_min
from core.parser import parse_pdf, ParseError
from core.analysis import build_records, available_dates
from core.stats import compute, filters, export_people
from core import report, infographic, workbook


def _has_chromium():
    """True when Playwright + Chromium can render HTML (desktop). Phones use the pure-Python renderer."""
    if os.environ.get('ATTENDANCE_LITE') == '1':
        return False
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False

NAVY = '#1F3864'; BLUE = '#2A78D6'; ORANGE = '#EB6834'; AQUA = '#1BAF7A'; RED = '#B3261E'; GREEN = '#1B7F3B'
BG = '#F3F4F6'; CARD = '#FFFFFF'; MUTED = '#5A6474'
DEFAULT_OUT = os.path.join(os.path.expanduser('~'), 'Documents', 'تقارير الحضور')
ANDROID_OUT = '/storage/emulated/0/Download/AttendanceReports'


def open_path(path):
    """Open a file or folder with the system's default program."""
    try:
        if sys.platform.startswith('win'):
            os.startfile(path)  # noqa
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception:
        pass


def safe_name(s):
    return ''.join(ch for ch in str(s) if ch not in '\\/:*?"<>|').strip()[:80]


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.cfg = Settings.load()
        self.raw = None; self.prev_raw = None; self.r = None; self.S = None
        self.pdf_path = ''; self.prev_path = ''
        self.people_filter = 'all'; self.people_query = ''; self.people_sort = ('name', True)
        self.report_opts = dict(report.DEFAULT_OPTIONS); self.report_opts['extra_lists'] = []
        self.generated = []   # (label, path)
        self.busy = False

        plat = getattr(page, 'platform', None)
        self.mobile = os.environ.get('ATTENDANCE_MOBILE') == '1' or plat in (getattr(ft.PagePlatform, 'ANDROID', 'android'), getattr(ft.PagePlatform, 'IOS', 'ios'))
        self.lite = self.mobile or not _has_chromium()
        if self.lite:
            from core import pdf_lite
            self.R_full, self.R_person, self.R_list, self.R_info = pdf_lite.save_full_report, pdf_lite.save_person_report, pdf_lite.save_people_list, pdf_lite.save_infographic
        else:
            self.R_full, self.R_person, self.R_list, self.R_info = report.save_full_report, report.save_person_report, report.save_people_list, infographic.save_infographic
        self.out_dir = self._default_out()
        page.title = 'تقارير الحضور والانصراف'
        page.rtl = True
        page.bgcolor = BG
        page.padding = 0
        page.theme = ft.Theme(color_scheme_seed=NAVY)
        page.theme_mode = ft.ThemeMode.LIGHT
        if not self.mobile:
            page.window.width = 1360; page.window.height = 860; page.window.min_width = 1000; page.window.min_height = 640

        # pickers (must live in the overlay)
        self.fp_main = ft.FilePicker(on_result=self._on_pick_main)
        self.fp_prev = ft.FilePicker(on_result=self._on_pick_prev)
        self.fp_dir = ft.FilePicker(on_result=self._on_pick_dir)
        self.fp_save = ft.FilePicker(on_result=self._on_save_result)
        self._save_job = None
        page.overlay.extend([self.fp_main, self.fp_prev, self.fp_dir, self.fp_save])

        # busy overlay
        self.busy_text = ft.Text('', size=15, color=NAVY)
        self.busy_bar = ft.ProgressBar(width=360, value=None, color=BLUE)
        self.busy_layer = ft.Container(
            content=ft.Container(ft.Column([ft.ProgressRing(color=BLUE), self.busy_text, self.busy_bar],
                                           horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14, tight=True),
                                 bgcolor=CARD, padding=30, border_radius=14, width=440),
            alignment=ft.alignment.center, bgcolor='#66000000', visible=False, expand=True)

        self.rail = ft.NavigationRail(
            selected_index=0, label_type=ft.NavigationRailLabelType.ALL, min_width=96, bgcolor=CARD,
            leading=ft.Container(ft.Column([ft.Icon(ft.Icons.FINGERPRINT, color=NAVY, size=34),
                                            ft.Text('الحضور', size=12, weight=ft.FontWeight.BOLD, color=NAVY)],
                                           horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2), padding=ft.padding.only(top=14, bottom=10)),
            destinations=[
                ft.NavigationRailDestination(icon=ft.Icons.UPLOAD_FILE_OUTLINED, selected_icon=ft.Icons.UPLOAD_FILE, label='البيانات'),
                ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD_OUTLINED, selected_icon=ft.Icons.DASHBOARD, label='لوحة المؤشرات'),
                ft.NavigationRailDestination(icon=ft.Icons.PEOPLE_OUTLINE, selected_icon=ft.Icons.PEOPLE, label='الموظفون'),
                ft.NavigationRailDestination(icon=ft.Icons.PICTURE_AS_PDF_OUTLINED, selected_icon=ft.Icons.PICTURE_AS_PDF, label='التقارير'),
                ft.NavigationRailDestination(icon=ft.Icons.SETTINGS_OUTLINED, selected_icon=ft.Icons.SETTINGS, label='الإعدادات'),
            ],
            on_change=lambda e: self.show(e.control.selected_index))
        self.body = ft.Container(expand=True, padding=10 if self.mobile else 24)
        if self.mobile:
            # phones: bottom navigation bar instead of the side rail
            self.rail = ft.NavigationBar(
                selected_index=0, bgcolor=CARD,
                destinations=[ft.NavigationBarDestination(icon=d.icon, selected_icon=d.selected_icon, label=d.label) for d in self.rail.destinations],
                on_change=lambda e: self.show(e.control.selected_index))
            page.navigation_bar = self.rail
            page.add(ft.SafeArea(ft.Stack([self.body, self.busy_layer], expand=True), expand=True))
        else:
            page.add(ft.Stack([ft.Row([self.rail, ft.VerticalDivider(width=1), self.body], expand=True, spacing=0), self.busy_layer], expand=True))
        self.show(0)

    def _default_out(self):
        if not self.mobile:
            return DEFAULT_OUT
        for d in (ANDROID_OUT, os.path.join(os.environ.get('FLET_APP_STORAGE_DATA', os.path.expanduser('~')), 'reports')):
            try:
                os.makedirs(d, exist_ok=True)
                test = os.path.join(d, '.write_test'); open(test, 'w').close(); os.remove(test)
                return d
            except Exception:
                continue
        return os.path.expanduser('~')

    def open_file(self, path):
        if self.mobile:
            self.toast(f'المسار: {path}  (افتحه من تطبيق «الملفات» ← التنزيلات)')
        else:
            open_path(path)

    # ------------------------------------------------------------------ helpers
    def toast(self, msg, error=False):
        self.page.open(ft.SnackBar(ft.Text(msg, color='white'), bgcolor=RED if error else NAVY, duration=5000 if error else 3000))

    def set_busy(self, on, msg='', value=None):
        self.busy = on
        self.busy_layer.visible = on
        self.busy_text.value = msg
        self.busy_bar.value = value
        self.page.update()

    def run_bg(self, msg, job, done=None):
        """Run job() in a thread with the busy overlay; done(result) runs afterwards."""
        if self.busy:
            return
        self.set_busy(True, msg)
        if getattr(self, 'sync', False):   # used by the automated tests
            res = job(); self.set_busy(False)
            if done: done(res)
            return

        def worker():
            try:
                res = job()
            except Exception as ex:
                traceback.print_exc()
                self.set_busy(False)
                self.toast(f'حدث خطأ: {ex}', error=True)
                return
            self.set_busy(False)
            if done:
                done(res)
        threading.Thread(target=worker, daemon=True).start()

    def show(self, idx):
        self.rail.selected_index = idx
        views = [self.view_data, self.view_dashboard, self.view_people, self.view_reports, self.view_settings]
        if idx in (1, 2, 3) and self.S is None:
            self.body.content = self.empty_state()
        else:
            self.body.content = views[idx]()
        self.page.update()

    def empty_state(self):
        return ft.Column([ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED, size=64, color=MUTED),
                          ft.Text('لم يتم تحميل تقرير البصمة بعد', size=20, color=NAVY, weight=ft.FontWeight.BOLD),
                          ft.Text('ابدأ من صفحة «البيانات» واختر ملف PDF المصدَّر من نظام البصمة.', color=MUTED),
                          ft.FilledButton('اذهب إلى البيانات', icon=ft.Icons.UPLOAD_FILE, on_click=lambda e: self.show(0))],
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, expand=True)

    @staticmethod
    def title(text, sub=''):
        items = [ft.Text(text, size=26, weight=ft.FontWeight.BOLD, color=NAVY)]
        if sub: items.append(ft.Text(sub, size=13, color=MUTED))
        return ft.Column(items, spacing=2)

    @staticmethod
    def card(content, padding=16, expand=None, width=None, on_click=None, tooltip=None):
        return ft.Container(content, bgcolor=CARD, border_radius=12, padding=padding, expand=expand, width=width,
                            border=ft.border.all(1, '#E3E6EA'), on_click=on_click, tooltip=tooltip,
                            ink=on_click is not None)

    # ------------------------------------------------------------------ data
    def view_data(self):
        c = self.cfg
        self.tf_start = ft.TextField(label='من تاريخ (YYYY-MM-DD)', value=c.start_date, width=210, dense=True)
        self.tf_end = ft.TextField(label='إلى تاريخ (YYYY-MM-DD)', value=c.end_date, width=210, dense=True)
        self.tf_excl = ft.TextField(label='تواريخ مستبعدة (مفصولة بفاصلة)', value=', '.join(c.excluded_dates), expand=True, dense=True,
                                    hint_text='مثال: 2026-10-18, 2026-10-19')
        self.wd_checks = [ft.Checkbox(label=WEEKDAY_NAMES[d], value=d in c.workdays, data=d) for d in [6, 0, 1, 2, 3, 4, 5]]
        info = []
        if self.raw:
            a, b = available_dates(self.raw)
            info.append(ft.Text(f'✔ {os.path.basename(self.pdf_path)} • {len(self.raw["emps"])} موظفاً • {len(self.raw["recs"])} سجلاً • '
                                f'التواريخ المتاحة {a:%d/%m/%Y} – {b:%d/%m/%Y}', color=GREEN))
        if self.prev_raw:
            info.append(ft.Text(f'✔ التقرير السابق: {os.path.basename(self.prev_path)} • {len(self.prev_raw["emps"])} موظفاً', color=GREEN))
        if self.S:
            A = self.S['ALL']
            info.append(ft.Text(f'التحليل الحالي: {self.S["period"]} • {A["days"]} يوم عمل • {A["emp"]} موظفاً', color=NAVY, weight=ft.FontWeight.BOLD))
        return ft.Column([
            self.title('البيانات', 'حمّل «تقرير حركة موظف (مختصر)» بصيغة PDF من نظام البصمة، ثم حدد الفترة.'),
            self.card(ft.Column([
                ft.Text('1. ملف تقرير البصمة', size=17, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Row([ft.FilledButton('اختيار ملف PDF', icon=ft.Icons.UPLOAD_FILE,
                                        on_click=lambda e: self.fp_main.pick_files(dialog_title='اختر تقرير البصمة', allowed_extensions=['pdf'])),
                        ft.OutlinedButton('تقرير سابق للمقارنة (اختياري)', icon=ft.Icons.COMPARE_ARROWS,
                                          on_click=lambda e: self.fp_prev.pick_files(dialog_title='اختر التقرير السابق', allowed_extensions=['pdf'])),
                        ft.TextButton('إزالة التقرير السابق', on_click=self._clear_prev, visible=self.prev_raw is not None)], wrap=True),
                ft.Text('القراءة الأولى لملف كبير تستغرق دقيقة تقريباً؛ بعد ذلك يُحفظ في الذاكرة المؤقتة ويفتح فوراً.', size=12, color=MUTED),
                *info], spacing=10)),
            self.card(ft.Column([
                ft.Text('2. الفترة وأيام العمل', size=17, weight=ft.FontWeight.BOLD, color=NAVY),
                ft.Row([self.tf_start, self.tf_end, self.tf_excl]),
                ft.Row([ft.Text('أيام العمل:')] + self.wd_checks, wrap=True),
                ft.Row([ft.FilledButton('تطبيق وإعادة الحساب', icon=ft.Icons.REFRESH, on_click=self._apply_period, disabled=self.raw is None),
                        ft.TextButton('كل الفترة', on_click=self._full_period, disabled=self.raw is None)]),
            ], spacing=10)),
        ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def _on_pick_main(self, e):
        if not e.files: return
        if not e.files[0].path:
            self.toast('تعذر الوصول إلى الملف. انسخه إلى مجلد التنزيلات ثم اختره من هناك.', error=True); return
        self.load_pdf(e.files[0].path)

    def _on_pick_prev(self, e):
        if not e.files or not e.files[0].path: return
        path = e.files[0].path

        def job():
            return parse_pdf(path, progress=self._progress)

        def done(raw):
            self.prev_raw, self.prev_path = raw, path
            if self.raw: self.recompute()
            self.show(0); self.toast('تم تحميل التقرير السابق للمقارنة')
        self.run_bg('قراءة التقرير السابق…', job, done)

    def _clear_prev(self, e):
        self.prev_raw = None; self.prev_path = ''
        if self.raw: self.recompute()
        self.show(0)

    def _progress(self, done, total):
        self.busy_bar.value = done / max(total, 1)
        self.busy_text.value = f'قراءة الصفحات… {done} من {total}'
        self.page.update()

    def load_pdf(self, path, then_show=1):
        def job():
            raw = parse_pdf(path, progress=self._progress)
            return raw

        def done(raw):
            self.raw, self.pdf_path = raw, path
            # a new file: reset the period to the whole file
            self.cfg.start_date = ''; self.cfg.end_date = ''; self.cfg.excluded_dates = []
            if self.recompute():
                self.toast(f'تم التحليل: {self.S["ALL"]["emp"]} موظفاً')
                self.show(then_show)
        self.run_bg('فتح تقرير البصمة…', job, done)

    def recompute(self):
        try:
            self.r = build_records(self.raw, self.cfg)
            self.S = compute(self.r, self.cfg, prev_raw=self.prev_raw)
            return True
        except Exception as ex:
            traceback.print_exc()
            self.toast(f'تعذر الحساب: {ex}', error=True)
            return False

    def _read_period_fields(self):
        def chk(v):
            v = v.strip()
            if v: dt.date.fromisoformat(v)
            return v
        start, end = chk(self.tf_start.value or ''), chk(self.tf_end.value or '')
        excl = [chk(x) for x in (self.tf_excl.value or '').replace('،', ',').split(',') if x.strip()]
        wd = [c.data for c in self.wd_checks if c.value]
        if not wd: raise ValueError('اختر يوم عمل واحداً على الأقل')
        return start, end, excl, wd

    def _apply_period(self, e):
        try:
            start, end, excl, wd = self._read_period_fields()
        except ValueError as ex:
            self.toast(f'تحقق من التواريخ (الصيغة YYYY-MM-DD): {ex}', error=True); return
        self.cfg.start_date, self.cfg.end_date, self.cfg.excluded_dates, self.cfg.workdays = start, end, excl, wd
        self.cfg.save()
        if self.recompute():
            self.toast(f'تمت إعادة الحساب: {self.S["period"]}'); self.show(1)

    def _full_period(self, e):
        self.cfg.start_date = ''; self.cfg.end_date = ''; self.cfg.excluded_dates = []
        if self.recompute(): self.show(0)

    # ------------------------------------------------------------------ dashboard
    def kpi(self, label, value, sub, color=NAVY, filt=None):
        col = ft.Column([ft.Text(label, size=13, color=MUTED), ft.Text(str(value), size=26 if self.mobile else 34, weight=ft.FontWeight.BOLD, color=color),
                         ft.Text(sub, size=12, color=MUTED)], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        c = self.card(col, padding=10 if self.mobile else 14, on_click=(lambda e: self.open_people(filt)) if filt else None,
                      tooltip='اضغط لعرض الأسماء' if filt else None)
        c.col = {'xs': 6, 'md': 3}
        return c

    def bars(self, items, colors, maxv=None, height=120):
        """Grouped mini bar chart from containers: items = [(label, [v1,v2,v3])]."""
        maxv = maxv or max([max(v) for _, v in items] + [1])
        groups = []
        for lab, vals in items:
            bars_ = [ft.Column([ft.Text(f'{v:g}', size=10, color=MUTED),
                                ft.Container(width=14, height=max(2, height * v / maxv), bgcolor=c, border_radius=ft.border_radius.only(top_left=3, top_right=3),
                                             tooltip=f'{lab}: {v:g}')], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                               alignment=ft.MainAxisAlignment.END)
                     for v, c in zip(vals, colors)]
            groups.append(ft.Column([ft.Row(bars_, spacing=3, vertical_alignment=ft.CrossAxisAlignment.END, height=height + 18),
                                     ft.Text(lab, size=11, color=MUTED)], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4))
        return ft.Row(groups, alignment=ft.MainAxisAlignment.SPACE_AROUND, vertical_alignment=ft.CrossAxisAlignment.END)

    @staticmethod
    def legend(items):
        return ft.Row([ft.Row([ft.Container(width=12, height=12, bgcolor=c, border_radius=3), ft.Text(t, size=12)], spacing=5) for t, c in items], spacing=16)

    def view_dashboard(self):
        S = self.S; A = S['ALL']; WK = S['WK']; LW = S['LW']; PW = S['PW']; wr = S['wr']; REP = S['rep']
        row1 = ft.ResponsiveRow([self.kpi('إجمالي الموظفين', A['emp'], f"{A['days']} يوم عمل", filt='all'),
                       self.kpi('يحضرون يومياً (متوسط)', f"{A['avg_pres']:.0f}", f"نسبة الحضور {A['att'] * 100:.1f}%"),
                       self.kpi('منضبطون تماماً', A['clean'], 'بلا تأخير ولا غياب/انصراف دون إذن', AQUA, 'clean'),
                       self.kpi('غائبون طوال الفترة', A['allabs'], f"{S['n_discon']} منقطعون • {S['n_onleave']} إجازة", RED, 'allabs')], spacing=12, run_spacing=12)
        row2 = ft.ResponsiveRow([self.kpi('تأخروا مرة على الأقل', A['late'], f"منهم {A['lu']} دون إذن", ORANGE, 'late'),
                       self.kpi('تأخروا دون إذن', A['lu'], 'اضغط للأسماء', ORANGE, 'lu'),
                       self.kpi('متأخرون باستمرار', S['n_chronic'], f'{REP} مرات فأكثر', ORANGE, 'chronic'),
                       self.kpi('غابوا يوماً على الأقل', A['absent'], f"منهم {A['unx']} دون عذر", BLUE, 'absent')], spacing=12, run_spacing=12)
        row3 = ft.ResponsiveRow([self.kpi('غابوا دون عذر', A['unx'], 'اضغط للأسماء', BLUE, 'unx'),
                       self.kpi('انصرفوا مبكراً', A['early'], f"منهم {A['eu']} دون إذن", AQUA, 'early'),
                       self.kpi('انصرفوا دون إذن', A['eu'], 'اضغط للأسماء', AQUA, 'eu'),
                       self.kpi('انصراف مبكر متكرر', S['n_relief'], f'{REP} مرات فأكثر', AQUA, 'relief')], spacing=12, run_spacing=12)
        weeks = S['weeks']
        week_chart = self.card(ft.Column([ft.Text('عدد الموظفين أسبوعياً', size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                                          self.bars([(f'أ{w}', [WK[w]['absent'], WK[w]['late'], WK[w]['early']]) for w in weeks], [BLUE, ORANGE, AQUA]),
                                          self.legend([('غابوا', BLUE), ('تأخروا', ORANGE), ('انصرفوا مبكراً', AQUA)])], spacing=10))
        week_chart.col = {'xs': 12, 'lg': 6}
        D = S['DAY']; DAYS = S['DAYS']
        day_chart = self.card(ft.Column([ft.Text('متوسط الموظفين يومياً حسب اليوم', size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                                         self.bars([(d, [round(D[d]['absent'], 1), round(D[d]['late'], 1), round(D[d]['early'], 1)]) for d in DAYS], [BLUE, ORANGE, AQUA]),
                                         ft.Text(f'الأصعب: {S["worst_day"]} • الأفضل: {S["best_day"]}', size=12, color=MUTED)], spacing=10))
        day_chart.col = {'xs': 12, 'lg': 6}
        # weekly table
        hdr = ['الأسبوع', 'الفترة', 'نسبة الحضور', 'غابوا', 'دون عذر', 'تأخروا', 'دون إذن', 'انصرفوا مبكراً', 'دون إذن', 'بصمة ناقصة']
        rows = [[f'{w}', f'{wr[w][0]}–{wr[w][1]}', f"{WK[w]['att'] * 100:.1f}%", WK[w]['absent'], WK[w]['unx'], WK[w]['late'], WK[w]['lu'], WK[w]['early'], WK[w]['eu'], WK[w]['inc']] for w in weeks]
        rows.append(['الإجمالي', S['period_short'], f"{A['att'] * 100:.1f}%", A['absent'], A['unx'], A['late'], A['lu'], A['early'], A['eu'], A['inc']])
        wtable = ft.DataTable(columns=[ft.DataColumn(ft.Text(h, weight=ft.FontWeight.BOLD)) for h in hdr],
                              rows=[ft.DataRow([ft.DataCell(ft.Text(str(v), weight=ft.FontWeight.BOLD if i == len(rows) - 1 else None)) for v in rw]) for i, rw in enumerate(rows)],
                              heading_row_color='#EAF1F8', column_spacing=22, data_row_min_height=34, data_row_max_height=38)
        cmp_card = None
        if PW:
            a, b = WK[PW], WK[LW]
            def ln(lab, x, y, good=-1):
                d = y - x; col = GREEN if d * good > 0 else (RED if d else MUTED)
                return ft.Row([ft.Text(lab, expand=True), ft.Text(f'{x} → {y}', width=90), ft.Text(f"{'▲' if d > 0 else '▼' if d < 0 else '═'} {abs(d)}", color=col, width=60, weight=ft.FontWeight.BOLD)])
            cmp_card = self.card(ft.Column([ft.Text(f'الأسبوع {LW} ({wr[LW][0]}–{wr[LW][1]}) مقارنة بالأسبوع {PW}', size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                                            ln('غابوا', a['absent'], b['absent']), ln('غابوا دون عذر', a['unx'], b['unx']), ln('تأخروا', a['late'], b['late']),
                                            ln('تأخروا دون إذن', a['lu'], b['lu']), ln('انصرفوا مبكراً', a['early'], b['early']), ln('انصرفوا دون إذن', a['eu'], b['eu']),
                                            ln('بصمة ناقصة', a['inc'], b['inc']), ft.Divider(),
                                            ft.Row([ft.TextButton(f'متحسن {S["TR"]["متحسن"]}', on_click=lambda e: self.open_people('improving')),
                                                    ft.TextButton(f'متراجع {S["TR"]["متراجع"]}', on_click=lambda e: self.open_people('declining')),
                                                    ft.TextButton(f'غائب طوال الأسبوع {S["TR"]["منقطع"]}', on_click=lambda e: self.open_people('lw_absent'))], wrap=True)],
                                           spacing=6))
            cmp_card.col = {'xs': 12, 'lg': 4}
        extra = []
        if S['has_prev']:
            extra.append(self.card(ft.Column([ft.Text('مقارنة بالتقرير السابق', size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                                              ft.Text(f'موظفون جدد: {len(S["new_people"])}', weight=ft.FontWeight.BOLD),
                                              *[ft.Text(f'• {n} — {j}', size=13) for c, n, j in S['new_people']],
                                              ft.Text(f'غير موجودين في هذا التقرير: {len(S["gone"])}', weight=ft.FontWeight.BOLD),
                                              *[ft.Text(f'• {n} — {j}', size=13) for c, n, j in S['gone']]], spacing=4)))
        return ft.Column([
            self.title('لوحة المؤشرات', f"{self.cfg.school_name} • {S['period']} • كل رقم = عدد موظفين (أفراد) • اضغط على أي بطاقة لعرض الأسماء"),
            row1, row2, row3,
            ft.ResponsiveRow([week_chart, day_chart], spacing=12, run_spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
            ft.ResponsiveRow([self._col(self.card(ft.Column([ft.Text('المسار الأسبوعي (عدد الموظفين)', size=16, weight=ft.FontWeight.BOLD, color=NAVY),
                                                             ft.Row([wtable], scroll=ft.ScrollMode.AUTO)])), {'xs': 12, 'lg': 8 if cmp_card else 12})] + ([cmp_card] if cmp_card else []),
                             spacing=12, run_spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
            *extra,
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    @staticmethod
    def _col(ctl, col):
        ctl.col = col
        return ctl

    # ------------------------------------------------------------------ people
    PEOPLE_COLS = [('name', 'الاسم', False), ('job', 'الوظيفة', False), ('pres', 'الحضور', True), ('absd', 'الغياب', True),
                   ('unx', 'دون عذر', True), ('late', 'التأخير', True), ('lu', 'دون إذن', True), ('lmin', 'دقائق', True),
                   ('early', 'انصراف مبكر', True), ('eu', 'دون إذن', True), ('inc', 'بصمة ناقصة', True), ('full', 'دوام كامل', True),
                   ('tr', 'المسار', False), ('status', 'التصنيف', False)]

    def open_people(self, filt):
        self.people_filter = filt or 'all'; self.people_query = ''
        self.show(2)

    def people_subset(self):
        E = self.S['E']; F = filters(self.cfg)
        lab, fn = F.get(self.people_filter, F['all'])
        sub = E[fn(E)]
        q = (self.people_query or '').strip()
        if q:
            sub = sub[sub.name.str.contains(q, regex=False) | sub.cid.str.contains(q, regex=False) | sub.job.str.contains(q, regex=False)]
        key, asc = self.people_sort
        sub = sub.sort_values(key, ascending=asc, kind='stable')
        return lab, sub

    def view_people(self):
        F = filters(self.cfg)
        self.dd_filter = ft.Dropdown(label='عرض', value=self.people_filter, width=300,
                                     options=[ft.dropdown.Option(k, v[0]) for k, v in F.items()], on_change=self._people_filter)
        self.tf_search = ft.TextField(label='بحث بالاسم أو الرقم المدني أو الوظيفة', value=self.people_query, width=340, dense=True,
                                      prefix_icon=ft.Icons.SEARCH, on_change=self._people_search)
        self.people_count = ft.Text('', size=14, weight=ft.FontWeight.BOLD, color=NAVY)
        self.people_table_holder = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)
        chips = ft.Row([ft.Chip(label=ft.Text(F[k][0]), selected=self.people_filter == k, on_select=lambda e, k=k: self._set_filter(k))
                        for k in ['all', 'late', 'lu', 'chronic', 'absent', 'unx', 'allabs', 'early', 'eu', 'relief', 'inc', 'clean', 'declining']],
                       wrap=True, spacing=6, run_spacing=6)
        self.refresh_people_table(update=False)
        return ft.Column([
            self.title('الموظفون', 'اختر مجموعة أو ابحث، واضغط على أي موظف لعرض سجله اليومي وتقريره الفردي.'),
            chips,
            ft.Row([self.dd_filter, self.tf_search, self.people_count,
                    ft.Container(expand=True),
                    ft.OutlinedButton('تصدير Excel', icon=ft.Icons.TABLE_VIEW, on_click=lambda e: self._export_list('xlsx')),
                    ft.OutlinedButton('طباعة القائمة PDF', icon=ft.Icons.PRINT, on_click=lambda e: self._export_list('pdf')),
                    ft.OutlinedButton('إضافة كملحق للتقرير', icon=ft.Icons.PLAYLIST_ADD, on_click=self._add_list_to_report)], wrap=True),
            self.card(self.people_table_holder, padding=6, expand=True),
        ], spacing=12, expand=True)

    def refresh_people_table(self, update=True):
        lab, sub = self.people_subset()
        key, asc = self.people_sort
        idx = [k for k, _, _ in self.PEOPLE_COLS].index(key) if key in [k for k, _, _ in self.PEOPLE_COLS] else None
        cols = [ft.DataColumn(ft.Text(h, weight=ft.FontWeight.BOLD), numeric=num, on_sort=lambda e, k=k: self._sort(k))
                for k, h, num in self.PEOPLE_COLS]
        rows = []
        for x in sub.itertuples():
            cells = []
            for k, _, num in self.PEOPLE_COLS:
                v = getattr(x, k)
                color = None
                if k in ('lu', 'eu', 'unx') and v: color = RED
                if k == 'tr': color = {'متحسن': GREEN, 'متراجع': RED, 'منقطع': MUTED}.get(v)
                txt = ft.Text(str(v), color=color, weight=ft.FontWeight.BOLD if k == 'name' else None,
                              max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, width=230 if k == 'name' else (170 if k in ('job', 'status') else None))
                cells.append(ft.DataCell(txt))
            rows.append(ft.DataRow(cells, on_select_changed=lambda e, n=x.name: self.person_dialog(n)))
        table = ft.DataTable(columns=cols, rows=rows, sort_column_index=idx, sort_ascending=asc, heading_row_color='#EAF1F8',
                             column_spacing=16, data_row_min_height=36, data_row_max_height=40, show_checkbox_column=False)
        self.people_count.value = f'{lab}: {len(sub)} موظفاً'
        self.people_table_holder.controls = [ft.Row([table], scroll=ft.ScrollMode.AUTO)] if rows else [ft.Text('لا يوجد موظفون في هذه المجموعة.', color=MUTED)]
        if update: self.page.update()

    def _set_filter(self, k):
        self.people_filter = k; self.show(2)

    def _people_filter(self, e):
        self.people_filter = e.control.value; self.show(2)

    def _people_search(self, e):
        self.people_query = e.control.value; self.refresh_people_table()

    def _sort(self, key):
        k, asc = self.people_sort
        self.people_sort = (key, not asc if k == key else (key in ('name', 'job', 'tr', 'status')))
        self.refresh_people_table()

    def person_dialog(self, name):
        E = self.S['E']; x = E[E.name == name].iloc[0]
        d = self.r[self.r.name == name].sort_values('date')
        tm = lambda m: f'{int(m) // 60:02d}:{int(m) % 60:02d}' if m else '—'
        stat = lambda lab, v, c=NAVY: ft.Container(ft.Column([ft.Text(lab, size=11, color=MUTED), ft.Text(str(v), size=20, weight=ft.FontWeight.BOLD, color=c)],
                                                             spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER), padding=8, border_radius=8, bgcolor='#F5F7FA',
                                                col={'xs': 6, 'sm': 4, 'md': 3})
        rows = []
        for row in d.itertuples():
            bg = '#FDECEA' if row.status == 'غياب كامل' else ('#FFF4E5' if row.late or row.early else None)
            note = ' '.join(s for s in [row.abs_type, row.perm] if s)
            flags = []
            if row.late: flags.append('تأخير' + (' دون إذن' if row.lu else ''))
            if row.early: flags.append('مبكر' + (' دون إذن' if row.eu else ''))
            if row.full: flags.append('دوام كامل')
            rows.append(ft.DataRow([ft.DataCell(ft.Text(row.date.strftime('%d/%m'))), ft.DataCell(ft.Text(row.day)), ft.DataCell(ft.Text(tm(row.t1m))),
                                    ft.DataCell(ft.Text(tm(row.t2m))), ft.DataCell(ft.Text(tm(row.outm))), ft.DataCell(ft.Text(row.status)),
                                    ft.DataCell(ft.Text('، '.join(flags))), ft.DataCell(ft.Text(note, size=12))], color=bg))
        table = ft.DataTable(columns=[ft.DataColumn(ft.Text(h, weight=ft.FontWeight.BOLD)) for h in ['التاريخ', 'اليوم', 'الحضور', 'T2', 'الانصراف', 'الحالة', 'ملاحظات', 'النظام']],
                             rows=rows, column_spacing=14, data_row_min_height=30, data_row_max_height=34, heading_row_color='#EAF1F8')
        dlg = ft.AlertDialog(
            title=ft.Column([ft.Text(name, weight=ft.FontWeight.BOLD, color=NAVY), ft.Text(f'{x.job} • الرقم المدني {x.cid} • {x.status} • المسار: {x.tr}', size=13, color=MUTED)], spacing=2),
            content=ft.Container(ft.Column([
                ft.ResponsiveRow([stat('الحضور', f'{x.pres}/{x.days}'), stat('الغياب (دون عذر)', f'{x.absd} ({x.unx})', BLUE), stat('التأخير (دون إذن)', f'{x.late} ({x.lu})', ORANGE),
                        stat('دقائق التأخير', x.lmin, ORANGE), stat('مبكر (دون إذن)', f'{x.early} ({x.eu})', AQUA), stat('دوام كامل', x.full, GREEN), stat('متوسط الساعات', f'{x.hours:.2f}')], spacing=6, run_spacing=6),
                ft.Text(f'أسباب الغياب: {x.abs_reasons}', size=12, color=MUTED) if x.abs_reasons else ft.Container(),
                ft.Row([table], scroll=ft.ScrollMode.AUTO) if self.mobile else ft.Container(),
                ft.Column([table], scroll=ft.ScrollMode.AUTO, expand=True) if not self.mobile else ft.Container()], spacing=10,
                scroll=ft.ScrollMode.AUTO if self.mobile else None),
                width=self._dlg_width(), height=self._dlg_height()),
            actions=[ft.FilledButton('تقرير PDF لهذا الموظف', icon=ft.Icons.PICTURE_AS_PDF, on_click=lambda e: self._person_pdf(name)),
                     ft.TextButton('إغلاق', on_click=lambda e: self.page.close(dlg))],
            actions_alignment=ft.MainAxisAlignment.START)
        self.page.open(dlg)

    def _dlg_width(self):
        w = getattr(self.page, 'width', None)
        return min(1000, w - 24) if isinstance(w, (int, float)) and w > 100 else 1000

    def _dlg_height(self):
        h = getattr(self.page, 'height', None)
        return min(560, h - 200) if isinstance(h, (int, float)) and h > 300 else 560

    def _person_pdf(self, name):
        path = os.path.join(self.ensure_out(), f'تقرير موظف - {safe_name(name)}.pdf')
        self.run_bg('إنشاء تقرير الموظف…', lambda: self.R_person(self.r, self.S, self.cfg, name, path),
                    lambda p: self._generated('تقرير موظف: ' + name, p))

    def _export_list(self, kind):
        lab, sub = self.people_subset()
        if sub.empty:
            self.toast('القائمة فارغة', error=True); return
        base = os.path.join(self.ensure_out(), f'قائمة - {safe_name(lab)}')
        if kind == 'xlsx':
            self.run_bg('تصدير القائمة…', lambda: export_people(sub, base + '.xlsx'), lambda p: self._generated(f'قائمة Excel: {lab}', p))
        else:
            show = self.report_opts.get('show_names', True)
            self.run_bg('إنشاء PDF للقائمة…', lambda: self.R_list(sub, lab, self.S, self.cfg, base + '.pdf', show),
                        lambda p: self._generated(f'قائمة PDF: {lab}', p))

    def _add_list_to_report(self, e):
        k = self.people_filter
        if k == 'all':
            self.report_opts['app_roster'] = True; self.toast('سجل جميع الموظفين مضاف إلى التقرير'); return
        if k not in self.report_opts['extra_lists']:
            self.report_opts['extra_lists'].append(k)
        self.toast(f'أضيفت «{filters(self.cfg)[k][0]}» كملحق في التقرير الكامل')

    # ------------------------------------------------------------------ reports
    def ensure_out(self):
        os.makedirs(self.out_dir, exist_ok=True)
        return self.out_dir

    def _generated(self, label, path):
        self.generated.insert(0, (label, path))
        self.toast(f'تم الحفظ: {os.path.basename(path)}')
        if self.rail.selected_index == 3:
            self.show(3)

    def view_reports(self):
        o = self.report_opts; F = filters(self.cfg)
        def opt_box(k, lab):
            return ft.Checkbox(label=lab, value=bool(o.get(k)), on_change=lambda e, k=k: o.__setitem__(k, e.control.value))
        extra = [ft.Checkbox(label=F[k][0], value=k in o['extra_lists'], on_change=lambda e, k=k: self._toggle_extra(k, e.control.value))
                 for k in F if k not in ('all',)]
        files = [ft.ListTile(leading=ft.Icon(ft.Icons.PICTURE_AS_PDF if p.endswith('.pdf') else ft.Icons.IMAGE if p.endswith('.png') else ft.Icons.TABLE_VIEW, color=NAVY),
                             title=ft.Text(lab), subtitle=ft.Text(p, size=11, color=MUTED),
                             trailing=ft.IconButton(ft.Icons.OPEN_IN_NEW, tooltip='فتح', on_click=lambda e, p=p: self.open_file(p)),
                             on_click=lambda e, p=p: self.open_file(p)) for lab, p in self.generated]
        S = self.S
        return ft.Column([
            self.title('التقارير', f"{S['period']} • {S['ALL']['emp']} موظفاً • كل الأعداد بالأفراد"),
            self.card(ft.Row([ft.Icon(ft.Icons.FOLDER, color=NAVY), ft.Text(f'مجلد الحفظ: {self.out_dir}', expand=True),
                              ft.OutlinedButton('تغيير', on_click=lambda e: self.fp_dir.get_directory_path(dialog_title='اختر مجلد الحفظ')),
                              ft.OutlinedButton('فتح المجلد', on_click=lambda e: self.open_file(self.ensure_out()), visible=not self.mobile)], wrap=True)),
            ft.ResponsiveRow([
                self._col(self.card(ft.Column([ft.Text('إنشاء', size=17, weight=ft.FontWeight.BOLD, color=NAVY),
                                     ft.FilledButton('التقرير الكامل (PDF)', icon=ft.Icons.PICTURE_AS_PDF, on_click=self.gen_report),
                                     ft.FilledButton('الإنفوجرافيك (PDF)' if self.lite else 'الإنفوجرافيك (PNG + PDF)', icon=ft.Icons.INSIGHTS, on_click=self.gen_info),
                                     ft.FilledButton('ملف Excel التفاعلي (10 أوراق)', icon=ft.Icons.TABLE_CHART, on_click=self.gen_xlsx),
                                     ft.OutlinedButton('جدول جميع الموظفين (Excel)', icon=ft.Icons.TABLE_VIEW, on_click=self.gen_people_xlsx),
                                     ft.Divider(),
                                     ft.FilledTonalButton('إنشاء الكل', icon=ft.Icons.DONE_ALL, on_click=self.gen_all),
                                     ft.Text('ملف Excel يحسب معادلاته عند فتحه في Excel.' + (' على الهاتف: الإنفوجرافيك PDF فقط، وتُحفظ الملفات في مجلد التنزيلات/AttendanceReports.' if self.mobile else ''), size=11, color=MUTED)], spacing=10)), {'xs': 12, 'md': 4}),
                self._col(self.card(ft.Column([ft.Text('محتوى التقرير الكامل', size=17, weight=ft.FontWeight.BOLD, color=NAVY),
                                     ft.Row([ft.Column([opt_box(k, lab) for k, lab in report.OPTION_LABELS[:7]], spacing=0),
                                             ft.Column([opt_box(k, lab) for k, lab in report.OPTION_LABELS[7:]], spacing=0)], vertical_alignment=ft.CrossAxisAlignment.START, wrap=True),
                                     ft.Text('ملاحق إضافية بأسماء الموظفين', size=15, weight=ft.FontWeight.BOLD, color=NAVY),
                                     ft.Row(extra, wrap=True, spacing=4, run_spacing=0)], spacing=8)), {'xs': 12, 'md': 8}),
            ], vertical_alignment=ft.CrossAxisAlignment.START, spacing=12, run_spacing=12),
            self.card(ft.Column([ft.Text('الملفات المُنشأة', size=17, weight=ft.FontWeight.BOLD, color=NAVY)] +
                                (files or [ft.Text('لم يُنشأ أي ملف بعد.', color=MUTED)]), spacing=4)),
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    def _toggle_extra(self, k, on):
        L = self.report_opts['extra_lists']
        if on and k not in L: L.append(k)
        if not on and k in L: L.remove(k)

    def _on_pick_dir(self, e):
        if e.path:
            self.out_dir = e.path; self.show(3)

    def _on_save_result(self, e):
        pass

    def _stamp(self):
        S = self.S
        return f"{S['period_short'].replace('/', '-')}"

    def _report_path(self): return os.path.join(self.ensure_out(), f'تقرير الحضور {self._stamp()}.pdf')
    def _info_paths(self):
        b = os.path.join(self.ensure_out(), f'إنفوجرافيك الحضور {self._stamp()}')
        return b + '.png', b + '.pdf'
    def _xlsx_path(self): return os.path.join(self.ensure_out(), f'تحليل الحضور {self._stamp()}.xlsx')

    def gen_report(self, e=None):
        p = self._report_path()
        self.run_bg('إنشاء التقرير الكامل…', lambda: self.R_full(self.S, self.cfg, p, self.report_opts),
                    lambda r_: self._generated('التقرير الكامل', p))

    def gen_info(self, e=None):
        png, pdf = self._info_paths()
        def done(_):
            self._generated('الإنفوجرافيك (PDF)', pdf)
            if not self.lite: self._generated('الإنفوجرافيك (صورة)', png)
        self.run_bg('إنشاء الإنفوجرافيك…', lambda: self.R_info(self.S, self.cfg, None if self.lite else png, pdf), done)

    def gen_xlsx(self, e=None):
        p = self._xlsx_path()
        self.run_bg('إنشاء ملف Excel (قد يستغرق دقيقة)…', lambda: workbook.build_workbook(self.r, p, self.cfg), lambda r_: self._generated('ملف Excel التفاعلي', p))

    def gen_people_xlsx(self, e=None):
        p = os.path.join(self.ensure_out(), f'جميع الموظفين {self._stamp()}.xlsx')
        self.run_bg('تصدير الجدول…', lambda: export_people(self.S['E'], p), lambda r_: self._generated('جدول جميع الموظفين', p))

    def gen_all(self, e=None):
        rp = self._report_path(); png, pdf = self._info_paths(); xp = self._xlsx_path()
        def job():
            self.busy_text.value = 'التقرير الكامل…'; self.page.update()
            self.R_full(self.S, self.cfg, rp, self.report_opts)
            self.busy_text.value = 'الإنفوجرافيك…'; self.page.update()
            self.R_info(self.S, self.cfg, None if self.lite else png, pdf)
            self.busy_text.value = 'ملف Excel…'; self.page.update()
            workbook.build_workbook(self.r, xp, self.cfg)
            return True
        def done(_):
            for lab, p in [('ملف Excel التفاعلي', xp)] + ([] if self.lite else [('الإنفوجرافيك (صورة)', png)]) + [('الإنفوجرافيك (PDF)', pdf), ('التقرير الكامل', rp)]:
                self.generated.insert(0, (lab, p))
            self.toast('تم إنشاء جميع الملفات'); self.show(3)
        self.run_bg('إنشاء جميع الملفات…', job, done)

    # ------------------------------------------------------------------ settings
    def view_settings(self):
        c = self.cfg
        def tf(label, val, width=220, **kw): return ft.TextField(label=label, value=str(val), width=width, dense=True, **kw)
        self.s_fields = dict(
            school_name=tf('اسم المدرسة', c.school_name, 520), org_line=tf('سطر الجهة (أعلى التقرير)', c.org_line, 720),
            sig1=tf('التوقيع 1', c.signatures[0] if len(c.signatures) > 0 else ''), sig2=tf('التوقيع 2', c.signatures[1] if len(c.signatures) > 1 else ''),
            sig3=tf('التوقيع 3', c.signatures[2] if len(c.signatures) > 2 else ''),
            late_from=tf('التأخير: الحضور عند أو بعد (HH:MM)', c.late_from), early_before=tf('الانصراف المبكر: قبل (HH:MM)', c.early_before),
            day_start=tf('بداية احتساب النصاب (HH:MM)', c.day_start), full_minutes=tf('نصاب الدوام الكامل (دقيقة)', c.full_minutes),
            t2_min=tf('نافذة T2 من (دقيقة بعد T1)', c.t2_min), t2_max=tf('نافذة T2 إلى (دقيقة بعد T1)', c.t2_max),
            repeat_threshold=tf('حد التكرار (مرات)', c.repeat_threshold), trend_delta=tf('حد تغير المسار (مثال 0.10)', c.trend_delta))
        f = self.s_fields
        return ft.Column([
            self.title('الإعدادات', 'تُحفظ تلقائياً وتُطبق على كل التقارير.'),
            self.card(ft.Column([ft.Text('بيانات الجهة', size=17, weight=ft.FontWeight.BOLD, color=NAVY), f['school_name'], f['org_line'],
                                 ft.Row([f['sig1'], f['sig2'], f['sig3']], wrap=True)], spacing=10)),
            self.card(ft.Column([ft.Text('قواعد الاحتساب', size=17, weight=ft.FontWeight.BOLD, color=NAVY),
                                 ft.Row([f['late_from'], f['early_before'], f['day_start'], f['full_minutes']], wrap=True),
                                 ft.Row([f['t2_min'], f['t2_max'], f['repeat_threshold'], f['trend_delta']], wrap=True),
                                 ft.Text('الغياب دون عذر = حالة «غياب» أو «منقطع» في النظام، أو يوم بلا أي بصمة وبلا إجازة. «دون إذن» = لا يوجد إذن مسجل في النظام يغطي الحالة.', size=12, color=MUTED)], spacing=10)),
            ft.Row([ft.FilledButton('حفظ وإعادة الحساب', icon=ft.Icons.SAVE, on_click=self._save_settings),
                    ft.TextButton('استعادة القيم الافتراضية', on_click=self._reset_settings),
                    ft.TextButton('مسح الذاكرة المؤقتة للملفات', on_click=self._clear_cache)]),
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    def _save_settings(self, e):
        f = self.s_fields; c = self.cfg
        old = dict(c.__dict__)
        try:
            c.school_name = f['school_name'].value.strip(); c.org_line = f['org_line'].value.strip()
            c.signatures = [f[k].value.strip() for k in ('sig1', 'sig2', 'sig3') if f[k].value.strip()]
            for k in ('late_from', 'early_before', 'day_start'):
                v = f[k].value.strip(); to_min(v); setattr(c, k, v)
            c.full_minutes = int(f['full_minutes'].value); c.t2_min = int(f['t2_min'].value); c.t2_max = int(f['t2_max'].value)
            c.repeat_threshold = int(f['repeat_threshold'].value); c.trend_delta = float(f['trend_delta'].value)
            errs = c.validate()
            if errs: raise ValueError('؛ '.join(errs))
        except Exception as ex:
            c.__dict__.update(old)
            self.toast(f'قيمة غير صالحة: {ex}', error=True); return
        c.save()
        if self.raw and self.recompute():
            self.toast('تم الحفظ وإعادة الحساب')
        else:
            self.toast('تم حفظ الإعدادات')
        self.show(4)

    def _reset_settings(self, e):
        keep = dict(start_date=self.cfg.start_date, end_date=self.cfg.end_date, excluded_dates=self.cfg.excluded_dates, workdays=self.cfg.workdays)
        self.cfg = Settings(**keep); self.cfg.save()
        if self.raw: self.recompute()
        self.show(4); self.toast('تمت استعادة القيم الافتراضية')

    def _clear_cache(self, e):
        from core.parser import CACHE_DIR
        n = 0
        if os.path.isdir(CACHE_DIR):
            for fn in os.listdir(CACHE_DIR):
                os.remove(os.path.join(CACHE_DIR, fn)); n += 1
        self.toast(f'تم حذف {n} ملف مؤقت')


def main(page: ft.Page):
    App(page)


if __name__ == '__main__':
    ft.app(target=main)
