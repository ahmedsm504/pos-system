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
MAIN_PRINTER   = "Main Printer"      # فاتورة كاملة للكاشير
KITCHEN_PRINTER = "Kitchen Printer"  # طابعة المطبخ
BAR_PRINTER    = "Bar Printer"       # طابعة البار
# ─────────────────────────────────────────────────────────────────────────────

# ── ESC/POS Constants ────────────────────────────────────────────────────────
ESC = b'\x1b'
GS  = b'\x1d'

INIT          = ESC + b'@'           # تهيئة الطابعة
CUT           = GS  + b'V\x41\x03'  # قطع الورق
ALIGN_CENTER  = ESC + b'a\x01'
ALIGN_LEFT    = ESC + b'a\x00'
BOLD_ON       = ESC + b'E\x01'
BOLD_OFF      = ESC + b'E\x00'
DOUBLE_HEIGHT = ESC + b'!\x10'
NORMAL_SIZE   = ESC + b'!\x00'
LINE_FEED     = b'\n'

# Cash Drawer — يشغّل على pin 2
OPEN_DRAWER   = ESC + b'p\x00\x19\xfa'

# ── Arabic encoding helper ───────────────────────────────────────────────────
def encode_arabic(text: str) -> bytes:
    for enc in ('cp720', 'cp864', 'utf-8'):
        try:
            return text.encode(enc)
        except Exception:
            continue
    return text.encode('ascii', errors='replace')


def build_receipt(lines: list[dict]) -> bytes:
    data = INIT
    for line in lines:
        if line.get('divider'):
            data += ALIGN_LEFT + encode_arabic('─' * 42) + LINE_FEED
            continue

        align = line.get('align', 'right')
        data += ALIGN_CENTER if align == 'center' else ALIGN_LEFT

        if line.get('bold'):
            data += BOLD_ON
        if line.get('size') == 'large':
            data += DOUBLE_HEIGHT

        data += encode_arabic(line.get('text', '')) + LINE_FEED

        if line.get('size') == 'large':
            data += NORMAL_SIZE
        if line.get('bold'):
            data += BOLD_OFF

    data += LINE_FEED * 3
    data += CUT
    return data


def build_kitchen_ticket(lines: list[dict]) -> bytes:
    data = INIT
    for line in lines:
        if line.get('divider'):
            data += ALIGN_LEFT + encode_arabic('=' * 42) + LINE_FEED
            continue
        data += ALIGN_CENTER if line.get('align') == 'center' else ALIGN_LEFT
        if line.get('bold'): data += BOLD_ON
        if line.get('size') == 'large': data += DOUBLE_HEIGHT
        data += encode_arabic(line.get('text', '')) + LINE_FEED
        if line.get('size') == 'large': data += NORMAL_SIZE
        if line.get('bold'): data += BOLD_OFF
    data += LINE_FEED * 2
    data += CUT
    return data


def print_raw(printer_name: str, data: bytes) -> bool:
    try:
        import win32print
        h = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(h, 1, ('POS Job', None, 'RAW'))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        log.info(f'✅ Printed → {printer_name}')
        return True
    except ImportError:
        log.warning('win32print غير متاح — محاكاة الطباعة')
        log.info(f'[MOCK PRINT] → {printer_name}\n{data}')
        return True
    except Exception as e:
        log.error(f'❌ Print error ({printer_name}): {e}')
        return False


def open_cash_drawer(printer_name: str) -> bool:
    return print_raw(printer_name, INIT + OPEN_DRAWER)


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
            data = INIT + OPEN_DRAWER + data
        results['main'] = print_raw(MAIN_PRINTER, data)

    if kitchen_lines:
        results['kitchen'] = print_raw(KITCHEN_PRINTER, build_kitchen_ticket(kitchen_lines))

    if bar_lines:
        results['bar'] = print_raw(BAR_PRINTER, build_kitchen_ticket(bar_lines))

    success = all(results.values()) if results else False
    return jsonify({'status': 'done', 'results': results, 'success': success})


@app.route('/drawer', methods=['POST'])
def open_drawer_route():
    ok = open_cash_drawer(MAIN_PRINTER)
    return jsonify({'success': ok})


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'running', 'version': '2.0'})


@app.route('/printers', methods=['GET'])
def list_printers():
    try:
        import win32print
        printers = [p[2] for p in win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )]
        return jsonify({'printers': printers})
    except ImportError:
        return jsonify({'printers': [], 'note': 'win32print غير متاح'})
    except Exception as e:
        return jsonify({'error': str(e)})


if __name__ == '__main__':
    log.info('🖨️  Print Service v2.0 شغّال على http://127.0.0.1:5000')
    log.info('   http://127.0.0.1:5000/printers  ← شوف الطابعات')
    log.info('   http://127.0.0.1:5000/health    ← تأكد إنه شغّال')
    app.run(host='127.0.0.1', port=5000, debug=False)