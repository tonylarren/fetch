"""Download PaddleOCR models at image build time."""
import os
import sys

lang = os.environ.get("OCR_LANG", "fr")
from paddleocr import PaddleOCR  # noqa: E402

try:
    PaddleOCR(lang=lang, use_textline_orientation=True)
except TypeError:
    PaddleOCR(lang=lang, use_angle_cls=True, show_log=False)
print(f"models baked for lang={lang}", file=sys.stderr)
