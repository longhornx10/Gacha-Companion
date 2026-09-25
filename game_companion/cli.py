"""``game-companion`` CLI: serve, init-db, export, create-player, import-roster, list-games, check-sources."""

from __future__ import annotations

import argparse
import json
import sys


def _cmd_init_db(args) -> int:
    from game_companion.config import get_settings
    from game_companion.db.migrations.runner import upgrade_to_head

    settings = get_settings()
    upgrade_to_head()
    print(f"database ready: {settings.resolved_database_url}")
    return 0


def _cmd_serve(args) -> int:
    import uvicorn

    from game_companion.config import get_settings
    from game_companion.db.migrations.runner import upgrade_to_head

    settings = get_settings()
    host = args.host or settings.host
    if not host.startswith(("127.", "localhost", "[::1]", "::1")) and not settings.expose:
        print(
            f"refusing to bind {host}: the local UI/API is unauthenticated by design.\n"
            "To expose it anyway (e.g. LAN), set GAME_COMPANION_EXPOSE=1 and add your\n"
            "own reverse proxy with auth."
        )
        return 2
    upgrade_to_head()  # local single-user app: ensure schema before serving
    uvicorn.run(
        "game_companion.app:create_app",
        host=host,
        port=args.port or settings.port,
        factory=True,
        log_level=settings.log_level.lower(),
    )
    return 0


def _cmd_export(args) -> int:
    from game_companion.config import get_settings
    from game_companion.core.exports.service import ExportService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.repositories import PlayerRepository
    from game_companion.db.session import create_db_engine, create_session_factory

    settings = get_settings()
    engine = create_db_engine(settings.resolved_database_url)
    session = create_session_factory(engine)()
    try:
        player_id = args.player
        if not player_id:
            profile = PlayerRepository(session).require_sole()
            player_id = profile.id
        else:
            PlayerRepository(session).get_or_raise(player_id, "player")
        service = ExportService(session, get_adapter(args.game), settings)
        paths = service.write_exports(args.game, player_id)
        for path in paths:
            print(path)
    finally:
        session.close()
        engine.dispose()
    return 0


def _cmd_create_player(args) -> int:
    from game_companion.config import get_settings
    from game_companion.db.migrations.runner import upgrade_to_head
    from game_companion.db.models import PlayerProfile
    from game_companion.db.repositories import PlayerRepository
    from game_companion.db.session import create_db_engine, create_session_factory

    settings = get_settings()
    upgrade_to_head()
    engine = create_db_engine(settings.resolved_database_url)
    session = create_session_factory(engine)()
    try:
        profile = PlayerRepository(session).add(
            PlayerProfile(display_name=args.name, notes=args.notes)
        )
        session.commit()
        print(json.dumps({"id": profile.id, "display_name": profile.display_name}))
    finally:
        session.close()
        engine.dispose()
    return 0


def _cmd_import_roster(args) -> int:
    from pathlib import Path

    from game_companion.config import get_settings
    from game_companion.core.games.registry import get_adapter
    from game_companion.core.roster import importer
    from game_companion.db.migrations.runner import upgrade_to_head
    from game_companion.db.repositories import PlayerRepository
    from game_companion.db.session import create_db_engine, create_session_factory

    settings = get_settings()
    upgrade_to_head()
    engine = create_db_engine(settings.resolved_database_url)
    session = create_session_factory(engine)()
    try:
        player_id = args.player
        if not player_id:
            player_id = PlayerRepository(session).require_sole().id
        else:
            PlayerRepository(session).get_or_raise(player_id, "player")
        text = Path(args.file).read_text(encoding="utf-8")
        parsed = importer.parse_roster_text(text, get_adapter(args.game))
        row = importer.stage_roster_import(session, get_adapter(args.game), args.game, player_id, parsed)
        session.commit()
        summary = importer.summarize(row)
        print(json.dumps(summary, indent=2, default=str))
        if args.yes:
            from datetime import UTC, datetime

            result = importer.apply_roster_entries(
                session, get_adapter(args.game), args.game, player_id,
                row.candidate.get("entries", []),
            )
            row.status = "applied"
            row.applied_at = datetime.now(UTC)
            session.commit()
            print(json.dumps({"applied": result}, indent=2))
        else:
            print(f"staged as import {row.id} — confirm via the app or "
                  f"re-run with --yes")
    finally:
        session.close()
        engine.dispose()
    return 0


def _cmd_app(_args) -> int:
    from game_companion.app_window import open_app

    try:
        mode = open_app()
    except RuntimeError as exc:
        print(str(exc))
        return 1
    print(f"Gacha Companion opened in a {mode}.")
    return 0


