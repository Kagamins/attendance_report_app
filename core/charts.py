# SVG chart helpers (people-based charts). Palette: reference categorical slots 1-3.
import html
C=dict(blue='#2a78d6',orange='#eb6834',aqua='#1baf7a',ink='#0b0b0b',ink2='#52514e',muted='#8a8984',grid='#e6e5e0',surf='#fcfcfb',red='#d03b3a',navy='#1F3864')
SER=[C['blue'],C['orange'],C['aqua']]
FONT='Tahoma, DejaVu Sans, Segoe UI, Arial, sans-serif'
esc=lambda s: html.escape(str(s))
def svg(w,h,body,label=''):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{esc(label)}" font-family="{FONT}">{body}</svg>'
def t(x,y,s,size=12,fill=None,anchor='middle',weight='normal'):
    # rtl text: swap start/end because direction=rtl flips the anchor meaning
    a=anchor
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill or C["ink2"]}" text-anchor="{a}" font-weight="{weight}" direction="rtl">{esc(s)}</text>'
def tn(x,y,s,size=12,fill=None,anchor='middle',weight='normal'):
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill or C["ink2"]}" text-anchor="{anchor}" font-weight="{weight}" direction="ltr">{esc(s)}</text>'
def bar(x,y,w,h,color):
    # 4px rounded data end anchored to baseline (top corners rounded)
    r=min(4,w/2,h)
    if h<=0: return ''
    return f'<path d="M{x:.1f},{y+h:.1f} V{y+r:.1f} Q{x:.1f},{y:.1f} {x+r:.1f},{y:.1f} H{x+w-r:.1f} Q{x+w:.1f},{y:.1f} {x+w:.1f},{y+r:.1f} V{y+h:.1f} Z" fill="{color}"/>'
