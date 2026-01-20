# PythonPhotobook - Architecture & Developer Guide

## Project Overview

A photo organization tool that sorts images by date into structured directories and handles HEIC-to-JPEG conversion. Designed for human readability, maintainability, and professional code quality.

## Design Principles

1. **Standard Library First**: Use Python's built-in modules (`logging`, `pathlib`, `dataclasses`) instead of custom implementations
2. **Type Safety**: Full type hints on all functions for IDE support and catching errors early
3. **Single Responsibility**: Each function does one thing well
4. **No Magic Values**: All constants centralized in `config.py`
5. **Proper Logging**: Use logging levels, not print statements
6. **Explicit Over Implicit**: Clear function names, no hidden side effects

## Directory Structure

```
PythonPhotobook/
├── photobook.py              # CLI entry point
├── modules/
│   ├── config.py             # Centralized configuration
│   ├── logger.py             # Logging setup
│   ├── directories.py        # Path validation
│   ├── convert.py            # HEIC → JPEG conversion
│   ├── sorting.py            # File organization logic
│   └── integrity.py          # Post-processing validation
├── requirements.txt          # Python dependencies
└── README.md                 # User documentation
```

## Module Responsibilities

### `photobook.py` - Main Entry Point
- **Purpose**: CLI argument parsing and workflow orchestration
- **Key Functions**: `main()`
- **Dependencies**: All modules
- **Exit Codes**:
  - `0`: Success
  - `1`: Error (file not found, permissions, etc.)
  - `130`: User cancelled (Ctrl+C)

### `modules/config.py` - Configuration
- **Purpose**: Single source of truth for all constants
- **Pattern**: Frozen dataclass (immutable)
- **Key Constants**:
  - `IMAGE_EXTENSIONS`: Supported file types
  - `IMAGES_DIR`, `UNSORTED_DIR`: Output folder names
  - Date format strings
  - JPEG quality setting

**Why frozen dataclass?**
- Prevents accidental modification
- IDE autocomplete support
- Clear structure vs scattered constants

### `modules/logger.py` - Logging Setup
- **Purpose**: Standard Python logging configuration
- **Key Function**: `setup_logger(name, log_file=None, level=INFO)`
- **Features**:
  - Console output with timestamps
  - Optional file logging
  - Consistent format across all modules

**Pattern**: Each module creates its own logger:
```python
logger = logging.getLogger(__name__)
```

### `modules/directories.py` - Path Validation
- **Purpose**: Validate source/destination before processing
- **Key Function**: `validate_paths(source_path, destination_path)`
- **Checks**:
  1. Source exists and is a directory
  2. Source is readable
  3. Destination exists (creates if missing)
  4. Destination is writable

**Why separate module?**
- Early validation prevents partial operations
- Reusable across different entry points
- Clear error messages with exception chaining

### `modules/convert.py` - HEIC Conversion
- **Purpose**: Convert Apple HEIC images to JPEG
- **Key Function**: `convert_heic_to_jpeg(src_path, delete_original=True)`
- **Features**:
  - Preserves original modification time
  - Configurable quality (from config)
  - Optional original file deletion
  - Skips if JPEG already exists

**Important**: `delete_original` parameter makes side effect explicit

### `modules/sorting.py` - File Organization (Core Logic)
- **Purpose**: Main file organization workflow
- **Architecture**: Small, focused functions instead of one large function

#### Function Breakdown

**Date Extraction**:
- `get_earliest_date(file_path)`: Get file's oldest timestamp
- `extract_date_from_filename(file_name)`: Parse `YYYYMMDD_*` pattern
- `update_file_date(file_path, date)`: Update file modification time
- `get_file_date(file_path, allow_update)`: Orchestrates date logic

**Path Building**:
- `build_destination_path(...)`: Construct output path with date folders
- `should_convert_file(...)`: Check if HEIC conversion needed
- `get_destination_for_file(...)`: Route images vs unsorted files

**Processing**:
- `collect_files_to_process(...)`: Count files for progress bar
- `process_file(...)`: Convert (if needed) and copy single file
- `organize_files(...)`: Main orchestration function

**Legacy Compatibility**:
- `image_sorting(...)`: Wrapper maintaining old function signature

#### Why This Structure?

**Before** (AI-generated pattern):
```python
def image_sorting(...):  # 156 lines
    # Walk directory tree to count files
    for root, _, files in os.walk(source):
        # ... 50 lines ...

    # Walk directory tree AGAIN to process files
    for root, _, files in os.walk(source):
        # ... 100 lines of nested logic ...
```

**After** (human-written pattern):
```python
def organize_files(...):
    total = collect_files_to_process(...)  # One walk
    for each file:
        dest = get_destination_for_file(...)
        process_file(src, dest, ...)
```

**Benefits**:
- Single directory traversal
- Each function testable in isolation
- Clear data flow
- Easy to debug specific steps

### `modules/integrity.py` - Validation
- **Purpose**: Verify organization completed successfully
- **Key Functions**:
  - `count_files_with_extensions(...)`: Count matching files
  - `check_file_counts(...)`: Verify source == destination count
  - `check_file_formats(...)`: Find unexpected file types
  - `integrity_check(...)`: Run all checks

**Usage**: Run after organization with `-i` flag

## Data Flow

### Normal Organization Flow
```
1. photobook.py: Parse arguments
2. logger.py: Setup logging
3. directories.py: Validate paths
4. sorting.py: organize_files()
   ├─ collect_files_to_process() → count
   ├─ For each file:
   │  ├─ get_destination_for_file()
   │  │  └─ build_destination_path()
   │  │     └─ get_file_date()
   │  └─ process_file()
   │     └─ convert_heic_to_jpeg() [if needed]
   └─ Copy to destination
5. Log success
```

