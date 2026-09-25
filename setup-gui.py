#!/usr/bin/env python3
"""Gacha Companion — graphical setup wizard (browser-based, stdlib only).

Run from the repo root:

    python3 setup-gui.py            # opens your browser automatically
    python3 setup-gui.py --no-browser --port 8790

Serves a one-shot wizard on 127.0.0.1 only, guarded by a random token in the
URL path. The front page is a single guided flow (one button runs everything);
the old step-by-step controls live under "Manual controls". Auto-detects
everything it can: existing .env values, player profiles, a running service,
the model list from the LLM endpoint, and a local Open WebUI instance.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent
ENV_FILE = REPO / ".env"
ENV_EXAMPLE = REPO / ".env.example"
TOOLFILE = REPO / "game_companion" / "integrations" / "openwebui" / "gacha_companion_tools.py"
OWUI_PORTS = (3000, 8080, 8081, 8090)

# Players are listed through the project venv (needs the app's dependencies).
PLAYERS_SNIPPET = (
    "from game_companion.config import get_settings\n"
    "from game_companion.db.session import create_db_engine, create_session_factory\n"
    "from game_companion.db.repositories import PlayerRepository\n"
    "engine = create_db_engine(get_settings().resolved_database_url)\n"
    "session = create_session_factory(engine)()\n"
    "try:\n"
    "    for p in PlayerRepository(session).list_all():\n"
    "        print(p.id + '\\t' + p.display_name)\n"
    "finally:\n"
    "    session.close()\n"
    "    engine.dispose()\n"
)


# --------------------------------------------------------------- helpers

def run(cmd: list[str] | str, timeout: int = 600, shell: bool = False) -> tuple[bool, str]:
    """Run a command, return (ok, combined output)."""
    try:
        p = subprocess.run(
            cmd, shell=shell, cwd=REPO, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        return p.returncode == 0, (p.stdout or "").replace("\r", "\n")
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s: {cmd}"
    except FileNotFoundError:
        return False, f"command not found: {cmd[0] if not shell else cmd}"


def env_key(key: str) -> str:
    if not ENV_FILE.exists():
        return ""
    vals = re.findall(rf"(?m)^{key}=(.*)$", ENV_FILE.read_text())
    return vals[-1].strip() if vals else ""   # last line wins, like dotenv


def service_port() -> int:
    p = os.environ.get("GAME_COMPANION_PORT") or env_key("GAME_COMPANION_PORT")
    try:
        return int(p) if p else 8765
    except ValueError:
        return 8765


def http_get(url: str, key: str = "", timeout: float = 12.0) -> tuple[int, str]:
    req = urllib.request.Request(url)
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(2_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def write_env(base: str, model: str, key: str | None) -> str:
    """Set the three LLM keys in .env (seeded from .env.example on first run).

    Preserves any other lines the user may have customized. Returns a note
    about what happened to the previous file, if any.
    """
    note = ""
    if ENV_FILE.exists():
        backup = ENV_FILE.with_name(
            f".env.backup.{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(ENV_FILE, backup)
        note = f"previous .env backed up as {backup.name}"
    elif ENV_EXAMPLE.exists():
        shutil.copy2(ENV_EXAMPLE, ENV_FILE)
    text = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    values = {"GAME_COMPANION_LLM_BASE_URL": base,
              "GAME_COMPANION_LLM_MODEL": model}
    if key is not None:  # None = keep whatever is already there
        values["GAME_COMPANION_LLM_API_KEY"] = key
    for k, v in values.items():
        line = f"{k}={v}"
        if re.search(rf"(?m)^{k}=", text):
            text = re.sub(rf"(?m)^{k}=.*$", lambda _m, repl=line: repl, text)
        else:
            text = (text.rstrip("\n") + "\n" if text else "") + line + "\n"
    ENV_FILE.write_text(text)
    os.chmod(ENV_FILE, 0o600)
    return note


def uv_path() -> str:
    return shutil.which("uv") or str(Path.home() / ".local/bin/uv")


def data_dir() -> Path:
    d = os.environ.get("GAME_COMPANION_DATA_DIR") or env_key("GAME_COMPANION_DATA_DIR")
    return Path(d).expanduser() if d else Path.home() / ".local" / "share" / "gacha-companion"


def detect_state() -> dict:
    base = env_key("GAME_COMPANION_LLM_BASE_URL")
    model = env_key("GAME_COMPANION_LLM_MODEL")
    key = env_key("GAME_COMPANION_LLM_API_KEY")
    port = service_port()
    svc_code, svc_body = http_get(f"http://127.0.0.1:{port}/health", timeout=3)

    players = []
    venv_python = REPO / ".venv/bin/python"
    if venv_python.exists():
        ok, out = run([str(venv_python), "-c", PLAYERS_SNIPPET], timeout=60)
        if ok:
            for line in out.splitlines():
                pid, _, pname = line.partition("\t")
                if pid:
                    players.append({"id": pid, "name": pname})

    owui = None
    for p in OWUI_PORTS:
        code, body = http_get(f"http://127.0.0.1:{p}/api/config", timeout=1.5)
        if code == 200 and "open webui" in body.lower():
            owui = p
            break

    uv = uv_path()
    uv_ok = bool(uv) and Path(uv).exists()
    uv_ver = ""
    if uv_ok:
        _, v = run([uv, "--version"], timeout=20)
        uv_ver = v.strip().removeprefix("uv ").split(" ")[0]  # "uv 0.11.32 (…)" → "0.11.32"

    try:
        default_name = getpass.getuser()
    except Exception:
        default_name = "Player"

    _, commit = run(["git", "rev-parse", "--short", "HEAD"], timeout=10)
    _, behind = run(["git", "rev-list", "--count", "HEAD..@{u}"], timeout=10)

    return {
        "repo_root": str(REPO),
        "is_repo": (REPO / ".git").exists(),
        "git": bool(shutil.which("git")),
        "curl": bool(shutil.which("curl")),
        "python": sys.version.split()[0],
        "uv": {"path": uv, "ok": uv_ok, "version": uv_ver},
        "venv": venv_python.exists(),
        "env": {"base": base, "model": model, "key_set": bool(key)},
        "players": players,
        "service": {"port": port, "running": svc_code == 200, "health": svc_body},
        "openwebui_port": owui,
        "autoupdate": autoupdate_status(),
        "commit": commit.strip() if commit else "",
        "behind": behind.strip() if behind.strip().isdigit() else None,
        "data_dir": str(data_dir()),
        "toolfile": str(TOOLFILE),
        "toolfile_exists": TOOLFILE.exists(),
        "default_name": default_name,
    }


def autoupdate_status() -> str:
    """'on' when the daily auto-update timer is enabled, else 'off'."""
    ok, out = run(["systemctl", "--user", "is-enabled",
                   "gacha-companion-update.timer"], timeout=10)
    return "on" if ok and out.strip() == "enabled" else "off"


def autoupdate_toggle() -> dict:
    """Enable/disable the daily auto-update systemd user timer."""
    if autoupdate_status() == "on":
        ok, out = run(["systemctl", "--user", "disable", "--now",
                       "gacha-companion-update.timer"], timeout=30)
        return {"ok": ok, "on": False,
                "log": out.strip() or "automatic updates turned off"}

    units = Path.home() / ".config" / "systemd" / "user"
    units.mkdir(parents=True, exist_ok=True)
    bash = shutil.which("bash") or "/bin/bash"
    (units / "gacha-companion-update.service").write_text(
        "[Unit]\n"
        "Description=Gacha Companion auto-update\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={bash} {REPO / 'auto-update.sh'}\n")
    (units / "gacha-companion-update.timer").write_text(
        "[Unit]\n"
        "Description=Run Gacha Companion auto-update daily\n"
        "\n"
        "[Timer]\n"
        "OnCalendar=*-*-* 03:00\n"
        "Persistent=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n")
    ok1, out1 = run(["systemctl", "--user", "daemon-reload"], timeout=30)
    ok2, out2 = run(["systemctl", "--user", "enable", "--now",
                     "gacha-companion-update.timer"], timeout=30)
    _, nxt = run(["systemctl", "--user", "show", "-p", "NextElapseUSecRealtime",
                  "--value", "gacha-companion-update.timer"], timeout=15)
    on = autoupdate_status() == "on"
    log = (out1 + " " + out2).strip()
    if on:
        log = "automatic updates turned on (daily)"
    elif not log:
        log = ("could not reach systemctl — is this a normal desktop session? "
               "you can still update with: bash auto-update.sh")
    return {"ok": ok1 and ok2 and on, "on": on, "log": log, "next": nxt.strip()}


def redact(text: str) -> str:
    """Scrub secrets from arbitrary text before it goes into a report."""
    text = re.sub(
        r"(?im)^(\s*[A-Z0-9_]*(KEY|SECRET|TOKEN|PASSWORD)[A-Z0-9_]*)\s*=\s*.+$",
        r"\1=<hidden>", text)
    text = re.sub(r"sk-[A-Za-z0-9_\-]{6,}", "sk-<hidden>", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9_\-.]+", "Bearer <hidden>", text)
    text = re.sub(r"(?i)(https?://)([^/@\s:]+):([^@\s]+)@", r"\1<credentials-hidden>@", text)
    return text


def build_report(client: dict) -> str:
    """Assemble a full diagnostic bundle (secrets redacted) for support."""
    import platform as _p
    from collections import deque

    bar = "\u2500" * 52
    L: list[str] = [bar, "GACHA COMPANION \u2014 PROBLEM REPORT",
                    time.strftime("%Y-%m-%d %H:%M %Z"), bar, ""]

    L += ["WHAT HAPPENED",
          f"step    : {client.get('step', '(unknown)')}",
          f"message : {client.get('message', '')}", ""]
    raw = redact(str(client.get("raw", "")))
    if raw:
        L += ["raw output:", raw[:4000], ""]
    if client.get("probe"):
        L += ["llm probe : " + json.dumps(client["probe"]), ""]

    os_name = ""
    try:
        osr = Path("/etc/os-release").read_text()
        os_name = re.search(r'PRETTY_NAME="([^"]+)"', osr).group(1)
    except Exception:
        pass
    du = shutil.disk_usage(str(REPO))
    vpy_ok, vpy_out = run([".venv/bin/python", "--version"], timeout=10)
    venv_ver = f" / {vpy_out.strip().split()[1]} (.venv)" if vpy_ok else ""
    uv_p = uv_path()
    L += ["COMPUTER",
          f"os          : {os_name or _p.system()} (kernel {_p.release()})",
          f"python      : {sys.version.split()[0]} (system){venv_ver}",
          f"uv          : {uv_p if Path(uv_p).exists() else 'MISSING'}",
          f"disk free   : {du.free // (2**30)} GB of {du.total // (2**30)} GB", ""]

    def g(*args: str) -> str:
        ok, out = run(list(args), timeout=15)
        return out.strip() if ok else ""

    status = g("git", "status", "--short")
    L += ["PROJECT",
          f"path        : {REPO}",
          "git         : "
          + (f"{g('git', 'rev-parse', '--abbrev-ref', 'HEAD')} @ "
             f"{g('git', 'rev-parse', '--short', 'HEAD')}" if (REPO / ".git").exists()
             else "not a git checkout"),
          f"remote      : {redact(g('git', 'remote', 'get-url', 'origin'))}",
          f"git status  : {'clean' if not status else redact(status)[:500]}",
          f".venv       : {'present' if (REPO / '.venv/bin/python').exists() else 'MISSING'}", ""]

    env_txt = redact(ENV_FILE.read_text()) if ENV_FILE.exists() else "(no .env)"
    L += ["SETTINGS (.env \u2014 secrets hidden)", env_txt.strip() or "(empty)", ""]

    port = service_port()
    code, body = http_get(f"http://127.0.0.1:{port}/health", timeout=3)
    L += ["SERVICE",
          f"port {port}  : "
          + (f"running \u2014 {body[:200]}" if code == 200 else f"not answering (probe code {code})")]
    logf = REPO / "serve.log"
    if logf.exists():
        with logf.open(errors="replace") as f:
            tail = redact("\n".join(deque(f, maxlen=80)))
        L += ["serve.log (last 80 lines):", tail]
    upd = REPO / "update.log"
    if upd.exists():
        with upd.open(errors="replace") as f:
            utail = redact("\n".join(deque(f, maxlen=20)))
        L += ["update.log (last 20 lines):", utail]
    ok, j = run(["journalctl", "--user", "-u", "gacha-companion-update.service",
                 "-n", "20", "--no-pager"], timeout=15)
    if ok and j.strip() and "No journal files" not in j:
        L += ["auto-update timer journal (last 20 lines):", redact(j.strip())[:2000]]
    L.append("")

    players = ""
    if (REPO / ".venv/bin/python").exists():
        ok, out = run([str(REPO / ".venv/bin/python"), "-c", PLAYERS_SNIPPET], timeout=60)
        if ok:
            players = "; ".join(ln.split("\t")[1] for ln in out.splitlines() if "\t" in ln)
    L += ["PROFILES", players or "(none / not readable)", ""]

    L += ["BROWSER", f"user agent  : {client.get('ua', '')}", "client errors:"]
    errs = [f"- {redact(str(e))}" for e in client.get("errors", [])]
    L += (errs or ["(none)"])
    L += [bar, "END OF REPORT \u2014 paste everything above to whoever is helping you", bar]
    return "\n".join(L)


def desktop_shortcut() -> dict:
    """Write double-clickable launchers into the app menu: the setup wizard
    and the day-to-day control panel."""
    apps = Path.home() / ".local" / "share" / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    venv_cli = REPO / ".venv" / "bin" / "game-companion"
    # The launcher logic lives in a real script (not an inline Exec) — .desktop
    # Exec quoting rules are strict and a rejected entry silently vanishes from
    # GNOME's menu. The script prefers the installed CLI app and falls back to
    # the control panel, so launchers created before setup finishes heal
    # themselves once the CLI appears.
    launch_dir = Path.home() / ".local" / "share" / "gacha-companion"
    launch_dir.mkdir(parents=True, exist_ok=True)
    launch = launch_dir / "launch.sh"
    launch.write_text(
        "#!/bin/bash\n"
        "# Gacha Companion launcher (rewritten by the setup wizard)\n"
        f'X="{venv_cli}"\n'
        '[ -x "$X" ] && exec "$X" app\n'
        f'exec python3 "{REPO / "setup-gui.py"}" --panel\n'
    )
    launch.chmod(0o755)
    entries = [
        ("gacha-companion.desktop", "Gacha Companion", "Open your Gacha Companion", str(launch)),
        ("gacha-companion-setup.desktop", "Gacha Companion Setup",
         "Run the Gacha Companion setup wizard",
         f"python3 {REPO / 'setup-gui.py'}"),
    ]
    written = []
    for filename, name, comment, exec_line in entries:
        path = apps / filename
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={name}\n"
            f"Comment={comment}\n"
            f"Exec={exec_line}\n"
            "Icon=applications-games\n"
            "Terminal=false\n"
            "Categories=Game;\n"
        )
        # Best-effort trust flag; on some desktops the user confirms once instead.
        if shutil.which("gio"):
            run(["gio", "set", str(path), "metadata::trusted", "true"], timeout=10)
        written.append(str(path))
    return {"ok": True, "paths": written}


# --------------------------------------------------------------- handler

class Wizard:
    def __init__(self, token: str):
        self.token = token

    def dispatch(self, method: str, path: str, body: bytes) -> tuple[int, str, str]:
        """Returns (status, content_type, payload). 404s anything un-tokenized."""
        prefix = f"/{self.token}"
        if not path.startswith(prefix):
            if method == "GET":
                # a browser landed here: an old bookmark/tab (the token rotates
                # every launch) or a bare port — explain instead of raw text
                return 404, "text/html; charset=utf-8", STALE_PAGE
            return 404, "text/plain", "not found"
        route = path[len(prefix):].rstrip("/") or "/"
        try:
            if method == "GET" and route == "/":
                return 200, "text/html; charset=utf-8", PAGE
            if method == "GET" and route == "/panel":
                return 200, "text/html; charset=utf-8", PANEL_PAGE
            if method == "GET" and route == "/api/state":
                return 200, "application/json", json.dumps(detect_state())
            if method == "GET" and route == "/api/toolfile":
                if TOOLFILE.exists():
                    return 200, "text/plain; charset=utf-8", TOOLFILE.read_text()
                return 404, "application/json", json.dumps({"error": "tool file missing"})
            data = json.loads(body or b"{}")
            if method == "POST" and route == "/api/uv-install":
                ok, out = run("curl -LsSf https://astral.sh/uv/install.sh | sh",
                              timeout=300, shell=True)
                return 200, "application/json", json.dumps({"ok": ok, "log": out})
            if method == "POST" and route == "/api/install":
                return 200, "application/json", json.dumps(self.do_install())
            if method == "POST" and route == "/api/llm-probe":
                return 200, "application/json", json.dumps(
                    self.llm_probe(data.get("base", ""), data.get("key", "")))
            if method == "POST" and route == "/api/config":
                return 200, "application/json", json.dumps(
                    self.save_config(data))
            if method == "POST" and route == "/api/players/create":
                return 200, "application/json", json.dumps(
                    self.create_player(str(data.get("name", "")).strip()))
            if method == "POST" and route == "/api/service/start":
                ok, out = run(["bash", str(REPO / "start-service.sh")], timeout=120)
                return 200, "application/json", json.dumps({"ok": ok, "log": out.strip()})
            if method == "POST" and route == "/api/service/stop":
                ok, out = run(["bash", str(REPO / "stop-service.sh")], timeout=60)
                return 200, "application/json", json.dumps({"ok": ok, "log": out.strip()})
            if method == "POST" and route == "/api/desktop-shortcut":
                return 200, "application/json", json.dumps(desktop_shortcut())
            if method == "POST" and route == "/api/autoupdate/toggle":
                return 200, "application/json", json.dumps(autoupdate_toggle())
            if method == "POST" and route == "/api/update-check":
                ok, out = run(["bash", str(REPO / "auto-update.sh")], timeout=600)
                updf = REPO / "update.log"
                if updf.exists():
                    tail = "\n".join(updf.read_text(errors="replace").splitlines()[-15:])
                    out = (out.strip() + "\n" if out.strip() else "") + tail
                return 200, "application/json", json.dumps({"ok": ok, "log": redact(out.strip())})
            if method == "GET" and route.split("?")[0] == "/api/logs":
                import urllib.parse as _up
                qs = _up.parse_qs(_up.urlparse("http://x" + path).query)
                which = (qs.get("which") or ["serve"])[0]
                name = {"serve": "serve.log", "update": "update.log"}.get(which)
                if not name:
                    return 404, "application/json", json.dumps({"error": "unknown log"})
                f = REPO / name
                text = f.read_text(errors="replace")[-8000:] if f.exists() else "(no log yet)"
                return 200, "application/json", json.dumps({"log": redact(text)})
            if method == "POST" and route == "/api/open-folder":
                targets = {"data": data_dir(), "repo": REPO,
                           "exports": data_dir() / "exports"}
                target = targets.get(str(data.get("which", "data")))
                if target is None:
                    return 404, "application/json", json.dumps({"error": "unknown folder"})
                opener = shutil.which("xdg-open")
                if not opener:
                    return 200, "application/json", json.dumps(
                        {"ok": False, "error": f"no file browser found — the folder is: {target}"})
                run([opener, str(target)], timeout=15)
                return 200, "application/json", json.dumps({"ok": True, "path": str(target)})
            if method == "POST" and route == "/api/report":
                return 200, "application/json", json.dumps(
                    {"report": build_report(data if isinstance(data, dict) else {})})
        except Exception as e:  # surface backend errors to the UI instead of hanging
            return 500, "application/json", json.dumps({"error": f"{type(e).__name__}: {e}"})
        return 404, "application/json", json.dumps({"error": "unknown route"})

    def do_install(self) -> dict:
        log = []
        port = service_port()
        was_running = http_get(f"http://127.0.0.1:{port}/health", timeout=2)[0] == 200
        if (REPO / ".git").exists():
            ok, out = run(["git", "pull", "--ff-only"], timeout=120)
            log.append(f"$ git pull --ff-only\n{out.strip()}\n")
        else:
            log.append("not a git checkout — skipping update\n")
        uv = uv_path()
        if not Path(uv).exists():
            return {"ok": False, "log": "".join(log) + "uv is missing — install it first (button in System check)"}
        if not (REPO / ".venv/bin/python").exists():
            ok, out = run([uv, "venv", "--python", "3.12"], timeout=600)
            log.append(f"$ uv venv --python 3.12\n{out.strip()}\n")
            if not ok:
                return {"ok": False, "log": "".join(log)}
        ok, out = run([uv, "pip", "install", "--python", ".venv/bin/python",
                       "-e", ".[dev]"], timeout=600)
        log.append(f"$ uv pip install -e \".[dev]\"\n{out.strip()}\n")
        if not ok:
            return {"ok": False, "log": "".join(log)}
        ok, out = run([".venv/bin/game-companion", "list-games"], timeout=60)
        log.append(f"$ game-companion list-games\n{out.strip()}\n")
        if was_running and ok:
            # the code just changed — a running service is now stale and would
            # keep serving the old version (this is how /ui "went missing")
            stop = run(["bash", "stop-service.sh"], timeout=60)
            start = run(["bash", "start-service.sh"], timeout=60)
            log.append(
                f"$ bash stop-service.sh\n{(stop[1] or '').strip()}\n"
                f"$ bash start-service.sh\n{(start[1] or '').strip()}\n"
            )
            ok = ok and start[0]
        return {"ok": ok, "log": "".join(log)}

    def llm_probe(self, base: str, key: str) -> dict:
        base = (base or env_key("GAME_COMPANION_LLM_BASE_URL")).rstrip("/")
        key = key or env_key("GAME_COMPANION_LLM_API_KEY")
        code, body = http_get(f"{base}/models", key=key, timeout=12)
        models = []
        if code == 200:
            try:
                data = json.loads(body)
                raw = data.get("data", data if isinstance(data, list) else [])
                models = sorted({m.get("id", "?") for m in raw if isinstance(m, dict)})
            except Exception:
                pass
        return {"code": code, "models": models, "base": base}

    def save_config(self, data: dict) -> dict:
        base = str(data.get("base", "")).strip()
        model = str(data.get("model", "")).strip()
        key = data.get("key")
        if not base or not model:
            return {"ok": False, "error": "base URL and model are required"}
        note = write_env(base, model, key if key else None)
        return {"ok": True, "note": note}

    def create_player(self, name: str) -> dict:
        if not name:
            return {"ok": False, "error": "name is required"}
        if not (REPO / ".venv/bin/game-companion").exists():
            return {"ok": False, "error": "run Install / update first (no .venv yet)"}
        ok, out = run([".venv/bin/game-companion", "create-player", name], timeout=60)
        if not ok:
            return {"ok": False, "error": out.strip()}
        try:
            return {"ok": True, "player": json.loads(out.strip().splitlines()[-1])}
        except Exception:
            return {"ok": False, "error": f"unexpected output: {out.strip()}"}


def make_handler(wizard: Wizard):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_a):  # keep the launching terminal quiet
            pass

        def _reply(self, status: int, ctype: str, payload: str):
            data = payload.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            s, c, p = wizard.dispatch("GET", self.path, b"")
            self._reply(s, c, p)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            s, c, p = wizard.dispatch("POST", self.path, self.rfile.read(n))
            self._reply(s, c, p)

    return Handler


# --------------------------------------------------------------- the page

PANEL_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gacha Companion</title>
<style>
  :root{
    --bg:#0b0f14; --card:#121822; --card2:#0e141d; --line:#1f2b3a;
    --text:#dbe4ee; --dim:#7b8ba0; --acc:#22d3ee; --acc2:#e879f9;
    --ok:#34d399; --warn:#fbbf24; --err:#f87171;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:16px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
  .wrap{max-width:880px;margin:0 auto;padding:28px 18px 80px}
  header{margin-bottom:24px;text-align:center}
  h1{font-size:26px;margin:0;letter-spacing:.5px}
  h1 .spark{color:var(--acc)}
  .sub{color:var(--dim);margin-top:8px;font-size:15px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
        padding:22px 24px;margin-bottom:18px}
  h2{font-size:17px;margin:0 0 14px;font-weight:700}
  .badge{font-size:12px;padding:3px 9px;border-radius:999px;font-weight:600}
  .b-ok{background:rgba(52,211,153,.15);color:var(--ok)}
  .b-err{background:rgba(248,113,113,.15);color:var(--err)}
  .b-warn{background:rgba(251,191,36,.15);color:var(--warn)}
  .b-dim{background:rgba(123,139,160,.15);color:var(--dim)}
  button{background:var(--acc);border:0;border-radius:10px;color:#06222b;
         font-weight:800;padding:12px 18px;cursor:pointer;font-size:15.5px}
  button:hover{filter:brightness(1.12)}
  button.sec{background:transparent;border:1px solid var(--line);color:var(--text)}
  button.mini{padding:6px 12px;font-size:13px;font-weight:600}
  button.big{width:100%;padding:18px;font-size:19px;margin-top:22px;border-radius:12px}
  .btns{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap;align-items:center}
  .hint{color:var(--dim);font-size:13.5px;margin-top:6px}
  .mono{font-family:ui-monospace,Menlo,monospace;font-size:13px}
  .kv{display:flex;gap:8px;align-items:center;margin:8px 0;flex-wrap:wrap}
  .kv code{background:var(--card2);border:1px solid var(--line);border-radius:6px;
           padding:4px 10px;font-size:13.5px;word-break:break-all}
  .row{display:flex;justify-content:space-between;align-items:center;gap:10px;
       padding:7px 0;border-bottom:1px dashed var(--line);font-size:14px}
  .row:last-child{border-bottom:0}
  .msg{font-size:14px;margin-top:10px;min-height:18px}
  .m-ok{color:var(--ok)} .m-err{color:var(--err)} .m-warn{color:var(--warn)}
  pre{background:#070a0f;border:1px solid var(--line);border-radius:10px;
      padding:12px 14px;font:12px/1.55 ui-monospace,Menlo,monospace;
      color:#9fb3c8;white-space:pre-wrap;word-break:break-word;
      max-height:280px;overflow-y:auto;margin-top:8px;text-align:left}
  select{background:var(--card2);border:1px solid var(--line);border-radius:8px;
         color:var(--text);padding:8px 10px;font:14px ui-monospace,Menlo,monospace}
  input[type=password]{background:var(--card2);border:1px solid var(--line);
        border-radius:8px;color:var(--text);padding:10px 12px;font-size:15px}
  a{color:var(--acc)}
</style></head><body><div class="wrap">

<header>
  <h1><span class="spark">&#10022;</span> GACHA COMPANION <span class="spark">&#10022;</span></h1>
  <div class="sub" id="statusline">checking&hellip;</div>
</header>

<div class="card" style="border-color:var(--ok,#39d98a)">
  <h2>Open your companion</h2>
  <div class="btns">
    <a id="btn-open-companion" class="btn" style="text-decoration:none;text-align:center" href="http://127.0.0.1:8765/ui" target="_blank">Dashboard &amp; chat &rarr;</a>
    <a id="btn-open-chat" class="btn sec" style="text-decoration:none;text-align:center" href="http://127.0.0.1:8765/ui/chat" target="_blank">Chat</a>
  </div>
  <div class="hint" id="companion-hint">Everything lives in the companion now &mdash; roster, teams, resources, codes and chat.</div>
</div>

<div class="card">
  <h2>Keep it fresh <span id="upd-badge" class="badge b-dim"></span></h2>
  <div class="btns">
    <button id="btn-update">Check for updates now</button>
  </div>
  <div class="hint" id="upd-hint"></div>
  <div class="msg" id="upd-msg"></div>
  <pre id="upd-log" style="display:none"></pre>
</div>

<div class="card">
  <h2>The service <span id="svc-badge" class="badge b-dim">checking&hellip;</span></h2>
  <div class="btns">
    <button id="btn-start">Start</button>
    <button id="btn-stop" class="sec">Stop</button>
  </div>
  <div class="msg" id="svc-msg"></div>
</div>

<div class="card">
  <h2>Something wrong?</h2>
  <div class="btns">
    <button id="btn-report">Copy problem report</button>
    <button id="btn-open-repo" class="sec">Open the program folder</button>
    <button id="btn-open-data" class="sec">Open the data folder</button>
  </div>
  <div class="hint">The report contains no secrets — it is safe to send to whoever helps you.</div>
  <details id="report-box" hidden style="margin-top:12px">
    <summary>report text (if copying is blocked, select it here)</summary>
    <pre id="report-text"></pre>
  </details>
</div>

<div class="card">
  <h2>Peek at the logs</h2>
  <div class="btns" style="margin-top:0">
    <select id="log-select">
      <option value="serve">service log (serve.log)</option>
      <option value="update">update log (update.log)</option>
    </select>
    <button id="btn-log" class="sec mini">Refresh</button>
  </div>
  <pre id="log-view">press Refresh</pre>
</div>

<div class="card">
  <h2>Open WebUI quick reference</h2>
  <div class="kv">base_url <code id="c-url"></code>
    <button class="mini sec" data-copy="c-url">copy</button></div>
  <div class="kv">game_id <code id="c-game">zzz</code>
    <button class="mini sec" data-copy="c-game">copy</button></div>
  <div class="kv">player_id <code id="c-player"></code>
    <button class="mini sec" data-copy="c-player">copy</button></div>
  <div class="btns">
    <button id="btn-copy-tool" class="sec mini">copy the tool code</button>
    <a id="owui-link" href="#" target="_blank" style="display:none">open Open WebUI</a>
  </div>
</div>

<div class="card">
  <h2>Automatic updates <span id="au-badge" class="badge b-dim"></span></h2>
  <div class="btns">
    <button id="btn-au" class="sec">Turn on</button>
  </div>
  <div class="hint" id="au-hint"></div>
</div>

<div class="center" style="margin-top:10px">
  <a href="./">Run the full setup wizard again</a>
</div>

</div>

<script>
const $ = (id) => document.getElementById(id);
const TOKEN = location.pathname.split("/")[1];
const api = (p) => "/" + TOKEN + p;
let STATE = null;
const clientErrors = [];
window.addEventListener("error", e => clientErrors.push(e.message || "error"));

async function post(path, body){
  let r;
  try {
    r = await fetch(api(path), {method:"POST",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify(body||{})});
  } catch (e) { throw new Error("HELPER_STOPPED"); }
  return r.json();
}
async function refresh(){
  STATE = await (await fetch(api("/api/state"))).json();
  render();
}
async function copyText(text){
  try { await navigator.clipboard.writeText(text); return true; }
  catch (e) {}
  try {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy"); ta.remove(); return ok;
  } catch (e) { return false; }
}
document.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", async () => {
  const ok = await copyText($(b.dataset.copy).textContent);
  b.textContent = ok ? "copied!" : "copy failed";
  setTimeout(()=> b.textContent="copy", 1200);
}));

function render(){
  const s = STATE;
  const bits = [];
  bits.push("version " + (s.commit || "?"));
  bits.push(s.service.running ? "service running" : "service stopped");
  if (s.behind !== null && s.behind !== undefined) {
    if (Number(s.behind) > 0) bits.push(s.behind + " update(s) waiting");
  }
  $("statusline").textContent = bits.join("  ·  ");
  $("svc-badge").className = "badge " + (s.service.running ? "b-ok" : "b-warn");
  $("svc-badge").textContent = s.service.running ? "running" : "stopped";
  const upd = Number(s.behind);
  const ub = $("upd-badge");
  if (s.behind !== null && s.behind !== undefined && upd > 0){
    ub.className = "badge b-warn"; ub.textContent = s.behind + " waiting";
  } else { ub.className = "badge b-ok"; ub.textContent = "current"; }
  $("upd-hint").textContent = "checks, installs and restarts by itself — safe to press any time";
  $("au-badge").className = "badge " + (s.autoupdate === "on" ? "b-ok" : "b-dim");
  $("au-badge").textContent = s.autoupdate === "on" ? "daily" : "off";
  $("btn-au").textContent = s.autoupdate === "on" ? "Turn off" : "Turn on";
  const companionBase = "http://127.0.0.1:" + (s.service && s.service.port ? s.service.port : 8765);
  $("btn-open-companion").href = companionBase + "/ui";
  $("btn-open-chat").href = companionBase + "/ui/chat";
  $("au-hint").textContent = s.autoupdate === "on"
    ? "updates every night by itself, rolls back a bad update automatically"
    : "off — updates only happen when you press the button above";
  $("c-url").textContent = "http://127.0.0.1:" + s.service.port;
  $("c-player").textContent = (s.players[0] && s.players[0].id) || "(create a profile in setup)";
  if (s.openwebui_port){
    $("owui-link").href = "http://127.0.0.1:" + s.openwebui_port + "/";
    $("owui-link").style.display = "";
  }
}
function log(text, el){ const e = $(el||"upd-log"); e.style.display = "";
  e.textContent += text + "\\n"; e.scrollTop = e.scrollHeight; }
function msg(id, text, cls){ const el=$(id); el.textContent=text||""; el.className="msg "+(cls||""); }

$("btn-update").onclick = async () => {
  msg("upd-msg", "checking + updating… this can take a minute");
  $("btn-update").disabled = true;
  let r;
  try { r = await post("/api/update-check"); }
  catch (e) {
    $("btn-update").disabled = false;
    return msg("upd-msg", "the helper stopped — reopen Gacha Companion from the menu", "m-err");
  }
  $("btn-update").disabled = false;
  log(r.log);
  msg("upd-msg", r.ok ? "done ✓ (details below)" : "finished with problems — see below",
      r.ok ? "m-ok" : "m-warn");
  refresh();
};
$("btn-start").onclick = async () => {
  msg("svc-msg", "starting…");
  const r = await post("/api/service/start");
  msg("svc-msg", r.ok ? "running ✓" : (r.log || "failed"), r.ok ? "m-ok" : "m-err");
  refresh();
};
$("btn-stop").onclick = async () => {
  const r = await post("/api/service/stop");
  msg("svc-msg", r.ok ? "stopped" : (r.log || "failed"), r.ok ? "" : "m-err");
  refresh();
};
async function copyReport(){
  const client = {step: "(panel — report requested)", message: "", raw: "",
                  errors: clientErrors.slice(-10), ua: navigator.userAgent};
  let text;
  try { text = (await post("/api/report", client)).report; }
  catch (e) {
    text = "GACHA COMPANION — PROBLEM REPORT (partial: helper not answering)\\n"
      + "errors: " + (client.errors.join(" | ") || "none") + "\\nUA: " + client.ua;
  }
  $("report-box").hidden = false;
  $("report-text").textContent = text;
  $("report-box").open = true;
  const ok = await copyText(text);
  $("btn-report").textContent = ok ? "Report copied ✓ — send it to whoever helps you"
                                   : "copy blocked — select the text below instead";
  setTimeout(() => $("btn-report").textContent = "Copy problem report", 4000);
}
$("btn-report").onclick = copyReport;
$("btn-open-repo").onclick = () => post("/api/open-folder", {which:"repo"});
$("btn-open-data").onclick = () => post("/api/open-folder", {which:"data"});
$("btn-log").onclick = async () => {
  $("log-view").textContent = "loading…";
  const r = await fetch(api("/api/logs?which=" + $("log-select").value));
  const d = await r.json();
  $("log-view").textContent = d.log || "(empty)";
  $("log-view").scrollTop = $("log-view").scrollHeight;
};
$("btn-au").onclick = async () => {
  msg("au-hint", "working…");
  const r = await post("/api/autoupdate/toggle");
  if (r.ok){ await refresh(); }
  else $("au-hint").textContent = "couldn't change it — " + (r.log || "copy a problem report");
};
$("btn-copy-tool").onclick = async () => {
  const t = await (await fetch(api("/api/toolfile"))).text();
  const ok = await copyText(t);
  $("btn-copy-tool").textContent = ok ? "copied — paste into Workspace → Tools"
                                      : "copy blocked";
  setTimeout(()=> $("btn-copy-tool").textContent = "copy the tool code", 2500);
};
refresh();
</script></body></html>
"""

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gacha Companion — Setup</title>
<style>
  :root{
    --bg:#0b0f14; --card:#121822; --card2:#0e141d; --line:#1f2b3a;
    --text:#dbe4ee; --dim:#7b8ba0; --acc:#22d3ee; --acc2:#e879f9;
    --ok:#34d399; --warn:#fbbf24; --err:#f87171;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:16px/1.55 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif}
  .wrap{max-width:880px;margin:0 auto;padding:28px 18px 90px}
  header{margin-bottom:24px;text-align:center}
  h1{font-size:28px;margin:0;letter-spacing:.5px}
  h1 .spark{color:var(--acc)}
  .sub{color:var(--dim);margin-top:8px;font-size:15px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;
        padding:22px 24px;margin-bottom:18px}
  h2{font-size:18px;margin:0 0 14px;font-weight:700}
  h3{font-size:15px;margin:22px 0 10px;color:var(--acc)}
  .badge{font-size:12px;padding:3px 9px;border-radius:999px;font-weight:600}
  .b-ok{background:rgba(52,211,153,.15);color:var(--ok)}
  .b-err{background:rgba(248,113,113,.15);color:var(--err)}
  .b-warn{background:rgba(251,191,36,.15);color:var(--warn)}
  .b-dim{background:rgba(123,139,160,.15);color:var(--dim)}
  label{display:block;color:var(--dim);font-size:13.5px;margin:16px 0 6px;
        letter-spacing:.4px}
  input[type=text],input[type=password]{width:100%;background:var(--card2);
        border:1px solid var(--line);border-radius:10px;color:var(--text);
        padding:13px 14px;font-size:16px}
  input:focus{outline:none;border-color:var(--acc)}
  button{background:var(--acc);border:0;border-radius:10px;color:#06222b;
         font-weight:800;padding:12px 18px;cursor:pointer;font-size:16px}
  button:hover{filter:brightness(1.12)}
  button.sec{background:transparent;border:1px solid var(--line);color:var(--text)}
  button.mini{padding:6px 12px;font-size:13px;font-weight:600}
  button.big{width:100%;padding:18px;font-size:19px;margin-top:22px;border-radius:12px}
  .hint{color:var(--dim);font-size:13.5px;margin-top:6px}
  .center{text-align:center}
  .mono{font-family:ui-monospace,Menlo,monospace;font-size:13px}
  .kv{display:flex;gap:8px;align-items:center;margin:8px 0;flex-wrap:wrap}
  .kv code{background:var(--card2);border:1px solid var(--line);border-radius:6px;
           padding:4px 10px;font-size:13.5px;word-break:break-all}
  a{color:var(--acc)}
  /* checklist */
  #checklist{list-style:none;margin:0;padding:0}
  #checklist li{display:flex;gap:14px;align-items:flex-start;padding:11px 0;
                border-bottom:1px dashed var(--line)}
  #checklist li:last-child{border-bottom:0}
  .st{flex:0 0 26px;height:26px;border-radius:50%;display:flex;align-items:center;
      justify-content:center;font-weight:800;font-size:14px;
      background:var(--card2);border:1px solid var(--line);color:var(--dim)}
  li.run .st{color:var(--acc);border-color:var(--acc);animation:pulse 1s infinite}
  li.ok .st{color:#06222b;background:var(--ok);border-color:var(--ok)}
  li.err .st{color:#2b0606;background:var(--err);border-color:var(--err)}
  .lbl{font-weight:600}
  .sub2{color:var(--dim);font-size:13.5px}
  @keyframes pulse{50%{opacity:.45}}
  #err-panel{margin-top:14px;background:rgba(248,113,113,.08);border:1px solid var(--err);
             border-radius:10px;padding:14px}
  details.logbox{margin-top:14px}
  details.logbox summary{cursor:pointer;color:var(--dim)}
  pre#log{background:#070a0f;border:1px solid var(--line);border-radius:10px;
          padding:12px 14px;font:12px/1.55 ui-monospace,Menlo,monospace;
          color:#9fb3c8;white-space:pre-wrap;word-break:break-word;
          max-height:240px;overflow-y:auto;margin-top:8px}
  /* done screen */
  .donehead{display:flex;align-items:center;gap:14px}
  .donehead .bigcheck{width:46px;height:46px;border-radius:50%;background:var(--ok);
        color:#06222b;display:flex;align-items:center;justify-content:center;
        font-size:24px;font-weight:900}
  .chip{display:inline-flex;gap:8px;align-items:center;background:var(--card2);
        border:1px solid var(--line);border-radius:999px;padding:6px 14px;
        margin:4px 6px 4px 0;font-size:14px}
  .owcard{border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0;
          background:var(--card2)}
  .owcard.done{border-color:var(--ok);opacity:.75}
  .ownum{display:inline-flex;width:26px;height:26px;border-radius:50%;
         background:var(--acc);color:#06222b;align-items:center;justify-content:center;
         font-weight:800;margin-right:10px}
  .owtop{display:flex;justify-content:space-between;align-items:center;gap:10px}
  .owtitle{font-weight:700;font-size:15.5px}
  .owbody{margin:10px 0 4px;font-size:14.5px;color:var(--text)}
  .progress{height:8px;background:var(--card2);border:1px solid var(--line);
            border-radius:999px;overflow:hidden;margin:6px 0 14px}
  .progress i{display:block;height:100%;background:var(--ok);width:0;transition:width .4s}
  #key-reminder{background:rgba(251,191,36,.07);border:1px solid var(--warn);
                border-radius:12px;padding:14px 16px;margin-top:14px}
  /* advanced */
  details#advanced{margin-top:8px}
  details#advanced summary{cursor:pointer;color:var(--dim);padding:8px 0}
  .row{display:flex;justify-content:space-between;align-items:center;gap:10px;
       padding:7px 0;border-bottom:1px dashed var(--line);font-size:14px}
  .row:last-child{border-bottom:0}
  .row .v{color:var(--dim);font-family:ui-monospace,Menlo,monospace;font-size:12.5px;
          word-break:break-all;text-align:right}
  select{width:100%;background:var(--card2);border:1px solid var(--line);
         border-radius:10px;color:var(--text);padding:10px 12px;font:15px ui-monospace,Menlo,monospace}
  .btns{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap;align-items:center}
  .msg{font-size:14px;margin-top:10px;min-height:18px}
  .m-ok{color:var(--ok)} .m-err{color:var(--err)} .m-warn{color:var(--warn)}
