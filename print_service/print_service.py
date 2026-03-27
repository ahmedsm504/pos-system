"""
Print Service v5.0 — Xprinter XP-D200N
طباعة فواتير كـ Bitmap مع دعم كامل للعربية
يستخدم: arabic-reshaper + python-bidi + Pillow

تثبيت المتطلبات:
    pip install flask pywin32 Pillow arabic-reshaper python-bidi

تشغيل:
    python print_service.py
"""

from flask import Flask, request, jsonify
import logging
import sys
import os
import io

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  ⚙️  إعدادات — عدّلها حسب جهازك
# ══════════════════════════════════════════════════════════════════════════════

MAIN_PRINTER    = "Main Printer"      # طابعة الكاشير (فاتورة كاملة)
KITCHEN_PRINTER = "Kitchen Printer"   # طابعة المطبخ
BAR_PRINTER     = "Bar Printer"       # طابعة البار

# عرض ورقة الطابعة بالبكسل
# 80mm عند 203 DPI  ≈  576 px
# 80mm عند 180 DPI  ≈  566 px
# 58mm عند 203 DPI  ≈  384 px
PAGE_WIDTH_PX = 576

# مسار ملف الخط العربي  — يدعم Unicode كامل
# يمكنك استبداله بأي خط TrueType يدعم العربي
FONT_PATHS = [
    r"C:\Windows\Fonts\arial.ttf",          # Arial (يدعم عربي جيد)
    r"C:\Windows\Fonts\tahoma.ttf",         # Tahoma (أحسن للعربي)
    r"C:\Windows\Fonts\calibri.ttf",        # Calibri
    r"C:\Windows\Fonts\times.ttf",          # Times New Roman
]

# ══════════════════════════════════════════════════════════════════════════════
#  ESC/POS — Cash Drawer فقط (الطباعة بـ Bitmap)
# ══════════════════════════════════════════════════════════════════════════════

ESC         = b'\x1b'
GS          = b'\x1d'
INIT        = ESC + b'@'
OPEN_DRAWER = ESC + b'p\x00\x19\xfa'   # فتح الدرج على PIN 2
CUT_PAPER   = GS  + b'V\x41\x03'       # قطع الورق

# ══════════════════════════════════════════════════════════════════════════════
#  تحضير العربية
# ══════════════════════════════════════════════════════════════════════════════

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_OK = True
    log.info("✅ arabic_reshaper + python-bidi متاحان")
except ImportError:
    ARABIC_OK = False
    log.warning("⚠️  arabic_reshaper أو python-bidi غير مثبتَين — شغّل: pip install arabic-reshaper python-bidi")


def fix_arabic(text: str) -> str:
    """
    يُصلح العربية:
    1. arabic_reshaper  — يوصّل الحروف صح (ك + ت + ا + ب → كتاب)
    2. get_display      — يعكس الاتجاه RTL → LTR كما تتوقع PIL
    """
    if not text or not text.strip():
        return text
    if not ARABIC_OK:
        return text
    try:
        reshaped = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped)
        return bidi_text
    except Exception as e:
        log.warning(f"fix_arabic error: {e}")
        return text


# ══════════════════════════════════════════════════════════════════════════════
#  تحميل الخط
# ══════════════════════════════════════════════════════════════════════════════

def _load_font(size: int):
    """تحميل أول خط متاح من القائمة"""
    from PIL import ImageFont
    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    log.warning("لم يُعثر على خط TrueType — سيُستخدم الخط الافتراضي (قد لا يدعم العربية)")
    return ImageFont.load_default()


# ══════════════════════════════════════════════════════════════════════════════
#  بناء صورة الفاتورة
# ══════════════════════════════════════════════════════════════════════════════

