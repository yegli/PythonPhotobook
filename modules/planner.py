"""Decide where every file goes. Read-only: this module never writes anything."""

import filecmp
import hashlib
import logging
import os
import re
import shutil
import threading
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple, Union

from PIL import Image, ImageChops

from modules import config
from modules.dates import taken_date

logger = logging.getLogger(__name__)

# What happens to a file.
COPY = "copy"
CONVERT = "convert"
ALREADY_THERE = "already there"
DUPLICATE = "duplicate"

NUMBERING = re.compile(r" \(\d+\)(?=\.[^.]*$|$)")

Progress = Callable[[int, int, Path], None]  # done, total, current file


class FolderError(ValueError):
    """The chosen folders can't be used. The message is meant for the user."""


class Cancelled(Exception):
    """The user pressed cancel."""


@dataclass
class Item:
    src: Path
    dest: Path
    action: str
    kind: str          # "photo", "video" or "other"
    date_source: str   # "photo", "video", "name", "file" or "" for other files
    size: int

    @property
    def todo(self) -> bool:
        return self.action in (COPY, CONVERT)


@dataclass
class Plan:
    source: Path
    destination: Path
    items: List[Item] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)  # folders/files we could not read
    free_bytes: int = 0

    @property
    def todo(self) -> List[Item]:
        return [i for i in self.items if i.todo]

    @property
    def needed_bytes(self) -> int:
        return sum(i.size * (config.CONVERT_SIZE_FACTOR if i.action == CONVERT else 1) for i in self.todo)

    @property
    def enough_space(self) -> bool:
        return self.needed_bytes + config.SPACE_MARGIN_BYTES <= self.free_bytes

    def count(self, **match: str) -> int:
        return sum(all(getattr(i, k) == v for k, v in match.items()) for i in self.items)

    def days(self) -> Counter:
        """Number of new photos and videos per day folder."""
        return Counter(i.dest.parent.name for i in self.todo if i.kind != "other")


def check_folders(source: Path, destination: Path) -> None:
    """Refuse folder combinations that could go wrong, with a message a non-technical user understands."""
    if not source.is_dir():
        raise FolderError(f"The photo folder doesn't exist:\n{source}")
    existing = nearest_existing(destination.absolute())
    # Compare real folders, not spellings: macOS ignores upper/lower case and accents in names.
    if destination.exists() and os.path.samefile(destination, source):
        raise FolderError("Please choose a different folder to save the sorted photos to.")
    if any(os.path.samefile(folder, source) for folder in (existing, *existing.parents)):
        raise FolderError("The sorted photos can't be saved inside the folder being sorted.\n"
                          "Please choose a folder somewhere else.")
    if not existing.is_dir() or not os.access(existing, os.W_OK):
        raise FolderError(f"Can't save files to this folder:\n{existing}")


def nearest_existing(path: Path) -> Path:
    while not path.exists() and path.parent != path:
        path = path.parent
    return path


def walk(source: Path, problems: List[str]) -> Iterator[Path]:
    """Every real file below source, skipping hidden files and system clutter. Unreadable folders are reported."""
    def on_error(err: OSError) -> None:
        problems.append(f"Couldn't read folder {err.filename}: {err.strerror}")

    def first_visit(folder: str) -> bool:  # linked folders are followed, but each real folder only once
        try:
            st = os.stat(folder)
        except OSError as err:
            on_error(err)
            return False
        key = (st.st_dev, st.st_ino)
        if key in seen:
            return False
        seen.add(key)
        return True

    seen: Set[Tuple[int, int]] = set()
    first_visit(str(source))
    for root, dirs, files in os.walk(source, onerror=on_error, followlinks=True):
        if root.endswith(".photoslibrary"):
            dirs[:] = [d for d in dirs if d in config.PHOTOS_LIBRARY_ORIGINALS]
        else:
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() not in config.JUNK_DIRS)
        dirs[:] = [d for d in dirs if first_visit(os.path.join(root, d))]
        for name in sorted(files):
            if name.startswith(".") or name.lower() in config.JUNK_FILES:
                continue
            yield Path(root) / name


