# Notes for coding agents

`gallery` is a single-file Python program (`gallery.py`) that serves a
read-only photo gallery on localhost. `README.md` explains how to install and
run it; read it first.

## Rules

- **Never write to the photos folder.** No thumbnails, index files or
  renames there. Everything the program creates goes to `.cache/` next to
  `gallery.py`. `tests/test_gallery.py::test_never_touches_the_photos` guards
  this.
- **Stay on localhost.** `HOST` is `127.0.0.1`. Do not change it to `0.0.0.0`
  or add anything that sends data over the network unless the user explicitly
  asks and understands the consequence.
- **Keep it to one dependency.** Pillow is the only third-party package. Ask
  before adding another.
- Install into a virtual environment (`.venv`), not system-wide.

## Layout

| Part of `gallery.py` | What it does |
| --- | --- |
| settings block at the top | `TITLE`, `THUMB_SIZE`, `NEWEST_FIRST`, `HOST`, `DEFAULT_PORT` |
| `photo_date`, `find_photos`, `Library` | find photos, read EXIF dates, group by month, cache the index |
| `thumbnail` | make and cache thumbnails |
| `home_page`, `month_page`, `photo_page` | HTML pages (inline CSS, no JavaScript) |
| `pick_folder` | the **Choose folder** button: opens the system's own folder window (PowerShell on Windows and WSL, `osascript` on macOS, `zenity` or Tk on Linux) |
| `Handler`, `make_server`, `main` | HTTP routes and command line |

Routes: `/`, `/month/<YYYY-MM|undated>`, `/photo/<n>`, `/thumb/<n>`,
`/original/<n>`, `/choose`. Photos are addressed by index, never by path.

## Checking a change

```
python -m unittest
```

Then run it against a real folder and open the pages in a browser. Changes to
dates or grouping may need `--rescan`, because the index is cached.