def nice(m):
    for s in [5,10,20,25,50,100,200,250,500]:
        if m/s<=6: return s, s*int(-(-m//s))
    return 1000, 1000*int(-(-m//1000))
def legend(items,x,y,size=12):
    out='';cx=x
    for lab,col in items:
        out+=f'<rect x="{cx-12:.1f}" y="{y-10}" width="12" height="12" rx="3" fill="{col}"/>'+t(cx-18,y,lab,size,C['ink2'],'start')
        cx-=24+len(lab)*size*0.62
    return out
def grouped_bars(cats,series,w=760,h=330,title='',ymax=None,labels=True,unit=''):
    # series: [(name, values, color)]; categories laid right-to-left (RTL reading order)
    L,R,T,B=50,20,46,52
    m=max(max(v) for _,v,_ in series); step,top=nice(ymax or m)
    pw=w-L-R; ph=h-T-B; n=len(cats); k=len(series)
    gw=pw/n; bw=min(26,(gw*0.72)/k)
    body=''
    for gv in range(0,top+1,step):
        y=T+ph-ph*gv/top
        body+=f'<line x1="{L}" x2="{w-R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{C["grid"]}" stroke-width="1"/>'+tn(L-8,y+4,gv,11,C['muted'],'end')
    for i,c in enumerate(cats):
        gi=n-1-i  # rtl: first category on the right
        gx=L+gi*gw+(gw-bw*k-2*(k-1))/2
        for j,(nm,vals,col) in enumerate(series):
            v=vals[i]; bh=ph*v/top; x=gx+j*(bw+2); y=T+ph-bh
            body+=f'<g><title>{esc(c)} • {esc(nm)}: {v}{unit}</title>{bar(x,y,bw,bh,col)}</g>'
            if labels: body+=tn(x+bw/2,y-4,v,10,C['ink2'])
        body+=t(L+gi*gw+gw/2,T+ph+18,c,11.5,C['ink2'])
    body+=f'<line x1="{L}" x2="{w-R}" y1="{T+ph}" y2="{T+ph}" stroke="{C["muted"]}" stroke-width="1"/>'
    body+=legend([(nm,col) for nm,_,col in series],w-R,h-12)
    if title: body+=t(w-R,22,title,15,C['ink'],'start','bold')
    return svg(w,h,body,title)
def hbars(items,w=760,h=None,title='',color=None,unit='',maxv=None):
    color=color or C['blue']; n=len(items); h=h or 60+n*30
    L,R,T=50,250,44; pw=w-L-R; m=maxv or max(v for _,v in items)
    body=''
    for i,(lab,v) in enumerate(items):
        y=T+i*30; bw=pw*v/m
        x0=w-R  # bars grow leftward (rtl), label on the right
        body+=f'<g><title>{esc(lab)}: {v}{unit}</title><path d="M{x0},{y} H{x0-bw+4:.1f} Q{x0-bw:.1f},{y} {x0-bw:.1f},{y+4} V{y+16} Q{x0-bw:.1f},{y+20} {x0-bw+4:.1f},{y+20} H{x0} Z" fill="{color}"/></g>'
        body+=t(w-R+10,y+15,lab,12,C['ink2'],'end')
        body+=tn(x0-bw-6,y+15,f'{v}',12,C['ink'],'end','bold')
    if title: body+=t(w-8,22,title,15,C['ink'],'start','bold')
    return svg(w,h,body,title)
def line(cats,vals,w=760,h=260,title='',fmt=lambda v:f'{v:.1f}%',ymin=None,ymax=None,color=None):
    color=color or C['blue']; L,R,T,B=50,30,46,40; pw=w-L-R; ph=h-T-B; n=len(cats)
    lo=ymin if ymin is not None else min(vals)-2; hi=ymax if ymax is not None else max(vals)+2
    X=lambda i: L+pw*(n-1-i)/(n-1); Y=lambda v: T+ph-ph*(v-lo)/(hi-lo)
    body=''
    for gv in [lo+(hi-lo)*k/4 for k in range(5)]:
        body+=f'<line x1="{L}" x2="{w-R}" y1="{Y(gv):.1f}" y2="{Y(gv):.1f}" stroke="{C["grid"]}"/>'+tn(L-8,Y(gv)+4,fmt(gv),10.5,C['muted'],'end')
    pts=' '.join(f'{X(i):.1f},{Y(v):.1f}' for i,v in enumerate(vals))
    body+=f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2"/>'
    for i,v in enumerate(vals):
        body+=f'<g><title>{esc(cats[i])}: {fmt(v)}</title><circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="5" fill="{color}" stroke="{C["surf"]}" stroke-width="2"/></g>'+tn(X(i),Y(v)-11,fmt(v),10.5,C['ink'])
        body+=t(X(i),T+ph+20,cats[i],11.5,C['ink2'])
    if title: body+=t(w-R,22,title,15,C['ink'],'start','bold')
    return svg(w,h,body,title)
def stacked(cats,series,w=760,h=320,title=''):
    L,R,T,B=50,20,46,52; pw=w-L-R; ph=h-T-B; n=len(cats)
    tot=[sum(v[i] for _,v,_ in series) for i in range(n)]; step,top=nice(max(tot))
    gw=pw/n; bw=min(46,gw*0.55); body=''
    for gv in range(0,top+1,step):
        y=T+ph-ph*gv/top; body+=f'<line x1="{L}" x2="{w-R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{C["grid"]}"/>'+tn(L-8,y+4,gv,11,C['muted'],'end')
    for i,c in enumerate(cats):
        gi=n-1-i; x=L+gi*gw+(gw-bw)/2; acc=0
        for j,(nm,vals,col) in enumerate(series):
            v=vals[i]; bh=ph*v/top; y=T+ph-ph*(acc+v)/top
            if j==len(series)-1: body+=f'<g><title>{esc(c)} • {esc(nm)}: {v}</title>{bar(x,y,bw,bh-(2 if acc else 0),col)}</g>'
            else: body+=f'<g><title>{esc(c)} • {esc(nm)}: {v}</title><rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(bh-2,0):.1f}" fill="{col}"/></g>'
            acc+=v
        body+=tn(x+bw/2,T+ph-ph*acc/top-5,acc,10.5,C['ink'],'middle','bold')
        body+=t(L+gi*gw+gw/2,T+ph+18,c,11.5,C['ink2'])
    body+=f'<line x1="{L}" x2="{w-R}" y1="{T+ph}" y2="{T+ph}" stroke="{C["muted"]}"/>'
    body+=legend([(nm,col) for nm,_,col in series],w-R,h-12)
    if title: body+=t(w-R,22,title,15,C['ink'],'start','bold')
    return svg(w,h,body,title)
