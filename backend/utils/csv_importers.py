"""
CSV parsers that map vendor exports to Campaign metric fields.

Each parser returns a dict with keys matching Campaign columns:
  views, likes, comments, clicks, conversions, revenue.
Missing keys are left untouched on the campaign row.

Inputs are lenient: column name matching is case-insensitive and tolerant of
the slight wording differences between platform exports.
"""

import csv
import io
from typing import Dict, Optional


def _normalize_header(h: str) -> str:
    return (h or "").strip().lower().replace("_", " ").replace("-", " ")


def _read_rows(raw: bytes) -> list[dict]:
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append({_normalize_header(k): (v or "").strip() for k, v in row.items()})
    return rows


def _to_int(s: str) -> int:
    if not s:
        return 0
    s = s.replace(",", "").replace(" ", "")
    try:
        return int(float(s))
    except ValueError:
        return 0


def _to_float(s: str) -> float:
    if not s:
        return 0.0
    s = s.replace(",", "").replace(" ", "").replace("$", "").replace("€", "").replace("₺", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _pick(row: dict, *candidates: str) -> Optional[str]:
    for c in candidates:
        key = _normalize_header(c)
        if key in row:
            return row[key]
    return None


def parse_youtube_studio_csv(raw: bytes) -> Dict:
    """YouTube Studio video-performance export → {views, likes, comments}.

    Sums across all rows (one campaign can span multiple videos).
    """
    rows = _read_rows(raw)
    if not rows:
        raise ValueError("empty CSV")

    views = likes = comments = 0
    for row in rows:
        v = _pick(row, "views", "view count", "izlenme")
        l = _pick(row, "likes", "like count", "beğeni")
        c = _pick(row, "comments", "comment count", "yorum")
        views += _to_int(v) if v else 0
        likes += _to_int(l) if l else 0
        comments += _to_int(c) if c else 0

    if views == 0 and likes == 0 and comments == 0:
        raise ValueError("no recognizable Views/Likes/Comments columns")

    return {"views": views, "likes": likes, "comments": comments}


def parse_shopify_orders_csv(raw: bytes) -> Dict:
    """Shopify orders export → {conversions, revenue}.

    Each row is one order. Revenue = sum of 'Total' column. Conversions = row count.
    """
    rows = _read_rows(raw)
    if not rows:
        raise ValueError("empty CSV")

    revenue = 0.0
    conversions = 0
    for row in rows:
        total = _pick(row, "total", "order total", "subtotal", "net sales")
        if total is not None:
            revenue += _to_float(total)
            conversions += 1

    if conversions == 0:
        raise ValueError("no recognizable Total column")

    return {"conversions": conversions, "revenue": round(revenue, 2)}


def parse_stripe_payouts_csv(raw: bytes) -> Dict:
    """Stripe payouts export → {revenue}.

    Sums the 'Gross' (or 'amount') column. Conversions and views are not
    available from this export; caller should not rely on them being set.
    """
    rows = _read_rows(raw)
    if not rows:
        raise ValueError("empty CSV")

    revenue = 0.0
    matched = False
    for row in rows:
        gross = _pick(row, "gross", "amount", "amount captured", "amount gross")
        if gross is not None:
            revenue += _to_float(gross)
            matched = True

    if not matched:
        raise ValueError("no recognizable Gross/Amount column")

    return {"revenue": round(revenue, 2)}