</style></head><body><div class="wrap">

<header>
  <h1><span class="spark">&#10022;</span> GACHA COMPANION <span class="spark">&#10022;</span></h1>
  <div class="sub" id="subtitle">Let&rsquo;s set everything up for you &middot; about 2 minutes &middot;
  nothing can break &mdash; you can always run this again</div>
</header>

<!-- ============================ guided: start ========================= -->
<div class="card" id="start-card">
  <h2>Ready when you are &#128077;</h2>
  <label for="f-key">1 &middot; The secret key &mdash; paste it here</label>
  <input type="password" id="f-key" placeholder="sk-… (the key you were given)" autocomplete="off">
  <div class="hint" id="key-hint">No key yet? Leave it empty &mdash; you can add it on the last screen.</div>

  <label for="f-name">2 &middot; Your name in the game</label>
  <input type="text" id="f-name" placeholder="e.g. Phoenix">

  <button class="big" id="btn-go">Start setup &#9654;</button>
  <div class="hint center">(or press Enter)</div>
</div>

<!-- ============================ guided: progress ====================== -->
<div class="card" id="progress-card" hidden>
  <h2>Setting things up&hellip;</h2>
  <ol id="checklist">
    <li id="st0"><span class="st">1</span><div><div class="lbl">Checking your computer</div>
        <div class="sub2">making sure everything needed is there</div></div></li>
    <li id="st1"><span class="st">2</span><div><div class="lbl">Getting the latest version</div>
        <div class="sub2">a quick check with GitHub</div></div></li>
    <li id="st2"><span class="st">3</span><div><div class="lbl">Installing the pieces</div>
        <div class="sub2">the longest step &mdash; can take a minute the first time</div></div></li>
    <li id="st3"><span class="st">4</span><div><div class="lbl">Saving your settings</div>
        <div class="sub2">your key is kept only on this computer</div></div></li>
    <li id="st4"><span class="st">5</span><div><div class="lbl">Creating your profile</div>
        <div class="sub2">so the game remembers what you own</div></div></li>
    <li id="st5"><span class="st">6</span><div><div class="lbl">Turning it on</div>
        <div class="sub2">starting your companion</div></div></li>
  </ol>
  <div id="err-panel" hidden>
    <div id="err-text" style="font-size:15px"></div>
    <div class="kv" id="fix-box" hidden>
      <code id="fix-cmd" style="flex:1"></code>
      <button class="mini" id="btn-fix-copy">copy</button>
    </div>
    <div class="btns">
      <button id="btn-retry">Try again</button>
      <button id="btn-report" class="sec">Copy problem report</button>
    </div>
    <div class="hint">The report contains no secrets (your key stays hidden) —
    it&rsquo;s safe to send to whoever is helping you.</div>
  </div>
  <details class="logbox"><summary>Show what the computer is doing</summary>
    <pre id="log"></pre>
  </details>
