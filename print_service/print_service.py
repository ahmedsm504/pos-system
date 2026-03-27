"""
Print Service v4.0 — Xprinter XP-D200N
طباعة الفواتير كصور (Bitmap) لضمان ظهور العربية
تشغيل:  python print_service.py
"""

from flask import Flask, request, jsonify
import logging, sys
import win32print
import win32ui
import win32con
from PIL import Image, ImageDraw, ImageFont
import io

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

# ESC/POS Constants
ESC = b'\x1b'
GS  = b'\x1d'
INIT = ESC + b'@'
OPEN_DRAWER = ESC + b'p\x00\x19\xfa'

# عرض الصفحة بالبكسل (80mm ≈ 576 بكسل عند 203dpi)
PAGE_WIDTH = 576

# إعدادات الخط
FONT_REGULAR = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
FONT_BOLD    = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 14)
FONT_LARGE   = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 18)

def text_to_image(lines, width=PAGE_WIDTH):
    """تحويل قائمة السطور إلى صورة"""
    # حساب ارتفاع الصورة
    line_height = 30
    total_height = len(lines) * line_height + 50
    img = Image.new('RGB', (width, total_height), color='white')
    draw = ImageDraw.Draw(img)

    y = 10
    for line in lines:
        text = line.get('text', '')
        align = line.get('align', 'right')
        bold = line.get('bold', False)
        size = line.get('size', 'normal')

        # اختيار الخط
        if size == 'large':
            font = FONT_LARGE
        else:
            font = FONT_BOLD if bold else FONT_REGULAR

        # حساب عرض النص
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        if align == 'right':
            x = width - text_width - 10
        elif align == 'center':
            x = (width - text_width) // 2
        else:
            x = 10

        draw.text((x, y), text, font=font, fill='black')
        y += line_height

        # إذا كان هناك سطر فاصل
        if line.get('divider'):
            draw.line((10, y, width-10, y), fill='black', width=1)
            y += line_height

    return img

def image_to_escpos(img):
    """تحويل صورة إلى أوامر ESC/POS للطباعة"""
    # تحويل الصورة إلى تدرج رمادي ثم إلى 1-bit (ثنائي)
    img = img.convert('L')  # تدرج رمادي
    img = img.point(lambda x: 0 if x < 128 else 255, '1')  # عتبة لثنائي

    # إعادة التحجيم لعرض الطابعة
    img = img.resize((PAGE_WIDTH, int(img.height * PAGE_WIDTH / img.width)), Image.Resampling.LANCZOS)

    # الحصول على بيانات الصورة
    bitmap_data = []
    for y in range(img.height):
        row = 0
        for x in range(img.width):
            if x % 8 == 0:
                row = 0
            bit = (img.getpixel((x, y)) == 0)  # الأسود = 1
            row |= (bit << (7 - (x % 8)))
            if (x + 1) % 8 == 0 or x == img.width - 1:
                bitmap_data.append(row)
                row = 0

    # بناء الأمر
    cmd = INIT
    cmd += GS + b'v' + b'\x00' + (img.height & 0xff).to_bytes(1, 'little') + ((img.height >> 8) & 0xff).to_bytes(1, 'little')
    cmd += (img.width & 0xff).to_bytes(1, 'little') + ((img.width >> 8) & 0xff).to_bytes(1, 'little')
    cmd += bytes(bitmap_data)
    cmd += b'\x0a\x0a' + GS + b'V\x41\x03'  # قص الورق
    return cmd

def print_image(printer_name, lines, open_drawer=False):
    """طباعة الفاتورة كصورة"""
    try:
        img = text_to_image(lines)
        data = image_to_escpos(img)
        if open_drawer:
            data = OPEN_DRAWER + data
        # إرسال البيانات إلى الطابعة
        h = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(h, 1, ("POS Job", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        log.info(f"Print image OK → {printer_name}")
        return True
    except Exception as e:
        log.error(f"Print image error: {e}")
        return False

def print_drawer(printer_name):
    """فتح الدرج فقط"""
    try:
        h = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(h, 1, ("Drawer", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, INIT + OPEN_DRAWER)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        return True
    except Exception as e:
        log.error(f"Drawer error: {e}")
        return False

# ----------------------------------------------------------------------
# تحويل قائمة السطور إلى تنسيق داخلي
def prepare_image_lines(lines):
    """تحويل السطور من JSON إلى قائمة للصورة"""
    image_lines = []
    for line in lines:
        if line.get('divider'):
            image_lines.append({'divider': True})
            continue
        image_lines.append({
            'text': line.get('text', ''),
            'align': line.get('align', 'right'),
            'bold': line.get('bold', False),
            'size': line.get('size', 'normal')
        })
    return image_lines

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

    if main_lines:
        img_lines = prepare_image_lines(main_lines)
        results['main'] = print_image(MAIN_PRINTER, img_lines, open_drawer)

    if kitchen_lines:
        img_lines = prepare_image_lines(kitchen_lines)
        results['kitchen'] = print_image(KITCHEN_PRINTER, img_lines, open_drawer=False)

    if bar_lines:
        img_lines = prepare_image_lines(bar_lines)
        results['bar'] = print_image(BAR_PRINTER, img_lines, open_drawer=False)

    success = all(results.values()) if results else False
    log.info(f'Print results: {results}  success={success}')
    return jsonify({'status': 'done', 'results': results, 'success': success})

@app.route('/drawer', methods=['POST'])
def drawer_route():
    ok = print_drawer(MAIN_PRINTER)
    return jsonify({'success': ok})

@app.route('/health', methods=['GET'])
def health():
    try:
        import win32print
        win32_ok = True
        msg = 'win32print متاح'
    except ImportError:
        win32_ok = False
        msg = 'win32print غير متاح'
    return jsonify({'status': 'running', 'version': '4.0', 'win32print': win32_ok, 'note': msg})

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
    img_lines = prepare_image_lines(lines)
    ok = print_image(MAIN_PRINTER, img_lines, open_drawer=False)
    return jsonify({'success': ok, 'message': 'تم الارسال' if ok else 'فشلت الطباعة'})

if __name__ == '__main__':
    log.info('Print Service v4.0 (Bitmap Arabic) → http://127.0.0.1:5000')
    log.info('  /health        ← حالة الخدمة')
    log.info('  /printers      ← اسماء الطابعات')
    log.info('  /test          ← طباعة فاتورة اختبار')
    app.run(host='127.0.0.1', port=5000, debug=False)