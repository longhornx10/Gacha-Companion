"""Shared Prydwen page parsers (M25).

Prydwen renders redeem-code boxes identically across game pages (ZZZ hub,
NTE codes page, HSR hub): a copy icon, then ``<p class="code">CODE</p>
<p class="rewards">...</p><p class="date">Released on DD.MM.YYYY</p>``.
Adapters call :func:`parse_codes` from their ``codes_transform`` hook.

The warp/banners pages are also shared markup across games: server-rendered
``<article class="banner-card">`` blocks carrying ``data-section``
(current/upcoming), per-region ISO start/end timestamps and featured rate-up
links. :func:`parse_banners` turns those into ``banner`` catalog rows.
"""

from __future__ import annotations

import html as html_mod
import re
from datetime import UTC, datetime
from typing import Any

_CODE_BOX = re.compile(
    r'<p class="code">(?:<svg.*?</svg>\s*(?:<!-- -->)?)?([A-Za-z0-9]+)</p>'
    r'<p class="rewards">(.*?)</p>'
    r'<p class="date">(?:<!-- -->)?(.*?)</p>',
    re.S,
)
_DATE_SUFFIX = re.compile(r"Released on\s*(?:<!-- -->)?\s*")
_TAG = re.compile(r"<[^>]+>")
# A codes section header that says "expired" flips the status of boxes after it.
_EXPIRED_HEADER = re.compile(r"<h[1-6][^>]*>[^<]*expired[^<]*</h[1-6]>", re.IGNORECASE)


def parse_codes(html: str) -> list[dict[str, Any]]:
    if not isinstance(html, str):
        return []
    expired_from = len(html)
    header = _EXPIRED_HEADER.search(html)
    if header:
        expired_from = header.end()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _CODE_BOX.finditer(html):
        code, rewards, date_text = match.groups()
        code = code.strip()
        if not code or code.lower() in seen:
            continue
        seen.add(code.lower())
        discovered = None
        raw = _DATE_SUFFIX.sub("", _TAG.sub("", date_text)).strip()
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                discovered = datetime.strptime(raw, fmt).replace(tzinfo=UTC)
                break
            except ValueError:
                continue
        rows.append(
            {
                "code": code,
                "rewards": _TAG.sub("", rewards).strip() or None,
                "status": "expired" if match.start() >= expired_from else "active",
                "discovered_at": discovered,
                "source": "prydwen",
            }
        )
    return rows


_BANNER_SPLIT = re.compile(r'(<article class="banner-card[^"]*"[^>]*>)')
_SECTION = re.compile(r'data-section="(\w+)"')
_CATEGORY = re.compile(r'data-category="(\w+)"')
_BANNER_NAME = re.compile(r'<p class="banner-name">([^<]+)</p>')
_BANNER_TYPE = re.compile(r'<span class="banner-type">([^<]+)</span>')
_RARITY = re.compile(r'<span class="rarity">([^<]+)</span>')
_ART = re.compile(r'<img[^>]+src="(https://cdn\.prydwen\.gg/[^"]+)"')
_TIMER = re.compile(r'data-mode="(\w+)"[^>]*data-start-na="([^"]*)"[^>]*data-end-na="([^"]*)"')
_PHASE = re.compile(r'<div class="banner-phase-meta"><span>([^<]+)</span>')
_FEATURED_LINK = re.compile(r'<a class="featured-rate-up" href="([^"]+)">([^<]+)</a>')
_CARD_LINK = re.compile(r'<a class="banner-card-link"[^>]*href="([^"]+)"')
_ASSET_SLUG = re.compile(r"/([a-z0-9-]+)(?:_full)?\.webp")


def _rarity_number(text: str) -> int | None:
    """>S-Rank<, >5-star Light Cone<, >4-star< -> 5/4 (None when unparseable)."""
    m = re.search(r"(\d)-star", text)
    if m:
        return int(m.group(1))
    m = re.search(r"\b([SAB])[- ]?Rank\b", text)
    return {"S": 5, "A": 4, "B": 3}.get(m.group(1)) if m else None


def parse_banners(html: str) -> list[dict[str, Any]]:
    """Warp/banners page HTML -> ``banner`` catalog rows.

    One row per banner run: key is slug + start date so a rerun is a new row.
    Dates are the NA server window (Prydwen's canonical display) and are kept
    as raw strings when unparseable — honest unknown beats a wrong guess.
    """
    if not isinstance(html, str):
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    parts = _BANNER_SPLIT.split(html)
    pairs = list(zip(parts[1::2], parts[2::2], strict=True))  # (article open tag, card body)
    for tag, raw_block in pairs:
        block = raw_block.split("</article>")[0]
        name_m = _BANNER_NAME.search(block)
        if not name_m:
            continue
        name = html_mod.unescape(name_m.group(1)).strip()
        start_m = _TIMER.search(block)
        start_raw = start_m.group(2) if start_m else ""
        slug = ""
        link_m = _CARD_LINK.search(block)
        if link_m:
            m = re.search(r"/(?:characters|light-cones)/([a-z0-9-]+)", link_m.group(1))
            if m:
                slug = m.group(1)
        if not slug:
            art_m = _ART.search(block)
            if art_m:
                slug_m = _ASSET_SLUG.search(art_m.group(1))
                slug = slug_m.group(1) if slug_m else ""
        if not slug or not start_raw:
            continue  # teased banners without dates are skipped, not guessed
        start_iso = start_raw[:10]
        key = f"{slug}_{start_iso}"
        if key in seen:
            continue
        seen.add(key)
        section_m = _SECTION.search(tag)
        category_m = _CATEGORY.search(tag)
        type_m = _BANNER_TYPE.search(block)
        rarity_m = _RARITY.search(block)
        phase_m = _PHASE.search(block)
        art_m = _ART.search(block)
        featured = [
            {"name": html_mod.unescape(fname).strip(), "path": fpath}
            for fpath, fname in _FEATURED_LINK.findall(block)
        ]
        rows.append(
            {
                "key": key,
                "name": name,
                "rarity": _rarity_number(rarity_m.group(1)) if rarity_m else None,
                "meta": {
                    "slug": slug,
                    "section": section_m.group(1) if section_m else None,
                    "kind": category_m.group(1) if category_m else None,
                    "banner_type": type_m.group(1) if type_m else None,
                    "starts_at": start_raw or None,
                    "ends_at": (start_m.group(3) if start_m else "") or None,
                    "phase": phase_m.group(1).strip() if phase_m else None,
                    "art": art_m.group(1) if art_m else None,
                    "featured": featured,
                    "community_data": True,
                },
                "source": "prydwen",
            }
        )
    return rows