</div>

<!-- ============================ guided: done ========================== -->
<div class="card" id="done-card" hidden>
  <div class="donehead">
    <div class="bigcheck">&#10003;</div>
    <div><h2 style="margin:0">All done!</h2>
    <div class="sub2">Your companion is running and remembering things.</div></div>
  </div>

  <div id="key-reminder" hidden>
    <b>One small thing left:</b> you haven&rsquo;t added the secret key yet, so
    reading screenshots and a few smart features stay off. Paste it here whenever
    you&rsquo;re ready:
    <div class="kv" style="margin-top:8px">
      <input type="password" id="f-key2" placeholder="sk-…" style="flex:1">
      <button class="mini" id="btn-key2">Save key</button>
    </div>
    <div class="msg" id="key2-msg"></div>
  </div>

  <div class="owcard" data-ow="0" style="border-color:var(--ok,#39d98a)">
    <div class="owtop"><span class="owtitle"><span class="ownum">&#9894;</span>You&rsquo;re done &mdash; open your companion</span></div>
    <div class="owbody">Everything now lives in your companion&rsquo;s own app:
      roster, teams, resources, codes and <b>chat with your companion</b> &mdash; no Open WebUI needed.
      <a id="open-companion" href="http://127.0.0.1:8765/ui" target="_blank"><b>Open your companion &rarr;</b></a>
      &nbsp;or double-click the <b>Gacha Companion</b> desktop icon any time.
      <div class="hint" id="companion-hint" style="margin-top:6px"></div>
    </div>
  </div>

  <h3>Optional &mdash; also use it from Open WebUI <span id="owui-progress-label"></span></h3>
  <div class="progress"><i id="owui-bar"></i></div>
  <div class="hint" id="owui-hint"></div>

  <div class="owcard" data-ow="1">
    <div class="owtop"><span class="owtitle"><span class="ownum">1</span>Give Open WebUI its brain</span>
      <label><input type="checkbox" class="owcheck"> Done</label></div>
    <div class="owbody">Open WebUI &rarr; <b>Settings</b> (bottom&#8209;left) &rarr; <b>Admin Settings</b> &rarr;
      <b>Connections</b> &rarr; OpenAI API &rarr; add
      <span class="mono" id="c-base"></span> with the same secret key,
      then pick your chat model.<span id="owui-link-1"></span></div>
  </div>

  <div class="owcard" data-ow="2">
    <div class="owtop"><span class="owtitle"><span class="ownum">2</span>Add the companion tool</span>
      <label><input type="checkbox" class="owcheck"> Done</label></div>
    <div class="owbody">Open WebUI &rarr; <b>Workspace</b> &rarr; <b>Tools</b> &rarr; press
      <b>+</b>, name it <b>Gacha Companion</b>, then
      <button class="mini" id="btn-copy-tool">copy the tool code</button>
      and paste it into the big box. Press save.<span id="owui-link-2"></span></div>
  </div>

  <div class="owcard" data-ow="3">
    <div class="owtop"><span class="owtitle"><span class="ownum">3</span>Introduce them</span>
      <label><input type="checkbox" class="owcheck"> Done</label></div>
    <div class="owbody">On the tool&rsquo;s <b>Valves</b> (gear icon), fill in exactly these three:</div>
    <div class="kv">base_url <code id="c-url"></code>
      <button class="mini sec" data-copy="c-url">copy</button></div>
    <div class="kv">game_id <code id="c-game">zzz</code>
      <button class="mini sec" data-copy="c-game">copy</button></div>
    <div class="kv">player_id <code id="c-player"></code>
      <button class="mini sec" data-copy="c-player">copy</button></div>
  </div>

  <div class="owcard" data-ow="4">
    <div class="owtop"><span class="owtitle"><span class="ownum">4</span>Say hello</span>
      <label><input type="checkbox" class="owcheck"> Done</label></div>
    <div class="owbody">Start a new chat &rarr; press <b>+</b> next to the message box &rarr;
      <b>Tools</b> &rarr; turn on <b>Gacha Companion</b>. Then type:
      <div class="hint" style="font-size:15px">&ldquo;I own Burnice, Ellen and Lycaon.&rdquo;</div>
      <span id="owui-link-4"></span></div>
  </div>

  <h3>Make it easy on yourself</h3>
  <div class="btns">
    <button id="btn-shortcut">Add desktop icons &#128187;</button>
    <button id="btn-autoupd" class="sec">Turn on automatic updates</button>
    <button id="btn-again" class="sec">Check for updates now</button>
  </div>
  <div class="hint" id="shortcut-msg">Two icons: <b>Gacha Companion</b> (opens the companion
  app window &mdash; starts the service first if needed) and <b>Gacha Companion Setup</b> (this
  wizard &mdash; also a control panel: updates, logs, reports). No terminal needed, ever again.</div>
  <div class="hint" id="autoupd-msg"></div>
</div>

<!-- ============================ advanced =============================== -->
<details id="advanced">
  <summary>Manual controls (for the curious &mdash; everything already ran above)</summary>
  <div class="card" style="margin-top:12px">
    <h2>System check <span id="sysbadge" class="badge b-dim">checking&hellip;</span></h2>
    <div id="sysrows"></div>
    <div class="btns">
      <button id="btn-uv" style="display:none">Install uv</button>
      <button id="btn-install" class="sec">Install / update</button>
    </div>
    <div class="msg" id="install-msg"></div>
  </div>
  <div class="card">
    <h2>LLM endpoint</h2>
    <div class="hint">The companion <b>service</b> uses this for screenshot extraction,
    research and tutoring &mdash; separate from what Open WebUI chats with.
    The key is stored only in your local <span class="mono">.env</span>.</div>
    <label for="f-base2">Base URL (OpenAI-compatible)</label>
    <input type="text" id="f-base2" placeholder="https://llm.tictac.one/v1">
    <label for="f-key3">API key</label>
    <input type="password" id="f-key3" placeholder="sk-..." autocomplete="off">
    <label for="f-model">Model</label>
    <input type="text" id="f-model" placeholder="muse-glimmer-30b-vlm-128k">
    <select id="f-model-list" style="display:none;margin-top:6px"></select>
    <div class="btns">
      <button id="btn-probe" class="sec">Test connection &amp; load models</button>
      <button id="btn-save" class="sec">Save configuration</button>
    </div>
    <div class="msg" id="llm-msg"></div>
  </div>
  <div class="card">
    <h2>Player profiles</h2>
    <div id="player-list"></div>
    <label for="f-player">New profile name</label>
    <div style="display:flex;gap:8px">
      <input type="text" id="f-player" placeholder="e.g. Phoenix" style="flex:1">
      <button id="btn-player" class="sec">Create</button>
    </div>
    <div class="msg" id="player-msg"></div>
  </div>
  <div class="card">
    <h2>Local service <span id="svc-badge" class="badge b-dim">checking&hellip;</span></h2>
    <div class="row"><span>companion API</span><span class="v" id="svc-url"></span></div>
    <div class="btns">
      <button id="btn-svc-start" class="sec">Start</button>
      <button id="btn-svc-stop" class="sec">Stop</button>
    </div>
    <div class="msg" id="svc-msg"></div>
  </div>
</details>

<div class="center" style="margin-top:26px">
  <button id="btn-report2" class="sec mini">Something&rsquo;s wrong? Copy a problem report</button>
  <details id="report-box" hidden style="margin-top:12px;text-align:left">
    <summary>report text (if the copy button doesn&rsquo;t work, select it here)</summary>
    <pre id="report-text" style="background:#070a0f;border:1px solid var(--line);border-radius:10px;
padding:12px;font:11.5px/1.5 ui-monospace,Menlo,monospace;color:#9fb3c8;white-space:pre-wrap;
max-height:300px;overflow-y:auto"></pre>
  </details>
</div>

</div>

<script>
const $ = (id) => document.getElementById(id);
const TOKEN = location.pathname.split("/")[1];
const api = (p) => "/" + TOKEN + p;
let STATE = null;
let currentStep = 0, lastFailure = null, lastProbe = null;
const clientErrors = [];
window.addEventListener("error", e =>
  clientErrors.push((e.message||"error") + " @" + (e.filename||"").split("/").pop() + ":" + (e.lineno||"?")));
window.addEventListener("unhandledrejection", e =>
  clientErrors.push("promise: " + ((e.reason && e.reason.message) || e.reason)));

function log(text){ const el=$("log"); el.parentElement.open = true;
  el.textContent += text + "\\n"; el.scrollTop = el.scrollHeight; }
function msg(id, text, cls){ const el=$(id); el.textContent=text||""; el.className="msg "+(cls||""); }

async function post(path, body){
  let r;
  try {
    r = await fetch(api(path), {method:"POST",
      headers:{"Content-Type":"application/json"}, body:JSON.stringify(body||{})});
  } catch (e) {
    throw new Error("HELPER_STOPPED");   // wizard process is gone / terminal closed
  }
  return r.json();
}
async function refresh(){
  STATE = await (await fetch(api("/api/state"))).json();
  renderAdvanced();
  return STATE;
}

/* ---------------- guided flow ---------------- */
const STEPS_TEXT = ["Checking your computer", "Getting the latest version",
  "Installing the pieces", "Saving your settings", "Creating your profile", "Turning it on"];
const stepEls = [0,1,2,3,4,5].map(i => $("st"+i));
function setStep(i, state){
  currentStep = i;
  stepEls.forEach((el, j) => {
    el.className = j < i ? "ok" : (j === i ? state : "");
    el.querySelector(".st").textContent = j < i || state === "ok" ? "✓" : (state === "err" ? "✗" : String(j+1));
  });
}

function explain(raw){
  raw = (raw || "").toLowerCase();
  if (/could not resolve host|network is unreachable|connection refused|temporary failure|timed out|timeout|failed to connect/.test(raw))
    return {hint: "This looks like an internet problem — check your connection, then press Try again."};
  if (/authentication failed|does not appear to be a git repository|403/.test(raw) && /git|github|repository/.test(raw))
    return {hint: "GitHub didn't accept this computer — ask the person who invited you to check your access."};
  if (/no space left/.test(raw))
    return {hint: "Your disk is full — free some space, then press Try again."};
  if (/address already in use/.test(raw))
    return {cmd: "bash ~/Gacha-Companion/stop-service.sh",
      hint: "something is already using the port — copy this into a terminal, press Enter, then come back and press Try again."};
  if (/permission denied/.test(raw))
    return {hint: "a permissions problem — send the report below so it can be pinpointed."};
  return {};
}

function fail(i, friendly, raw, fixCmd){
  setStep(i, "err");
  lastFailure = {step: STEPS_TEXT[i], message: friendly, raw: (raw||"").slice(0,4000)};
  const ex = explain(raw);
  $("err-text").textContent = friendly + (ex.hint ? " — " + ex.hint : "");
  if (ex.cmd || fixCmd){
    $("fix-box").hidden = false;
    $("fix-cmd").textContent = ex.cmd || fixCmd;
  } else {
    $("fix-box").hidden = true;
  }
  if (raw) log(raw);
  $("err-panel").hidden = false;
}

async function copyReport(){
  const client = {
    step: lastFailure ? lastFailure.step : "(manual — no specific step failed)",
    message: lastFailure ? lastFailure.message : ($("err-text").textContent || "(no error message — general report)"),
    raw: lastFailure ? lastFailure.raw : "",
    errors: clientErrors.slice(-10),
    ua: navigator.userAgent,
    probe: lastProbe
  };
  let text;
  try {
    const r = await post("/api/report", client);
    text = r.report || JSON.stringify(r);
  } catch (e) {
    text = "GACHA COMPANION — PROBLEM REPORT (partial: the helper program is not answering)\\n"
      + "step: " + client.step + "\\nmessage: " + client.message + "\\n"
      + (client.raw ? "raw:\\n" + client.raw + "\\n" : "")
      + "errors: " + (client.errors.join(" | ") || "none") + "\\nUA: " + client.ua;
  }
  $("report-box").hidden = false;
  $("report-text").textContent = text;
  $("report-box").open = true;
  const ok = await copyText(text);
  const label = ok ? "Report copied ✓ — send it to whoever helps you"
                   : "copy blocked — select the text in the box below instead";
  if (!$("err-panel").hidden) $("btn-report").textContent = label;
  $("btn-report2").textContent = ok ? "Report copied ✓" : "copy blocked — text is in the box";
  setTimeout(() => { $("btn-report").textContent = "Copy problem report";
    $("btn-report2").textContent = "Something’s wrong? Copy a problem report"; }, 4000);
}

async function runGuided(){
  try { await runGuidedInner(); }
  catch (e) {
    const es = String((e && e.message) || e);
    if (es.includes("HELPER_STOPPED")){
      fail(currentStep, "The helper program has stopped — is the terminal window " +
        "where you started setup still open? If not, open a terminal, paste this, and start again:", "",
        "bash ~/Gacha-Companion/setup.sh");
    } else {
      clientErrors.push("uncaught: " + es);
      fail(currentStep, "Something unexpected happened — it's not your fault. " +
        "Copy the problem report and send it.", es);
    }
  }
}

async function runGuidedInner(){
  $("start-card").hidden = true;
  $("done-card").hidden = true;
  $("progress-card").hidden = false;
  $("err-panel").hidden = true;
  $("fix-box").hidden = true;

  // 1 · check the computer
  setStep(0, "run");
  let s = await refresh();
  if (!s.git || !s.curl){
    return fail(0, "Your computer is missing a small piece (git or curl). " +
      "Copy this into a terminal, press Enter (it may ask your password), then come back and press Try again.",
      "", "sudo apt install -y git curl");
  }
  setStep(0, "ok");

  // 2 · latest version (uv install folds in here if ever needed)
  setStep(1, "run");
  if (!s.uv.ok){
    const r = await post("/api/uv-install"); log(r.log);
    if (!r.ok) return fail(1, "We couldn't install the Python helper. " +
      "Check your internet connection, then press Try again.", r.log);
    s = await refresh();
  }
  setStep(1, "ok");

  // 3 · install pieces
  setStep(2, "run");
  const inst = await post("/api/install"); log(inst.log);
  if (!inst.ok) return fail(2, "We couldn't install the pieces. " +
    "Check your internet connection, then press Try again.", inst.log);
  setStep(2, "ok");

  // 4 · save settings (only the key is ever really new)
  setStep(3, "run");
  const key = $("f-key").value.trim();
  let base = s.env.base || "https://llm.tictac.one/v1";
  let model = s.env.model || "";
  if (!model){
    // ask the endpoint what models it has, and pick a sensible one
    const probe = await post("/api/llm-probe", {base, key});
    lastProbe = probe;
    if (probe.code === 200 && probe.models.length){
      model = probe.models.find(m => /vlm|glimmer|multimodal/i.test(m)) || probe.models[0];
    } else {
      model = "muse-glimmer-30b-vlm-128k";
    }
  }
  if (key || !s.env.key_set || !s.env.base || !s.env.model){
    const r = await post("/api/config", {base, model, key});
    if (!r.ok) return fail(3, "We couldn't save the settings. Press Try again.", r.error);
  }
  setStep(3, "ok");

  // 5 · player profile
  setStep(4, "run");
  s = await refresh();
  let playerId = null, playerName = null;
  if (s.players.length){
    playerId = s.players[0].id; playerName = s.players[0].name;
  } else {
    const name = $("f-name").value.trim() || s.default_name || "Player";
    const r = await post("/api/players/create", {name});
    if (!r.ok) return fail(4, "We couldn't create your profile. Press Try again.", r.error);
    playerId = r.player.id; playerName = r.player.display_name;
  }
  setStep(4, "ok");

  // 6 · service on
  setStep(5, "run");
  s = await refresh();
  if (!s.service.running){
    const r = await post("/api/service/start"); log(r.log);
    if (!r.ok) return fail(5, "Your companion wouldn't start. Press Try again — " +
      "if it keeps failing, copy the problem report and send it.", r.log);
  }
  setStep(5, "ok");

  await refresh();
  showDone(playerId, playerName);
}

function renderAutoUpd(){
  const on = STATE.autoupdate === "on";
  $("btn-autoupd").textContent = on ? "Automatic updates: ON — click to turn off"
                                    : "Turn on automatic updates";
  $("autoupd-msg").textContent = on
    ? "on — checks once a day, installs updates, restarts itself, and rolls back a bad update automatically"
    : "one click: checks once a day, keeps everything fresh, and relaunches the companion if it ever stops";
}

function showDone(playerId, playerName){
  $("start-card").hidden = true;
  $("progress-card").hidden = true;
  $("done-card").hidden = false;
  const s = STATE;
  if (!playerId && s.players.length){ playerId = s.players[0].id; playerName = s.players[0].name; }

  $("c-url").textContent = `http://127.0.0.1:${s.service.port}`;
  $("c-base").textContent = s.env.base || "https://llm.tictac.one/v1";
  $("c-player").textContent = playerId || "";
  const companionUrl = `http://127.0.0.1:${s.service.port}/ui`;
  $("open-companion").href = companionUrl;
  $("companion-hint").textContent = "Your companion lives at " + companionUrl + " — bookmark it.";

  $("key-reminder").hidden = s.env.key_set;
  const links = s.openwebui_port ? `http://127.0.0.1:${s.openwebui_port}` : null;
  $("owui-hint").textContent = links
    ? "We found your Open WebUI — the links below open the right pages."
    : "We couldn't find Open WebUI on this computer. Open the app first, then refresh this page.";
  $("owui-link-1").innerHTML = links ? ` &middot; <a href="${links}/admin/settings" target="_blank">open Settings</a>` : "";
  $("owui-link-2").innerHTML = links ? ` &middot; <a href="${links}/workspace/tools" target="_blank">open Tools</a>` : "";
  $("owui-link-4").innerHTML = links ? ` &middot; <a href="${links}/" target="_blank">open a chat</a>` : "";
  renderOwuiProgress();
  renderAutoUpd();
}

$("btn-go").onclick = runGuided;
$("btn-retry").onclick = runGuided;
$("btn-again").onclick = runGuided;   // re-running the guided flow = check for updates
$("btn-autoupd").onclick = async () => {
  $("autoupd-msg").textContent = "working…";
  const r = await post("/api/autoupdate/toggle");
  if (r.ok){
    await refresh();
    renderAutoUpd();
    if (r.next) $("autoupd-msg").textContent += " · next check: " + r.next;
  } else {
    $("autoupd-msg").textContent = "couldn't change it — " + (r.log || "copy a problem report");
    log(r.log || "");
  }
};
$("btn-report").onclick = copyReport;
$("btn-report2").onclick = copyReport;
$("btn-fix-copy").onclick = async () => {
  const ok = await copyText($("fix-cmd").textContent);
  $("btn-fix-copy").textContent = ok ? "copied!" : "select it";
  setTimeout(()=> $("btn-fix-copy").textContent = "copy", 1500);
};
$("btn-again").onclick = async () => {
  $("again-msg").textContent = "re-checking…";
  const s = await refresh();
  $("again-msg").textContent = "";
  showDone();
};
["f-key","f-name"].forEach(id => $(id).addEventListener("keydown", e => {
  if (e.key === "Enter") runGuided();
}));

/* done-screen extras */
document.querySelectorAll(".owcheck").forEach(cb => cb.addEventListener("change", () => {
  localStorage.setItem("owui_" + cb.closest(".owcard").dataset.ow, cb.checked ? "1" : "0");
  renderOwuiProgress();
}));
function renderOwuiProgress(){
  const cards = [...document.querySelectorAll(".owcard")];
  let done = 0;
  cards.forEach(c => {
    const checked = localStorage.getItem("owui_" + c.dataset.ow) === "1";
    c.classList.toggle("done", checked);
    c.querySelector(".owcheck").checked = checked;
    if (checked) done++;
  });
  $("owui-bar").style.width = (done / cards.length * 100) + "%";
  $("owui-progress-label").textContent = `— ${done} of ${cards.length} done`;
}
$("btn-key2").onclick = async () => {
  const k = $("f-key2").value.trim();
  if (!k) return;
  const s = STATE;
  const r = await post("/api/config", {base: s.env.base, model: s.env.model, key: k});
  if (r.ok){
    await refresh();
    $("key-reminder").hidden = true;
    msg("key2-msg", "saved ✓", "m-ok");
  } else msg("key2-msg", r.error, "m-err");
};
$("btn-shortcut").onclick = async () => {
  const r = await post("/api/desktop-shortcut");
  $("shortcut-msg").textContent = r.ok
    ? "Icon added ✓ — look for “Gacha Companion Setup” in your applications menu. If it refuses to open, right-click it once and choose “Allow launching”."
    : "couldn't add the icon — " + (r.error || "unknown error");
};

/* ---------------- copy helpers ---------------- */
async function copyText(text){
  try { await navigator.clipboard.writeText(text); return true; }
  catch (e) { /* needs user activation or permission — try the legacy path */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch (e) { return false; }
}
document.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", async () => {
  const ok = await copyText($(b.dataset.copy).textContent);
  b.textContent = ok ? "copied!" : "copy failed";
  setTimeout(()=> b.textContent="copy", 1200);
}));
$("btn-copy-tool").onclick = async () => {
  const t = await (await fetch(api("/api/toolfile"))).text();
  const ok = await copyText(t);
  if (ok){
    $("btn-copy-tool").textContent = "copied — now paste it into the tool editor";
    setTimeout(()=> $("btn-copy-tool").textContent = "copy the tool code", 2500);
  } else {
    $("btn-copy-tool").textContent = "copy blocked — code opened in the log below, select it there";
    log(t);
  }
};

