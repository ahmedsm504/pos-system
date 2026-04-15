"""One-off helper: fetch Cairo+Outfit woff2 from Google and write local CSS. Run: python scripts/vendor_google_fonts.py"""
import re
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "static", "vendor", "fonts")
FILES_DIR = os.path.join(OUT_DIR, "files")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
FONT_CSS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Cairo:wght@400;500;600;700;800;900&"
    "family=Outfit:wght@500;600;700&display=swap"
)


def main():
    os.makedirs(FILES_DIR, exist_ok=True)
    req = urllib.request.Request(FONT_CSS_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r:
        css = r.read().decode("utf-8")

    urls = sorted(set(re.findall(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", css)))
    print(f"Found {len(urls)} font files")

    mapping = {}
    used_names = set()
    for u in urls:
        base = u.split("/")[-1].split("?")[0]
        fname = base
        n = 0
        while fname in used_names:
            n += 1
            fname = f"{n}_{base}"
        used_names.add(fname)
        path = os.path.join(FILES_DIR, fname)
        if not os.path.exists(path):
            print("  downloading", fname)
            urllib.request.urlretrieve(u, path)
        mapping[u] = f"files/{fname}"

    for old, new in mapping.items():
        css = css.replace(old, new)

    out_path = os.path.join(OUT_DIR, "cairo-outfit.css")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(css)
    print("Wrote", out_path)


if __name__ == "__main__":
    main()
