"""Install Personal Finance as a desktop app on Windows: a Start menu entry and a tray icon.

    install-desktop.cmd                 (double-click; runs this with the signed python.org Python)
    py -3 desktop\\install.py [--autostart] [--no-launch]

What it does:
  1. Copies the app into its own folder, %LOCALAPPDATA%\\Programs\\PersonalFinance, so the
     shortcut keeps working when this checkout moves or changes.
  2. Gives that copy its own Python environment, made from the Python running this script
     (a python.org Python is signed, which Smart App Control requires), and installs what the
     app and the tray need.
  3. Writes the program icon, the Start menu entry and, with --autostart, a sign-in entry.
  4. Starts the tray.

Run it again to update the installed app. Settings and local data are in
%LOCALAPPDATA%\\PersonalFinance and are never touched. Uninstall: python desktop\\install.py --uninstall
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOURCE))

from desktop import settings as cfg  # noqa: E402

PROGRAM = "Finance.exe"     # a renamed pythonw.exe, so Task Manager shows "Finance"
DESKTOP_REQUIREMENTS = ["pystray>=0.19", "pillow>=10"]
COPY_SKIP = {".git", ".venv", "venv", ".claude", "instance", "tests", "docs", "deploy", "skill-updates",
             "node_modules", "__pycache__", ".pytest_cache", ".env"}


def app_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return Path(os.environ.get("FINANCE_APP_HOME") or base / "Programs" / "PersonalFinance")


def menu_shortcut() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs" / f"{cfg.APP_NAME}.lnk"


def program() -> Path:
    return app_dir() / ".venv" / "Scripts" / PROGRAM


def icon_file() -> Path:
    return app_dir() / "finance.ico"


def _ignore(directory, names):
    return [n for n in names if n in COPY_SKIP or n.endswith((".pyc", ".lnk"))]


def copy_app(target: Path) -> None:
    """Replace the installed code with this checkout's, keeping the installed environment."""
    target.mkdir(parents=True, exist_ok=True)
    for entry in target.iterdir():
        if entry.name in (".venv", "finance.ico"):
            continue
        shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
    for entry in SOURCE.iterdir():
        if entry.name in COPY_SKIP or entry.suffix == ".lnk":
            continue
        dest = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest, ignore=_ignore)
        else:
            shutil.copy2(entry, dest)


def make_environment(target: Path) -> None:
    venv = target / ".venv"
    py = venv / "Scripts" / "python.exe"
    if not py.exists():
        print(f"Making the app's Python environment from {sys.executable}...")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    print("Installing what the app needs (a minute or two the first time)...")
    subprocess.run([str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                    "-r", str(target / "requirements.txt"), *DESKTOP_REQUIREMENTS], check=True)
    # The tray runs as Finance.exe: pythonw.exe under another name, next to it so it finds the environment.
    shutil.copy2(venv / "Scripts" / "pythonw.exe", venv / "Scripts" / PROGRAM)


def make_icon(target: Path) -> Path:
    """finance.ico from the app's own icon, drawn by the app's environment (it has Pillow; this Python may not)."""
    ico = target / "finance.ico"
    code = ("import sys; from PIL import Image; Image.open(sys.argv[1]).save(sys.argv[2], "
            "sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])")
    subprocess.run([str(target / ".venv" / "Scripts" / "python.exe"), "-c", code,
                    str(target / "static" / "icons" / "icon-512.png"), str(ico)], check=True)
    return ico


def make_shortcut(path: Path, open_on_start: bool = True) -> Path:
    """A Windows shortcut that starts the tray (and opens the app when `open_on_start`)."""
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK_PATH); "
          "$s.TargetPath = $env:LNK_TARGET; $s.Arguments = $env:LNK_ARGS; $s.WorkingDirectory = $env:LNK_DIR; "
          "$s.IconLocation = \"$env:LNK_ICON,0\"; $s.Description = $env:LNK_DESC; $s.WindowStyle = 7; $s.Save()")
    args = '"' + str(app_dir() / "desktop" / "tray.py") + '"' + (" --open" if open_on_start else "")
    env = {**os.environ, "LNK_PATH": str(path), "LNK_TARGET": str(program()), "LNK_ARGS": args,
           "LNK_DIR": str(app_dir()), "LNK_ICON": str(icon_file()),
           "LNK_DESC": "Personal Finance: open the app; the tray keeps this PC's AI available to it"}
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, check=True,
                   capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return path


def stop_running_tray() -> None:
    """The installed files are about to be replaced: end a running tray first."""
    if sys.platform != "win32":
        return
    subprocess.run(["taskkill", "/IM", PROGRAM, "/F"], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def start_tray() -> None:
    subprocess.Popen([str(program()), str(app_dir() / "desktop" / "tray.py"), "--open"], cwd=str(app_dir()),
                     close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


def uninstall() -> None:
    stop_running_tray()
    for lnk in (menu_shortcut(), cfg.startup_shortcut()):
        lnk.unlink(missing_ok=True)
    shutil.rmtree(app_dir(), ignore_errors=True)
    print(f"Removed the app and its shortcuts. Settings and local data are still in {cfg.data_dir()}.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Install Personal Finance as a desktop app (Start menu + tray).")
    parser.add_argument("--autostart", action="store_true", help="also start the tray when you sign in")
    parser.add_argument("--no-launch", action="store_true", help="don't start the tray afterwards")
    parser.add_argument("--uninstall", action="store_true", help="remove the app and its shortcuts")
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("The installer is for Windows. Elsewhere, run: python desktop/tray.py --open")
        return 1
    if args.uninstall:
        uninstall()
        return 0

    target = app_dir()
    stop_running_tray()
    print(f"Copying the app to {target}...")
    copy_app(target)
    make_environment(target)
    make_icon(target)
    print(f"Start menu entry: {make_shortcut(menu_shortcut())}")
    if args.autostart:
        print(f"Starts at sign-in: {make_shortcut(cfg.startup_shortcut(), open_on_start=False)}")
    s = cfg.load()
    if s["mode"] == "server" and not s["server_url"]:
        found = cfg.server_from_tailscale()
        if found:
            cfg.save({"server_url": found})
            print(f"Found your finance server through Tailscale: {found}")
        else:
            print("No finance server found on your tailnet yet; the tray looks again when you open the app.")
    if not args.no_launch:
        start_tray()
        print("Started. Look for the Personal Finance icon in the notification area.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