/* ---------------- advanced panel ---------------- */
function badge(el, ok, yes, no){
  el.className = "badge " + (ok ? "b-ok" : "b-err");
  el.textContent = ok ? (yes||"ok") : (no||"missing");
}
function renderAdvanced(){
  const s = STATE;
  if (!s) return;
  const rows = [
    ["git", s.git], ["curl", s.curl],
    ["python " + s.python, true],
    ["uv " + (s.uv.version || ""), s.uv.ok],
    [".venv (project environment)", s.venv],
    ["git checkout", s.is_repo],
  ].map(([name, ok]) =>
    `<div class="row"><span>${name}</span>
     <span class="badge ${ok?"b-ok":"b-err"}">${ok?"ready":"missing"}</span></div>`).join("");
  const svc = `<div class="row"><span>companion service :${s.service.port}</span>
     <span class="badge ${s.service.running?"b-ok":"b-dim"}">${s.service.running?"running":"stopped"}</span></div>`;
  const owui = s.openwebui_port
    ? `<div class="row"><span>Open WebUI detected</span>
       <span class="badge b-ok">port ${s.openwebui_port}</span></div>`
    : `<div class="row"><span>Open WebUI</span>
       <span class="badge b-dim">not detected (start the Desktop app)</span></div>`;
  const au = `<div class="row"><span>automatic updates</span>
     <span class="badge ${s.autoupdate === "on" ? "b-ok" : "b-dim"}">${s.autoupdate === "on" ? "daily" : "off"}</span></div>`;
  $("sysrows").innerHTML = rows + svc + owui + au;
  badge($("sysbadge"), s.git && s.curl && s.uv.ok && s.venv, "ready", "see below");
  $("btn-uv").style.display = s.uv.ok ? "none" : "";

  if (!$("f-base2").value) $("f-base2").value = s.env.base || "https://llm.tictac.one/v1";
  if (!$("f-model").value) $("f-model").value = s.env.model || "muse-glimmer-30b-vlm-128k";
  $("svc-badge").className = "badge " + (s.service.running ? "b-ok" : "b-warn");
  $("svc-badge").textContent = s.service.running ? "running" : "stopped";
  $("svc-url").textContent = `http://127.0.0.1:${s.service.port}`;
  $("player-list").innerHTML = s.players.length
    ? s.players.map(p => `<div class="row"><span>${p.name}</span><span class="v">${p.id}</span></div>`).join("")
    : `<div class="hint">no profiles yet</div>`;
}

