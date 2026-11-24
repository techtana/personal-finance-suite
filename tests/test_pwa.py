"""Installable web app: manifest, service worker, offline page, icons and the page shell."""

import re
from pathlib import Path

import pytest
from PIL import Image

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_manifest_meets_install_requirements(client):
    res = client.get("/manifest.webmanifest")
    assert res.status_code == 200 and res.mimetype == "application/manifest+json"
    m = res.get_json()
    assert m["name"] and m["short_name"] and m["start_url"] == "/overview" and m["scope"] == "/"
    assert m["display"] == "standalone" and m["theme_color"] and m["background_color"]
    sizes = {(i["sizes"], i["purpose"]) for i in m["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= sizes
    for icon in m["icons"] + [i for s in m["shortcuts"] for i in s["icons"]]:
        assert client.get(icon["src"]).status_code == 200, icon["src"]
    for shortcut in m["shortcuts"]:
        assert client.get(shortcut["url"]).status_code == 200


@pytest.mark.parametrize("name,size", [("icon-192.png", 192), ("icon-512.png", 512), ("maskable-512.png", 512),
                                       ("maskable-192.png", 192), ("apple-touch-icon.png", 180), ("icon-96.png", 96)])
def test_icons_have_the_declared_size(name, size):
    with Image.open(STATIC / "icons" / name) as img:
        assert img.size == (size, size)
        if name.startswith(("maskable", "apple")):
            # Full-bleed: the platform masks it, so no transparent corners.
            assert img.convert("RGBA").getpixel((0, 0))[3] == 255


def test_service_worker_is_served_from_the_root_and_never_cached(client):
    res = client.get("/sw.js")
    assert res.status_code == 200 and res.mimetype == "text/javascript"
    assert res.headers["Cache-Control"] == "no-cache" and res.headers["Service-Worker-Allowed"] == "/"
    body = res.get_data(as_text=True)
    assert "'/api/'" in body, "financial data must bypass the cache"
    precache = re.search(r"const PRECACHE = (\[.*?\]);", body).group(1)
    urls = re.findall(r'"([^"]+)"', precache)
    assert any("vendor/alpine.min.js" in u for u in urls) and any("build/tailwind.css" in u for u in urls)
    assert not any("/src/" in u for u in urls)
    for url in urls:
        assert client.get(url).status_code == 200, url


def test_asset_version_changes_when_a_static_file_changes(client, tmp_path):
    before = re.search(r'const VERSION = "(\w+)"', client.get("/sw.js").get_data(as_text=True)).group(1)
    probe = STATIC / "zz-version-probe.txt"
    try:
        probe.write_text("x", encoding="utf-8")
        after = re.search(r'const VERSION = "(\w+)"', client.get("/sw.js").get_data(as_text=True)).group(1)
    finally:
        probe.unlink()
    assert before != after


def test_offline_page_stands_alone(client):
    res = client.get("/offline")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Try again" in html and "/api/" not in html and "x-data" not in html


def test_favicon(client):
    assert client.get("/favicon.ico").status_code == 200


def test_pages_load_everything_from_this_server(client):
    html = client.get("/overview").get_data(as_text=True)
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html
    assert 'name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"' in html
    assert 'rel="apple-touch-icon"' in html and 'name="theme-color"' in html
    # No third-party scripts or styles: works offline and leaks nothing to a CDN.
    assert not re.search(r'(src|href)="https?://', html)
    for ref in re.findall(r'(?:src|href)="(/static/[^"]+)"', html):
        assert "?v=" in ref and client.get(ref).status_code == 200, ref


def test_phone_navigation_is_present(client):
    html = client.get("/plan").get_data(as_text=True)
    tabbar = html[html.index('class="tabbar"'):html.index("</nav>", html.index('class="tabbar"'))]
    assert [t for t in ("/overview", "/forecast", "/plan", "/balances", "/insights") if f'href="{t}"' in tabbar] == \
           ["/overview", "/forecast", "/plan", "/balances", "/insights"]
    assert 'aria-current="page"' in tabbar and "Open menu" in html and "Skip to content" in html


def test_compiled_stylesheet_covers_template_classes():
    css = (STATIC / "build" / "tailwind.css").read_text(encoding="utf-8")
    # A few classes only the new templates use; if these are missing the CSS needs `python scripts/build_css.py`.
    for cls in ("max-h-\\[300px\\]", "min-w-\\[130px\\]", "text-emerald-700", "sm\\:grid-cols-3"):
        assert "." + cls in css, cls
