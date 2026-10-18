# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sorts photos and videos by date taken into `Images/YYYYMM_Month/YYYY-MM-DD/`, other files into
`Unsorted_Files/EXT/`, optionally converting HEIC to JPEG. Built for non-technical users: a tkinter window
(no arguments) plus a CLI. **Safety is the top requirement:** never modify the source, never overwrite or
delete anything in the destination, never silently skip a file.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python photobook.py                                   # window
.venv/bin/python photobook.py -s SRC -d DST [-c] [--dry-run]    # CLI
.venv/bin/python test_photobook.py                              # tests (stdlib unittest)
.venv/bin/python test_photobook.py --demo demo/photos           # sample library to play with
```

## Architecture

Two phases, so preview can never write anything:

- `modules/planner.py` — **read-only**. One walk of the source → `Plan` of `Item`s (src, dest, action).
  `Namer` indexes the destination once and decides: already there (same name + same size/mtime or bytes;
  for HEIC: our source-hash tag in the JPEG comment, or visually identical for files from old versions),
  duplicate within this run, or a new free name `name (2).ext`.
- `modules/executor.py` — the only module that writes. Copy/convert to a hidden temp file in the dest folder,
  then `os.link` (fails if the name exists) or exists-check + rename on file systems without hard links.
  Thread pool, cancel event, stops on disk full, per-file errors are collected, never abort the run.
- `modules/dates.py` — EXIF DateTimeOriginal → MP4/MOV `mvhd` → date in filename → file time.
- `modules/report.py` — plain-language summaries shared by GUI and CLI.
- `modules/gui.py` — tkinter; work runs in a thread, events go through a queue polled by `after()`.
- `modules/config.py` — all constants.

## Code Style

- `pathlib.Path`, `logging.getLogger(__name__)` (per-file details at DEBUG go to the log file only), type hints.
- Constants in `config.py`. Functions short. Walk each tree once.
- Broad `except Exception` only where Pillow can raise anything for odd files, or to keep one file's error
  from stopping the rest; always with a comment.
- Every safety-relevant behaviour has a test in `test_photobook.py`; the tests snapshot the source and
  assert it is unchanged.