$("btn-uv").onclick = async () => {
  msg("install-msg", "installing uv…");
  const r = await post("/api/uv-install");
  log(r.log); msg("install-msg", r.ok?"uv installed":"uv install failed", r.ok?"m-ok":"m-err");
  refresh();
};
$("btn-install").onclick = async () => {
  msg("install-msg", "updating code and installing dependencies… (first run can take a minute)");
  const r = await post("/api/install");
  log(r.log);
  msg("install-msg", r.ok ? "installed ✓" : "failed — see log", r.ok?"m-ok":"m-err");
  refresh();
};
$("btn-probe").onclick = async () => {
  msg("llm-msg", "testing endpoint…");
  const r = await post("/api/llm-probe", {base:$("f-base2").value, key:$("f-key3").value});
  lastProbe = r;
  if (r.code === 200 && r.models.length){
    const sel = $("f-model-list");
    sel.innerHTML = r.models.map(m =>
      `<option ${m===$("f-model").value?"selected":""}>${m}</option>`).join("");
    sel.style.display = "";
    sel.onchange = () => $("f-model").value = sel.value;
    msg("llm-msg", `reachable — ${r.models.length} models loaded`, "m-ok");
  } else if (r.code === 401 || r.code === 403){
    msg("llm-msg", "reachable, but the key was rejected — check the API key", "m-warn");
  } else if (r.code === 0){
    msg("llm-msg", "could not reach the endpoint — check the URL / network", "m-warn");
  } else {
    msg("llm-msg", `endpoint answered HTTP ${r.code} (no model list)`, "m-warn");
  }
};
$("btn-save").onclick = async () => {
  const r = await post("/api/config", {base:$("f-base2").value.trim(),
    model:$("f-model").value.trim(), key:$("f-key3").value});
  if (r.ok){
    $("f-key3").value = "";
    msg("llm-msg", "saved to .env " + (r.note ? "(" + r.note + ")" : ""), "m-ok");
    refresh();
  } else msg("llm-msg", r.error, "m-err");
};
$("btn-player").onclick = async () => {
  const r = await post("/api/players/create", {name:$("f-player").value});
  if (r.ok){
    msg("player-msg", `created “${r.player.display_name}” ✓`, "m-ok");
    await refresh();
  } else msg("player-msg", r.error || "failed", "m-err");
};
$("btn-svc-start").onclick = async () => {
  msg("svc-msg", "starting…");
  const r = await post("/api/service/start"); log(r.log);
  msg("svc-msg", r.ok ? "service running ✓" : r.log || "failed", r.ok?"m-ok":"m-err");
  refresh();
};
$("btn-svc-stop").onclick = async () => {
  const r = await post("/api/service/stop"); log(r.log);
  msg("svc-msg", r.ok ? "stopped" : r.log || "failed", r.ok?"":"m-err");
  refresh();
};

