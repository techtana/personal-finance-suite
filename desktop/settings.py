"""Where the desktop app keeps its files, and its few settings.

Everything lives under one folder that survives reinstalling the app:
    %LOCALAPPDATA%\\PersonalFinance        (Windows)
    ~/.local/share/personal-finance        (elsewhere)
holding settings.json, tray.log and, for the local mode only, data/finance.db.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "Personal Finance"
LOCAL_PORT = 5057
CONTROL_PORT = 47657   # a second launch tells the running tray to open the app, then exits

DEFAULTS = {
    "mode": "server",          # server: open the private cloud server | local: run the app on this computer
    "server_url": "",          # https://finance.<tailnet>.ts.net; found through Tailscale when empty
    "share_ai": True,          # run the home AI runner in the background (server mode only)
    "runner_name": "home computer",
}


def data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "PersonalFinance"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "personal-finance"


def settings_file() -> Path:
    return data_dir() / "settings.json"


def load() -> dict:
    try:
        stored = json.loads(settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def save(values: dict) -> dict:
    merged = {**load(), **{k: v for k, v in values.items() if k in DEFAULTS}}
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    tmp.replace(path)
    return merged


def server_from_tailscale(status_json: str | None = None) -> str:
    """https://finance.<tailnet>.ts.net when a device named "finance" is on this computer's tailnet, else ""."""
    if status_json is None:
        exe = shutil.which("tailscale")
        if not exe:
            return ""
        try:
            status_json = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=10,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.SubprocessError):
            return ""
    try:
        status = json.loads(status_json or "{}")
    except ValueError:
        return ""
    for peer in (status.get("Peer") or {}).values():
        name = (peer.get("DNSName") or "").rstrip(".")
        if name.split(".")[0] == "finance" and name.endswith(".ts.net"):
            return f"https://{name}"
    return ""


def startup_shortcut() -> Path:
    """The Windows sign-in entry (exists only when "Start when I sign in" is on)."""
    return Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup" / f"{APP_NAME}.lnk"


def app_url(values: dict) -> str:
    if values.get("mode") == "local":
        return f"http://127.0.0.1:{LOCAL_PORT}"
    return (values.get("server_url") or "").rstrip("/")
