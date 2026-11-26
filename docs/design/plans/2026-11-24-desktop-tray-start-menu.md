# Windows desktop app: Start menu entry and tray

**Status:** done, PR #10 (merged 2026-11-24). The tray menu items and local mode were not tried by hand.

## Goal

Open Finance from the Start menu like any other app, and share this PC's AI with the server while the PC is on.

## Approach

- `install-desktop.cmd` runs `desktop/install.py`. It copies the app out of the checkout to `%LOCALAPPDATA%\Programs\PersonalFinance` and builds its own Python environment there from the signed python.org Python, which Smart App Control accepts.
- The tray runs as `Finance.exe`, a renamed `pythonw`, so Task Manager shows "Finance".
- It opens the private server found through Tailscale (a device named `finance`), or a copy that runs on this PC with its own data.
- It runs the home AI runner in a thread while **Share this PC's AI with the server** is ticked.
- One tray at a time: a second start only asks the first to open the window.
- `--autostart` adds a Startup shortcut; `--uninstall` removes the app and the shortcuts but never the data.

## Left out

Other operating systems. Elsewhere you run `python desktop/tray.py --open`.