/* ---------------- boot: skip to done when everything's ready ----------- */
(async () => {
  const s = await refresh();
  const ready = s.venv && s.players.length && s.service.running;
  if (ready && s.env.key_set){
    showDone();
  } else {
    if (s.players.length) $("f-name").value = s.players[0].name;
    else if (s.default_name) $("f-name").value = "";
    if (s.env.key_set) $("key-hint").textContent = "a key is already saved — paste a new one only if it changed";
  }
})();
</script></body></html>
"""


# --------------------------------------------------------------- main

PANEL_LOCK = REPO / ".panel.json"

STALE_PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gacha Companion — link expired</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#0b0f14;color:#dbe4ee;font:16px/1.6 system-ui,sans-serif;text-align:center}
  .card{max-width:30rem;padding:2.2rem;background:#121822;border:1px solid #1f2b3a;border-radius:14px}
  h1{font-size:1.25rem;margin:0 0 .6rem}
  p{margin:.4rem 0;color:#7b8ba0}
  b{color:#22d3ee}
</style></head><body>
<div class="card">
  <h1>This helper link has expired</h1>
  <p>Each opening of the Gacha Companion helper uses a fresh private address,
  so old tabs and bookmarks stop working &mdash; that's the privacy working as intended.</p>
  <p><b>Close this tab</b> and click the <b>Gacha Companion</b> icon in your applications menu again.</p>
</div>
</body></html>
"""


