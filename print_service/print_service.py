"""
Print Service — Xprinter XP-D200N (USB + LAN)
يدعم الطباعة عبر GDI للنص العربي، وأوامر ESC/POS للدرج
تشغيل:  python print_service.py
"""

from flask import Flask, request, jsonify
import logging, sys, io
import win32print
import win32ui
import win32con
from PIL import Image, ImageDraw, ImageFont
import os

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

# ESC/POS Constants (للدرج فقط)
ESC = b'\x1b'
GS  = b'\x1d'
INIT = ESC + b'@'
OPEN_DRAWER = ESC + b'p\x00\x19\xfa'
LINE_FEED = b'\r\n'

# ----------------------------------------------------------------------
# طباعة عبر GDI (نص عربي)
def print_gdi(printer_name, lines, open_drawer=False):
    """طباعة نص عربي عبر GDI باستخدام خط Arial"""
    try:
        # فتح الطابعة
        hprinter = win32print.OpenPrinter(printer_name)
        try:
            # بدء المستند
            win32print.StartDocPrinter(hprinter, 1, ("POS Job", None, "RAW"))
            win32print.StartPagePrinter(hprinter)

            # إنشاء DC للطابعة
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)
            hdc.StartDoc("POS Job")
            hdc.StartPage()

            # تعيين الخط (حجم 12 نقطة، عربي)
            font = win32ui.CreateFont({
                "name": "Arial",
                "height": -180,  # 12pt = -180
                "weight": win32con.FW_NORMAL,
                "charset": 0,     # ANSI charset (يدعم العربية)
            })
            hdc.SelectObject(font)

            # رسم النص
            y = 100  # بداية من أعلى
            for line in lines:
                if line.get('divider'):
                    # رسم خط فاصل
                    hdc.MoveTo((100, y))
                    hdc.LineTo((800, y))
                    y += 40
                    continue

                align = line.get('align', 'right')
                text = line.get('text', '')
                if not text:
                    continue

                # قياس عرض النص لتحديد المحاذاة
                rect = hdc.GetTextExtent(text)
                x = 800 - rect[0] - 100 if align == 'right' else 100 if align == 'left' else (800 - rect[0]) // 2

                if line.get('bold'):
                    font_bold = win32ui.CreateFont({
                        "name": "Arial Bold",
                        "height": -180,
                        "weight": win32con.FW_BOLD,
                        "charset": 0,
                    })
                    hdc.SelectObject(font_bold)
                    hdc.TextOut(x, y, text)
                    hdc.SelectObject(font)
                else:
                    hdc.TextOut(x, y, text)

                y += 40  # مسافة بين السطور

            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()

            win32print.EndPagePrinter(hprinter)
            win32print.EndDocPrinter(hprinter)

            # فتح الدرج إذا طلب
            if open_drawer:
                # إرسال أمر ESC/POS لفتح الدرج عبر طابعة منفصلة (نفس الطابعة)
                try:
                    h2 = win32print.OpenPrinter(printer_name)
                    try:
                        win32print.StartDocPrinter(h2, 1, ("Drawer Job", None, "RAW"))
                        win32print.StartPagePrinter(h2)
                        win32print.WritePrinter(h2, INIT + OPEN_DRAWER)
                        win32print.EndPagePrinter(h2)
                        win32print.EndDocPrinter(h2)
                    finally:
                        win32print.ClosePrinter(h2)
                except Exception as e:
                    log.error(f"Drawer open error: {e}")

            log.info(f"GDI Print OK -> {printer_name}")
            return True

        finally:
            win32print.ClosePrinter(hprinter)

    except Exception as e:
        log.error(f"GDI Print error: {e}")
        return False

# ----------------------------------------------------------------------
# تحويل قائمة السطور إلى تنسيق مناسب لـ GDI
def prepare_gdi_lines(lines):
    """تحويل السطور الواردة إلى قائمة سطور GDI"""
    gdi_lines = []
    for line in lines:
        if line.get('divider'):
            gdi_lines.append({'divider': True})
            continue
        gdi_lines.append({
            'text': line.get('text', ''),
            'align': line.get('align', 'right'),
            'bold': line.get('bold', False)
        })
    return gdi_lines

# ----------------------------------------------------------------------
# Routes
@app.route('/print', methods=['POST'])
def handle_print():
    d = request.json or {}

    main_lines    = d.get('main_lines', [])
    kitchen_lines = d.get('kitchen_lines', [])
    bar_lines     = d.get('bar_lines', [])
    open_drawer   = d.get('open_drawer', False)

    results = {}

    # طباعة الفاتورة الرئيسية عبر GDI
    if main_lines:
        gdi_lines = prepare_gdi_lines(main_lines)
        results['main'] = print_gdi(MAIN_PRINTER, gdi_lines, open_drawer=open_drawer)

    # طابعة المطبخ (يمكن استخدام GDI أيضًا أو ESC/POS)
    if kitchen_lines:
        gdi_lines_kit = prepare_gdi_lines(kitchen_lines)
        results['kitchen'] = print_gdi(KITCHEN_PRINTER, gdi_lines_kit, open_drawer=False)

    # طابعة البار
    if bar_lines:
        gdi_lines_bar = prepare_gdi_lines(bar_lines)
        results['bar'] = print_gdi(BAR_PRINTER, gdi_lines_bar, open_drawer=False)

    success = all(results.values()) if results else False
    log.info(f'Print results: {results}  success={success}')
    return jsonify({'status': 'done', 'results': results, 'success': success})

@app.route('/drawer', methods=['POST'])
def drawer_route():
    """فتح الدرج فقط"""
    try:
        h = win32print.OpenPrinter(MAIN_PRINTER)
        try:
            win32print.StartDocPrinter(h, 1, ("Drawer Job", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, INIT + OPEN_DRAWER)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        return jsonify({'success': True})
    except Exception as e:
        log.error(f"Drawer open error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    try:
        import win32print
        win32_ok = True
        msg = 'win32print متاح'
    except ImportError:
        win32_ok = False
        msg = 'win32print غير متاح'
    return jsonify({'status': 'running', 'version': '3.0', 'win32print': win32_ok, 'note': msg})

@app.route('/printers', methods=['GET'])
def list_printers():
    try:
        printers = [p[2] for p in win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )]
        return jsonify({'printers': printers})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/test', methods=['GET'])
def test_print():
    """طباعة فاتورة اختبار"""
    lines = [
        {'text': 'اختبار الطباعة', 'align': 'center', 'bold': True},
        {'divider': True},
        {'text': 'طلب رقم: #999', 'bold': True},
        {'text': 'الطاولة: طاولة 5'},
        {'text': 'كوكاكولا  x2'},
        {'text': 'بيتزا مارجريتا  x1'},
        {'divider': True},
        {'text': 'الاجمالي: 150 ج', 'bold': True, 'align': 'center'},
        {'text': 'شكرا لزيارتكم', 'align': 'center'},
    ]
    gdi_lines = prepare_gdi_lines(lines)
    ok = print_gdi(MAIN_PRINTER, gdi_lines, open_drawer=False)
    return jsonify({'success': ok, 'message': 'تم الارسال' if ok else 'فشلت الطباعة'})

if __name__ == '__main__':
    log.info('Print Service v3.0 (GDI Arabic) → http://127.0.0.1:5000')
    log.info('  /health        ← حالة الخدمة')
    log.info('  /printers      ← اسماء الطابعات')
    log.info('  /test          ← طباعة فاتورة اختبار')
    app.run(host='127.0.0.1', port=5000, debug=False)