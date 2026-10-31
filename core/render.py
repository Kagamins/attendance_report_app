"""HTML -> PDF / PNG through Playwright's Chromium (handles Arabic shaping and right-to-left layout).

One-time setup on a new computer:  python -m playwright install chromium
"""
import os, tempfile

FONT_STACK = 'Tahoma, "DejaVu Sans", "Segoe UI", Arial, sans-serif'


class RenderError(Exception):
    pass


def _browser(p):
    try:
        return p.chromium.launch()
    except Exception as e:
        raise RenderError('متصفح Chromium غير مثبت. شغّل مرة واحدة:  python -m playwright install chromium\n' + str(e))


def _tmp_html(html):
    fd, path = tempfile.mkstemp(suffix='.html')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(html)
    return path


def html_to_pdf(html, out_path, footer_text='', landscape=False):
    from playwright.sync_api import sync_playwright
    src = _tmp_html(html)
    footer = (f'<div style="font-size:8px;width:100%;text-align:center;color:#666;font-family:{FONT_STACK};direction:rtl">'
              f'{footer_text} • صفحة <span class="pageNumber"></span> من <span class="totalPages"></span></div>')
    try:
        with sync_playwright() as p:
            b = _browser(p); pg = b.new_page()
            pg.goto('file:///' + src.replace('\\', '/')); pg.wait_for_timeout(400)
            pg.pdf(path=out_path, format='A4', landscape=landscape, print_background=True,
                   margin=dict(top='13mm', bottom='15mm', left='12mm', right='12mm'),
                   display_header_footer=True, header_template='<span></span>', footer_template=footer)
            b.close()
    finally:
        os.remove(src)
    return out_path


def html_to_image_and_pdf(html, png_path=None, pdf_path=None, width=1123, selector='.wrap'):
    """Single tall page (infographic): screenshot to PNG and/or one-page PDF of the same height."""
    from playwright.sync_api import sync_playwright
    src = _tmp_html(html)
    try:
        with sync_playwright() as p:
            b = _browser(p); pg = b.new_page(viewport={'width': width, 'height': 1400}, device_scale_factor=2)
            pg.goto('file:///' + src.replace('\\', '/')); pg.wait_for_timeout(400)
            h = pg.evaluate(f'Math.ceil(document.querySelector("{selector}").getBoundingClientRect().height)')
            pg.set_viewport_size({'width': width, 'height': h})
            if png_path: pg.screenshot(path=png_path, full_page=True)
            if pdf_path: pg.pdf(path=pdf_path, width=f'{width}px', height=f'{h + 2}px', print_background=True,
                                margin=dict(top='0', bottom='0', left='0', right='0'))
            b.close()
    finally:
        os.remove(src)
    return png_path, pdf_path
