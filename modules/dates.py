"""Find out when a photo or video was taken."""

import logging
import re
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Tuple

from PIL import Image
from pillow_heif import register_heif_opener

from modules import config

register_heif_opener()
logger = logging.getLogger(__name__)

EXIF_IFD = 0x8769
DATE_TIME_ORIGINAL = 36867
DATE_TIME_DIGITIZED = 36868
DATE_TIME = 306
QUICKTIME_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)

# 20250120, 2025-01-20, 2025_01_20, 2025.01.20 - not part of a longer number, except a glued-on time
# like 20250120153000.
FILENAME_DATE = re.compile(
    r"(?<!\d)((?:19|20)\d\d)[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?:(?!\d)|(?=\d{6}(?!\d)))")


def is_plausible(date: datetime) -> bool:
    """Reject camera defaults like 1970 / 0000 and dates in the future."""
    return datetime(1980, 1, 1) <= date <= datetime.now() + timedelta(days=2)


def exif_date(path: Path) -> Optional[datetime]:
    """Date the photo was taken, from EXIF. Reads only the header, not the pixels."""
    try:
        with Image.open(path) as img:  # read everything while open: TIFF loads the sub-IFD from the file
            exif = img.getexif()
            sub = exif.get_ifd(EXIF_IFD)
            candidates = (sub.get(DATE_TIME_ORIGINAL), sub.get(DATE_TIME_DIGITIZED), exif.get(DATE_TIME))
    except Exception:  # Pillow raises many types for odd files; any failure means "no EXIF date"
        return None
    for raw in candidates:
        if isinstance(raw, bytes):  # some cameras store the date as bytes
            raw = raw.decode("ascii", errors="ignore")
        try:
            date = datetime.strptime(str(raw).strip("\x00 ")[:19], "%Y:%m:%d %H:%M:%S")
        except ValueError:
            continue
        if is_plausible(date):
            return date
    return None


def _atoms(f: BinaryIO, start: int, end: int) -> Iterator[Tuple[bytes, int, int]]:
    """Yield (type, body_start, atom_end) for each MP4/QuickTime atom between start and end."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        size, kind = struct.unpack(">I4s", f.read(8))
        body = pos + 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            body += 8
        elif size == 0:
            size = end - pos
        if size < 8:
            return
        yield kind, body, pos + size
        pos += size


def video_date(path: Path) -> Optional[datetime]:
    """Creation time stored in the moov/mvhd atom of .mov/.mp4 files (UTC → local time)."""
    try:
        with open(path, "rb") as f:
            end = f.seek(0, 2)
            for kind, body, atom_end in _atoms(f, 0, end):
                if kind != b"moov":
                    continue
                for sub_kind, sub_body, _ in _atoms(f, body, atom_end):
                    if sub_kind == b"mvhd":
                        f.seek(sub_body)
                        version = f.read(4)[0]
                        fmt = ">Q" if version == 1 else ">I"
                        seconds = struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]
                        if not seconds:
                            return None
                        date = (QUICKTIME_EPOCH + timedelta(seconds=seconds)).astimezone().replace(tzinfo=None)
                        return date if is_plausible(date) else None
    except (OSError, struct.error, IndexError, OverflowError):
        return None
    return None


def filename_date(name: str) -> Optional[datetime]:
    """Date in names like IMG_20250120_1530.jpg, PXL_20250120…, Screenshot 2025-01-20…"""
    match = FILENAME_DATE.search(name)
    if not match:
        return None
    try:
        date = datetime(*map(int, match.groups()))
    except ValueError:  # e.g. 2023-02-30
        return None
    return date if is_plausible(date) else None


def file_date(path: Path) -> datetime:
    """Oldest timestamp the filesystem knows. Unreliable after copying, hence the last resort."""
    st = path.stat()
    return datetime.fromtimestamp(min(st.st_mtime, getattr(st, "st_birthtime", st.st_mtime)))


def taken_date(path: Path) -> Tuple[datetime, str]:
    """Best guess when a file was taken, plus where the date came from: photo, video, name or file."""
    ext = path.suffix.lower()
    if ext in config.PHOTO_EXTENSIONS and (date := exif_date(path)):
        return date, "photo"
    if ext in config.QUICKTIME_EXTENSIONS and (date := video_date(path)):
        return date, "video"
    if date := filename_date(path.name):
        return date, "name"
    return file_date(path), "file"
