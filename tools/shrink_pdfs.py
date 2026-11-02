"""
Shrink the PDFs in pdf/ by recompressing their photos (Chromium embeds them uncompressed).

    pip install pymupdf pillow
    python tools/shrink_pdfs.py

make_pdfs.js runs this for you at the end. Photos become 720px JPEGs, which is plenty for a
letter page and makes each workout about 1 MB instead of 15.
"""
import glob, io, os, sys

import pymupdf
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def shrink(path, max_px=720, quality=70):
    doc = pymupdf.open(path)
    seen = set()
    for page in doc:
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen:
                continue
            seen.add(xref)
            pix = pymupdf.Pixmap(doc, xref)
            if pix.n > 3:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            im.thumbnail((max_px, max_px))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=quality, optimize=True)
            page.replace_image(xref, stream=buf.getvalue())
    tmp = path + ".tmp"
    doc.save(tmp, garbage=4, deflate=True)
    doc.close()
    os.replace(tmp, path)


def main():
    for path in sorted(glob.glob(os.path.join(ROOT, "pdf", "*.pdf"))):
        before = os.path.getsize(path)
        shrink(path)
        print(f"{os.path.relpath(path, ROOT)}: {before // 1024} KB -> {os.path.getsize(path) // 1024} KB")


if __name__ == "__main__":
    sys.exit(main())
