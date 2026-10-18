# 📸 Photobook

Photobook sorts your photos and videos into folders by the date they were taken:

```
Sorted photos/
├── Images/
│   ├── 202407_July/
│   │   ├── 2024-07-14/
│   │   │   ├── IMG_0001.jpg
│   │   │   └── clip.mov
│   │   └── 2024-07-15/
│   └── 202501_January/
├── Unsorted_Files/        ← everything that isn't a photo or video, by type
│   └── PDF/
└── Photobook_Logs/        ← a list of everything that was done
```

**Your original files are never changed, moved or deleted.** Photobook only makes copies.
Nothing in the destination is ever overwritten either.

## Start

**Mac:** double-click `Photobook.command`.
**Windows:** double-click `Photobook.bat`.

The first start sets things up and takes about a minute (it needs internet once).
If it says Python is missing, install it from [python.org/downloads](https://www.python.org/downloads/)
(on Windows tick **"Add python.exe to PATH"**) and double-click again.

> Mac says the file "can't be opened"? Right-click it → **Open** → **Open**. Only needed once.

## Use

1. **Photos to sort:** choose the folder with your photos, e.g. a phone backup, a USB stick or an SD card.
2. **Save sorted photos to:** choose where the sorted photos should go (it can already contain photos).
3. Click **Preview**. You'll see how many photos will be sorted, how much space it needs, and some fun facts.
   Nothing is copied yet.
4. Click **Start sorting**. You can cancel at any time.

Run it again whenever you have new photos. Photos that are already there are recognised and skipped,
even if you moved them to another folder in the meantime.

## Good to know

- **Dates** come from the photo itself (the camera's "date taken"), then from the video, then from names like
  `IMG_20250120_…` or `Screenshot 2025-01-20…`, and only as a last resort from the file date.
  The preview tells you how many files had to fall back to the file date.
- **iPhone photos (HEIC)** can be converted to JPG so they open on any computer and printing service.
  Date, location and colours are kept. If a photo can't be converted, the original is copied instead.
- **Same name, different photo** (e.g. two phones both have `IMG_0001.jpg`): both are kept, the second one
  becomes `IMG_0001 (2).jpg`.
- **Exact duplicates** in the photo folder are copied only once.
- **Not enough space?** Photobook checks before it starts. If the drive fills up anyway, it stops cleanly
  without leaving broken files behind. Free up space and run again; it continues where it stopped.
- Hidden files and system clutter (`.DS_Store`, `Thumbs.db`, …) are skipped. In an Apple Photos library,
  only the original photos are taken, not the thumbnails.

## For the command line

```bash
python photobook.py                                       # opens the window
python photobook.py -s ~/Pictures/Phone -d ~/Sorted --dry-run    # only show what would happen
python photobook.py -s ~/Pictures/Phone -d ~/Sorted -c           # sort, converting HEIC to JPG
```

`--dry-run` (or `-i`) also works as a check: it lists anything from the source that isn't in the destination yet.

## For developers

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python test_photobook.py                        # safety tests
.venv/bin/python test_photobook.py --demo demo/photos     # sample photos to play with
```

Standalone app, no Python needed by the user. Build on the system you build for:

```bash
make install       # Mac: dist/Photobook.app → /Applications, `photobook` command on PATH
make install-win   # Windows (GNU make): dist\Photobook.exe → on PATH, start with Win+R → Photobook
```

`make build` / `make build-win` only build, `make test` / `make test-win` run the tests.
