"""Installable web app: manifest, service worker, offline page and versioned static URLs.

Static files are requested as /static/<file>?v=<version>. The version is a hash of every
static file's size and modification time, so it changes whenever any of them does. The
service worker embeds the same version, which is how an installed app notices an update.
"""

import hashlib
import json
import os

from flask import Response, current_app, has_request_context, render_template, request, url_for

from pages import pages_bp

APP_NAME = "Personal Finance Suite"
SHORT_NAME = "Finance"
THEME = "#0f172a"
BACKGROUND = "#f6f7fb"
SKIP_DIRS = {"src"}  # build inputs, never served to the browser


def _static_files() -> list[str]:
    root = current_app.static_folder
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            out.append(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return out


def _compute_version() -> str:
    root = current_app.static_folder
    h = hashlib.sha1()
    for rel in _static_files():
        st = os.stat(os.path.join(root, rel))
        h.update(f"{rel}:{st.st_size}:{st.st_mtime_ns};".encode())
    return h.hexdigest()[:12]


def asset_version() -> str:
    """Computed once per request (a page asks for it about ten times)."""
    if not has_request_context():
        return _compute_version()
    version = getattr(request, "_asset_version", None)
    if version is None:
        version = request._asset_version = _compute_version()
    return version


@pages_bp.app_template_global()
def asset(filename: str) -> str:
    return url_for("static", filename=filename, v=asset_version())


@pages_bp.route("/manifest.webmanifest")
def manifest():
    icon = lambda name, size, purpose="any", kind="image/png": {  # noqa: E731
        "src": asset(f"icons/{name}"), "sizes": size, "type": kind, "purpose": purpose}
    data = {
        "id": "/",
        "name": APP_NAME,
        "short_name": SHORT_NAME,
        "description": "Your plan, balances and forecast, kept on machines you control.",
        "lang": "en",
        "start_url": "/overview",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "theme_color": THEME,
        "background_color": BACKGROUND,
        "categories": ["finance", "productivity"],
        "icons": [
            icon("icon-192.png", "192x192"),
            icon("icon-512.png", "512x512"),
            icon("maskable-192.png", "192x192", "maskable"),
            icon("maskable-512.png", "512x512", "maskable"),
            icon("favicon.svg", "any", kind="image/svg+xml"),
        ],
        "shortcuts": [
            {"name": "Update balances", "short_name": "Check-in", "url": "/balances?checkin=1",
             "description": "Walk through the balances that need a new value",
             "icons": [icon("icon-96.png", "96x96")]},
            {"name": "Add a one-off entry", "short_name": "Add entry", "url": "/plan?new=entry",
             "icons": [icon("icon-96.png", "96x96")]},
            {"name": "Insights", "url": "/insights", "icons": [icon("icon-96.png", "96x96")]},
        ],
    }
    resp = Response(json.dumps(data, indent=2), mimetype="application/manifest+json")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@pages_bp.route("/sw.js")
def service_worker():
    version = asset_version()
    precache = [url_for("static", filename=f, v=version) for f in _static_files()]
    body = render_template("sw.js", version=version, precache=precache, offline_url=url_for("pages.offline"))
    resp = Response(body, mimetype="text/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@pages_bp.route("/offline")
def offline():
    return render_template("offline.html")


@pages_bp.route("/favicon.ico")
def favicon():
    return current_app.send_static_file("icons/favicon-32.png")
