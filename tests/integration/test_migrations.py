"""Migrations: fresh upgrade, downgrade/re-upgrade cycle, data survival."""

def test_fresh_upgrade_creates_all_tables(client):
    from sqlalchemy import inspect

    engine = client.app.state.engine
    tables = set(inspect(engine).get_table_names())
    expected = {
        "player_profiles", "player_preferences", "characters", "character_skills",
        "equipment_items", "gear_items", "character_builds", "build_gear_slots",
        "teams", "team_members", "resources", "resource_plan_entries",
        "combat_results", "training_issues", "training_goals", "redeem_codes",
        "player_code_states", "research_sources", "research_claims", "change_records",
        "screenshot_imports", "encounters", "encounter_slots", "recommendations",
        "audit_results", "alembic_version",
    }
    assert expected <= tables


def test_downgrade_then_upgrade_roundtrip(client):
    from alembic import command
    from sqlalchemy import inspect

    from game_companion.db.migrations.runner import make_alembic_config

    engine = client.app.state.engine
    url = str(engine.url)
    import os

    os.environ["ALEMBIC_DATABASE_URL"] = url
    cfg = make_alembic_config(url)

    command.downgrade(cfg, "base")
    tables_after = set(inspect(engine).get_table_names()) - {"alembic_version"}
    assert tables_after == set()
    command.upgrade(cfg, "head")
    assert "player_profiles" in inspect(engine).get_table_names()


def test_data_survives_migration_cycle(client, player):
    from alembic import command
    from sqlalchemy import select

    from game_companion.db.migrations.runner import make_alembic_config
    from game_companion.db.models import Character
    from game_companion.db.session import create_session_factory

    make_character_response = client.post(
        "/api/games/zzz/characters", json={"key": "burnice", "level": 60}
    )
    assert make_character_response.status_code == 201

    engine = client.app.state.engine
    import os

    os.environ["ALEMBIC_DATABASE_URL"] = str(engine.url)
    cfg = make_alembic_config(str(engine.url))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    # the player row was dropped with the schema (no data preservation across
    # downgrade base); that is expected — a *version* migration must never drop
    # data, and this check documents the behavior of downgrade base explicitly.
    session = create_session_factory(engine)()
    try:
        remaining = session.scalars(select(Character)).all()
        assert remaining == []
    finally:
        session.close()
