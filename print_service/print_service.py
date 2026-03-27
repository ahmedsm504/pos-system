"""
Print Service v6.0 — Xprinter XP-D200N LAN
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
import struct

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  إعدادات الطابعات
# ══════════════════════════════════════════════════════════════════════════════

MAIN_PRINTER    = "Main Printer"
KITCHEN_PRINTER = "Kitchen Printer"
BAR_PRINTER     = "Bar Printer"

# عرض ورقة الطابعة بالبكسل (XP-D200N @ 203 DPI, 80mm paper)
PAGE_WIDTH_PX = 576

# مسارات الخطوط — نختار خط يدعم العربية بشكل ممتاز
FONT_PATHS = [
    r"C:\Windows\Fonts\arialbd.ttf",       # Arial Bold
    r"C:\Windows\Fonts\arial.ttf",          # Arial
    r"C:\Windows\Fonts\tahoma.ttf",         # Tahoma
    r"C:\Windows\Fonts\calibri.ttf",        # Calibri
]

FONT_PATHS_REGULAR = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
]

FONT_PATHS_BOLD = [
    r"C:\Windows\Fonts\arialbd.ttf",       # Arial Bold
    r"C:\Windows\Fonts\tahomabd.ttf",      # Tahoma Bold
    r"C:\Windows\Fonts\calibrib.ttf",      # Calibri Bold
    r"C:\Windows\Fonts\arial.ttf",          # fallback
]

# ══════════════════════════════════════════════════════════════════════════════
#  ESC/POS commands
# ══════════════════════════════════════════════════════════════════════════════

ESC         = b'\x1b'
GS          = b'\x1d'
INIT        = ESC + b'@'
OPEN_DRAWER = ESC + b'p\x00\x19\xfa'
CUT_PAPER   = GS  + b'V\x41\x03'

# ══════════════════════════════════════════════════════════════════════════════
#  تحضير العربية
# ══════════════════════════════════════════════════════════════════════════════

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    _reshaper = arabic_reshaper.ArabicReshaper(configuration={
        'delete_harakat': True,
        'support_ligatures': True,
        'LETTERS_ARABIC': True,
        'LETTERS_ARABIC_V2': True,
        'support_zwj': True,
    })
    ARABIC_OK = True
    log.info("arabic_reshaper + python-bidi loaded OK")
except ImportError:
    _reshaper = None
    ARABIC_OK = False
    log.warning("arabic_reshaper or python-bidi missing — pip install arabic-reshaper python-bidi")


def fix_arabic(text: str) -> str:
    if not text or not text.strip():
        return text
    if not ARABIC_OK:
        return text
    try:
        reshaped = _reshaper.reshape(text)
        bidi_text = get_display(reshaped)
        return bidi_text
    except Exception as e:
        log.warning(f"fix_arabic error: {e}")
        return text


# ══════════════════════════════════════════════════════════════════════════════
#  تحميل الخط
# ══════════════════════════════════════════════════════════════════════════════

_font_cache = {}

def _load_font(size: int, bold: bool = False):
    cache_key = (size, bold)
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    from PIL import ImageFont
    paths = FONT_PATHS_BOLD if bold else FONT_PATHS_REGULAR
    for path in paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                _font_cache[cache_key] = font
                return font
            except Exception:
                continue

    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                _font_cache[cache_key] = font
                return font
            except Exception:
                continue

    log.warning("No TrueType font found — using default (Arabic may not work)")
    font = ImageFont.load_default()
    _font_cache[cache_key] = font
    return font


# ══════════════════════════════════════════════════════════════════════════════
#  بناء صورة الفاتورة
# ══════════════════════════════════════════════════════════════════════════════

def render_receipt_image(lines: list[dict], width: int = PAGE_WIDTH_PX) -> "Image":
    """
    يحوّل قائمة السطور إلى صورة PIL جاهزة للطباعة.

    كل عنصر في `lines` هو dict:
        text      : str   — نص السطر
        align     : str   — 'right' | 'center' | 'left'  (افتراضي: 'right')
        bold      : bool  — عريض
        size      : str   — 'small' | 'normal' | 'large' | 'xlarge'
        divider   : bool  — رسم خط فاصل
        divider_style : str — 'line' | 'double' | 'dashed' | 'stars' (default: 'dashed')
        spacing   : int   — مسافة إضافية بعد السطر
        cols      : list  — أعمدة [{'text': ..., 'width': fraction, 'align': ...}]
    """
    from PIL import Image, ImageDraw

    PADDING        = 16
    FONT_SIZE_SM   = 18
    FONT_SIZE_NORM = 22
    FONT_SIZE_LG   = 28
    FONT_SIZE_XL   = 34

    LINE_H_SM      = 26
    LINE_H_NORM    = 34
    LINE_H_LG      = 42
    LINE_H_XL      = 50
    LINE_H_DIV     = 18
    LINE_H_SPACE   = 10

    def _get_font_and_height(line):
        sz = line.get('size', 'normal')
        is_bold = line.get('bold', False)
        if sz == 'small':
            return _load_font(FONT_SIZE_SM, is_bold), LINE_H_SM
        elif sz == 'large':
            return _load_font(FONT_SIZE_LG, is_bold), LINE_H_LG
        elif sz == 'xlarge':
            return _load_font(FONT_SIZE_XL, is_bold), LINE_H_XL
        else:
            return _load_font(FONT_SIZE_NORM, is_bold), LINE_H_NORM

    # --- حساب الارتفاع الكلي ---
    total_h = PADDING
    for line in lines:
        if line.get('divider'):
            total_h += LINE_H_DIV
        elif line.get('spacer'):
            total_h += line.get('height', LINE_H_SPACE)
        elif line.get('cols'):
            _, lh = _get_font_and_height(line)
            total_h += lh
        else:
            _, lh = _get_font_and_height(line)
            total_h += lh
        total_h += line.get('spacing', 0)
    total_h += PADDING + 20

    # --- إنشاء الصورة (grayscale ثم يتحول 1-bit عند الطباعة) ---
    img  = Image.new('L', (width, total_h), color=255)  # grayscale, white
    draw = ImageDraw.Draw(img)

    y = PADDING

    for line in lines:
        extra_spacing = line.get('spacing', 0)

        # --- spacer ---
        if line.get('spacer'):
            y += line.get('height', LINE_H_SPACE)
            continue

        # --- خط فاصل ---
        if line.get('divider'):
            style = line.get('divider_style', 'dashed')
            mid = y + LINE_H_DIV // 2

            if style == 'double':
                draw.line([(PADDING, mid - 2), (width - PADDING, mid - 2)], fill=0, width=1)
                draw.line([(PADDING, mid + 2), (width - PADDING, mid + 2)], fill=0, width=1)
            elif style == 'stars':
                star_text = fix_arabic('★' * 30)
                font = _load_font(FONT_SIZE_SM, False)
                try:
                    bbox = draw.textbbox((0, 0), star_text, font=font)
                    tw = bbox[2] - bbox[0]
                except AttributeError:
                    tw, _ = draw.textsize(star_text, font=font)
                x = (width - tw) // 2
                draw.text((x, y), star_text, font=font, fill=0)
            elif style == 'line':
                draw.line([(PADDING, mid), (width - PADDING, mid)], fill=0, width=2)
            else:  # dashed
                dash_w = 4
                gap_w = 4
                x_pos = PADDING
                while x_pos < width - PADDING:
                    end_x = min(x_pos + dash_w, width - PADDING)
                    draw.line([(x_pos, mid), (end_x, mid)], fill=0, width=1)
                    x_pos += dash_w + gap_w

            y += LINE_H_DIV + extra_spacing
            continue

        # --- أعمدة (مثلا اسم المنتج | السعر) ---
        if line.get('cols'):
            font, lh = _get_font_and_height(line)
            cols = line['cols']
            usable_w = width - 2 * PADDING
            col_x = PADDING

            for col in cols:
                col_w = int(usable_w * col.get('width', 1.0 / len(cols)))
                col_text = fix_arabic(col.get('text', ''))
                col_align = col.get('align', 'right')
                col_bold = col.get('bold', line.get('bold', False))
                col_font = _load_font(
                    {'small': FONT_SIZE_SM, 'large': FONT_SIZE_LG, 'xlarge': FONT_SIZE_XL}.get(
                        line.get('size', 'normal'), FONT_SIZE_NORM
                    ),
                    col_bold
                )

                try:
                    bbox = draw.textbbox((0, 0), col_text, font=col_font)
                    tw = bbox[2] - bbox[0]
                    th = bbox[3] - bbox[1]
                except AttributeError:
                    tw, th = draw.textsize(col_text, font=col_font)

                if col_align == 'center':
                    cx = col_x + (col_w - tw) // 2
                elif col_align == 'left':
                    cx = col_x
                else:
                    cx = col_x + col_w - tw

                cx = max(col_x, min(cx, col_x + col_w - tw))
                draw.text((cx, y + (lh - th) // 2), col_text, font=col_font, fill=0)
                col_x += col_w

            y += lh + extra_spacing
            continue

        # --- سطر نص عادي ---
        raw_text = line.get('text', '')
        align    = line.get('align', 'right')
        font, lh = _get_font_and_height(line)

        display_text = fix_arabic(raw_text)

        try:
            bbox   = draw.textbbox((0, 0), display_text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except AttributeError:
            text_w, text_h = draw.textsize(display_text, font=font)

        if align == 'center':
            x = (width - text_w) // 2
        elif align == 'left':
            x = PADDING
        else:
            x = width - text_w - PADDING

        x = max(PADDING, x)

        draw.text((x, y + (lh - text_h) // 2), display_text, font=font, fill=0)

        y += lh + extra_spacing

    return img


# ══════════════════════════════════════════════════════════════════════════════
#  تحويل الصورة إلى أوامر ESC/POS Bitmap
# ══════════════════════════════════════════════════════════════════════════════

def image_to_escpos_bitmap(img) -> bytes:
    """
    يحوّل PIL Image إلى أوامر ESC/POS GS v 0 (Raster Bit Image).
    متوافق مع XP-D200N وغالبية طابعات Xprinter.
    """
    from PIL import Image

    gray = img.convert('L')
    # threshold: anything darker than 180 → black
    bw = gray.point(lambda px: 0 if px < 180 else 255, '1')
    w, h = bw.size

    if w % 8 != 0:
        new_w = ((w + 7) // 8) * 8
        padded = Image.new('1', (new_w, h), color=1)
        padded.paste(bw, (0, 0))
        bw = padded
        w = new_w

    bytes_per_row = w // 8
    pixels = list(bw.getdata())

    # بناء البيانات — الصورة تُرسل بشرائح (stripes) عشان ما نتعداش حد الذاكرة
    MAX_STRIPE_H = 255

    cmd = bytearray()
    cmd += INIT

    row_offset = 0
    while row_offset < h:
        stripe_h = min(MAX_STRIPE_H, h - row_offset)

        stripe_data = bytearray()
        for row in range(row_offset, row_offset + stripe_h):
            for col_byte in range(bytes_per_row):
                byte_val = 0
                for bit in range(8):
                    col = col_byte * 8 + bit
                    if col < w:
                        px = pixels[row * w + col]
                        if px == 0:
                            byte_val |= (0x80 >> bit)
                stripe_data.append(byte_val)

        xL = bytes_per_row & 0xFF
        xH = (bytes_per_row >> 8) & 0xFF
        yL = stripe_h & 0xFF
        yH = (stripe_h >> 8) & 0xFF

        cmd += GS + b'v0' + b'\x00'
        cmd += bytes([xL, xH, yL, yH])
        cmd += bytes(stripe_data)

        row_offset += stripe_h

    cmd += b'\n' * 5
    cmd += CUT_PAPER
    return bytes(cmd)


# ══════════════════════════════════════════════════════════════════════════════
#  إرسال للطابعة عبر win32print
# ══════════════════════════════════════════════════════════════════════════════

def print_raw(printer_name: str, data: bytes) -> bool:
    try:
        import win32print
        h = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(h, 1, ('POS-Receipt', None, 'RAW'))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        log.info(f"Printed OK -> {printer_name}  ({len(data):,} bytes)")
        return True

    except ImportError:
        log.warning(f"[MOCK] win32print not available — simulating print -> {printer_name}")
        return True

    except Exception as e:
        log.error(f"Print error ({printer_name}): {e}")
        return False


def print_ticket(printer_name: str, lines: list[dict], open_drawer: bool = False) -> bool:
    try:
        img  = render_receipt_image(lines)
        data = image_to_escpos_bitmap(img)

        if open_drawer:
            data = INIT + OPEN_DRAWER + data

        return print_raw(printer_name, data)
    except Exception as e:
        log.error(f"print_ticket error: {e}")
        import traceback
        traceback.print_exc()
        return False


def open_drawer_only(printer_name: str) -> bool:
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
    log.info(f"Print results: {results} — success={success}")
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
            deps[pkg] = 'OK'
        except ImportError:
            deps[pkg] = 'MISSING'
    return jsonify({
        'status':  'running',
        'version': '6.0',
        'deps':    deps,
        'arabic':  'OK' if ARABIC_OK else 'MISSING: pip install arabic-reshaper python-bidi',
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
        return jsonify({'printers': [], 'note': 'win32print not available'})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/test', methods=['GET'])
def test_print():
    lines = _build_test_receipt()
    ok = print_ticket(MAIN_PRINTER, lines, open_drawer=False)
    return jsonify({
        'success': ok,
        'message': 'Test receipt sent' if ok else 'Print failed',
        'arabic_support': 'OK' if ARABIC_OK else 'MISSING',
    })


@app.route('/test-save', methods=['GET'])
def test_save_image():
    lines = _build_test_receipt()
    try:
        img = render_receipt_image(lines)
        save_path = os.path.join(os.path.dirname(__file__), 'test_receipt.png')
        img.save(save_path)
        return jsonify({'success': True, 'saved_to': save_path,
                        'arabic': 'OK' if ARABIC_OK else 'MISSING'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


def _build_test_receipt():
    return [
        {'spacer': True, 'height': 5},
        {'text': 'كافيه الريان', 'align': 'center', 'bold': True, 'size': 'xlarge'},
        {'text': 'شارع التحرير - القاهرة', 'align': 'center', 'size': 'small'},
        {'text': 'تليفون: 01012345678', 'align': 'center', 'size': 'small'},
        {'divider': True, 'divider_style': 'double'},

        {'text': 'فاتورة بيع', 'align': 'center', 'bold': True, 'size': 'large'},
        {'divider': True, 'divider_style': 'dashed'},

        {'cols': [
            {'text': '#999', 'width': 0.3, 'align': 'right', 'bold': True},
            {'text': 'طلب رقم', 'width': 0.7, 'align': 'right'},
        ], 'bold': True},
        {'cols': [
            {'text': 'داخل المحل', 'width': 0.3, 'align': 'right'},
            {'text': 'النوع', 'width': 0.7, 'align': 'right'},
        ]},
        {'cols': [
            {'text': 'طاولة 5', 'width': 0.3, 'align': 'right'},
            {'text': 'الطاولة', 'width': 0.7, 'align': 'right'},
        ]},
        {'cols': [
            {'text': 'محمد', 'width': 0.3, 'align': 'right'},
            {'text': 'الويتر', 'width': 0.7, 'align': 'right'},
        ]},
        {'cols': [
            {'text': '14:35', 'width': 0.3, 'align': 'right'},
            {'text': 'الوقت', 'width': 0.7, 'align': 'right'},
        ]},
        {'cols': [
            {'text': 'احمد', 'width': 0.3, 'align': 'right'},
            {'text': 'الكاشير', 'width': 0.7, 'align': 'right'},
        ]},

        {'divider': True, 'divider_style': 'double'},

        {'cols': [
            {'text': 'الاجمالي', 'width': 0.25, 'align': 'left'},
            {'text': 'السعر', 'width': 0.2, 'align': 'center'},
            {'text': 'الكمية', 'width': 0.15, 'align': 'center'},
            {'text': 'الصنف', 'width': 0.4, 'align': 'right'},
        ], 'bold': True, 'size': 'small'},
        {'divider': True, 'divider_style': 'dashed'},

        {'cols': [
            {'text': '30 ج', 'width': 0.25, 'align': 'left'},
            {'text': '15', 'width': 0.2, 'align': 'center'},
            {'text': '2', 'width': 0.15, 'align': 'center'},
            {'text': 'كوكاكولا', 'width': 0.4, 'align': 'right'},
        ]},
        {'cols': [
            {'text': '85 ج', 'width': 0.25, 'align': 'left'},
            {'text': '85', 'width': 0.2, 'align': 'center'},
            {'text': '1', 'width': 0.15, 'align': 'center'},
            {'text': 'بيتزا مارجريتا', 'width': 0.4, 'align': 'right'},
        ]},
        {'text': '  * بدون بصل', 'align': 'right', 'size': 'small'},
        {'cols': [
            {'text': '50 ج', 'width': 0.25, 'align': 'left'},
            {'text': '25', 'width': 0.2, 'align': 'center'},
            {'text': '2', 'width': 0.15, 'align': 'center'},
            {'text': 'عصير مانجو', 'width': 0.4, 'align': 'right'},
        ]},

        {'divider': True, 'divider_style': 'double'},

        {'cols': [
            {'text': '165.00 ج', 'width': 0.5, 'align': 'left', 'bold': True},
            {'text': 'الاجمالي', 'width': 0.5, 'align': 'right', 'bold': True},
        ], 'bold': True, 'size': 'large'},

        {'divider': True, 'divider_style': 'double'},
        {'spacer': True, 'height': 8},
        {'text': 'شكرا لزيارتكم', 'align': 'center', 'bold': True, 'size': 'normal'},
        {'text': 'نتمنى لكم وقتا سعيدا', 'align': 'center', 'size': 'small'},
        {'spacer': True, 'height': 10},
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    log.info("=" * 55)
    log.info("  Print Service v6.0 — Arabic Bitmap Printing")
    log.info("=" * 55)
    log.info(f"  Arabic : {'OK' if ARABIC_OK else 'MISSING — pip install arabic-reshaper python-bidi'}")
    log.info(f"  Main   : {MAIN_PRINTER}")
    log.info(f"  Kitchen: {KITCHEN_PRINTER}")
    log.info(f"  Bar    : {BAR_PRINTER}")
    log.info(f"  Width  : {PAGE_WIDTH_PX} px")
    log.info("-" * 55)
    log.info("  Endpoints:")
    log.info("    http://127.0.0.1:5050/health")
    log.info("    http://127.0.0.1:5050/printers")
    log.info("    http://127.0.0.1:5050/test")
    log.info("    http://127.0.0.1:5050/test-save")
    log.info("=" * 55)
    app.run(host='127.0.0.1', port=5050, debug=False)
