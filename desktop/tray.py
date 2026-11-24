"""Personal Finance in the tray.

Started by the Start menu entry (and at sign-in, if chosen). It stays in the notification area
and does two things in the background:

  - Opens the app: the private cloud server (found through Tailscale), or, in local mode, a copy
    of the app it runs on this computer (127.0.0.1 only).
  - Shares this computer's AI with the server: it runs home_runner, which collects AI work from
    the server and answers it with the local model. The server never connects to this computer.

Double-click the icon (or start it again from the Start menu) to open the app.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from desktop import settings as cfg  # noqa: E402

LOG = cfg.data_dir() / "tray.log"

if __name__ == "__main__" and (sys.stdout is None or not sys.stdout.isatty()):
    # pythonw has no console: keep a log, opened before the heavier imports so their errors land in it.
    LOG.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)

import pystray  # noqa: E402
from PIL import Image  # noqa: E402

ICON_FILE = ROOT / "static" / "icons" / "icon-192.png"
BROWSERS = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
]


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


# ── one tray at a time ────────────────────────────────────────────────────────

def tell_running_tray(command: str = "open") -> bool:
    """True if a tray is already running (and has been told to `command`)."""
    try:
        with socket.create_connection(("127.0.0.1", cfg.CONTROL_PORT), timeout=1) as s:
            s.sendall(command.encode())
            return True
    except OSError:
        return False


def listen_for_commands(on_command) -> socket.socket | None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", cfg.CONTROL_PORT))
    except OSError:
        return None
    srv.listen(4)

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(2)
                try:
                    on_command(conn.recv(32).decode(errors="ignore").strip())
                except OSError:
                    pass

    threading.Thread(target=loop, name="control", daemon=True).start()
    return srv


# ── opening the app ───────────────────────────────────────────────────────────

def open_window(url: str) -> None:
    """An app window (no tabs or address bar) in Edge or Chrome, else the default browser."""
    for exe in BROWSERS:
        if exe.is_file():
            subprocess.Popen([str(exe), f"--app={url}"], close_fds=True,
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            return
    webbrowser.open(url)


def reachable(url: str, timeout: float = 6) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── the tray ──────────────────────────────────────────────────────────────────

class Tray:
    def __init__(self):
        self.settings = cfg.load()
        if self.settings["mode"] == "server" and not self.settings["server_url"]:
            found = cfg.server_from_tailscale()
            if found:
                self.settings = cfg.save({"server_url": found})
                log(f"found the server through Tailscale: {found}")
        self.runner_status: dict = {}
        self.runner_stop: threading.Event | None = None
        self.local_server = None
        self.server_up: bool | None = None
        self.icon = pystray.Icon("personal-finance", Image.open(ICON_FILE), cfg.APP_NAME, menu=self.menu())

    # state shown in the menu
    def where_text(self, _=None) -> str:
        s = self.settings
        if s["mode"] == "local":
            return "Running on this computer" if self.local_server else "Local app: starting"
        if not s["server_url"]:
            return "No server set (Tailscale finds it when connected)"
        host = s["server_url"].split("//")[-1].split(".")[0]
        state = {True: "reachable", False: "not reachable (is Tailscale connected?)", None: "checking"}[self.server_up]
        return f"Server {host}: {state}"

    def ai_text(self, _=None) -> str:
        if self.settings["mode"] != "server":
            return "AI: used directly by the local app"
        if not self.settings["share_ai"]:
            return "This PC's AI: not shared"
        st = self.runner_status
        if st.get("connected"):
            return f"This PC's AI: shared, {st.get('jobs', 0)} request(s) answered"
        return "This PC's AI: waiting for the server"

    def menu(self) -> pystray.Menu:
        server = lambda item: self.settings["mode"] == "server"  # noqa: E731
        return pystray.Menu(
            pystray.MenuItem(f"Open {cfg.APP_NAME}", lambda *_: self.open_app(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self.where_text, None, enabled=False),
            pystray.MenuItem(self.ai_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Share this PC's AI with the server", lambda *_: self.toggle_ai(),
                             checked=lambda item: self.settings["share_ai"], visible=server),
            pystray.MenuItem("Run the app on this computer instead", lambda *_: self.toggle_mode(),
                             checked=lambda item: self.settings["mode"] == "local"),
            pystray.MenuItem("Start when I sign in", lambda *_: self.toggle_autostart(),
                             checked=lambda item: autostart_enabled(), visible=sys.platform == "win32"),
            pystray.MenuItem("Open the log", lambda *_: os.startfile(LOG) if hasattr(os, "startfile") else None,
                             visible=LOG.exists()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda *_: self.quit()),
        )

    def refresh(self):
        try:
            self.icon.update_menu()
        except Exception:  # the icon may be closing
            pass

    # actions
    def open_app(self):
        url = cfg.app_url(self.settings)
        if not url:
            found = cfg.server_from_tailscale()
            if found:
                self.settings = cfg.save({"server_url": found})
                url = found
        if not url:
            self.icon.notify("No server found. Connect Tailscale, or choose \"Run the app on this computer instead\".",
                             cfg.APP_NAME)
            return
        if self.settings["mode"] == "server" and not reachable(url):
            self.server_up = False
            self.refresh()
            self.icon.notify("Can't reach the finance server. Check that Tailscale is connected.", cfg.APP_NAME)
            return
        open_window(url)

    def toggle_ai(self):
        self.settings = cfg.save({"share_ai": not self.settings["share_ai"]})
        self.apply()

    def toggle_mode(self):
        self.settings = cfg.save({"mode": "server" if self.settings["mode"] == "local" else "local"})
        if self.settings["mode"] == "local":
            self.icon.notify("The app now runs on this computer, with its own data, separate from the server.",
                             cfg.APP_NAME)
        self.apply()

    def toggle_autostart(self):
        set_autostart(not autostart_enabled())
        self.refresh()

    def quit(self):
        if self.runner_stop:
            self.runner_stop.set()
        self.icon.stop()

    # background work
    def apply(self):
        """Start or stop the runner and the local app to match the settings."""
        s = self.settings
        want_runner = s["mode"] == "server" and s["share_ai"] and bool(s["server_url"])
        if want_runner and not self.runner_stop:
            self.start_runner()
        elif not want_runner and self.runner_stop:
            self.runner_stop.set()
            self.runner_stop = None
            self.runner_status = {}
        if s["mode"] == "local" and not self.local_server:
            self.start_local_app()
        elif s["mode"] != "local" and self.local_server:
            self.local_server.close()
            self.local_server = None
        self.refresh()

    def start_runner(self):
        import home_runner

        client = home_runner.local_client()
        if not client.enabled:
            log(f"AI runner not started: {client.blocked_reason}")
            return
        stop = threading.Event()
        self.runner_stop = stop
        server = home_runner.Server(self.settings["server_url"], os.environ.get("AI_RUNNER_TOKEN", ""))

        def run():
            log(f"sharing this PC's AI ({client.model}) with {self.settings['server_url']}")
            home_runner.serve(server, client, self.settings["runner_name"], log=log, stop=stop,
                              status=self.runner_status)

        threading.Thread(target=run, name="home-runner", daemon=True).start()

    def start_local_app(self):
        """The whole app on 127.0.0.1, with its own database in the data folder."""
        data = cfg.data_dir() / "data"
        data.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("FINANCE_DB_PATH", str(data / "finance.db"))
        os.environ.setdefault("IMPORT_STORAGE_DIR", str(data / "imports"))
        os.environ.setdefault("FLASK_ENV", "production")
        os.environ.setdefault("SECRET_KEY", _local_secret(data))

        def run():
            from waitress import create_server

            from app import create_app

            self.local_server = create_server(create_app(), host="127.0.0.1", port=cfg.LOCAL_PORT, threads=8)
            log(f"local app on http://127.0.0.1:{cfg.LOCAL_PORT}")
            self.refresh()
            self.local_server.run()

        threading.Thread(target=run, name="local-app", daemon=True).start()

    def watch(self):
        """Every minute: is the server reachable, and what to show."""
        while True:
            if self.settings["mode"] == "server" and self.settings["server_url"]:
                self.server_up = reachable(self.settings["server_url"])
            self.refresh()
            time.sleep(60)

    def run(self, open_now: bool):
        def setup(icon):
            icon.visible = True
            self.apply()
            threading.Thread(target=self.watch, name="watch", daemon=True).start()
            if open_now:
                threading.Thread(target=self.open_app, daemon=True).start()

        self.icon.run(setup=setup)


def _local_secret(data: Path) -> str:
    path = data / "secret_key"
    if not path.exists():
        import secrets

        path.write_text(secrets.token_hex(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()


# ── start at sign-in (Windows) ────────────────────────────────────────────────

def autostart_enabled() -> bool:
    return sys.platform == "win32" and cfg.startup_shortcut().exists()


def set_autostart(on: bool) -> None:
    from desktop import install

    if on:
        install.make_shortcut(cfg.startup_shortcut(), open_on_start=False)
    else:
        cfg.startup_shortcut().unlink(missing_ok=True)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    open_now = "--open" in argv
    if tell_running_tray("open" if open_now else "noop"):
        return 0
    tray = Tray()
    if listen_for_commands(lambda cmd: cmd == "open" and tray.open_app()) is None:
        return 0  # another tray took the port a moment ago
    log("tray started")
    try:
        tray.run(open_now)
    except Exception:
        traceback.print_exc()
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
