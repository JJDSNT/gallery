"""gallery — browse a folder of photos by month, in your browser.

Reads the date stored inside each photo (EXIF), groups the photos by year
and month, and serves a small website on your own computer. Nothing is sent
anywhere and the photos are never modified: thumbnails and the index live in
the `.cache` folder next to this file.

Usage:
    python gallery.py /path/to/photos
    python gallery.py /path/to/photos --port 8080
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - message for people running it bare
    sys.exit(
        "gallery needs the Pillow library to read photos.\n"
        "Install it with:  pip install -r requirements.txt"
    )

# ---------------------------------------------------------------- settings
# The things people usually want to change live here.

TITLE = "My photos"
THUMB_SIZE = 320          # thumbnail size, in pixels
NEWEST_FIRST = False      # True shows the most recent months first
HOST = "127.0.0.1"        # only this computer can open the gallery
DEFAULT_PORT = 8000

PHOTO_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".png": "image/png", ".webp": "image/webp"}
UNSUPPORTED = {".heic", ".heif", ".raw", ".cr2", ".nef", ".dng"}

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

CACHE = Path(__file__).resolve().parent / ".cache"

# EXIF tags: DateTimeOriginal lives in the Exif sub-IFD; DateTime in the main one.
EXIF_IFD, DATETIME_ORIGINAL, DATETIME = 0x8769, 36867, 306


# ---------------------------------------------------------------- reading
def photo_date(path: Path) -> datetime | None:
    """The moment the photo was taken, as recorded by the camera, if any.

    File dates are not used: copying a folder resets them, and a gallery
    that puts ten years of photos in the month you copied them is worse
    than one that admits it does not know.
    """
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            raw = exif.get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL) or exif.get(DATETIME)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip("\x00 ")[:19], "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def find_photos(root: Path) -> tuple[list[Path], int]:
    """Every supported photo under `root`, and how many were skipped."""
    found, skipped = [], 0
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            ext = Path(name).suffix.lower()
            if ext in PHOTO_TYPES:
                found.append(Path(folder) / name)
            elif ext in UNSUPPORTED:
                skipped += 1
    return found, skipped


class Library:
    """The photos of one folder, indexed by month."""

    def __init__(self, root: Path, rescan: bool = False, quiet: bool = False):
        self.root = root.resolve()
        self.quiet = quiet
        paths, self.skipped = find_photos(self.root)
        known = {} if rescan else self._load_index()
        self.photos: list[dict] = []
        for n, path in enumerate(paths, 1):
            st = path.stat()
            key = str(path)
            entry = known.get(key)
            if not entry or entry["mtime"] != st.st_mtime or entry["size"] != st.st_size:
                taken = photo_date(path)
                entry = {"mtime": st.st_mtime, "size": st.st_size,
                         "date": taken.isoformat() if taken else None}
            self.photos.append({"path": key, **entry})
            if not quiet and n % 500 == 0:
                print(f"  read {n} of {len(paths)} photos...", flush=True)
        self._save_index()
        self.photos.sort(key=lambda p: (p["date"] is None, p["date"] or "", p["path"]))
        self.months = self._group()

    # The index only saves time on the next start; losing it loses nothing.
    def _index_file(self) -> Path:
        digest = hashlib.sha1(str(self.root).encode()).hexdigest()[:12]
        return CACHE / f"index-{digest}.json"

    def _load_index(self) -> dict:
        try:
            data = json.loads(self._index_file().read_text("utf-8"))
            return {p["path"]: p for p in data["photos"]}
        except (OSError, ValueError, KeyError):
            return {}

    def _save_index(self) -> None:
        CACHE.mkdir(exist_ok=True)
        data = {"root": str(self.root), "photos": self.photos}
        self._index_file().write_text(json.dumps(data), "utf-8")

    def _group(self) -> dict[str, list[int]]:
        months: dict[str, list[int]] = {}
        for i, p in enumerate(self.photos):
            months.setdefault(p["date"][:7] if p["date"] else "undated", []).append(i)
        return months

    def month_keys(self) -> list[str]:
        dated = sorted((k for k in self.months if k != "undated"), reverse=NEWEST_FIRST)
        return dated + (["undated"] if "undated" in self.months else [])


def month_label(key: str) -> str:
    if key == "undated":
        return "No date"
    year, month = key.split("-")
    return f"{MONTHS[int(month) - 1]} {year}"


def thumbnail(photo: dict) -> Path:
    """A small JPEG of the photo, made once and kept in the cache."""
    name = hashlib.sha1(f"{photo['path']}|{photo['mtime']}|{THUMB_SIZE}".encode()).hexdigest()
    out = CACHE / "thumbs" / f"{name}.jpg"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(photo["path"]) as im:
            im.draft("RGB", (THUMB_SIZE * 2, THUMB_SIZE * 2))  # JPEG: decode already reduced
            im = ImageOps.exif_transpose(im)
            im.thumbnail((THUMB_SIZE, THUMB_SIZE))
            tmp = out.with_suffix(".tmp")
            im.convert("RGB").save(tmp, "JPEG", quality=82)
            tmp.replace(out)
    return out


# ---------------------------------------------------------------- pages
STYLE = f"""
body {{ margin: 0; font-family: system-ui, sans-serif; background: #16181b; color: #e8e6e3; }}
header {{ padding: 20px 24px; border-bottom: 1px solid #2a2d31; }}
header a {{ color: inherit; text-decoration: none; }}
h1 {{ margin: 0; font-size: 22px; }}
h2 {{ margin: 28px 24px 12px; font-size: 18px; color: #b9b6b1; }}
.grid {{ display: grid; gap: 8px; padding: 0 24px 24px;
         grid-template-columns: repeat(auto-fill, minmax({THUMB_SIZE // 2}px, 1fr)); }}
.grid a {{ display: block; color: inherit; text-decoration: none; }}
.grid img {{ width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; background: #22252a; }}
.label {{ font-size: 14px; padding: 6px 2px; }}
.count {{ color: #8d8a85; }}
.viewer {{ text-align: center; padding: 16px; }}
.viewer img {{ max-width: 100%; max-height: 80vh; }}
nav {{ padding: 12px 24px; display: flex; gap: 16px; }}
nav a {{ color: #9ec1ff; }}
.note {{ padding: 0 24px; color: #8d8a85; }}
"""


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{STYLE}</style></head>
<body><header><h1><a href="/">{html.escape(TITLE)}</a></h1></header>
{body}</body></html>""".encode("utf-8")


def home_page(lib: Library) -> bytes:
    if not lib.photos:
        return page(TITLE, '<p class="note">No photos found in this folder.</p>')
    parts, year = [], None
    for key in lib.month_keys():
        this_year = key[:4] if key != "undated" else "undated"
        if this_year != year:
            if year is not None:
                parts.append("</div>")
            heading = "Photos without a date" if this_year == "undated" else this_year
            parts.append(f'<h2>{heading}</h2><div class="grid">')
            year = this_year
        ids = lib.months[key]
        parts.append(
            f'<a href="/month/{key}"><img src="/thumb/{ids[0]}" loading="lazy" alt="">'
            f'<div class="label">{month_label(key)} '
            f'<span class="count">· {len(ids)}</span></div></a>')
    parts.append("</div>")
    if lib.skipped:
        parts.append(f'<p class="note">{lib.skipped} files in formats this gallery '
                     "cannot show (such as HEIC) were left out.</p>")
    return page(TITLE, "".join(parts))


def month_page(lib: Library, key: str) -> bytes | None:
    ids = lib.months.get(key)
    if ids is None:
        return None
    cells = "".join(f'<a href="/photo/{i}"><img src="/thumb/{i}" loading="lazy" alt=""></a>'
                    for i in ids)
    return page(month_label(key), f'<nav><a href="/">← All months</a></nav>'
                                  f'<h2>{month_label(key)}</h2><div class="grid">{cells}</div>')


def photo_page(lib: Library, i: int) -> bytes:
    photo = lib.photos[i]
    key = photo["date"][:7] if photo["date"] else "undated"
    ids = lib.months[key]
    pos = ids.index(i)
    links = [f'<a href="/month/{key}">← {month_label(key)}</a>']
    if pos > 0:
        links.append(f'<a href="/photo/{ids[pos - 1]}">Previous</a>')
    if pos < len(ids) - 1:
        links.append(f'<a href="/photo/{ids[pos + 1]}">Next</a>')
    name = html.escape(Path(photo["path"]).name)
    when = (datetime.fromisoformat(photo["date"]).strftime("%d %b %Y, %H:%M")
            if photo["date"] else "no date")
    return page(name, f'<nav>{"".join(links)}</nav><div class="viewer">'
                      f'<img src="/original/{i}" alt="{name}"><p class="count">{name} · {when}</p></div>')


# ---------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    library: Library

    def do_GET(self) -> None:
        parts = unquote(self.path.split("?")[0]).strip("/").split("/")
        lib = self.library
        try:
            if parts == [""]:
                return self._send(home_page(lib), "text/html; charset=utf-8")
            if len(parts) == 2 and parts[0] == "month":
                body = month_page(lib, parts[1])
                if body:
                    return self._send(body, "text/html; charset=utf-8")
            if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) < len(lib.photos):
                i = int(parts[1])
                if parts[0] == "photo":
                    return self._send(photo_page(lib, i), "text/html; charset=utf-8")
                if parts[0] == "thumb":
                    return self._send(thumbnail(lib.photos[i]).read_bytes(), "image/jpeg")
                if parts[0] == "original":
                    path = Path(lib.photos[i]["path"])
                    return self._send(path.read_bytes(), PHOTO_TYPES[path.suffix.lower()])
        except OSError as err:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(err))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _send(self, body: bytes, kind: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep the terminal readable
        pass


def make_server(lib: Library, port: int) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"library": lib})
    return ThreadingHTTPServer((HOST, port), handler)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Browse a folder of photos by month.")
    ap.add_argument("folder", help="the folder with your photos")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--rescan", action="store_true",
                    help="read every photo again, ignoring the saved index")
    args = ap.parse_args(argv)

    root = Path(args.folder).expanduser()
    if not root.is_dir():
        sys.exit(f"Folder not found: {root}")

    print(f"Reading photos in {root.resolve()} ...", flush=True)
    lib = Library(root, rescan=args.rescan)
    undated = len(lib.months.get("undated", []))
    print(f"{len(lib.photos)} photos, {len(lib.months) - (1 if undated else 0)} months"
          + (f", {undated} without a date" if undated else "")
          + (f", {lib.skipped} skipped (unsupported format)" if lib.skipped else ""))

    try:
        server = make_server(lib, args.port)
    except OSError:
        sys.exit(f"Port {args.port} is already in use. Try: --port {args.port + 1}")
    print(f"\nOpen http://{HOST}:{args.port} in your browser.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
