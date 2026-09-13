"""ZZZ research source registry (starter)."""

from __future__ import annotations

from game_companion.core.games.base import SourceDefinition

SOURCES = [
    SourceDefinition(
        key="zzz_official_site",
        name="Zenless Zone Zero Official Site",
        url="https://zenless.hoyoverse.com/",
        category="official",
        trust=5,
    ),
    SourceDefinition(
        key="zzz_official_news",
        name="ZZZ Official News / Patch Notes",
        url="https://zenless.hoyoverse.com/news",
        category="announcements",
        trust=5,
        notes="patch notes and version announcements",
    ),
    SourceDefinition(
        key="hoyolab_zzz",
        name="HoYoLAB ZZZ community hub (official posts)",
        url="https://www.hoyolab.com/",
        category="announcements",
        trust=4,
    ),
    SourceDefinition(
        key="hakush_zzz",
        name="Hakush.in ZZZ database",
        url="https://hakush.in/zzz/",
        category="database",
        trust=4,
    ),
    SourceDefinition(
        key="prydwen_zzz",
        name="Prydwen ZZZ guides",
        url="https://www.prydwen.gg/zenless-zone-zero/",
        category="build_guide",
        trust=3,
    ),
    SourceDefinition(
        key="game8_zzz",
        name="Game8 ZZZ guides",
        url="https://game8.co/games/Zenless-Zone-Zero",
        category="build_guide",
        trust=3,
    ),
    SourceDefinition(
        key="zzz_fandom",
        name="ZZZ Fandom wiki",
        url="https://zenless-zone-zero.fandom.com/",
        category="wiki",
        trust=3,
    ),
]

CODE_DISCOVERY_SOURCE_KEYS = ["zzz_official_news", "hoyolab_zzz"]

CODE_CONFIG_NOTES = (
    "Redeem codes are usually announced on official channels and often expire within "
    "weeks. Codes marked expired can be recycled by events — keep showing them with a "
    "recycled flag instead of silently hiding them."
)
