"""Delight pass: The Hall, media urls, achievements, sounds plumbing."""

from __future__ import annotations

from game_companion.core.games.registry import get_adapter


def test_media_urls_follow_verified_cdn_patterns():
    zzz = get_adapter("zzz")
    assert zzz.media_url("character", "burnice") == (
        "https://cdn.prydwen.gg/images/zenless-zone-zero/characters/burnice.webp"
    )
    assert zzz.media_url("character", "jane_doe").endswith("/characters/jane-doe.webp")
    assert zzz.media_url("equipment", "angel_in_the_shell") == (
        "https://cdn.prydwen.gg/images/zenless-zone-zero/w-engines/angel-in-the-shell_image.webp"
    )
    assert zzz.media_url("gear_set", "woodpecker_electro") == (
        "https://cdn.prydwen.gg/images/zenless-zone-zero/drives/set_woodpecker-electro.webp"
    )
    assert zzz.media_url("element", "electric").endswith("icons/ele_electric.webp")
    assert zzz.media_url("element", "toaster") is None

    hsr = get_adapter("hsr")
    assert hsr.media_url("character", "1001").endswith("icon/avatar/1001.png")
    assert hsr.media_url("equipment", "20000").endswith("icon/light_cone/20000.png")
    assert hsr.media_url("character", "not-numeric") is None

    nte = get_adapter("nte")
    assert nte.media_url("character", "linko") == (
        "https://cdn.prydwen.gg/images/nte/characters/linko_card.webp"
    )
    assert nte.media_url("character", "akane_rin").endswith("/akane-rin_card.webp")

    # the example adapter defines no pattern: honest None
    assert get_adapter("example").media_url("character", "aria") is None


def test_themes_carry_mood_and_backdrop():
    for gid in ("zzz", "hsr", "nte"):
        theme = get_adapter(gid).theme()
        assert theme.get("mood"), gid
        assert theme.get("bg") and theme.get("radius"), gid


def test_themes_carry_vendored_logos():
    from pathlib import Path

    static = Path("game_companion/ui/static/images/logos")
    for gid in ("zzz", "hsr", "nte"):
        theme = get_adapter(gid).theme()
        assert theme.get("logo", "").startswith("/ui/static/images/logos/"), gid
        assert (static / Path(theme["logo"]).name).exists(), gid
    # NTE's emblem is dark grey — it ships a filter so it shows on dark bg
    assert "invert" in get_adapter("nte").theme()["logo_filter"]


def _seed_banner(client, meta: dict, key: str = "claret_live") -> None:
    from game_companion.db.models import CatalogEntry
    from game_companion.db.session import create_session_factory
    from game_companion.utils import utcnow

    session = create_session_factory(client.app.state.engine)()
    session.add(
        CatalogEntry(
            game_id="zzz", entity_type="banner", key=key,
            display_name=meta.pop("name", "Claret"),
            rarity=5, source="prydwen", fetched_at=utcnow(), meta=meta,
        )
    )
    session.commit()
    session.close()


def test_home_rail_is_one_panel_with_clickable_sections(client, player):
    client.post(f"/api/games/zzz/characters?player_id={player}", json={"key": "burnice"})
    page = client.get("/ui")
    assert 'class="rail' in page.text  # unified panel, not stacked cards
    # every rail section deep-links to its screen
    assert 'href="/ui/trackers#codes"' in page.text
    assert 'href="/ui/trackers#resources"' in page.text
    assert 'href="/ui/trackers#history"' in page.text
    assert 'href="/ui/teams"' in page.text
    assert 'href="/ui/roster"' in page.text


def test_home_shows_achievements_progress(client, player):
    page = client.get("/ui")
    assert "Achievements" in page.text
    assert "0 of 10 earned" in page.text  # honest before anything is done
    assert "medal" in page.text
    client.post(f"/api/games/zzz/characters?player_id={player}", json={"key": "burnice"})
    page2 = client.get("/ui")
    assert "1 of 10 earned" in page2.text


def test_home_banner_hero_shows_live_banner(client, player):
    from datetime import timedelta

    from game_companion.utils import utcnow

    now = utcnow()
    _seed_banner(
        client,
        {
            "name": "Claret",
            "section": "current",
            "kind": "character",
            "banner_type": "new",
            "starts_at": (now - timedelta(days=3)).isoformat(),
            "ends_at": (now + timedelta(days=10)).isoformat(),
            "phase": "Patch 3.2 Phase 1",
            "art": "https://cdn.prydwen.gg/images/zenless-zone-zero/banners/x.webp",
            "featured": [{"name": "Claret", "path": "/zenless/characters/claret"}],
        },
    )
    page = client.get("/ui")
    assert "Now on banner" in page.text
    assert "Claret" in page.text
    assert "Ends " in page.text
    assert "community data" in page.text  # honesty caption
    assert "cdn.prydwen.gg" in page.text  # banner art wired


def test_home_banner_hero_hides_undated_banners(client, player):
    _seed_banner(
        client,
        {
            "name": "Teased One",
            "section": "current",
            "kind": "character",
            "starts_at": None,
            "ends_at": None,
        },
        key="teased",
    )
    page = client.get("/ui")
    assert "Now on banner" not in page.text
    assert "Teased One" not in page.text


