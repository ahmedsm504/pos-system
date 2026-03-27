"""
Print Service — Xprinter XP-D200N  (USB + LAN)
ESC/POS commands + Cash Drawer auto-open
تشغيل:  python print_service.py
"""

from flask import Flask, request, jsonify
import logging, sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ── اسم الطابعات في Windows (غيّرها حسب الأسماء عندك) ──────────────────────
MAIN_PRINTER    = "Main Printer"      # فاتورة كاملة للكاشير
KITCHEN_PRINTER = "Kitchen Printer"   # طابعة المطبخ
BAR_PRINTER     = "Bar Printer"       # طابعة البار
# ─────────────────────────────────────────────────────────────────────────────

# ── ESC/POS Constants ────────────────────────────────────────────────────────
ESC = b'\x1b'
GS  = b'\x1d'

INIT          = ESC + b'@'
CUT           = GS  + b'V\x41\x03'
ALIGN_CENTER  = ESC + b'a\x01'
ALIGN_LEFT    = ESC + b'a\x00'
ALIGN_RIGHT   = ESC + b'a\x02'
BOLD_ON       = ESC + b'E\x01'
BOLD_OFF      = ESC + b'E\x00'
DOUBLE_HEIGHT = ESC + b'!\x10'
NORMAL_SIZE   = ESC + b'!\x00'
LINE_FEED     = b'\r\n'
OPEN_DRAWER   = ESC + b'p\x00\x19\xfa'

# أفضل محاولة: cp1256 مع أمر إضافي (ESC R 0) لضبط اللغة العربية
# يمكن تجربة cp1252 بدلاً من ذلك: SET_CODEPAGE = ESC + b't\x1a'
SET_CODEPAGE = ESC + b't\x1c' + ESC + b'R\x00'   # cp1256 + language Arabic

# ── Arabic encoding ───────────────────────────────────────────────────────────
def encode_arabic(text: str) -> bytes:
    try:
        return text.encode('cp1256')
    except (UnicodeEncodeError, LookupError):
        return text.encode('cp1256', errors='replace')

# ── Build receipts ────────────────────────────────────────────────────────────
def build_receipt(lines: list) -> bytes:
    data = INIT + SET_CODEPAGE

    for line in lines:
        if line.get('divider'):
            data += ALIGN_LEFT + encode_arabic('-' * 32) + LINE_FEED
            continue

        align = line.get('align', 'right')
        if align == 'center':
            data += ALIGN_CENTER
        elif align == 'left':
            data += ALIGN_LEFT
        else:
            data += ALIGN_RIGHT

        if line.get('bold'):
            data += BOLD_ON
        if line.get('size') == 'large':
            data += DOUBLE_HEIGHT

        data += encode_arabic(line.get('text', '')) + LINE_FEED

        if line.get('size') == 'large':
            data += NORMAL_SIZE
        if line.get('bold'):
            data += BOLD_OFF

    data += LINE_FEED * 3 + CUT
    return data

def build_kitchen_ticket(lines: list) -> bytes:
    # نفس البناء لكن بدون فتح الدرج
    data = INIT + SET_CODEPAGE

    for line in lines:
        if line.get('divider'):
            data += ALIGN_LEFT + encode_arabic('=' * 32) + LINE_FEED
            continue

        align = line.get('align', 'right')
        if align == 'center':
            data += ALIGN_CENTER
        elif align == 'left':
            data += ALIGN_LEFT
        else:
            data += ALIGN_RIGHT

        if line.get('bold'):
            data += BOLD_ON
        if line.get('size') == 'large':
            data += DOUBLE_HEIGHT

        data += encode_arabic(line.get('text', '')) + LINE_FEED

        if line.get('size') == 'large':
            data += NORMAL_SIZE
        if line.get('bold'):
            data += BOLD_OFF

    data += LINE_FEED * 2 + CUT
    return data

# ── Raw print via Windows win32print ─────────────────────────────────────────
def print_raw(printer_name: str, data: bytes) -> bool:
    try:
        import win32print
    except ImportError:
        log.error('win32print غير متاح — شغل الـ service على Windows')
        return False

    try:
        h = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(h, 1, ('POS Job', None, 'RAW'))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        log.info(f'Printed OK → {printer_name}')
        return True
    except Exception as e:
        log.error(f'Print error ({printer_name}): {e}')
        return False

# ── Cash Drawer ───────────────────────────────────────────────────────────────
def open_cash_drawer() -> bool:
    return print_raw(MAIN_PRINTER, INIT + SET_CODEPAGE + OPEN_DRAWER)

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/print', methods=['POST'])
def handle_print():
    d = request.json or {}

    main_lines    = d.get('main_lines', [])
    kitchen_lines = d.get('kitchen_lines', [])
    bar_lines     = d.get('bar_lines', [])
    open_drawer   = d.get('open_drawer', False)

    results = {}

    if main_lines:
        data = build_receipt(main_lines)
        if open_drawer:
            # إضافة أمر فتح الدرج قبل الطباعة
            data = INIT + SET_CODEPAGE + OPEN_DRAWER + data[len(INIT+SET_CODEPAGE):]
        results['main'] = print_raw(MAIN_PRINTER, data)

    if kitchen_lines:
        results['kitchen'] = print_raw(KITCHEN_PRINTER, build_kitchen_ticket(kitchen_lines))

    if bar_lines:
        results['bar'] = print_raw(BAR_PRINTER, build_kitchen_ticket(bar_lines))

    success = all(results.values()) if results else False
    log.info(f'Print results: {results}  success={success}')
    return jsonify({'status': 'done', 'results': results, 'success': success})

@app.route('/drawer', methods=['POST'])
def drawer_route():
    ok = open_cash_drawer()
    return jsonify({'success': ok})

@app.route('/health', methods=['GET'])
def health():
    try:
        import win32print
        win32_ok = True
        msg = 'win32print متاح'
    except ImportError:
        win32_ok = False
        msg = 'win32print غير متاح — الطباعة مش هتشتغل'
    return jsonify({'status': 'running', 'version': '2.3', 'win32print': win32_ok, 'note': msg})

@app.route('/printers', methods=['GET'])
def list_printers():
    try:
        import win32print
        printers = [p[2] for p in win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )]
        return jsonify({'printers': printers})
    except ImportError:
        return jsonify({'printers': [], 'error': 'win32print غير متاح'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/test', methods=['GET'])
def test_print():
    lines = [
        {'text': 'اختبار الطباعة', 'align': 'center', 'bold': True, 'size': 'large'},
        {'divider': True},
        {'text': 'طلب رقم: #999', 'bold': True},
        {'text': 'الطاولة: طاولة 5'},
        {'text': 'كوكاكولا  x2'},
        {'text': 'بيتزا مارجريتا  x1'},
        {'divider': True},
        {'text': 'الاجمالي: 150 ج', 'bold': True, 'align': 'center'},
        {'text': 'شكرا لزيارتكم', 'align': 'center'},
    ]
    ok = print_raw(MAIN_PRINTER, build_receipt(lines))
    return jsonify({'success': ok, 'message': 'تم الارسال' if ok else 'فشلت الطباعة'})

if __name__ == '__main__':
    log.info('Print Service v2.3  →  http://127.0.0.1:5000')
    log.info('  /health   ← حالة win32print')
    log.info('  /printers ← اسماء الطابعات')
    log.info('  /test     ← اختبار طباعة عربي')
    app.run(host='127.0.0.1', port=5000, debug=False)