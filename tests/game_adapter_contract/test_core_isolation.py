"""Core isolation: game-specific code must never leak into core modules."""

from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[2] / "game_companion" / "core"
FORBIDDEN = (
    "from game_companion.games",
    "import game_companion.games",
    "from game_companion.integrations",
)


def _py_files(root: Path):
    yield from sorted(root.rglob("*.py"))


def test_core_never_imports_game_packages():
    offenders = []
    for path in _py_files(CORE_ROOT):
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith(("#", '"', "'")):
                continue
            for forbidden in FORBIDDEN:
                if forbidden in stripped and "registry" not in path.name:
                    offenders.append(f"{path.name}: {stripped}")
    assert not offenders, f"core modules import game/integration packages: {offenders}"


def test_registry_references_adapters_only_as_strings():
    source = (CORE_ROOT / "games" / "registry.py").read_text(encoding="utf-8")
    assert '"zzz": "game_companion.games.zzz.adapter:ZZZAdapter"' in source
    assert "importlib.import_module" in source
    assert "from game_companion.games" not in source


def test_zzz_specific_words_absent_from_core_source():
    banned_words = ("drive disc", "w-engine", "wengine", "mindscape", "deadly assault", "burnice")
    offenders = []
    for path in _py_files(CORE_ROOT):
        if "registry" in path.name:
            continue
        text = path.read_text(encoding="utf-8").lower()
        for word in banned_words:
            if word in text:
                offenders.append(f"{path.name}: contains '{word}'")
    assert not offenders, f"ZZZ vocabulary leaked into core: {offenders}"


def test_zzz_vocabulary_lives_in_the_adapter():
    adapter_dir = Path(__file__).resolve().parents[2] / "game_companion" / "games" / "zzz"
    text = "\n".join(p.read_text(encoding="utf-8").lower() for p in adapter_dir.rglob("*") if p.suffix in (".py", ".toml", ".md", ".json"))
    for word in ("drive disc", "w-engine", "mindscape", "core skill", "deadly assault"):
        assert word in text, f"expected ZZZ adapter to define '{word}'"