def kind_of(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in config.PHOTO_EXTENSIONS:
        return "photo"
    if ext in config.VIDEO_EXTENSIONS:
        return "video"
    return "other"


def target_folder(path: Path, destination: Path, kind: str) -> Tuple[Path, str]:
    """Images/202501_January/2025-01-20 for photos and videos, Unsorted_Files/PDF for the rest."""
    if kind == "other":
        return destination / config.UNSORTED_DIR / (path.suffix[1:].upper() or "NO_EXT"), ""
    date, source = taken_date(path)
    month = f"{date:%Y%m}_{config.MONTHS[date.month - 1]}"
    return destination / config.IMAGES_DIR / month / date.strftime(config.DAY_FORMAT), source


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def converted_from(jpeg: Path) -> Optional[bytes]:
    """The source hash photobook wrote into a converted JPEG, if any."""
    try:
        with Image.open(jpeg) as img:
            comment = img.info.get("comment", b"")
    except Exception:  # not an image we made
        return None
    if isinstance(comment, bytes) and comment.startswith(config.CONVERTED_TAG):
        return comment[len(config.CONVERTED_TAG):]
    return None


def numbered(name: str, n: int) -> str:
    """IMG_1.jpg, IMG_1 (2).jpg, IMG_1 (3).jpg, …"""
    if n == 1:
        return name
    stem, dot, ext = name.rpartition(".")
    return f"{stem} ({n}).{ext}" if dot else f"{name} ({n})"


def name_key(name: str) -> str:
    """How macOS/Windows compare names: case and accent encoding (é as one or two characters) don't matter."""
    return unicodedata.normalize("NFC", name).casefold()


def base_name(name: str) -> str:
    """Name without our " (2)" numbering: the key for finding a file anywhere in the destination."""
    return name_key(NUMBERING.sub("", name))


def same_bytes(a: Path, b: Path) -> bool:
    """Same content? Copies keep the file time, so for those the start and end of the file are checked;
    otherwise every byte is compared."""
    sa, sb = a.stat(), b.stat()
    if sa.st_size != sb.st_size:
        return False
    if abs(sa.st_mtime - sb.st_mtime) > config.SAME_TIME_SECONDS:
        return filecmp.cmp(a, b, shallow=False)
    with open(a, "rb") as fa, open(b, "rb") as fb:
        for offset in (0, max(0, sa.st_size - config.QUICK_COMPARE_BYTES)):
            fa.seek(offset)
            fb.seek(offset)
            if fa.read(config.QUICK_COMPARE_BYTES) != fb.read(config.QUICK_COMPARE_BYTES):
                return False
    return True


def looks_same(heic: Path, jpeg: Path) -> bool:
    """Is this JPEG a conversion of this HEIC? For JPEGs made by older versions that left no tag."""
    size = (config.LOOKS_SAME_SIZE, config.LOOKS_SAME_SIZE)
    try:
        with Image.open(heic) as a, Image.open(jpeg) as b:
            if a.size != b.size:
                return False
            b.draft("L", size)
            small_a, small_b = (img.convert("L").resize(size) for img in (a, b))
    except Exception:  # unreadable means "can't prove it's the same", so it gets copied
        return False
    histogram = ImageChops.difference(small_a, small_b).histogram()
    differing = sum(histogram[config.LOOKS_SAME_PIXEL_DIFF:]) / sum(histogram)
    return differing < config.LOOKS_SAME_MAX_SHARE


def readable_and(check: Callable[[], bool]) -> bool:
    """A broken or unreadable file in the destination is simply "not the same", never a reason to fail."""
    try:
        return check()
    except OSError:
        return False


def index_destination(destination: Path) -> Dict[str, List[Path]]:
    """Every file already in the destination by base name, so files are recognised even if moved or misdated."""
    index: Dict[str, List[Path]] = {}
    for folder in (destination / config.IMAGES_DIR, destination / config.UNSORTED_DIR):
        for root, _, files in os.walk(folder):
            for name in files:
                index.setdefault(base_name(name), []).append(Path(root) / name)
    return index


class Namer:
    """Picks a destination name per file so nothing is ever overwritten and nothing is copied twice."""

    def __init__(self, destination: Path) -> None:
        self.existing = index_destination(destination)
        self.claimed: Dict[str, Path] = {}  # name_key of planned destination -> source

    def already_there(self, src: Path, folder: Path, name: str, convert: bool) -> Optional[Path]:
        # An exact copy of the original counts, also for conversions (e.g. HEIC kept because conversion failed).
        for candidate in self.existing.get(base_name(src.name), []):
            if readable_and(lambda: same_bytes(candidate, src)):
                return candidate
        candidates = self.existing.get(base_name(name), []) if convert else []
        if candidates:
            source_hash = sha256(src).encode()
            for candidate in candidates:
                tag = converted_from(candidate)
                if tag == source_hash or (tag is None and self.old_conversion(src, folder, candidate)):
                    return candidate
        return None

    @staticmethod
    def old_conversion(src: Path, folder: Path, jpeg: Path) -> bool:
        """JPEGs from older versions carry no tag. Only trust a visual match if the JPEG is in the same day
        folder or kept the HEIC's exact file time (as older versions did), so a different photo with the
        same name from another day is never mistaken for it."""
        same_place = name_key(str(jpeg.parent)) == name_key(str(folder))
        same_time = readable_and(lambda: abs(jpeg.stat().st_mtime - src.stat().st_mtime) <= config.SAME_TIME_SECONDS)
        return (same_place or same_time) and looks_same(src, jpeg)

    def place(self, src: Path, folder: Path, name: str, convert: bool) -> Tuple[Path, str]:
        if found := self.already_there(src, folder, name, convert):
            return found, ALREADY_THERE
        for n in range(1, 10_000):
            candidate = folder / numbered(name, n)
            key = name_key(str(candidate))
            if key in self.claimed:
                if filecmp.cmp(self.claimed[key], src, shallow=False):
                    return candidate, DUPLICATE
                continue
            if candidate.exists():  # a different file (same ones were found above): never overwrite it
                continue
            self.claimed[key] = src
            return candidate, CONVERT if convert else COPY
        raise FolderError(f"Too many files called {name} in {folder}")


def can_open(path: Path) -> bool:
    """Header check, so unreadable HEICs are planned as plain copies (and recognised on re-runs)."""
    try:
        with Image.open(path):
            return True
    except Exception:  # Pillow raises many types for broken files
        return False


def inspect(path: Path, destination: Path, convert_heic: bool) -> Union[Item, Exception]:
    """The slow part of planning (reading file headers), independent per file so it can run in parallel."""
    try:
        kind = kind_of(path)
        folder, date_source = target_folder(path, destination, kind)
        convert = convert_heic and path.suffix.lower() in (".heic", ".heif") and can_open(path)
        name = path.stem + ".jpg" if convert else path.name
        return Item(path, folder / name, CONVERT if convert else COPY, kind, date_source, path.stat().st_size)
    except Exception as err:  # vanished, unreadable or very odd file: reported, never stops the scan
        return err


def make_plan(source: Path, destination: Path, convert_heic: bool,
              progress: Optional[Progress] = None, cancel: Optional[threading.Event] = None) -> Plan:
    """Scan source once and decide what happens to every file. Writes nothing."""
    source, destination = Path(source), Path(destination)
    check_folders(source, destination)
    plan = Plan(source, destination)
    files = list(walk(source, plan.problems))
    namer = Namer(destination)
    pool = ThreadPoolExecutor(config.WORKERS)
    try:
        inspected = pool.map(lambda path: inspect(path, destination, convert_heic), files)
        for n, (path, item) in enumerate(zip(files, inspected), 1):
            if cancel and cancel.is_set():
                raise Cancelled()
            try:
                if isinstance(item, Exception):
                    raise item
                # Naming runs in order, one file at a time, so the result is the same every time.
                item.dest, item.action = namer.place(path, item.dest.parent, item.dest.name, item.action == CONVERT)
                plan.items.append(item)
            except Exception as err:  # report it, keep going
                plan.problems.append(f"Couldn't read {path}: {getattr(err, 'strerror', None) or err}")
            if progress:
                progress(n, len(files), path)
    finally:
        pool.shutdown(cancel_futures=True)
    plan.free_bytes = shutil.disk_usage(nearest_existing(destination)).free
    return plan
