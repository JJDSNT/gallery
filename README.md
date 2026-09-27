# gallery

Browse a folder of photos by month, in your browser.

`gallery` reads the date your camera or phone recorded inside each photo,
groups the photos by year and month, and serves a small website on your own
computer. Open it in the browser, pick a month, and click through the photos.

- **Private.** It runs only on your computer and listens only on `127.0.0.1`.
  Nothing is uploaded, nothing is published.
- **Read-only.** Your photos are never moved, renamed or changed. Thumbnails
  and the index are kept in a `.cache` folder next to the program.
- **Small.** One Python file and one dependency ([Pillow](https://python-pillow.org),
  to read photos and make thumbnails).

## Requirements

- Python 3.9 or newer
- Pillow (see `requirements.txt`)

## Install

```
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

On Debian and Ubuntu, `python3 -m venv` may ask you to install the
`python3-venv` package first.

## Run

```
python gallery.py /path/to/your/photos
```

Then open <http://127.0.0.1:8000>. Press `Ctrl+C` in the terminal to stop.

You can also start it without a folder (`python gallery.py`) and click
**Choose folder** in the browser; it opens your computer's own folder window.
The button is at the top of every page, to switch folders.

The first start reads every photo and can take a while on large folders; later
starts reuse the saved index and only read what changed. Thumbnails are made
the first time each one is shown.

Options:

| Option | What it does |
| --- | --- |
| `--port 8080` | Use another port, if 8000 is taken |
| `--rescan` | Read every photo again, ignoring the saved index |

## Settings

The things people usually want to change are at the top of `gallery.py`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `TITLE` | `"My photos"` | Title shown at the top of every page |
| `THUMB_SIZE` | `320` | Thumbnail size, in pixels |
| `NEWEST_FIRST` | `False` | Show the most recent months first |

## How dates are chosen

The date comes from the photo's EXIF data (`DateTimeOriginal`, or `DateTime`
when that is missing). Photos without a recorded date go to **No date** at
the end. File dates are not used on purpose: copying a folder resets them.

## Supported formats

JPEG, PNG and WebP. HEIC photos (the iPhone default) and camera RAW files are
counted and listed as skipped, not shown.

## Tests

```
python -m unittest
```

## Uninstall

Delete this folder. That removes the program, its virtual environment and the
cache. Your photos are not inside it.

## License

MIT — see `LICENSE`.
