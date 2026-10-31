import pandas as pd, numpy as np
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as CL
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.comments import Comment
from datetime import time

def build_workbook(r, out_path, cfg, progress=None):
    """Interactive 10-sheet workbook driven by formulas (Excel recalculates on open)."""
    r = r.copy()
    LT = cfg.late_min; LT1 = LT - 1; EB = cfg.early_min
    DSH, DSM = divmod(cfg.start_min, 60); FQ = int(cfg.full_minutes); FQH, FQM = divmod(FQ, 60)
    T2A, T2B = int(cfg.t2_min), int(cfg.t2_max); REP = int(cfg.repeat_threshold); TRD = float(cfg.trend_delta)
    LATE_S, EARLY_S, DS_S = cfg.late_from, cfg.early_before, cfg.day_start
    FQ_S = f'{FQH}:{FQM:02d}'; FQ_HRS = round(FQ / 60, 2)
    T2A_S = f'{T2A // 60}:{T2A % 60:02d}'; T2B_S = f'{T2B // 60}:{T2B % 60:02d}'
    say = progress or (lambda msg: None)
    emp=r.drop_duplicates('cid')[['cid','name','job','fileno']].sort_values('name').reset_index(drop=True)
    names=emp.name.tolist(); NE=len(names)
    N=len(r); LAST=N+1
    dates=sorted(r.date.unique()); weeks=sorted(r.week.unique()); LW=max(weeks)
    wk_range={w:(r[r.week==w].date.min(),r[r.week==w].date.max()) for w in weeks}
    SCHOOL=cfg.school_name
    DAYS=[d for d in ['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'] if d in set(r.day)]
    MODEL=names[0]
    PERIOD=f'{str(dates[0])[:10]} إلى {str(dates[-1])[:10]}'
    NAVY='1F3864'; TEAL='0E7C86'; LIGHT='EAF1F8'; GRAY='F4F6F8'; WHITE='FFFFFF'
    thin=Side(style='thin',color='C9D3DF'); B=Border(left=thin,right=thin,top=thin,bottom=thin)
    F=lambda **k: Font(name='Arial',**k)
    def fill(c): return PatternFill('solid',fgColor=c)
    CENTER=Alignment(horizontal='center',vertical='center',wrap_text=True)
    RIGHT=Alignment(horizontal='right',vertical='center',wrap_text=True)
    wb=Workbook(); wb.remove(wb.active)
    order=['تقرير_الموظف_الفردي','تحليل_الاتجاهات_الأسبوعية','تقرير_الأسبوع_الجديد','لوحة_المؤشرات_والملخص','المتأخرون_باستمرار','جدول_الغياب_والانقطاع','قائمة_الاستئذانات_المحتملة','الانصراف_المبكر_والاستثناءات','سجل_دوام_العاملين_Roster','سجل_البصمات_الشامل']
    S={n:wb.create_sheet(n) for n in order}
    for ws in S.values(): ws.sheet_view.rightToLeft=True; ws.sheet_view.showGridLines=False
    def q(n): return f"'{n}'"
    RAW=q('سجل_البصمات_الشامل'); ROS=q('سجل_دوام_العاملين_Roster')
    def title(ws,text,sub,ncols):
        ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=ncols)
        c=ws.cell(1,1,text); c.font=F(bold=True,size=16,color=WHITE); c.fill=fill(NAVY); c.alignment=CENTER; ws.row_dimensions[1].height=34
        ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=ncols)
        c=ws.cell(2,1,sub); c.font=F(size=10,color='44546A',italic=True); c.alignment=CENTER; ws.row_dimensions[2].height=32
    def header(ws,row,col,labels,color=NAVY):
        for i,l in enumerate(labels):
            c=ws.cell(row,col+i,l); c.font=F(bold=True,color=WHITE,size=10); c.fill=fill(color); c.alignment=CENTER; c.border=B
        ws.row_dimensions[row].height=40
    def cellw(ws,row,col,val,fmt=None,bold=False,bg=None,align=CENTER,color=None,size=10):
        c=ws.cell(row,col,val); c.font=F(bold=bold,size=size,color=color); c.alignment=align; c.border=B
        if fmt: c.number_format=fmt
        if bg: c.fill=fill(bg)
        return c
    def section(ws,row,col,text,ncols,color=TEAL):
        ws.merge_cells(start_row=row,start_column=col,end_row=row,end_column=col+ncols-1)
        c=ws.cell(row,col,text); c.font=F(bold=True,size=12,color=WHITE); c.fill=fill(color); c.alignment=RIGHT; ws.row_dimensions[row].height=24
    def widths(ws,lst):
        for i,w in enumerate(lst): ws.column_dimensions[CL(i+1)].width=w
    def cf_text(ws,rng,txt,bg=None,font=None):
        first=rng.split(':')[0]
        ws.conditional_formatting.add(rng,FormulaRule(formula=[f'ISNUMBER(SEARCH("{txt}",{first}))'],fill=fill(bg) if bg else None,font=font,stopIfTrue=bool(bg)))
    PCT='0.0%'; TM='hh:mm'; DT='yyyy-mm-dd'; H2='0.00'; DPCT='+0.0%;-0.0%;0.0%'
    def tm(m): return time(m//60,m%60)

    # ===== RAW
    ws=S['سجل_البصمات_الشامل']
    cols=['م','الرقم المدني','الاسم','الوظيفة','التاريخ','اليوم','الأسبوع','الحضور T1','التواجد T2','الانصراف','حالة الغياب/الإجازة (النظام)','الإذن/الاستثناء المسجل (النظام)','بصمة التواجد (النظام)','تأخير النظام (د)','حالة اليوم',f'تأخير صباحي (≥{LATE_S})','دقائق التأخير','الفارق T2−T1 (د)','حالة نافذة T2','فرق النافذة (د)','بداية النصاب','الانصراف المطلوب','ساعات العمل الفعلية','الفرق عن النصاب (د)',f'انصراف مبكر (<{EARLY_S})','دوام كامل مكتمل','التصنيف الرئيسي لليوم','تبرير التأخير','تبرير الانصراف المبكر','حاضر','التزام T2','ملزم بـ T2 وله بصمة دخول']
    header(ws,1,1,cols)
    for i,row in enumerate(r.itertuples(),start=2):
        n=i
        vals=[i-1,row.cid,row.name,row.job,row.date.to_pydatetime().date(),row.day,int(row.week),tm(row.t1m),tm(row.t2m),tm(row.outm),row.abs_type,row.perm,'غير ملزم' if row.t2_exempt else '',int(row.sys_late)]
        for j,v in enumerate(vals,1): ws.cell(n,j,v)
        f=[f'=IF(OR(K{n}<>"",AND(H{n}=0,I{n}=0,J{n}=0)),"غياب كامل",IF(AND(H{n}>0,J{n}>0),"حضور مكتمل","بصمة ناقصة"))',
           f'=IF(AND(H{n}>0,ROUND(H{n}*1440,0)>={LT}),1,0)',
           f'=IF(P{n}=1,ROUND(H{n}*1440,0)-{LT1},0)',
           f'=IF(AND(H{n}>0,I{n}>0),ROUND((I{n}-H{n})*1440,0),"")',
           f'=IF(H{n}=0,IF(I{n}>0,"بلا بصمة دخول","—"),IF(M{n}="غير ملزم","غير ملزم ببصمة التواجد",IF(I{n}=0,"لم تسجل بصمة تواجد",IF(R{n}<{T2A},"مبكر عن النافذة",IF(R{n}>{T2B},"متأخر عن النافذة","ملتزم بالنافذة")))))',
           f'=IF(R{n}="","",IF(R{n}<{T2A},{T2A}-R{n},IF(R{n}>{T2B},R{n}-{T2B},0)))',
           f'=IF(H{n}>0,MAX(H{n},TIME({DSH},{DSM},0)),"")',
           f'=IF(H{n}>0,U{n}+TIME({FQH},{FQM},0),"")',
           f'=IF(AND(H{n}>0,J{n}>0),ROUND((J{n}-H{n})*24,2),0)',
           f'=IF(AND(H{n}>0,J{n}>0),ROUND((J{n}-V{n})*1440,0),"")',
           f'=IF(AND(J{n}>0,ROUND(J{n}*1440,0)<{EB}),1,0)',
           f'=IF(AND(H{n}>0,J{n}>0),IF(ROUND(J{n}*1440,0)>=ROUND(V{n}*1440,0),1,0),0)',
           f'=IF(O{n}="غياب كامل","غياب",IF(P{n}=1,"تأخير صباحي",IF(Y{n}=1,"انصراف مبكر / استئذان",IF(Z{n}=1,"دوام كامل مكتمل","بصمة ناقصة / نقص نصاب"))))',
           f'=IF(P{n}=1,IF(OR(ISNUMBER(SEARCH("الحضور",L{n})),ISNUMBER(SEARCH("تخفيف",L{n}))),"مبرر بإذن مسجل","غير مبرر بالنظام"),"")',
           f'=IF(Y{n}=1,IF(OR(ISNUMBER(SEARCH("الانصراف",L{n})),ISNUMBER(SEARCH("تخفيف",L{n})),ISNUMBER(SEARCH("إعفاء",L{n}))),"مبرر بإذن مسجل","غير مبرر بالنظام"),"")',
           f'=IF(O{n}="غياب كامل",0,1)',
           f'=IF(S{n}="ملتزم بالنافذة",1,0)',
           f'=IF(AND(H{n}>0,M{n}<>"غير ملزم"),1,0)']
        for j,v in enumerate(f,15): ws.cell(n,j,v)
    for col,fmt in [('E',DT),('H',TM),('I',TM),('J',TM),('U',TM),('V',TM),('W',H2)]:
        for n in range(2,LAST+1): ws[f'{col}{n}'].number_format=fmt
    for n in range(2,LAST+1):
        ws.cell(n,2).number_format='@'
        for j in range(1,len(cols)+1):
            c=ws.cell(n,j); c.font=F(size=9); c.alignment=CENTER
    ws.freeze_panes='D2'; ws.auto_filter.ref=f"A1:{CL(len(cols))}{LAST}"
    widths(ws,[6,14,30,22,11,9,7,8,8,8,18,22,10,8,12,9,9,9,18,9,9,10,9,10,9,9,20,14,14,6,6,8])
    ws.conditional_formatting.add(f'O2:O{LAST}',CellIsRule(operator='equal',formula=['"غياب كامل"'],fill=fill('F8D7DA')))
    ws.conditional_formatting.add(f'O2:O{LAST}',CellIsRule(operator='equal',formula=['"بصمة ناقصة"'],fill=fill('FFF3CD')))
    for c_ in 'PY': ws.conditional_formatting.add(f'{c_}2:{c_}{LAST}',CellIsRule(operator='equal',formula=['1'],fill=fill('FCE4D6')))
    ws.conditional_formatting.add(f'Z2:Z{LAST}',CellIsRule(operator='equal',formula=['1'],fill=fill('D4EDDA')))
    cf_text(ws,f'AB2:AC{LAST}','غير مبرر',font=Font(color='C0392B',bold=True))
    NM={'R_CID':'B','R_NAME':'C','R_DATE':'E','R_DAY':'F','R_WEEK':'G','R_ABS':'K','R_PERM':'L','R_STAT':'O','R_LATE':'P','R_LATEMIN':'Q','R_T2S':'S','R_HOURS':'W','R_EARLY':'Y','R_FULL':'Z','R_CAT':'AA','R_LJ':'AB','R_EJ':'AC','R_PRES':'AD','R_T2OK':'AE','R_HAST1':'AF'}
    for k,c in NM.items(): wb.defined_names[k]=DefinedName(k,attr_text=f"{RAW}!${c}$2:${c}${LAST}")
    D=S['لوحة_المؤشرات_والملخص']
    wb.defined_names['LatestWeek']=DefinedName('LatestWeek',attr_text=f"{q('لوحة_المؤشرات_والملخص')}!$C$6")

    # ===== ROSTER
    R=S['سجل_دوام_العاملين_Roster']
    rcols=['م','الرقم المدني','الاسم','الوظيفة','أيام العمل','أيام الحضور','أيام الغياب (الكل)','منها إجازات/أعذار رسمية','منها غياب بدون عذر','بصمة ناقصة','تأخير صباحي','منه غير مبرر','إجمالي دقائق التأخير','انصراف مبكر','منه غير مبرر','دوام كامل مكتمل','التزام نافذة T2','نسبة الحضور','نسبة إتمام الدوام','متوسط ساعات العمل','مؤشر الالتزام التاريخي (الأسابيع السابقة)','مؤشر الالتزام: الأسبوع الأحدث','التغير','مؤشر اتجاه الأداء','التصنيف التشغيلي','تصنيف الانصراف المبكر']
    NC_R=len(rcols)
    title(R,f'سجل دوام العاملين التراكمي (Roster): {SCHOOL}',f'الفترة {PERIOD} • {NE} موظفاً مرتبطين بالرقم المدني • جميع القيم معادلات ديناميكية مرتبطة بسجل_البصمات_الشامل • مؤشر الالتزام = أيام الدوام الكامل ÷ أيام العمل • الغياب بدون عذر = «غياب» أو «منقطع عن العمل» في النظام',NC_R)
    header(R,4,1,rcols)
    R0=5; RL=R0+NE-1
    for i,e in emp.iterrows():
        n=R0+i; C=f'$C{n}'
        vals=[i+1,e.cid,e['name'],e.job,
          f'=COUNTIF(R_NAME,{C})',f'=COUNTIFS(R_NAME,{C},R_PRES,1)',f'=COUNTIFS(R_NAME,{C},R_STAT,"غياب كامل")',f'=G{n}-I{n}',
          f'=COUNTIFS(R_NAME,{C},R_ABS,"غياب*")+COUNTIFS(R_NAME,{C},R_ABS,"منقطع*")',
          f'=COUNTIFS(R_NAME,{C},R_STAT,"بصمة ناقصة")',f'=COUNTIFS(R_NAME,{C},R_LATE,1)',f'=COUNTIFS(R_NAME,{C},R_LJ,"غير مبرر*")',f'=SUMIFS(R_LATEMIN,R_NAME,{C})',
          f'=COUNTIFS(R_NAME,{C},R_EARLY,1)',f'=COUNTIFS(R_NAME,{C},R_EJ,"غير مبرر*")',f'=COUNTIFS(R_NAME,{C},R_FULL,1)',
          f'=IFERROR(COUNTIFS(R_NAME,{C},R_T2OK,1)/COUNTIFS(R_NAME,{C},R_HAST1,1),"غير ملزم")',
          f'=IF(E{n}=0,0,F{n}/E{n})',f'=IF(E{n}=0,0,P{n}/E{n})',
          f'=IFERROR(SUMIFS(R_HOURS,R_NAME,{C})/COUNTIFS(R_NAME,{C},R_HOURS,">0"),0)',
          f'=IFERROR(COUNTIFS(R_NAME,{C},R_WEEK,"<"&LatestWeek,R_FULL,1)/COUNTIFS(R_NAME,{C},R_WEEK,"<"&LatestWeek),0)',
          f'=IFERROR(COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek,R_FULL,1)/COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek),0)',
          f'=V{n}-U{n}',
          f'=IF(COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek,R_STAT,"غياب كامل")=COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek),"منقطع ✕",IF(W{n}>={TRD},"متحسن ↑",IF(W{n}<=-{TRD},"متراجع ↓","مستقر ═")))',
          f'=IF(G{n}=E{n},IF(I{n}>0,"منقطع كلياً","إجازة/إعفاء طوال الفترة"),IF(I{n}>={REP},"غياب متكرر بدون عذر",IF(N{n}>={REP},"تخفيف عمل / استثناء دوام",IF(K{n}>={REP},"متأخر باستمرار",IF(S{n}>=0.9,"ملتزم","ملتزم جزئياً")))))',
          f'=IF(N{n}=0,"—",IF(N{n}>={REP},"استثناء دوام يومي متكرر / تخفيف عمل","استئذان خروج مبكر عرضي"))']
        for j,v in enumerate(vals,1): cellw(R,n,j,v,bg=GRAY if i%2 else None,align=RIGHT if j in (3,4) else CENTER,size=9)
        R.cell(n,2).number_format='@'
        for j in (17,18,19,21,22): R.cell(n,j).number_format=PCT
        R.cell(n,23).number_format=DPCT; R.cell(n,20).number_format=H2
    R.freeze_panes='D5'; R.auto_filter.ref=f'A4:{CL(NC_R)}{RL}'
    widths(R,[5,14,30,24,7,7,8,9,9,7,7,7,9,7,7,8,8,8,8,8,11,11,8,11,20,24])
    for t,c in [('متحسن','D4EDDA'),('متراجع','F8D7DA'),('منقطع','D6D8DB')]: cf_text(R,f'X{R0}:X{RL}',t,c)
    for t,c in [('منقطع','D6D8DB'),('إجازة','DDEBF7'),('غياب','F8D7DA'),('متأخر','FCE4D6'),('تخفيف','FFF3CD'),('ملتزم جزئياً','EAF1F8'),('ملتزم','D4EDDA')]: cf_text(R,f'Y{R0}:Y{RL}',t,c)
    wb.defined_names['ROS_NAMES']=DefinedName('ROS_NAMES',attr_text=f"{ROS}!$C${R0}:$C${RL}")
    def RC(col): return f"{ROS}!${col}${R0}:${col}${RL}"

    MH=['الموظفون','متوسط الحاضرين يومياً','نسبة الحضور','غابوا (أفراد)','منهم بدون عذر (أفراد)','غائبون طوال المدة (أفراد)','تأخروا (أفراد)','منهم دون إذن (أفراد)','انصرفوا مبكراً (أفراد)','منهم دون إذن (أفراد)','بصمة ناقصة (أفراد)','دوام كامل في كل أيام حضورهم (أفراد)','التزام نافذة T2','متوسط ساعات العمل']
    NMH=len(MH)
    def P_(crit,extra=''):
        # number of distinct employees with at least one matching record
        return f'SUMPRODUCT(--(COUNTIFS(R_NAME,ROS_NAMES,{crit}{extra})>0))'
    def people_formulas(crit,L,n):
        k1,k2=crit.split(',',1)
        tot=f'COUNTIFS(R_NAME,ROS_NAMES,{crit})'
        return [f'={P_(crit)}',
           f'=IFERROR(COUNTIFS({crit},R_PRES,1)/(COUNTIFS({crit})/{L(0)}{n}),0)',
           f'=IFERROR(COUNTIFS({crit},R_PRES,1)/COUNTIFS({crit}),0)',
           f'={P_(crit,",R_STAT,\"غياب كامل\"")}',
           f'=SUMPRODUCT(--((COUNTIFS(R_NAME,ROS_NAMES,{crit},R_ABS,"غياب*")+COUNTIFS(R_NAME,ROS_NAMES,{crit},R_ABS,"منقطع*"))>0))',
           f'=SUMPRODUCT(({tot}>0)*(COUNTIFS(R_NAME,ROS_NAMES,{crit},R_STAT,"غياب كامل")={tot}))',
           f'={P_(crit,",R_LATE,1")}',f'={P_(crit,",R_LJ,\"غير مبرر*\"")}',
           f'={P_(crit,",R_EARLY,1")}',f'={P_(crit,",R_EJ,\"غير مبرر*\"")}',
           f'={P_(crit,",R_STAT,\"بصمة ناقصة\"")}',
           f'=SUMPRODUCT((COUNTIFS(R_NAME,ROS_NAMES,{crit},R_PRES,1)>0)*(COUNTIFS(R_NAME,ROS_NAMES,{crit},R_FULL,1)=COUNTIFS(R_NAME,ROS_NAMES,{crit},R_PRES,1)))',
           f'=IFERROR(COUNTIFS({crit},R_T2OK,1)/COUNTIFS({crit},R_HAST1,1),0)',
           f'=IFERROR(SUMIFS(R_HOURS,{k1},{k2})/COUNTIFS({crit},R_HOURS,">0"),0)']
    def fmt_cell(c,k):
        if k in (2,12): c.number_format=PCT
        elif k==13: c.number_format=H2
        elif k==1: c.number_format='0.0'
    def write_metric_row(ws,n,c0,crit,bg=None):
        L=lambda k: CL(c0+k)
        for k,v in enumerate(people_formulas(crit,L,n)):
            fmt_cell(cellw(ws,n,c0+k,v,bg=bg),k)
    def total_row(ws,n,c0,r0,r1,crit_all):
        L=lambda k: CL(c0+k)
        for k,v in enumerate(people_formulas(crit_all,L,n)):
            fmt_cell(cellw(ws,n,c0+k,v,bold=True,bg=LIGHT),k)
    NC=2+NMH  # 16
    def place(ws,ch,anchor,w=16,h=8.5): ch.width=w; ch.height=h; ws.add_chart(ch,anchor)
    # metric column letters (c0=3): C cnt,D pres,E abs,F unexc,G att,H late,I lateU,J early,K earlyU,L inc,M full,N comp,O t2,P hrs
    # ===== TRENDS
    T=S['تحليل_الاتجاهات_الأسبوعية']
    title(T,f'تحليل الاتجاهات الأسبوعية (Trends): {SCHOOL}',f'مقارنة الأسبوع الأحدث (الأسبوع {LW}) بالأسبوع السابق وبالمسار التاريخي منذ الأسبوع الأول • الأسبوع الأحدث يُضبط من الخلية C6 في لوحة المؤشرات',NC)
    section(T,13,1,'جدول (1): المسار الأسبوعي للمؤشرات من الأسبوع الأول حتى الأحدث',NC)
    header(T,14,1,['الأسبوع','الفترة']+MH)
    W0=15
    for i,w in enumerate(weeks):
        n=W0+i; cellw(T,n,1,int(w),bold=True); cellw(T,n,2,f"{wk_range[w][0].strftime('%d/%m')} – {wk_range[w][1].strftime('%d/%m')}")
        write_metric_row(T,n,3,f'R_WEEK,$A{n}',bg=GRAY if i%2 else None)
    WL=W0+len(weeks)-1
    section(T,3,1,'بطاقات المقارنة: الأسبوع الأحدث مقابل الأسبوع السابق',NC)
    cards=[('نسبة الحضور','E',PCT,1),('متوسط الحاضرين يومياً','D','0.0',1),('التزام نافذة T2','O',PCT,1),('متوسط ساعات العمل','P',H2,1),('موظفون غابوا','F','0',-1),('غابوا بدون عذر (أفراد)','G','0',-1),('موظفون تأخروا','I','0',-1),('موظفون انصرفوا مبكراً','K','0',-1)]
    for idx,(lab,col,fmt,good) in enumerate(cards):
        rr=4+(idx//4)*4; cc=1+(idx%4)*4
        T.merge_cells(start_row=rr,start_column=cc,end_row=rr,end_column=cc+3); cellw(T,rr,cc,lab,bold=True,bg=LIGHT,color=NAVY)
        T.merge_cells(start_row=rr+1,start_column=cc,end_row=rr+1,end_column=cc+3)
        cur=f'INDEX({col}{W0}:{col}{WL},MATCH(LatestWeek,A{W0}:A{WL},0))'; prev=f'INDEX({col}{W0}:{col}{WL},MATCH(LatestWeek-1,A{W0}:A{WL},0))'
        cellw(T,rr+1,cc,f'={cur}',fmt=fmt,bold=True,size=18,color=NAVY)
        T.merge_cells(start_row=rr+2,start_column=cc+2,end_row=rr+2,end_column=cc+3); T.merge_cells(start_row=rr+3,start_column=cc+2,end_row=rr+3,end_column=cc+3)
        cellw(T,rr+2,cc,'السابق',size=8,color='666666'); cellw(T,rr+2,cc+1,'التغير',size=8,color='666666'); cellw(T,rr+2,cc+2,'الاتجاه',size=8,color='666666')
        cellw(T,rr+3,cc,f'={prev}',fmt=fmt); cellw(T,rr+3,cc+1,f'={cur}-{prev}',fmt=(DPCT if fmt==PCT else ('+0.00;-0.00;0.00' if fmt==H2 else '+0;-0;0')))
        cellw(T,rr+3,cc+2,f'=IF({cur}-{prev}=0,"═ ثابت",IF(({cur}-{prev})*{good}>0,"▲ تحسن","▼ تراجع"))',bold=True)
        for k in range(4):
            for rw in range(rr,rr+4): T.cell(rw,cc+k).border=B
        T.row_dimensions[rr+1].height=30
    for rw in (7,11):
        T.conditional_formatting.add(f'A{rw}:P{rw}',FormulaRule(formula=[f'ISNUMBER(SEARCH("تحسن",A{rw}))'],font=Font(color='1E7B34',bold=True)))
        T.conditional_formatting.add(f'A{rw}:P{rw}',FormulaRule(formula=[f'ISNUMBER(SEARCH("تراجع",A{rw}))'],font=Font(color='C0392B',bold=True)))
    DR=WL+3
    section(T,DR,1,'جدول (2): الأنماط السلوكية حسب أيام الأسبوع (تراكمي لجميع الأسابيع)',NC)
    header(T,DR+1,1,['اليوم','عدد الأيام']+MH)
    D0=DR+2
    for i,dn in enumerate(DAYS):
        n=D0+i; cellw(T,n,1,dn,bold=True); cellw(T,n,2,int(r[r.day==dn].date.nunique()))
        write_metric_row(T,n,3,f'R_DAY,$A{n}',bg=GRAY if i%2 else None)
    DL=D0+4
    PR=DL+3
    section(T,PR,1,'جدول (3): تصنيف مسارات الموظفين الفردية (الأسبوع الأحدث مقابل المعدل التاريخي)',NC)
    header(T,PR+1,1,['المسار','عدد الموظفين','النسبة'])
    P0=PR+2
    for i,lab in enumerate(['مستقر ═','متحسن ↑','متراجع ↓','منقطع ✕']):
        n=P0+i; cellw(T,n,1,lab,bold=True); cellw(T,n,2,f'=COUNTIF({RC("X")},A{n})'); cellw(T,n,3,f'=B{n}/SUM($B${P0}:$B${P0+3})',fmt=PCT)
    cellw(T,P0+4,1,'قاعدة التصنيف',bold=True,bg=LIGHT)
    T.merge_cells(start_row=P0+4,start_column=2,end_row=P0+4,end_column=NC)
    cellw(T,P0+4,2,f'متحسن: ارتفاع مؤشر الالتزام في الأسبوع الأحدث {TRD*100:g} نقاط مئوية فأكثر عن المعدل التاريخي. متراجع: انخفاض {TRD*100:g} نقاط فأكثر. مستقر: تغير أقل من {TRD*100:g} نقاط. منقطع: غياب كامل (بأي سبب) طوال أيام الأسبوع الأحدث.',align=RIGHT,size=9)
    T.row_dimensions[P0+4].height=32
    ER=P0+6
    header(T,ER,1,['م','الاسم','','','المؤشر التاريخي','الأسبوع الأحدث','التغير','المسار','التصنيف التشغيلي'])
    T.merge_cells(start_row=ER,start_column=2,end_row=ER,end_column=4)
    for i in range(NE):
        n=ER+1+i; rn=R0+i
        cellw(T,n,1,i+1); T.merge_cells(start_row=n,start_column=2,end_row=n,end_column=4); cellw(T,n,2,f'={ROS}!C{rn}',align=RIGHT)
        cellw(T,n,5,f'={ROS}!U{rn}',fmt=PCT); cellw(T,n,6,f'={ROS}!V{rn}',fmt=PCT); cellw(T,n,7,f'={ROS}!W{rn}',fmt=DPCT)
        cellw(T,n,8,f'={ROS}!X{rn}',bold=True); cellw(T,n,9,f'={ROS}!Y{rn}')
    EL=ER+NE
    for t,c in [('متحسن','D4EDDA'),('متراجع','F8D7DA'),('منقطع','D6D8DB')]: cf_text(T,f'H{ER+1}:H{EL}',t,c)
    widths(T,[10,13,9,9,9,9,9,9,9,9,9,9,9,11,11,10]); T.column_dimensions['I'].width=22
    cats=Reference(T,min_col=1,min_row=W0,max_row=WL)
    lc=LineChart(); lc.title='مسار النسب الأسبوعية: الحضور • التزام T2'; lc.x_axis.title='الأسبوع'
    for col in (5,15): lc.add_data(Reference(T,min_col=col,min_row=14,max_row=WL),titles_from_data=True)
    lc.set_categories(cats); lc.y_axis.number_format='0%'; lc.y_axis.scaling.min=0.5; lc.y_axis.scaling.max=1
    for s_ in lc.series: s_.marker.symbol='circle'; s_.smooth=False
    place(T,lc,'R3')
    bc=BarChart(); bc.type='col'; bc.title='عدد الموظفين: الغائبون والمتأخرون والمنصرفون مبكراً أسبوعياً'; bc.x_axis.title='الأسبوع'
    for col in (6,9,11): bc.add_data(Reference(T,min_col=col,min_row=14,max_row=WL),titles_from_data=True)
    bc.set_categories(cats); place(T,bc,'R21')
    bd=BarChart(); bd.type='col'; bd.title='عدد الموظفين حسب أيام الأسبوع'
    for col in (6,9,11): bd.add_data(Reference(T,min_col=col,min_row=DR+1,max_row=DL),titles_from_data=True)
    bd.set_categories(Reference(T,min_col=1,min_row=D0,max_row=DL)); place(T,bd,'R39')
    pc=PieChart(); pc.title='توزيع مسارات الموظفين'
    pc.add_data(Reference(T,min_col=2,min_row=PR+1,max_row=P0+3),titles_from_data=True); pc.set_categories(Reference(T,min_col=1,min_row=P0,max_row=P0+3))
    pc.dataLabels=DataLabelList(); pc.dataLabels.showPercent=True; place(T,pc,'R57',12,8)
    for ch in (lc,bc,bd): ch.legend.position='b'

    # ===== LATEST WEEK
    L=S['تقرير_الأسبوع_الجديد']
    title(L,f'تقرير الأسبوع الأحدث (الأسبوع {LW}: {wk_range[LW][0].strftime("%Y-%m-%d")} إلى {wk_range[LW][1].strftime("%Y-%m-%d")})',f'{SCHOOL} • تفصيل يومي ثم تقييم كل موظف ومقارنته بمعدله التاريخي • العدّ بالأفراد (عدد الموظفين) لا بعدد البصمات',NC)
    section(L,3,1,'أولاً: التفصيل اليومي للأسبوع الأحدث',NC)
    header(L,4,1,['التاريخ','اليوم']+MH)
    lw_dates=sorted(r[r.week==LW].date.unique())
    for i,dd in enumerate(lw_dates):
        n=5+i; cellw(L,n,1,pd.Timestamp(dd).to_pydatetime().date(),fmt=DT,bold=True); cellw(L,n,2,r[r.date==dd].day.iloc[0])
        write_metric_row(L,n,3,f'R_DATE,$A{n}',bg=GRAY if i%2 else None)
    LT=5+len(lw_dates); cellw(L,LT,1,'إجمالي الأسبوع',bold=True,bg=LIGHT); cellw(L,LT,2,'',bg=LIGHT)
    total_row(L,LT,3,5,LT-1,'R_WEEK,LatestWeek')
    bl=BarChart(); bl.type='col'; bl.title='عدد الموظفين يومياً في الأسبوع الأحدث'
    for col in (6,9,11,13): bl.add_data(Reference(L,min_col=col,min_row=4,max_row=LT-1),titles_from_data=True)
    bl.set_categories(Reference(L,min_col=2,min_row=5,max_row=LT-1)); bl.legend.position='b'; place(L,bl,'R3',17,9)
    ES=LT+3
    section(L,ES,1,'ثانياً: تقييم جميع الموظفين في الأسبوع الأحدث ومقارنتهم بمعدلهم التاريخي',NC)
    header(L,ES+1,1,['م','الاسم','','حضور','غياب','منه بدون عذر','تأخير','انصراف مبكر','دوام كامل','مؤشر الالتزام (الأحدث)','المعدل التاريخي','التغير','المسار','تقييم الأسبوع','سبب الغياب (النظام)',''])
    L.merge_cells(start_row=ES+1,start_column=2,end_row=ES+1,end_column=3)
    for i in range(NE):
        n=ES+2+i; rn=R0+i; C=f'$B{n}'
        cellw(L,n,1,i+1); L.merge_cells(start_row=n,start_column=2,end_row=n,end_column=3); cellw(L,n,2,f'={ROS}!C{rn}',align=RIGHT)
        for k,fx in enumerate([f'=COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek,R_PRES,1)',f'=COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek,R_STAT,"غياب كامل")',f'=COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek,R_ABS,"غياب*")+COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek,R_ABS,"منقطع*")',f'=COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek,R_LATE,1)',f'=COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek,R_EARLY,1)',f'=COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek,R_FULL,1)'],4):
            cellw(L,n,k,fx,bg=GRAY if i%2 else None)
        cellw(L,n,10,f'={ROS}!V{rn}',fmt=PCT); cellw(L,n,11,f'={ROS}!U{rn}',fmt=PCT); cellw(L,n,12,f'=J{n}-K{n}',fmt=DPCT); cellw(L,n,13,f'={ROS}!X{rn}',bold=True)
        cellw(L,n,14,f'=IF(E{n}=COUNT($A$5:$A${LT-1}),"غياب كامل طوال الأسبوع",IF(I{n}=COUNT($A$5:$A${LT-1}),"التزام كامل",IF(J{n}>=0.6,"التزام جيد","يحتاج متابعة")))')
        nm=names[i]; dd=r[(r.name==nm)&(r.week==LW)&(r.abs_type!='')]
        L.merge_cells(start_row=n,start_column=15,end_row=n,end_column=16)
        cellw(L,n,15,'، '.join(sorted(dd.abs_type.unique())) or '—',size=9)
    LE=ES+1+NE
    for t,c in [('متحسن','D4EDDA'),('متراجع','F8D7DA'),('منقطع','D6D8DB')]: cf_text(L,f'M{ES+2}:M{LE}',t,c)
    cf_text(L,f'N{ES+2}:N{LE}','متابعة',font=Font(color='C0392B',bold=True))
    widths(L,[11,22,12,9,9,9,9,9,9,11,11,10,11,16,16,12]); L.freeze_panes='A5'

    # ===== DASHBOARD
    title(D,f'لوحة المؤشرات التنفيذية والملخص التراكمي: {SCHOOL}',f'وزارة التربية، دولة الكويت • الفترة {PERIOD} • {len(dates)} يوم عمل في {len(weeks)} أسابيع • {NE} موظفاً • المصدر: تقرير حركة موظف (مختصر) • جميع الأعداد بالأفراد',NC)
    section(D,4,1,'معايير الاحتساب النظامية (قابلة للمراجعة)',NC)
    params=[('الأسبوع الأحدث (يتحكم بكل المقارنات)',LW),('حد التأخير الصباحي',f'{LATE_S} فأكثر، ودقائق التأخير تبدأ من {LATE_S}'),('نافذة بصمة التواجد T2',f'T1 + {T2A_S} إلى T1 + {T2B_S} (يُستثنى غير الملزمين بها في النظام)'),('نصاب الدوام الكامل',f'{FQ_S} ساعة ({FQ} د = {FQ_HRS} س) من max({DS_S}، T1)'),('حد الانصراف المبكر',f'قبل {EARLY_S}'),('حد التكرار (متأخر باستمرار / تخفيف عمل)',f'{REP} مرات فأكثر • تغير المسار {TRD*100:g} نقاط مئوية')]
    for i,(a,b) in enumerate(params):
        n=6+i
        D.merge_cells(start_row=n,start_column=1,end_row=n,end_column=2); cellw(D,n,1,a,bold=True,bg=LIGHT,align=RIGHT)
        D.merge_cells(start_row=n,start_column=3,end_row=n,end_column=8); cellw(D,n,3,b,bold=(i==0),color=('C00000' if i==0 else None),bg='FFF2CC' if i==0 else None)
    D['C6'].comment=Comment('غيّر رقم الأسبوع هنا لإعادة احتساب كل المقارنات.','Claude')
    section(D,13,1,'المؤشرات التنفيذية التراكمية',NC)
    kpis=[('عدد الموظفين',f'=COUNTA({RC("C")})','0'),('متوسط الحاضرين يومياً','=SUM(R_PRES)/(COUNTA(R_NAME)/A15)','0.0'),('نسبة الحضور العامة','=SUM(R_PRES)/COUNTA(R_NAME)',PCT),('موظفون غابوا يوماً على الأقل',f'=COUNTIF({RC("G")},">0")','0'),
          ('منهم غابوا بدون عذر',f'=COUNTIF({RC("I")},">0")','0'),('منهم غابوا بعذر/إجازة فقط',f'=COUNTIFS({RC("G")},">0",{RC("I")},0)','0'),('موظفون تأخروا مرة على الأقل',f'=COUNTIF({RC("K")},">0")','0'),('منهم تأخروا دون إذن',f'=COUNTIF({RC("L")},">0")','0'),
          ('موظفون انصرفوا مبكراً',f'=COUNTIF({RC("N")},">0")','0'),('منهم انصرفوا دون إذن',f'=COUNTIF({RC("O")},">0")','0'),('موظفون لديهم بصمة ناقصة',f'=COUNTIF({RC("J")},">0")','0'),('منضبطون: دوام كامل كل أيام حضورهم',f'=SUMPRODUCT(({RC("P")}={RC("F")})*({RC("F")}>0))','0'),
          ('متوسط ساعات العمل اليومية','=SUM(R_HOURS)/COUNTIF(R_HOURS,">0")',H2),('التزام نافذة T2 (للملزمين)','=SUM(R_T2OK)/SUM(R_HAST1)',PCT),(f'المتأخرون باستمرار ({REP} فأكثر)',f'=COUNTIF({RC("K")},">={REP}")','0'),(f'تخفيف عمل ({REP} انصراف مبكر فأكثر)',f'=COUNTIF({RC("N")},">={REP}")','0'),
          ('المنقطعون كلياً',f'=COUNTIF({RC("Y")},"منقطع كلياً")','0'),('في إجازة/إعفاء طوال الفترة',f'=COUNTIF({RC("Y")},"إجازة*")','0'),('غائبون طوال الأسبوع الأحدث',f'=COUNTIF({RC("X")},"منقطع ✕")','0'),('ملتزمون (90% دوام كامل فأكثر)',f'=COUNTIF({RC("Y")},"ملتزم")','0')]
    for idx,(lab,fx,fmt) in enumerate(kpis):
        rr=14+(idx//4)*2; cc=1+(idx%4)*4
        D.merge_cells(start_row=rr,start_column=cc,end_row=rr,end_column=cc+3); cellw(D,rr,cc,lab,bold=True,bg=LIGHT,color=NAVY,size=9)
        D.merge_cells(start_row=rr+1,start_column=cc,end_row=rr+1,end_column=cc+3); cellw(D,rr+1,cc,fx,fmt=fmt,bold=True,size=16,color=NAVY)
        for k in range(4): D.cell(rr,cc+k).border=B; D.cell(rr+1,cc+k).border=B
        D.row_dimensions[rr+1].height=28
    section(D,25,1,'جدول المقارنة الأسبوعية الشامل',NC)
    header(D,26,1,['الأسبوع','الفترة']+MH)
    for i,w in enumerate(weeks):
        n=27+i; cellw(D,n,1,int(w),bold=True); cellw(D,n,2,f"{wk_range[w][0].strftime('%d/%m')} – {wk_range[w][1].strftime('%d/%m')}")
        write_metric_row(D,n,3,f'R_WEEK,$A{n}',bg=GRAY if i%2 else None)
    DWL=27+len(weeks)-1; cellw(D,DWL+1,1,'الإجمالي',bold=True,bg=LIGHT); cellw(D,DWL+1,2,'',bg=LIGHT)
    total_row(D,DWL+1,3,27,DWL,'R_WEEK,">0"')
    D.conditional_formatting.add(f'A27:P{DWL}',FormulaRule(formula=['$A27=LatestWeek'],font=Font(bold=True,color='C00000')))
    bdash=BarChart(); bdash.type='col'; bdash.title='المقارنة الأسبوعية بعدد الموظفين'
    for col in (14,6,9,11): bdash.add_data(Reference(D,min_col=col,min_row=26,max_row=DWL),titles_from_data=True)
    bdash.set_categories(Reference(D,min_col=1,min_row=27,max_row=DWL)); bdash.legend.position='b'; place(D,bdash,'A36',28,10)
    widths(D,[12,13,9,9,9,9,9,9,9,9,9,9,9,11,11,10])

    # ===== CHRONIC LATE
    CLs=S['المتأخرون_باستمرار']
    lt=r.groupby('name').late.sum(); chronic=lt[lt>=REP].sort_values(ascending=False).index.tolist()
    title(CLs,f'المتأخرون باستمرار (تأخير صباحي {REP} أيام فأكثر)',f'الحضور عند أو بعد {LATE_S} • دقائق التأخير تُحتسب بدءاً من {LATE_S} • {len(chronic)} موظفاً • مع فصل التأخير المبرر بإذن مسجل في النظام',14)
    header(CLs,4,1,['م','الاسم','الرقم المدني','إجمالي أيام التأخير','منها مبررة بإذن','منها غير مبررة','تأخير الأسابيع السابقة','متوسط أسبوعي سابق','تأخير الأسبوع الأحدث','الاتجاه','إجمالي دقائق التأخير','متوسط دقائق التأخير','تواريخ التأخير السابقة','تواريخ تأخير الأسبوع الأحدث'])
    for i,nm in enumerate(chronic):
        n=5+i; C=f'$B{n}'; d=r[(r.name==nm)&(r.late==1)]
        vals=[i+1,nm,d.cid.iloc[0],f'=COUNTIFS(R_NAME,{C},R_LATE,1)',f'=D{n}-F{n}',f'=COUNTIFS(R_NAME,{C},R_LJ,"غير مبرر*")',f'=COUNTIFS(R_NAME,{C},R_LATE,1,R_WEEK,"<"&LatestWeek)',f'=G{n}/(LatestWeek-1)',f'=COUNTIFS(R_NAME,{C},R_LATE,1,R_WEEK,LatestWeek)',
              f'=IF(I{n}>H{n},"▲ ازداد",IF(I{n}<H{n},"▼ انخفض","═ ثابت"))',f'=SUMIFS(R_LATEMIN,R_NAME,{C})',f'=IF(D{n}=0,0,K{n}/D{n})','، '.join(d[d.week<LW].date.dt.strftime('%d/%m')),'، '.join(d[d.week==LW].date.dt.strftime('%d/%m')) or '—']
        for j,v in enumerate(vals,1): cellw(CLs,n,j,v,align=RIGHT if j in (2,13,14) else CENTER,bg=GRAY if i%2 else None,size=9)
        CLs.cell(n,3).number_format='@'; CLs.cell(n,8).number_format='0.0'; CLs.cell(n,12).number_format='0.0'
    cf_text(CLs,f'J5:J{4+len(chronic)}','ازداد',font=Font(color='C0392B',bold=True)); cf_text(CLs,f'J5:J{4+len(chronic)}','انخفض',font=Font(color='1E7B34',bold=True))
    widths(CLs,[5,30,14,9,9,9,10,10,10,10,10,10,52,22]); CLs.freeze_panes='C5'

    # ===== ABSENCE
    A=S['جدول_الغياب_والانقطاع']
    ab=r[r.status=='غياب كامل'].groupby('name').size().sort_values(ascending=False)
    title(A,'جدول الغياب والانقطاع',f'غياب كامل = البصمات الثلاث 00:00 أو حالة غياب/إجازة في النظام • {len(ab)} موظفاً لديهم غياب • فصل الغياب بدون عذر عن الإجازات الرسمية، والسابق عن الأسبوع الأحدث',13)
    header(A,4,1,['م','الاسم','الرقم المدني','إجمالي أيام الغياب','منها بدون عذر','منها إجازات/أعذار','غياب الأسابيع السابقة','غياب الأسبوع الأحدث','نسبة الغياب','حالة الانقطاع','أنواع الغياب/الإجازة (النظام)','تواريخ الغياب السابقة','تواريخ غياب الأسبوع الأحدث'])
    for i,nm in enumerate(ab.index):
        n=5+i; C=f'$B{n}'; d=r[(r.name==nm)&(r.status=='غياب كامل')]
        def fmtd(x):
            if len(x)==0: return '—'
            if len(x)>=20: return f'جميع الأيام ({len(x)} يوماً)'
            return '، '.join(x.date.dt.strftime('%d/%m'))
        types='، '.join(f'{k} ({v})' for k,v in d.abs_type.value_counts().items())
        vals=[i+1,nm,d.cid.iloc[0],f'=COUNTIFS(R_NAME,{C},R_STAT,"غياب كامل")',f'=COUNTIFS(R_NAME,{C},R_ABS,"غياب*")+COUNTIFS(R_NAME,{C},R_ABS,"منقطع*")',f'=D{n}-E{n}',f'=COUNTIFS(R_NAME,{C},R_STAT,"غياب كامل",R_WEEK,"<"&LatestWeek)',f'=COUNTIFS(R_NAME,{C},R_STAT,"غياب كامل",R_WEEK,LatestWeek)',f'=D{n}/COUNTIF(R_NAME,{C})',
              f'=IF(D{n}=COUNTIF(R_NAME,{C}),IF(E{n}>0,"منقطع كلياً","إجازة/إعفاء طوال الفترة"),IF(H{n}=COUNTIFS(R_NAME,{C},R_WEEK,LatestWeek),"غائب طوال الأسبوع الأحدث",IF(E{n}>={REP},"غياب متكرر بدون عذر",IF(E{n}>0,"غياب متفرق","إجازات رسمية فقط"))))',types,fmtd(d[d.week<LW]),fmtd(d[d.week==LW])]
        for j,v in enumerate(vals,1): cellw(A,n,j,v,align=RIGHT if j in (2,11,12,13) else CENTER,bg=GRAY if i%2 else None,size=9)
        A.cell(n,3).number_format='@'; A.cell(n,9).number_format=PCT
    AL=4+len(ab)
    for t,c in [('منقطع كلياً','D6D8DB'),('إجازة','DDEBF7'),('غائب طوال','F8D7DA'),('متكرر','FCE4D6')]: cf_text(A,f'J5:J{AL}',t,c)
    widths(A,[5,30,14,9,9,9,10,10,9,20,34,45,22]); A.freeze_panes='C5'

    # ===== PERMISSIONS (late events)
    P=S['قائمة_الاستئذانات_المحتملة']
    le=r[r.late==1].sort_values(['name','date'])
    def lcat(m): return 'تأخير بسيط (1 إلى 15 د)' if m<=15 else ('تأخير متوسط (16 إلى 60 د)' if m<=60 else 'استئذان صباحي محتمل (أكثر من 60 د)')
    title(P,f'قائمة الاستئذانات المحتملة (الحضور الصباحي المتأخر {LATE_S} فأكثر)',f'{len(le)} حالة • مصنفة حسب مدة التأخير • مع الإذن المسجل في النظام وتبرير كل حالة',12)
    section(P,3,1,'ملخص التصنيف',4)
    labs=['تأخير بسيط (1 إلى 15 د)','تأخير متوسط (16 إلى 60 د)','استئذان صباحي محتمل (أكثر من 60 د)','مبرر بإذن مسجل','غير مبرر بالنظام']
    for i,lab in enumerate(labs):
        P.merge_cells(start_row=4+i,start_column=1,end_row=4+i,end_column=2); cellw(P,4+i,1,lab,bold=True,bg=LIGHT,align=RIGHT)
        colr='J' if i<3 else 'L'
        cellw(P,4+i,3,f'=COUNTIF(${colr}$11:${colr}${10+len(le)},A{4+i})',bold=True)
    header(P,10,1,['م','الاسم','التاريخ','اليوم','الأسبوع','الحضور T1','الانصراف','تأخير النظام (د)','دقائق التأخير','تصنيف مدة التأخير','الإذن المسجل في النظام','التبرير'])
    for i,row in enumerate(le.itertuples()):
        n=11+i
        vals=[i+1,row.name,row.date.to_pydatetime().date(),row.day,int(row.week),tm(row.t1m),tm(row.outm),int(row.sys_late),f'=ROUND(F{n}*1440,0)-{LT1}',lcat(row.late_min),row.perm or '—',row.late_just]
        for j,v in enumerate(vals,1): cellw(P,n,j,v,align=RIGHT if j==2 else CENTER,bg=GRAY if i%2 else None,size=9)
        P.cell(n,3).number_format=DT; P.cell(n,6).number_format=TM; P.cell(n,7).number_format=TM
    cf_text(P,f'J11:J{10+len(le)}','استئذان','F8D7DA'); cf_text(P,f'L11:L{10+len(le)}','غير مبرر',font=Font(color='C0392B',bold=True))
    widths(P,[6,30,11,9,7,9,9,9,9,26,24,16]); P.freeze_panes='C11'; P.auto_filter.ref=f'A10:L{10+len(le)}'

    # ===== EARLY
    E=S['الانصراف_المبكر_والاستثناءات']
    ee=r[r.early==1].sort_values(['name','date']); ecount=ee.groupby('name').size()
    title(E,f'الانصراف المبكر والاستثناءات (الخروج قبل {EARLY_S})',f'{len(ee)} حالة لـ {len(ecount)} موظفاً • {REP} مرات فأكثر = استثناء دوام يومي متكرر / تخفيف عمل • أقل من ذلك = استئذان خروج مبكر عرضي • مع الإذن المسجل في النظام',13)
    section(E,3,1,'ملخص التصنيف',4)
    summ=[('استثناء دوام يومي متكرر / تخفيف عمل (موظفون)',f'=COUNTIF({RC("N")},">={REP}")'),('استئذان خروج مبكر عرضي (موظفون)',f'=COUNTIFS({RC("N")},">0",{RC("N")},"<{REP}")'),('إجمالي حالات الانصراف المبكر','=SUM(R_EARLY)'),('منها مبررة بإذن مسجل',f'=COUNTIF(M11:M{10+len(ee)},"مبرر*")'),('منها غير مبررة بالنظام',f'=COUNTIF(M11:M{10+len(ee)},"غير مبرر*")')]
    for i,(a,b) in enumerate(summ):
        E.merge_cells(start_row=4+i,start_column=1,end_row=4+i,end_column=2); cellw(E,4+i,1,a,bold=True,bg=LIGHT,align=RIGHT); cellw(E,4+i,3,b,bold=True)
    header(E,10,1,['م','الاسم','التاريخ','اليوم','الأسبوع','الحضور T1','الانصراف','الانصراف النظامي المطلوب',f'دقائق النقص عن {EARLY_S}','عدد مرات الموظف','التصنيف','الإذن المسجل في النظام','التبرير'])
    for i,row in enumerate(ee.itertuples()):
        n=11+i
        vals=[i+1,row.name,row.date.to_pydatetime().date(),row.day,int(row.week),tm(row.t1m),tm(row.outm),f'=IF(F{n}>0,MAX(F{n},TIME({DSH},{DSM},0))+TIME({FQH},{FQM},0),"—")',f'={EB}-ROUND(G{n}*1440,0)',f'=COUNTIFS(R_NAME,B{n},R_EARLY,1)',f'=IF(J{n}>={REP},"استثناء دوام يومي متكرر / تخفيف عمل","استئذان خروج مبكر عرضي")',row.perm or '—',row.early_just]
        for j,v in enumerate(vals,1): cellw(E,n,j,v,align=RIGHT if j==2 else CENTER,bg=GRAY if i%2 else None,size=9)
        E.cell(n,3).number_format=DT
        for j in (6,7,8): E.cell(n,j).number_format=TM
    cf_text(E,f'K11:K{10+len(ee)}','تخفيف','FFF3CD'); cf_text(E,f'M11:M{10+len(ee)}','غير مبرر',font=Font(color='C0392B',bold=True))
    widths(E,[6,30,11,9,7,9,9,11,10,9,30,24,16]); E.freeze_panes='C11'; E.auto_filter.ref=f'A10:M{10+len(ee)}'

    # ===== INDIVIDUAL
    I=S['تقرير_الموظف_الفردي']
    title(I,'بطاقة الأداء الفردية للموظف: تقرير الحضور والانصراف',f'{SCHOOL} • اختر اسم الموظف من القائمة المنسدلة في الخلية C4 وستتحدث البطاقة والجداول والرسوم تلقائياً',12)
    I.merge_cells('A4:B4'); cellw(I,4,1,'اسم الموظف ▼',bold=True,bg=NAVY,color=WHITE)
    I.merge_cells('C4:G4'); cellw(I,4,3,MODEL,bold=True,size=13,bg='FFF2CC',color=NAVY)
    dv=DataValidation(type='list',formula1='=ROS_NAMES',allow_blank=False); I.add_data_validation(dv); dv.add('C4')
    mt=lambda col: f'=INDEX({RC(col)},MATCH($C$4,ROS_NAMES,0))'
    info=[('الرقم المدني',mt('B')),('الوظيفة',mt('D')),('الجهة',SCHOOL),('التصنيف التشغيلي',mt('Y')),('مؤشر اتجاه الأداء',mt('X')),('تصنيف الانصراف المبكر',mt('Z'))]
    for i,(a,b) in enumerate(info):
        rr=5+i//2; cc=1+(i%2)*6
        I.merge_cells(start_row=rr,start_column=cc,end_row=rr,end_column=cc+1); cellw(I,rr,cc,a,bold=True,bg=LIGHT,align=RIGHT)
        I.merge_cells(start_row=rr,start_column=cc+2,end_row=rr,end_column=cc+5); c=cellw(I,rr,cc+2,b,align=RIGHT)
        if a=='الرقم المدني': c.number_format='@'
    section(I,9,1,'مؤشرات الأداء الرئيسية (KPIs)',12)
    NM_='$C$4'
    k8=[('أيام الحضور',f'=COUNTIFS(R_NAME,{NM_},R_PRES,1)&" / "&COUNTIF(R_NAME,{NM_})',None),('أيام الغياب (منها بدون عذر)',f'=COUNTIFS(R_NAME,{NM_},R_STAT,"غياب كامل")&" ("&(COUNTIFS(R_NAME,{NM_},R_ABS,"غياب*")+COUNTIFS(R_NAME,{NM_},R_ABS,"منقطع*"))&")"',None),('التأخير الصباحي (غير المبرر)',f'=COUNTIFS(R_NAME,{NM_},R_LATE,1)&" ("&COUNTIFS(R_NAME,{NM_},R_LJ,"غير مبرر*")&")"',None),('الانصراف المبكر (غير المبرر)',f'=COUNTIFS(R_NAME,{NM_},R_EARLY,1)&" ("&COUNTIFS(R_NAME,{NM_},R_EJ,"غير مبرر*")&")"',None),
        ('دوام كامل مكتمل',f'=COUNTIFS(R_NAME,{NM_},R_FULL,1)','0'),('نسبة الحضور',f'=COUNTIFS(R_NAME,{NM_},R_PRES,1)/COUNTIF(R_NAME,{NM_})',PCT),('التزام نافذة T2',f'=IFERROR(COUNTIFS(R_NAME,{NM_},R_T2OK,1)/COUNTIFS(R_NAME,{NM_},R_HAST1,1),"غير ملزم")',PCT),('متوسط ساعات العمل',f'=IFERROR(SUMIFS(R_HOURS,R_NAME,{NM_})/COUNTIFS(R_NAME,{NM_},R_HOURS,">0"),0)',H2)]
    for idx,(lab,fx,fmt) in enumerate(k8):
        rr=10+(idx//4)*2; cc=1+(idx%4)*3
        I.merge_cells(start_row=rr,start_column=cc,end_row=rr,end_column=cc+2); cellw(I,rr,cc,lab,bold=True,bg=LIGHT,color=NAVY,size=9)
        I.merge_cells(start_row=rr+1,start_column=cc,end_row=rr+1,end_column=cc+2); cellw(I,rr+1,cc,fx,fmt=fmt,bold=True,size=16,color=NAVY)
        for k in range(3): I.cell(rr,cc+k).border=B; I.cell(rr+1,cc+k).border=B
        I.row_dimensions[rr+1].height=28
    section(I,15,1,'توزيع عناصر الالتزام',4)
    header(I,16,1,['العنصر','','عدد الأيام','النسبة']); I.merge_cells('A16:B16')
    CATS=['دوام كامل مكتمل','انصراف مبكر / استئذان','تأخير صباحي','غياب','بصمة ناقصة / نقص نصاب']
    for i,cname in enumerate(CATS):
        n=17+i; I.merge_cells(start_row=n,start_column=1,end_row=n,end_column=2)
        cellw(I,n,1,cname,bold=True,align=RIGHT); cellw(I,n,3,f'=COUNTIFS(R_NAME,{NM_},R_CAT,A{n})'); cellw(I,n,4,f'=IFERROR(C{n}/SUM($C$17:$C$21),0)',fmt=PCT)
    section(I,15,6,'التطور الأسبوعي',7)
    header(I,16,6,['الأسبوع','حضور','غياب','تأخير','انصراف مبكر','دوام كامل','إجمالي ساعات العمل'])
    for i,w in enumerate(weeks):
        n=17+i; cellw(I,n,6,int(w),bold=True)
        for k,fx in enumerate([f'=COUNTIFS(R_NAME,{NM_},R_WEEK,F{n},R_PRES,1)',f'=COUNTIFS(R_NAME,{NM_},R_WEEK,F{n},R_STAT,"غياب كامل")',f'=COUNTIFS(R_NAME,{NM_},R_WEEK,F{n},R_LATE,1)',f'=COUNTIFS(R_NAME,{NM_},R_WEEK,F{n},R_EARLY,1)',f'=COUNTIFS(R_NAME,{NM_},R_WEEK,F{n},R_FULL,1)',f'=SUMIFS(R_HOURS,R_NAME,{NM_},R_WEEK,F{n})']):
            cellw(I,n,7+k,fx)
        I.cell(n,12).number_format=H2
    IW=17+len(weeks)-1
    I.merge_cells(start_row=IW+1,start_column=6,end_row=IW+1,end_column=11); cellw(I,IW+1,6,f'النصاب الأسبوعي الكامل ({len(DAYS)} أيام × {FQ_S})',bold=True,bg=LIGHT,size=8); cellw(I,IW+1,12,f'={len(DAYS)}*{FQ}/60',fmt=H2,bold=True,bg=LIGHT)
    section(I,25,1,'السجل اليومي الكامل',13)
    header(I,26,1,['التاريخ','اليوم','الأسبوع','الحضور T1','التواجد T2','الانصراف','حالة اليوم','حالة نافذة T2','الانصراف المطلوب','ساعات العمل',f'النصاب ({FQ_HRS})','التصنيف','ملاحظة النظام'])
    START=f'MATCH($C$4,R_NAME,0)'
    src=['E','F','G','H','I','J','O','S','V','W',None,'AA','K']; fm=[DT,None,'0',TM,TM,TM,None,None,TM,H2,H2,None,None]
    for k in range(len(dates)):
        n=27+k
        for j,(col,f_) in enumerate(zip(src,fm),1):
            v=f'=INDEX({RAW}!${col}$2:${col}${LAST},{START}+{k})' if col else f'=ROUND({FQ}/60,2)'
            if col=='K': v=f'=INDEX({RAW}!$K$2:$K${LAST},{START}+{k})&IF(INDEX({RAW}!$L$2:$L${LAST},{START}+{k})<>""," "&INDEX({RAW}!$L$2:$L${LAST},{START}+{k}),"")'
            cellw(I,n,j,v,fmt=f_,bg=GRAY if k%2 else None,size=9)
    IL=27+len(dates)-1
    for t,c in [('غياب','F8D7DA'),('تأخير','FCE4D6'),('انصراف مبكر','FFF3CD'),('دوام كامل','D4EDDA')]: cf_text(I,f'L27:L{IL}',t,c)
    widths(I,[11,9,7,9,9,9,11,15,10,9,9,20,24])
    pi=PieChart(); pi.title='نسب التزام الموظف'
    pi.add_data(Reference(I,min_col=3,min_row=16,max_row=21),titles_from_data=True); pi.set_categories(Reference(I,min_col=1,min_row=17,max_row=21))
    pi.dataLabels=DataLabelList(); pi.dataLabels.showPercent=True; place(I,pi,'O3',13,8)
    bh=BarChart(); bh.type='col'; bh.title=f'ساعات العمل الفعلية اليومية مقارنة بالنصاب ({FQ_HRS} س)'
    bh.add_data(Reference(I,min_col=10,min_row=26,max_row=IL),titles_from_data=True); bh.set_categories(Reference(I,min_col=1,min_row=27,max_row=IL))
    ln=LineChart(); ln.add_data(Reference(I,min_col=11,min_row=26,max_row=IL),titles_from_data=True)
    ln.series[0].graphicalProperties.line.solidFill='C00000'; ln.series[0].graphicalProperties.line.dashStyle='dash'
    bh+=ln; bh.legend.position='b'; place(I,bh,'O20',22,9)
    lw=LineChart(); lw.title='إجمالي ساعات العمل الأسبوعية'; lw.x_axis.title='الأسبوع'
    lw.add_data(Reference(I,min_col=12,min_row=16,max_row=IW),titles_from_data=True); lw.set_categories(Reference(I,min_col=6,min_row=17,max_row=IW))
    lw.series[0].marker.symbol='circle'; lw.legend=None; place(I,lw,'O39',13,8)
    I.freeze_panes='A5'
    for ws in wb.worksheets:
        ws.sheet_properties.tabColor={'تقرير_الموظف_الفردي':'C00000','تحليل_الاتجاهات_الأسبوعية':TEAL,'تقرير_الأسبوع_الجديد':TEAL,'لوحة_المؤشرات_والملخص':NAVY}.get(ws.title,'8EA9DB')
        ws.page_setup.orientation='landscape'; ws.sheet_properties.pageSetUpPr.fitToPage=True; ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0
    wb.active=0
    wb.save(out_path)
    return out_path
