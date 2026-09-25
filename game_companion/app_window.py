"""Native app window (M23): open the local UI in a chrome-less window.

Detection order (D6): chromium-style browsers' ``--app`` mode first (a real
window, zero new dependencies), then the default browser as a plain tab.
pywebview is deliberately not on the critical path — WebKit2GTK system deps
are exactly the install fragility this project avoids.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from game_companion.config import get_settings

# the checkout root — the spawned service runs from here so the repo .env and
# serve.log resolve regardless of where the app was launched from
_REPO_ROOT = Path(__file__).resolve().parents[2]

_APP_BROWSERS = (
    "chromium-browser",
    "chromium",
    "brave-browser",
    "google-chrome-stable",
    "google-chrome",
    "microsoft-edge",
    "microsoft-edge-stable",
)


def find_app_window_command(base_url: str) -> list[str] | None:
    for browser in _APP_BROWSERS:
        if shutil.which(browser):
            return [browser, f"--app={base_url}/ui"]
    return None


def wait_for_service(base_url: str, timeout_seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            import urllib.request

            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass  # not up yet — retry until the deadline
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.4)


def open_app(ensure_service: bool = True) -> str:
    """Open the UI in an app window (or a browser tab). Returns the mode used."""
    settings = get_settings()
    base_url = f"http://{settings.host}:{settings.port}"

    if ensure_service and not wait_for_service(base_url, timeout_seconds=1.5):
        # Spawned via this interpreter, not by name: the venv's bin dir is not
        # on PATH for desktop-launched apps, and a bare Popen(["game-companion",
        # …]) would raise FileNotFoundError and kill the whole icon flow.
        # CWD is the checkout so the repo .env is picked up.
        subprocess.Popen(
            [sys.executable, "-m", "game_companion.cli", "serve"],
            cwd=str(_REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    if not wait_for_service(base_url):
        raise RuntimeError(
            f"the companion service did not come up at {base_url} — run 'game-companion serve' and check its output"
        )

    command = find_app_window_command(base_url)
    if command:
        subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
        return f"app window via {command[0]}"
    webbrowser.open(f"{base_url}/ui")
    return "default browser tab"
