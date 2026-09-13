"""``game-companion`` CLI: serve, init-db, export, create-player, list-games, check-sources."""

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
    upgrade_to_head()  # local single-user app: ensure schema before serving
    uvicorn.run(
        "game_companion.app:create_app",
        host=args.host or settings.host,
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