def running_panel_url() -> str | None:
    """URL of an already-running panel, or None."""
    try:
        info = json.loads(PANEL_LOCK.read_text())
        if Path(f"/proc/{info['pid']}").exists():
            return info["url"]
    except Exception:
        pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Gacha Companion setup wizard")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--panel", action="store_true",
                    help="open the day-to-day control panel")
    ap.add_argument("--report", action="store_true",
                    help="print a redacted diagnostic report and exit")
    args = ap.parse_args()

    if not (REPO / "pyproject.toml").exists():
        print("run me from inside the Gacha-Companion folder: cd Gacha-Companion && python3 setup-gui.py")
        return 1

    if args.report:
        print("copy everything below and send it back:", file=sys.stderr)
        print(build_report({"step": "(terminal report — run by hand)",
                            "message": "", "ua": "terminal"}))
        return 0

    if args.panel:
        if url := running_panel_url():
            print(f"Gacha Companion panel already open: {url}", flush=True)
            if not args.no_browser:
                threading_timer_launch(url + "panel/")
            return 0

    token = secrets.token_urlsafe(10)
    wiz = Wizard(token)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(wiz))
    port = httpd.server_address[1]
    url = f"http://127.0.0.1:{port}/{token}/"
    if args.panel:
        PANEL_LOCK.write_text(json.dumps({"pid": os.getpid(), "port": port,
                                          "token": token, "url": url}))
        print("Gacha Companion control panel", flush=True)
        print(f"  open:  {url}panel/", flush=True)
        print("  exit:  Ctrl+C here when you are done", flush=True)
        if not args.no_browser:
            threading_timer_launch(url + "panel/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            PANEL_LOCK.unlink(missing_ok=True)
            print("\nbye — reopen with “Gacha Companion” from your menu any time.")
        return 0
    print("Gacha Companion setup wizard", flush=True)
    print(f"  open:  {url}", flush=True)
    print("  exit:  Ctrl+C here when you are done", flush=True)
    if not args.no_browser:
        threading_timer_launch(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye — everything you saved is kept; re-run any time.")
    return 0


def threading_timer_launch(url: str) -> None:
    import threading
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()


if __name__ == "__main__":
    sys.exit(main())
