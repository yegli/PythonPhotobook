# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Photo organization tool that sorts images by date into structured directories (`YYYYMM_Month/YYYY-MM-DD/`) and converts HEIC to JPEG.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Basic usage
python photobook.py -s /source -d /destination

# Dry run (preview without changes)
python photobook.py -s /source -d /destination --dry-run

# With HEIC to JPEG conversion
python photobook.py -s /source -d /destination -c

# Integrity check (verify file counts match)
python photobook.py -s /source -d /destination -i

# With file logging
python photobook.py -s /source -d /destination --log-to-file
```

## Architecture

**Entry Point**: `photobook.py` - CLI argument parsing and workflow orchestration

**Modules** (`modules/`):
- `config.py` - Frozen dataclass with all constants (extensions, formats, directories)
- `logger.py` - Standard Python logging setup
- `directories.py` - Path validation before processing
- `convert.py` - HEIC → JPEG conversion with `pillow_heif`
- `sorting.py` - Core file organization logic (date extraction, path building, copying)
- `integrity.py` - Post-processing validation (file counts, format checking)

**Data Flow**: CLI args → validate paths → organize_files() (single directory walk) → copy/convert files → optional integrity check

## Code Style Requirements

- Use `pathlib.Path` not `os.path.join()`
- Use `logging.getLogger(__name__)` not `print()`
- Type hints on all functions
- Specific exceptions (`FileNotFoundError`) not generic `Exception`
- Add new constants to `config.py`, not inline
- Keep functions under ~40 lines
- Single directory traversal - don't walk the tree multiple times

## Output Structure

```
destination/
├── Images/
│   └── 202501_January/
│       └── 2025-01-20/
│           └── photo.jpg
└── Unsorted_Files/
    └── PDF/
        └── document.pdf
```

## Dependencies

- `pillow_heif` - HEIC format support
- `Pillow` - Image processing
- `tqdm` - Progress bars