def test_banner_art_opens_full_size_preview(client, player):
    _seed_banner(
        client,
        {
            "name": "Claret",
            "section": "current",
            "kind": "character",
            "banner_type": "new",
            "starts_at": "2026-09-09T03:00:00+00:00",
            "ends_at": "2026-09-30T16:59:00+00:00",
            "art": "https://cdn.prydwen.gg/images/zenless-zone-zero/banners/x.webp",
            "featured": [],
        },
    )
    page = client.get("/ui")
    assert 'data-lightbox="https://cdn.prydwen.gg/images/zenless-zone-zero/banners/x.webp"' in page.text
    assert "delight.js?v=4" in page.text  # lightbox plumbing shipped with delight
    assert "style.css?v=14" in page.text


def test_every_page_carries_the_game_logo_head(client, ui_player):
    for path in (
        "/ui/roster", "/ui/teams", "/ui/gear", "/ui/farm", "/ui/trackers",
        "/ui/imports", "/ui/games", "/ui/settings", "/ui/hall",
    ):
        page = client.get(path)
        assert page.status_code == 200, path
        assert "page-logo" in page.text, f"{path} has no logo in its page head"

def test_hall_page_renders_collection(client, player):
    from tests.conftest import make_zzz_roster

    make_zzz_roster(client, player, ["burnice", "ell en".replace(" ", "")])
    page = client.get("/ui/hall")
    assert page.status_code == 200
    assert "The Hall" in page.text
    assert "Burnice" in page.text
    assert "cdn.prydwen.gg" in page.text  # real portraits wired
    assert "Achievements" in page.text
    assert "First Recruit" in page.text


def test_hall_unlocks_achievements_with_badge(client, player):
    # empty roster: nothing unlocked, shelf shows locked states
    page = client.get("/ui/hall")
    assert "ach locked" in page.text
    # add an agent: First Recruit unlocks and a toast appears
    client.post(f"/api/games/zzz/characters?player_id={player}", json={"key": "burnice"})
    page2 = client.get("/ui/hall")
    assert "Achievement unlocked" in page2.text
    assert 'data-sound="sparkle"' in page2.text
    # second visit: toast gone, medal stays
    page3 = client.get("/ui/hall")
    assert "Achievement unlocked" not in page3.text
    assert "First Recruit" in page3.text


def test_build_at_a_glance_shows_equipped_gear(client, player):
    from tests.conftest import make_character

    make_character(client, "zzz", "burnice")
    disc = client.post(f"/api/games/zzz/gear?player_id={player}", json={
        "set_key": "woodpecker_electro", "slot": "4", "rarity": "S", "level": 15,
        "main_stat_key": "crit_rate", "character": "burnice",
    })
    assert disc.status_code == 201, disc.text
    equip = client.post(f"/api/games/zzz/equipment?player_id={player}", json={
        "key": "rainforest_gourmet", "display_name": "Rainforest Gourmet",
        "rarity": "S", "character": "burnice",
    })
    assert equip.status_code == 201, equip.text
    page = client.get("/ui/hall")
    assert "w-engines" in page.text  # engine icon from the CDN
    assert "set_woodpecker-electro" in page.text  # disc set icon


def test_hall_nav_link_present(client, ui_player):
    assert "/ui/hall" in client.get("/ui").text


def test_achievements_table_migration_roundtrip():
    import os
    import tempfile

    from alembic import command

    from game_companion.db.migrations.runner import (
        make_alembic_config,
        upgrade_to_head,
    )
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/t.db"
        upgrade_to_head(url)
        cfg = make_alembic_config(url)
        command.downgrade(cfg, "c8f4a2b6d9e1")
        command.upgrade(cfg, "head")
        assert os.path.exists(f"{tmp}/t.db")


def test_trackers_codes_grouping_and_redeem_celebration(client, player):
    client.post(f"/api/games/zzz/codes?player_id={player}", json={"code": "ZZZLIVE100"})
    client.post(
        f"/api/games/zzz/codes?player_id={player}",
        json={"code": "ZZZDEAD1", "status": "expired"},
    )
    page = client.get("/ui/trackers")
    text = page.text
    # active code gets a card with a copy button
    assert 'data-copy="ZZZLIVE100"' in text
    assert "Redeemed ✓" in text
    # expired hidden behind a toggle
    assert "Expired (1)" in text

    # marking used celebrates with the game's currency in the notice
    code_id = client.get(f"/api/games/zzz/codes?player_id={player}").json()["codes"]
    live_id = [c for c in code_id if c["code"] == "ZZZLIVE100"][0]["id"]
    marked = client.post(f"/ui/codes/{live_id}/toggle-used", follow_redirects=True)
    assert "redeemed" in marked.text.lower()
    assert "Polychrome" in marked.text  # ZZZ's currency names the reward
    # used codes move behind the Redeemed toggle
    after = client.get("/ui/trackers").text
    assert "Redeemed (1)" in after
    assert 'data-copy="ZZZLIVE100"' not in after
