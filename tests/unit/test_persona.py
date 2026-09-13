"""Persona system: tone-only influence, built-ins, persistence, overrides."""

from pathlib import Path

import pytest

from game_companion.config import Settings
from game_companion.core.persona.schema import PersonaConfig
from game_companion.core.persona.store import PersonaStore
from game_companion.errors import NotFoundError


def _store(tmp_path: Path) -> PersonaStore:
    return PersonaStore(Settings(data_dir=tmp_path / "data"))


def test_built_ins_available(tmp_path):
    personas = {p.id for p in _store(tmp_path).list_personas()}
    assert {"companion", "hustle_manager", "calm_tactician"} <= personas


def test_persona_fragment_is_tone_only(tmp_path):
    persona = _store(tmp_path).get("calm_tactician")
    fragment = persona.system_prompt_fragment("Agents are called Agents.")
    assert "TONE ONLY" in fragment
    assert "never alter facts" in fragment.lower()
    assert "Agents are called Agents." in fragment


def test_get_unknown_persona(tmp_path):
    with pytest.raises(NotFoundError):
        _store(tmp_path).get("does_not_exist")


def test_save_and_reload_user_persona(tmp_path):
    store = _store(tmp_path)
    persona = PersonaConfig(
        id="my_persona", name="My Persona", tone="playful", verbosity="low",
        style_traits=["terse"], bound_game="zzz",
    )
    store.save(persona)
    reloaded = store.get("my_persona")
    assert reloaded.tone == "playful"
    assert reloaded.bound_game == "zzz"


def test_broken_user_file_does_not_break_listing(tmp_path):
    store = _store(tmp_path)
    store._dir.mkdir(parents=True, exist_ok=True)
    (store._dir / "broken.json").write_text("{not json", encoding="utf-8")
    ids = [p.id for p in store.list_personas()]
    assert "companion" in ids