def render_receipt_image(lines: list[dict], width: int = PAGE_WIDTH_PX) -> "Image":
    """
    يحوّل قائمة السطور إلى صورة PIL جاهزة للطباعة.

    كل عنصر في `lines` هو dict يحتوي على:
        text    : str   — نص السطر
        align   : str   — 'right' | 'center' | 'left'  (افتراضي: 'right')
        bold    : bool  — عريض
        size    : str   — 'normal' | 'large'
        divider : bool  — رسم خط فاصل بدلاً من نص
    """
    from PIL import Image, ImageDraw

    PADDING       = 12          # هامش جانبي
    LINE_H_NORMAL = 32          # ارتفاع السطر العادي
    LINE_H_LARGE  = 44          # ارتفاع السطر الكبير
    LINE_H_DIV    = 20          # ارتفاع خط الفصل
    FONT_NORMAL   = _load_font(22)
    FONT_BOLD_N   = _load_font(22)   # سنستخدم نفس الحجم، PIL لا يدعم bold مباشرة إلا بخط منفصل
    FONT_LARGE    = _load_font(30)

    # --- حساب الارتفاع الكلي ---
    total_h = PADDING
    for line in lines:
        if line.get('divider'):
            total_h += LINE_H_DIV
        elif line.get('size') == 'large':
            total_h += LINE_H_LARGE
        else:
            total_h += LINE_H_NORMAL
    total_h += PADDING

    # --- إنشاء الصورة ---
    img  = Image.new('RGB', (width, total_h), color='white')
    draw = ImageDraw.Draw(img)

    y = PADDING
    for line in lines:

        # خط فاصل
        if line.get('divider'):
            mid = y + LINE_H_DIV // 2
            draw.line([(PADDING, mid), (width - PADDING, mid)], fill='black', width=2)
            y += LINE_H_DIV
            continue

        raw_text = line.get('text', '')
        align    = line.get('align', 'right')
        is_large = (line.get('size') == 'large')
        is_bold  = line.get('bold', False)

        font = FONT_LARGE if is_large else (FONT_BOLD_N if is_bold else FONT_NORMAL)
        lh   = LINE_H_LARGE if is_large else LINE_H_NORMAL

        # إصلاح العربية
        display_text = fix_arabic(raw_text)

        # حساب عرض النص
        try:
            bbox      = draw.textbbox((0, 0), display_text, font=font)
            text_w    = bbox[2] - bbox[0]
            text_h    = bbox[3] - bbox[1]
        except AttributeError:
            # PIL قديم
            text_w, text_h = draw.textsize(display_text, font=font)

        # حساب x حسب المحاذاة
        if align == 'center':
            x = (width - text_w) // 2
        elif align == 'left':
            x = PADDING
        else:  # right
            x = width - text_w - PADDING

        x = max(PADDING, x)  # لا يتجاوز الهامش

        # رسم النص
        # لو bold نرسمه مرتين بإزاحة بسيطة لمحاكاة العريض
        draw.text((x, y + (lh - text_h) // 2), display_text, font=font, fill='black')
        if is_bold:
            draw.text((x + 1, y + (lh - text_h) // 2), display_text, font=font, fill='black')

        y += lh

    return img


# ══════════════════════════════════════════════════════════════════════════════
#  تحويل الصورة إلى أوامر ESC/POS Bitmap
# ══════════════════════════════════════════════════════════════════════════════

def image_to_escpos_bitmap(img) -> bytes:
    """
    يحوّل PIL Image إلى أوامر ESC/POS GS v 0 (Raster Bit Image).
    مدعومة على الغالبية العظمى من الطابعات الحرارية بما فيها Xprinter.
    """
    from PIL import Image

    # تحويل إلى أبيض وأسود
    img = img.convert('L')                                # رمادي
    img = img.point(lambda px: 0 if px < 180 else 255)   # عتبة — كل ما هو أغمق من 180 يصبح أسود
    img = img.convert('1')                                # ثنائي (1-bit)

    w, h = img.size

    # كل صف = ceil(width / 8) byte
    bytes_per_row = (w + 7) // 8

    # بناء بيانات الـ bitmap
    bitmap_bytes = bytearray()
    pixels = list(img.getdata())

    for row in range(h):
        for col_byte in range(bytes_per_row):
            byte = 0
            for bit in range(8):
                col = col_byte * 8 + bit
                if col < w:
                    # في PIL Image(1), القيمة 0 = أسود، 255 = أبيض
                    px = pixels[row * w + col]
                    if px == 0:  # أسود → bit = 1
                        byte |= (0x80 >> bit)
            bitmap_bytes.append(byte)

    # أمر GS v 0:  GS 'v' '0' m xL xH yL yH [data]
    # m = 0 (normal density)
    xL = bytes_per_row & 0xFF
    xH = (bytes_per_row >> 8) & 0xFF
    yL = h & 0xFF
    yH = (h >> 8) & 0xFF

    cmd  = INIT
    cmd += GS + b'v' + b'\x00' + b'\x00'
    cmd += bytes([xL, xH, yL, yH])
    cmd += bytes(bitmap_bytes)
    cmd += b'\n' * 4     # تغذية ورق بعد الصورة
    cmd += CUT_PAPER
    return cmd


# ══════════════════════════════════════════════════════════════════════════════
#  إرسال للطابعة عبر win32print
# ══════════════════════════════════════════════════════════════════════════════

def print_raw(printer_name: str, data: bytes) -> bool:
    try:
        import win32print
        h = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(h, 1, ('POS-Bitmap', None, 'RAW'))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        log.info(f"✅  طُبع بنجاح ← {printer_name}  ({len(data):,} bytes)")
        return True

    except ImportError:
        # وضع التطوير على Linux / بدون win32print
        log.warning(f"[MOCK] win32print غير متاح — محاكاة طباعة ← {printer_name}")
        return True

    except Exception as e:
        log.error(f"❌  خطأ في الطباعة ({printer_name}): {e}")
        return False


def print_ticket(printer_name: str, lines: list[dict], open_drawer: bool = False) -> bool:
    """يبني الصورة ويطبعها، مع فتح الدرج اختيارياً"""
    try:
        img  = render_receipt_image(lines)
        data = image_to_escpos_bitmap(img)

        if open_drawer:
            data = INIT + OPEN_DRAWER + data

        return print_raw(printer_name, data)
    except Exception as e:
        log.error(f"print_ticket error: {e}")
        return False


def open_drawer_only(printer_name: str) -> bool:
    """فتح الدرج بدون طباعة"""
    try:
        return print_raw(printer_name, INIT + OPEN_DRAWER)
    except Exception as e:
        log.error(f"open_drawer error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  Flask Routes
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/print', methods=['POST'])
def handle_print():
    d = request.json or {}

    main_lines    = d.get('main_lines',    [])
    kitchen_lines = d.get('kitchen_lines', [])
    bar_lines     = d.get('bar_lines',     [])
    open_drawer   = d.get('open_drawer',   False)

    results = {}

    if main_lines:
        results['main'] = print_ticket(MAIN_PRINTER, main_lines, open_drawer=open_drawer)

    if kitchen_lines:
        results['kitchen'] = print_ticket(KITCHEN_PRINTER, kitchen_lines, open_drawer=False)

    if bar_lines:
        results['bar'] = print_ticket(BAR_PRINTER, bar_lines, open_drawer=False)

    success = all(results.values()) if results else False
    log.info(f"نتائج الطباعة: {results}  — نجاح={success}")
    return jsonify({'status': 'done', 'results': results, 'success': success})


@app.route('/drawer', methods=['POST'])
def drawer_route():
    ok = open_drawer_only(MAIN_PRINTER)
    return jsonify({'success': ok})


@app.route('/health', methods=['GET'])
def health():
    deps = {}
    for pkg in ('win32print', 'PIL', 'arabic_reshaper', 'bidi'):
        try:
            __import__(pkg)
            deps[pkg] = '✅'
        except ImportError:
            deps[pkg] = '❌ غير مثبت'
    return jsonify({
        'status':  'running',
        'version': '5.0',
        'deps':    deps,
        'arabic':  '✅ شغّال' if ARABIC_OK else '❌ محتاج: pip install arabic-reshaper python-bidi',
    })


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


@app.route('/test', methods=['GET'])
def test_print():
    """طباعة فاتورة اختبار للتحقق من العربية"""
    lines = [
        {'text': 'اختبار الطباعة العربية', 'align': 'center', 'bold': True,  'size': 'large'},
        {'divider': True},
        {'text': 'طلب رقم : #999',        'align': 'right',  'bold': True},
        {'text': 'الطاولة  : طاولة 5',    'align': 'right'},
        {'text': 'الويتر   : محمد',        'align': 'right'},
        {'text': 'الوقت    : 14:35',       'align': 'right'},
        {'divider': True},
        {'text': 'كوكاكولا  ×2',           'align': 'right',  'bold': True},
        {'text': '   2 × 15 = 30 ج',       'align': 'right'},
        {'text': 'بيتزا مارجريتا  ×1',     'align': 'right',  'bold': True},
        {'text': '   1 × 85 = 85 ج',       'align': 'right'},
        {'divider': True},
        {'text': 'الإجمالي: 115 ج',        'align': 'center', 'bold': True,  'size': 'large'},
        {'divider': True},
        {'text': 'شكراً لزيارتكم 🙏',      'align': 'center'},
        {'text': '',                        'align': 'center'},
    ]
    ok = print_ticket(MAIN_PRINTER, lines, open_drawer=False)
    return jsonify({
        'success': ok,
        'message': '✅ تم إرسال فاتورة الاختبار' if ok else '❌ فشلت الطباعة',
        'arabic_support': '✅ شغّال' if ARABIC_OK else '❌ arabic-reshaper غير مثبت',
    })


@app.route('/test-save', methods=['GET'])
def test_save_image():
    """
    حفظ صورة الفاتورة محلياً (للتطوير والاختبار بدون طابعة)
    افتح http://127.0.0.1:5000/test-save ثم تحقق من ملف test_receipt.png
    """
    lines = [
        {'text': 'اختبار العربية', 'align': 'center', 'bold': True,  'size': 'large'},
        {'divider': True},
        {'text': 'منتج واحد  ×2', 'align': 'right',  'bold': True},
        {'text': '   2 × 50 = 100 ج', 'align': 'right'},
        {'divider': True},
        {'text': 'الإجمالي: 100 ج', 'align': 'center', 'bold': True},
    ]
    try:
        img = render_receipt_image(lines)
        save_path = os.path.join(os.path.dirname(__file__), 'test_receipt.png')
        img.save(save_path)
        return jsonify({'success': True, 'saved_to': save_path,
                        'arabic': '✅ شغّال' if ARABIC_OK else '❌ تحتاج arabic-reshaper'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    log.info("=" * 55)
    log.info("  🖨️   Print Service v5.0 — Arabic Bitmap Printing")
    log.info("=" * 55)
    log.info(f"  العربية : {'✅ شغّال' if ARABIC_OK else '❌  pip install arabic-reshaper python-bidi'}")
    log.info(f"  الطابعة الرئيسية : {MAIN_PRINTER}")
    log.info(f"  طابعة المطبخ     : {KITCHEN_PRINTER}")
    log.info(f"  طابعة البار      : {BAR_PRINTER}")
    log.info(f"  عرض الورق        : {PAGE_WIDTH_PX} px")
    log.info("-" * 55)
    log.info("  Endpoints:")
    log.info("    http://127.0.0.1:5000/health      ← حالة الخدمة")
    log.info("    http://127.0.0.1:5000/printers    ← أسماء الطابعات")
    log.info("    http://127.0.0.1:5000/test        ← فاتورة اختبار")
    log.info("    http://127.0.0.1:5000/test-save   ← حفظ صورة اختبار (بدون طابعة)")
    log.info("=" * 55)
    app.run(host='127.0.0.1', port=5000, debug=False)