def _cmd_new_game(args) -> int:
    from pathlib import Path

    from game_companion.core.games.scaffold import register_installed, scaffold_new_game
    from game_companion.errors import DomainError

    games_root = Path(__file__).resolve().parent / "games"
    try:
        target = scaffold_new_game(args.game_id, games_root)
        register_installed(args.game_id, games_root)
    except DomainError as exc:
        print(f"could not scaffold: {exc.detail}")
        return 1
    print(f"scaffolded game '{args.game_id}' at {target}")
    print("next steps:")
    print(f"  1. edit games/{args.game_id}/data/terminology.json  (the chat model learns the game here)")
    print(f"  2. edit games/{args.game_id}/data/gear_families.json (slots, set rule, rarity)")
    print("  3. fill resource/encounter definitions in adapter.py, then `game-companion list-games`")
    print("  4. add the game id to tests/game_adapter_contract/test_contract.py ADAPTER_IDS")
    return 0


def _cmd_bootstrap_game(args) -> int:

    from game_companion.config import get_settings
    from game_companion.core.bootstrap.pipeline import BootstrapService
    from game_companion.core.games.registry import get_adapter
    from game_companion.db.session import create_db_engine, create_session_factory

    settings = get_settings()
    engine = create_db_engine(settings.resolved_database_url)
    session = create_session_factory(engine)()
    try:
        service = BootstrapService(session, get_adapter(args.game), settings)
        summary = service.run(args.source, apply=args.apply)
        session.commit()
        import json

        print(json.dumps(summary, indent=2, default=str))
    finally:
        session.close()
        engine.dispose()
    return 0


def _cmd_list_games(_args) -> int:
    from game_companion.core.games.registry import list_adapters

    for adapter in list_adapters():
        term = adapter.terminology()
        print(
            f"{adapter.game_id:10s} {adapter.display_name} "
            f"({term.character}, {term.equipment}, {term.gear}, "
            f"team {adapter.team_rules().min_size}-{adapter.team_rules().max_size})"
        )
    return 0


def _cmd_check_sources(args) -> int:
    from game_companion.config import get_settings
    from game_companion.core.games.registry import get_adapter
    from game_companion.core.research.service import ResearchService
    from game_companion.db.session import create_db_engine, create_session_factory

    settings = get_settings()
    engine = create_db_engine(settings.resolved_database_url)
    session = create_session_factory(engine)()
    try:
        service = ResearchService(session, get_adapter(args.game))
        print(json.dumps(service.check_sources(), indent=2, default=str))
        session.commit()
    finally:
        session.close()
        engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="game-companion", description="Gacha Companion")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="create/upgrade the SQLite schema")
    p_init.set_defaults(func=_cmd_init_db)

    p_serve = sub.add_parser("serve", help="start the local API (localhost only by default)")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)
    p_serve.set_defaults(func=_cmd_serve)

    p_export = sub.add_parser("export", help="write JSON + Markdown exports for a player")
    p_export.add_argument("--game", required=True, help="game id (see list-games)")
    p_export.add_argument("--player", default=None, help="player id (defaults to the sole profile)")
    p_export.set_defaults(func=_cmd_export)

    p_player = sub.add_parser("create-player", help="create a player profile")
    p_player.add_argument("name")
    p_player.add_argument("--notes", default=None)
    p_player.set_defaults(func=_cmd_create_player)

    p_roster = sub.add_parser("import-roster", help="stage a plain-text roster import for review")
    p_roster.add_argument("--game", required=True, help="game id (see list-games)")
    p_roster.add_argument("--file", required=True, help="path to the roster .txt")
    p_roster.add_argument("--player", default=None, help="player id (defaults to the sole profile)")
    p_roster.add_argument("--yes", action="store_true", help="apply immediately without review")
    p_roster.set_defaults(func=_cmd_import_roster)

    p_new = sub.add_parser("new-game", help="scaffold a new game adapter package (contract-ready)")
    p_new.add_argument("game_id")
    p_new.set_defaults(func=_cmd_new_game)

    p_boot = sub.add_parser("bootstrap-game", help="fetch a registered data source and stage changes for review")
    p_boot.add_argument("game")
    p_boot.add_argument("--source", default="auto", help="source key (default: first registered)")
    p_boot.add_argument("--apply", action="store_true",
                        help="also write transformed rows with provenance into <data_dir>/bootstrap/")
    p_boot.set_defaults(func=_cmd_bootstrap_game)

    sub.add_parser(
        "app", help="open the companion UI in an app window (starts the service if needed)"
    ).set_defaults(func=_cmd_app)

    sub.add_parser("list-games", help="list registered game adapters").set_defaults(func=_cmd_list_games)

    p_check = sub.add_parser("check-sources", help="fetch trusted sources and record changes")
    p_check.add_argument("--game", required=True)
    p_check.set_defaults(func=_cmd_check_sources)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":
    sys.exit(main())
