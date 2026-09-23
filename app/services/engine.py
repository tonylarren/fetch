"""PaddleOCR wrapper.

Two things matter here:
1. The model is loaded ONCE per worker process (lru_cache), never per request.
2. PaddleOCR changed its result shape between 2.x and 3.x. _normalize() handles
   both so a version bump doesn't silently break parsing.
"""
import logging
from functools import lru_cache

import numpy as np

log = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def get_engine(lang: str = "fr"):
    from paddleocr import PaddleOCR

    try:  # paddleocr >= 3.x
        return PaddleOCR(lang=lang, use_textline_orientation=True)
    except TypeError:  # paddleocr 2.x
        return PaddleOCR(lang=lang, use_angle_cls=True, show_log=False)


def warmup(lang: str) -> None:
    """Call at worker start so the first real CV isn't paying model load time."""
    img = np.full((64, 256, 3), 255, dtype=np.uint8)
    try:
        run(img, lang)
        log.info("ocr engine warm (lang=%s)", lang)
    except Exception as e:  # noqa: BLE001
        log.warning("warmup failed: %s", e)


def _poly_to_bbox(poly) -> list[float]:
    pts = np.asarray(poly, dtype=float).reshape(-1, 2)
    return [
        float(pts[:, 0].min()), float(pts[:, 1].min()),
        float(pts[:, 0].max()), float(pts[:, 1].max()),
    ]


def _normalize(raw) -> list[dict]:
    """Return [{text, score, bbox}] from either PaddleOCR result shape."""
    blocks: list[dict] = []
    if not raw:
        return blocks

    first = raw[0] if isinstance(raw, list) else raw

    # 3.x: dict-like with rec_texts / rec_scores / dt_polys (or rec_polys)
    if isinstance(first, dict) or hasattr(first, "get"):
        texts = first.get("rec_texts") or []
        scores = first.get("rec_scores") or []
        polys = first.get("rec_polys") or first.get("dt_polys") or []
        for i, text in enumerate(texts):
            score = float(scores[i]) if i < len(scores) else 0.0
            bbox = _poly_to_bbox(polys[i]) if i < len(polys) else [0, 0, 0, 0]
            blocks.append({"text": text, "score": score, "bbox": bbox})
        return blocks

    # 2.x: [[ [poly, (text, score)], ... ]]
    page = raw[0] if isinstance(raw[0], list) else raw
    for item in page or []:
        try:
            poly, (text, score) = item[0], item[1]
            blocks.append(
                {"text": text, "score": float(score), "bbox": _poly_to_bbox(poly)}
            )
        except Exception:  # noqa: BLE001, S112
            continue
    return blocks


def run(image: np.ndarray, lang: str) -> list[dict]:
    engine = get_engine(lang)
    if hasattr(engine, "predict"):
        raw = engine.predict(image)
    else:
        raw = engine.ocr(image, cls=True)
    return _normalize(raw)
