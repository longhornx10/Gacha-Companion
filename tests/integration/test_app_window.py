"""M23: native app window — browser detection and service orchestration."""

from __future__ import annotations

import game_companion.app_window as app_window


def test_find_app_window_command_prefers_chromium_family(monkeypatch):
    installed = []
    monkeypatch.setattr(app_window.shutil, "which", lambda name: name if name in installed else None)

    assert app_window.find_app_window_command("http://127.0.0.1:8765") is None

    installed.append("brave-browser")
    command = app_window.find_app_window_command("http://127.0.0.1:8765")
    assert command == ["brave-browser", "--app=http://127.0.0.1:8765/ui"]

    installed.append("chromium")  # chromium ranks first in the tuple
    command = app_window.find_app_window_command("http://127.0.0.1:8765")
    assert command[0] == "chromium"


def test_open_app_uses_app_window_when_available(monkeypatch, settings):
    launched = {}
    monkeypatch.setattr(app_window, "wait_for_service", lambda base, timeout_seconds=15.0: True)
    monkeypatch.setattr(
        app_window, "find_app_window_command", lambda base: ["chromium", f"--app={base}/ui"]
    )
    monkeypatch.setattr(
        app_window.subprocess, "Popen", lambda cmd, **kw: launched.setdefault("cmd", cmd)
    )

    mode = app_window.open_app(ensure_service=False)
    assert "chromium" in mode
    assert launched["cmd"] == ["chromium", "--app=http://127.0.0.1:8765/ui"]


def test_open_app_falls_back_to_browser_tab(monkeypatch, settings):
    opened = {}
    monkeypatch.setattr(app_window, "wait_for_service", lambda base, timeout_seconds=15.0: True)
    monkeypatch.setattr(app_window, "find_app_window_command", lambda base: None)
    monkeypatch.setattr(app_window.webbrowser, "open", lambda url: opened.setdefault("url", url))

    mode = app_window.open_app(ensure_service=False)
    assert "browser tab" in mode
    assert opened["url"] == "http://127.0.0.1:8765/ui"


def test_open_app_raises_when_service_never_comes_up(monkeypatch, settings):
    import pytest

    monkeypatch.setattr(app_window, "wait_for_service", lambda base, timeout_seconds=15.0: False)
    monkeypatch.setattr(app_window.subprocess, "Popen", lambda cmd, **kw: None)
    with pytest.raises(RuntimeError, match="did not come up"):
        app_window.open_app(ensure_service=True)


def test_cli_app_command_exists():
    # wiring: the subcommand exists
    import io
    from contextlib import redirect_stderr, redirect_stdout

    from game_companion import cli

    parser_err = io.StringIO()
    with redirect_stderr(parser_err), redirect_stdout(io.StringIO()):
        try:
            cli.main(["app", "--help"])
        except SystemExit as exc:
            assert exc.code == 0
