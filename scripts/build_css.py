"""Compile static/build/tailwind.css from the class names used in templates/ and static/*.js.

Needs Node.js (npx fetches the pinned Tailwind CLI on first run). The output is committed,
so running the app never needs Node.

    python scripts/build_css.py           # minified build
    python scripts/build_css.py --watch   # rebuild while editing templates
"""

import shutil
import subprocess
import sys
from pathlib import Path

TAILWIND = "tailwindcss@3.4.19"
ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    npx = shutil.which("npx")
    if not npx:
        print("npx not found: install Node.js to rebuild the stylesheet.", file=sys.stderr)
        return 1
    cmd = [npx, "--yes", TAILWIND, "-c", "tailwind.config.js", "-i", "static/src/tailwind.css",
           "-o", "static/build/tailwind.css", "--minify"]
    if "--watch" in sys.argv:
        cmd.append("--watch")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