### Integrity Check Flow
```
1. photobook.py: Parse arguments with -i
2. logger.py: Setup logging
3. directories.py: Validate paths
4. integrity.py: integrity_check()
   ├─ check_file_counts()
   │  └─ count_files_with_extensions()
   ├─ If mismatch: EXIT
   └─ check_file_formats()
```

## Output Structure

```
destination/
├── Images/
│   ├── 202501_January/
│   │   ├── 2025-01-15/
│   │   │   ├── photo1.jpg
│   │   │   └── photo2.png
│   │   └── 2025-01-20/
│   │       └── photo3.jpg
│   └── 202412_December/
│       └── 2024-12-25/
│           └── holiday.jpg
└── Unsorted_Files/
    ├── PDF/
    │   └── document.pdf
    └── TXT/
        └── notes.txt
```

## Common Patterns Used

### 1. Type Hints Everywhere
```python
def build_destination_path(
    file_path: Path,
    dest_dir: Path,
    allow_update: bool = True,
    dest_basename: Optional[str] = None
) -> Optional[Path]:
```

### 2. Early Returns
```python
def process_file(...) -> bool:
    if dest_path.exists():
        return False  # Early return

    # Main logic continues
    ...
    return True
```

### 3. Pathlib Over String Manipulation
```python
# Bad (AI-generated)
dest_path = os.path.join(dir, "Images", year, file)

# Good (human-written)
dest_path = dest_dir / "Images" / year / file_path.name
```

### 4. Specific Exception Handling
```python
# Bad (AI-generated)
except Exception as e:
    print(f"Error: {e}")

# Good (human-written)
except FileNotFoundError:
    logger.error(f"File not found: {path}")
    return None
except OSError as e:
    logger.error(f"File operation failed: {e}")
    return None
```

### 5. Logging Levels
```python
logger.debug("File already exists")  # Verbose detail
logger.info("Processing 100 files")   # Normal operation
logger.warning("Conversion failed")   # Recoverable issue
logger.error("Path not found")        # Error condition
logger.exception("Unexpected error")  # Error with traceback
```

## Testing Strategy (Future)

### Unit Tests (Recommended)
```python
# tests/test_sorting.py
def test_extract_date_from_filename():
    assert extract_date_from_filename("20250120_photo.jpg") == datetime(2025, 1, 20)
    assert extract_date_from_filename("photo.jpg") is None

def test_build_destination_path(tmp_path):
    result = build_destination_path(
        Path("20250120_test.jpg"),
        tmp_path
    )
    assert "202501_January" in str(result)
    assert "2025-01-20" in str(result)
```

### Integration Tests (Recommended)
- Create temp directory with test files
- Run organization
- Verify output structure
- Check file counts
- Validate no data loss

## Anti-Patterns Removed

### ❌ Custom Logging Class
**Before**: 56-line `Tee` class reinventing `logging` module
**After**: 2-line logger setup using standard library

### ❌ God Functions
**Before**: 156-line `image_sorting()` doing everything
**After**: 10 focused functions with clear responsibilities

### ❌ Magic Strings
**Before**: `"Images"`, `"%Y%m_%B"` scattered throughout
**After**: Centralized in `config.py`

### ❌ Duplicate Logic
**Before**: Walking directory tree twice
**After**: Single traversal with count caching

### ❌ Print Statements
**Before**: `print(f"Error: {e}")`
**After**: `logger.error(f"Error: {e}")`

### ❌ Commented-Out Code
**Before**: Lines 67-71 in integrity.py were debug code
**After**: Removed entirely

### ❌ Generic Exceptions
**Before**: `except Exception as e:`
**After**: `except (FileNotFoundError, OSError) as e:`

## Performance Considerations

- **Single Directory Walk**: Process files in one pass
- **Lazy Conversion**: HEIC converted only when needed
- **Early Skip**: Don't process files that already exist
- **Progress Bar**: Uses `tqdm` for user feedback

## Future Enhancements (Suggestions)

1. **Parallel Processing**: Use `concurrent.futures` for large directories
2. **Database Tracking**: SQLite for operation history
3. **Undo Functionality**: Keep operation log for reversal
4. **Smart Duplicates**: Hash-based duplicate detection
5. **Config File**: YAML/TOML for user customization
6. **Exif Date**: Use EXIF metadata for more accurate dates
7. **Unit Tests**: Full test coverage with pytest
8. **Type Checking**: Run mypy in CI

## Debugging Tips

### Enable Debug Logging
```python
logger = setup_logger("photobook", log_file, level=logging.DEBUG)
```

### Dry Run Everything
```bash
python3 photobook.py -s source -d dest --dry-run
```

### Check Specific Module
```python
import logging
logging.basicConfig(level=logging.DEBUG)

from modules.sorting import extract_date_from_filename
print(extract_date_from_filename("20250120_test.jpg"))
```

## Code Style

- **Line Length**: ≤ 88 characters (Black default)
- **Imports**: Standard library → Third party → Local modules
- **Docstrings**: Brief description, parameters, return value
- **Naming**:
  - Functions: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_CASE`
  - Private: `_leading_underscore`

## Dependencies

- **pillow_heif**: HEIC format support
- **Pillow**: Image processing
- **tqdm**: Progress bars

All other functionality uses standard library.

---

**Last Updated**: 2025-01-20
**Refactored From**: AI-generated code to human-written patterns
**Maintained By**: Project owner
