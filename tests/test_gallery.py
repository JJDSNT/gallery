"""Run with:  python -m unittest"""

from __future__ import annotations

import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from PIL import Image

import gallery


def make_photo(path: Path, taken: str | None = None, original: bool = True) -> None:
    """A small image, with the camera date written where a camera would."""
    path.parent.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    if taken and original:
        exif.get_ifd(gallery.EXIF_IFD)[gallery.DATETIME_ORIGINAL] = taken
    elif taken:
        exif[gallery.DATETIME] = taken
    Image.new("RGB", (640, 480), (120, 160, 200)).save(path, exif=exif)


class GaleriaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.photos = base / "photos"
        gallery.CACHE = base / "cache"
        make_photo(self.photos / "a.jpg", "2019:12:25 10:00:00")
        make_photo(self.photos / "trip" / "b.jpg", "2019:12:31 23:59:00", original=False)
        make_photo(self.photos / "c.jpg", "2021:03:02 08:30:00")
        make_photo(self.photos / "no-date.jpg")
        (self.photos / "phone.heic").write_bytes(b"not really a photo")
        (self.photos / "notes.txt").write_text("ignored")

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self):
        return {p: (p.stat().st_mtime, p.stat().st_size) for p in self.photos.rglob("*")}

    def test_reads_camera_date(self):
        self.assertEqual(str(gallery.photo_date(self.photos / "a.jpg")), "2019-12-25 10:00:00")
        self.assertEqual(str(gallery.photo_date(self.photos / "trip" / "b.jpg")), "2019-12-31 23:59:00")
        self.assertIsNone(gallery.photo_date(self.photos / "no-date.jpg"))

    def test_groups_by_month(self):
        lib = gallery.Library(self.photos, quiet=True)
        self.assertEqual(lib.month_keys(), ["2019-12", "2021-03", "undated"])
        self.assertEqual(len(lib.months["2019-12"]), 2)
        self.assertEqual(lib.skipped, 1)

    def test_newest_first(self):
        gallery.NEWEST_FIRST = True
        try:
            lib = gallery.Library(self.photos, quiet=True)
            self.assertEqual(lib.month_keys(), ["2021-03", "2019-12", "undated"])
        finally:
            gallery.NEWEST_FIRST = False

    def test_never_touches_the_photos(self):
        before = self.snapshot()
        lib = gallery.Library(self.photos, quiet=True)
        for photo in lib.photos:
            gallery.thumbnail(photo)
        self.assertEqual(before, self.snapshot())

    def test_serves_pages(self):
        lib = gallery.Library(self.photos, quiet=True)
        server = gallery.make_server(lib, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://{gallery.HOST}:{server.server_address[1]}"
        try:
            home = urllib.request.urlopen(base + "/").read().decode()
            self.assertIn("December 2019", home)
            self.assertIn("No date", home)
            self.assertIn("1 files in formats", home)
            self.assertIn("/thumb/0", urllib.request.urlopen(base + "/month/2019-12").read().decode())
            thumb = urllib.request.urlopen(base + "/thumb/0")
            self.assertEqual(thumb.headers["Content-Type"], "image/jpeg")
            self.assertIn("Next", urllib.request.urlopen(base + "/photo/0").read().decode())
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/original/999")
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "/month/../../etc")
        finally:
            server.shutdown()
            server.server_close()

    def test_choose_folder_button(self):
        server = gallery.make_server(None, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://{gallery.HOST}:{server.server_address[1]}"
        real_picker = gallery.pick_folder
        try:
            start = urllib.request.urlopen(base + "/").read().decode()
            self.assertIn("Choose folder", start)
            gallery.pick_folder = lambda: None          # window closed without choosing
            self.assertIn("Choose folder", urllib.request.urlopen(base + "/choose").read().decode())
            gallery.pick_folder = lambda: self.photos   # folder chosen
            self.assertIn("December 2019", urllib.request.urlopen(base + "/choose").read().decode())
        finally:
            gallery.pick_folder = real_picker
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
