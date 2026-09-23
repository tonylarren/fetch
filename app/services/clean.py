"""Deterministic post-processing only.

No LLM in here on purpose: if this service starts interpreting CVs, every prompt
tweak becomes a redeploy and you can't reprocess old output without re-OCRing.
"""
import re
import unicodedata

HYPHEN_BREAK = re.compile(r"(\w)[-\u2010\u2011]\s*\n\s*(\w)")
MULTI_SPACE = re.compile(r"[ \t\u00a0]{2,}")
MULTI_NEWLINE = re.compile(r"\n{3,}")
BULLETS = re.compile(r"^[\s]*[\u2022\u25cf\u25aa\u00b7\u2043\-\*o]\s+", re.MULTILINE)


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = HYPHEN_BREAK.sub(r"\1\2", text)          # de-hyphenate across line breaks
    text = BULLETS.sub("- ", text)                  # unify bullet glyphs
    text = MULTI_SPACE.sub(" ", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def detect_columns(blocks: list[dict], page_width: float) -> int:
    """Crude 1-vs-2 column detector: look for a vertical gutter near the middle."""
    if len(blocks) < 8 or page_width <= 0:
        return 1
    mid = page_width / 2
    band = page_width * 0.06
    crossing = sum(1 for b in blocks if b["bbox"][0] < mid - band < mid + band < b["bbox"][2])
    left = sum(1 for b in blocks if b["bbox"][2] <= mid)
    right = sum(1 for b in blocks if b["bbox"][0] >= mid)
    if crossing <= max(1, len(blocks) * 0.08) and left >= 3 and right >= 3:
        return 2
    return 1


def order_blocks(blocks: list[dict], page_width: float) -> list[dict]:
    """Sort into reading order. Two-column CVs come out scrambled otherwise."""
    if not blocks:
        return []
    columns = detect_columns(blocks, page_width)
    if columns == 2:
        mid = page_width / 2
        left = [b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 < mid]
        right = [b for b in blocks if (b["bbox"][0] + b["bbox"][2]) / 2 >= mid]
        key = lambda b: (round(b["bbox"][1] / 10), b["bbox"][0])  # noqa: E731
        return sorted(left, key=key) + sorted(right, key=key)
    return sorted(blocks, key=lambda b: (round(b["bbox"][1] / 10), b["bbox"][0]))


def blocks_to_text(blocks: list[dict]) -> str:
    lines, current, last_y = [], [], None
    for b in blocks:
        y = b["bbox"][1]
        if last_y is not None and abs(y - last_y) > 8:
            lines.append(" ".join(current))
            current = []
        current.append(b["text"].strip())
        last_y = y
    if current:
        lines.append(" ".join(current))
    return normalize_text("\n".join(l for l in lines if l.strip()))


def filter_blocks(blocks: list[dict], min_score: float) -> list[dict]:
    return [b for b in blocks if b.get("score", 1.0) >= min_score and b["text"].strip()]
