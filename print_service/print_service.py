"""
Print Service v5.0 — Xprinter XP-D200N
طباعة الفواتير كصور (Bitmap) مع دعم عربي صحيح
"""

from flask import Flask, request, jsonify
import logging, sys
import win32print
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# -------------------- إعداد اللوج --------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# -------------------- أسماء الطابعات --------------------
MAIN_PRINTER    = "Main Printer"
KITCHEN_PRINTER = "Kitchen Printer"
BAR_PRINTER     = "Bar Printer"

# -------------------- ESC/POS --------------------
ESC = b'\x1b'
GS  = b'\x1d'
INIT = ESC + b'@'
OPEN_DRAWER = ESC + b'p\x00\x19\xfa'

PAGE_WIDTH = 576

# -------------------- الخطوط --------------------
FONT_REGULAR = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
FONT_BOLD    = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 22)
FONT_LARGE   = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 28)

# -------------------- إصلاح العربي --------------------
def fix_arabic(text):
    try:
        reshaped = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped)
        return bidi_text
    except:
        return text

# -------------------- تحويل النص لصورة --------------------
def text_to_image(lines, width=PAGE_WIDTH):
    line_height = 40
    total_height = len(lines) * line_height + 50

    img = Image.new('RGB', (width, total_height), 'white')
    draw = ImageDraw.Draw(img)

    y = 10
    for line in lines:
        if line.get('divider'):
            draw.line((10, y, width-10, y), fill='black', width=2)
            y += line_height
            continue

        text = fix_arabic(line.get('text', ''))

        align = line.get('align', 'right')
        bold = line.get('bold', False)
        size = line.get('size', 'normal')

        font = FONT_LARGE if size == 'large' else (FONT_BOLD if bold else FONT_REGULAR)

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

    return img

# -------------------- تحويل لصيغة الطابعة --------------------
def image_to_escpos(img):
    img = img.convert('L')
    img = img.point(lambda x: 0 if x < 128 else 255, '1')

    bitmap_data = []
    for y in range(img.height):
        row = 0
        for x in range(img.width):
            if x % 8 == 0:
                row = 0
            bit = (img.getpixel((x, y)) == 0)
            row |= (bit << (7 - (x % 8)))
            if (x + 1) % 8 == 0:
                bitmap_data.append(row)

    cmd = INIT
    cmd += GS + b'v0'
    cmd += (img.width // 8).to_bytes(2, 'little')
    cmd += img.height.to_bytes(2, 'little')
    cmd += bytes(bitmap_data)
    cmd += b'\n\n' + GS + b'V\x41\x03'
    return cmd

# -------------------- طباعة --------------------
def print_image(printer_name, lines, open_drawer=False):
    try:
        img = text_to_image(lines)
        data = image_to_escpos(img)

        if open_drawer:
            data = OPEN_DRAWER + data

        h = win32print.OpenPrinter(printer_name)
        win32print.StartDocPrinter(h, 1, ("POS", None, "RAW"))
        win32print.StartPagePrinter(h)
        win32print.WritePrinter(h, data)
        win32print.EndPagePrinter(h)
        win32print.EndDocPrinter(h)
        win32print.ClosePrinter(h)

        return True
    except Exception as e:
        log.error(e)
        return False

# -------------------- API --------------------
@app.route('/print', methods=['POST'])
def handle_print():
    d = request.json or {}

    lines = d.get('main_lines', [])
    open_drawer = d.get('open_drawer', False)

    ok = print_image(MAIN_PRINTER, lines, open_drawer)

    return jsonify({'success': ok})

@app.route('/test')
def test():
    lines = [
        {'text': 'فاتورة اختبار', 'align': 'center', 'bold': True, 'size': 'large'},
        {'divider': True},
        {'text': 'طلب رقم: 123'},
        {'text': 'الطاولة: 5'},
        {'text': 'بيتزا ×1'},
        {'text': 'كولا ×2'},
        {'divider': True},
        {'text': 'الإجمالي: 150 جنيه', 'bold': True},
        {'text': 'شكرا لزيارتكم', 'align': 'center'},
    ]

    ok = print_image(MAIN_PRINTER, lines, open_drawer=True)

    return jsonify({'success': ok})

# --------------------
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)