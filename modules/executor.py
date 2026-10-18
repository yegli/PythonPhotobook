"""Carry out a plan. Only ever creates new files in the destination; never changes or deletes anything else."""

import errno
import logging
import os
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

from modules import config
from modules.planner import CONVERT, Item, Plan, Progress, numbered, sha256

logger = logging.getLogger(__name__)

EXIF_ORIENTATION = 0x0112


@dataclass
class Result:
    copied: int = 0
    converted: int = 0
    kept_heic: int = 0                                          # conversion failed, original copied instead
    failed: List[Tuple[Path, str]] = field(default_factory=list)
    cancelled: bool = False
    disk_full: bool = False
    log_file: Optional[Path] = None


def place(tmp: Path, dest: Path) -> Path:
    """Give the finished temp file its final name without ever replacing an existing file."""
    for n in range(1, 10_000):
        final = dest.with_name(numbered(dest.name, n))
        try:
            os.link(tmp, final)  # atomic, fails if the name is taken
            return final
        except FileExistsError:
            continue
        except OSError:  # file systems without hard links (FAT/exFAT USB sticks, some network drives)
            pass
        try:
            # Reserve the name (fails if it exists, even across apps), then replace only that empty placeholder.
            os.close(os.open(final, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            continue
        try:
            os.replace(tmp, final)
        except OSError:
            final.unlink(missing_ok=True)  # our own empty placeholder
            raise
        return final
    raise FileExistsError(f"No free name for {dest}")


def convert_to_jpeg(src: Path, tmp: Path) -> None:
    """HEIC → JPEG keeping EXIF (date, GPS) and colour profile, tagged with the source hash for re-runs."""
    with Image.open(src) as img:
        exif = img.getexif()
        exif[EXIF_ORIENTATION] = 1  # pixels are already rotated upright when decoded
        img.convert("RGB").save(
            tmp, "JPEG", quality=config.JPEG_QUALITY, exif=exif.tobytes(),
            icc_profile=img.info.get("icc_profile"),
            comment=config.CONVERTED_TAG + sha256(src).encode(),
        )
    st = src.stat()
    os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))


def copy_file(src: Path, tmp: Path) -> None:
    """Copy bytes and timestamps only (copy2 would also copy macOS "locked" flags)."""
    shutil.copyfile(src, tmp)
    st = src.stat()
    os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))  # exact, so re-runs recognise the copy quickly
    if tmp.stat().st_size != st.st_size:
        raise OSError(f"Copy is incomplete ({tmp.stat().st_size} of {st.st_size} bytes)")


def transfer(item: Item) -> str:
    """Copy or convert one file. Returns what happened: copied, converted or kept_heic."""
    item.dest.parent.mkdir(parents=True, exist_ok=True)
    # A unique, short, hidden temp file per item: two files never share one, whatever their names.
    fd, tmp_name = tempfile.mkstemp(dir=item.dest.parent, prefix=".", suffix=config.TEMP_SUFFIX)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        if item.action == CONVERT:
            try:
                convert_to_jpeg(item.src, tmp)
                item.dest = place(tmp, item.dest)
                return "converted"
            except Exception as err:  # HEIC that opens but won't decode: keep the original rather than lose it
                if isinstance(err, OSError) and err.errno == errno.ENOSPC:
                    raise
                logger.warning(f"Couldn't convert {item.src} ({err}), copying the original instead")
                tmp.unlink(missing_ok=True)
                item.dest = item.dest.with_suffix(item.src.suffix)
        copy_file(item.src, tmp)
        item.dest = place(tmp, item.dest)
        return "kept_heic" if item.action == CONVERT else "copied"
    finally:
        tmp.unlink(missing_ok=True)


def start_log(destination: Path) -> Path:
    log_file = destination / config.LOG_DIR / f"photobook_{datetime.now():{config.LOG_TIMESTAMP_FORMAT}}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    app_logger = logging.getLogger("modules")  # our messages only, not Pillow's
    app_logger.setLevel(logging.DEBUG)          # every single file goes into the log file
    app_logger.addHandler(handler)
    return log_file


def stop_log(log_file: Path) -> None:
    app_logger = logging.getLogger("modules")
    for handler in [h for h in app_logger.handlers if getattr(h, "baseFilename", None) == str(log_file)]:
        app_logger.removeHandler(handler)
        handler.close()


def run_plan(plan: Plan, progress: Optional[Progress] = None,
             cancel: Optional[threading.Event] = None) -> Result:
    """Copy/convert every file the plan says is new. Keeps going past single-file errors."""
    cancel = cancel or threading.Event()
    result = Result(log_file=start_log(plan.destination))
    todo = plan.todo
    logger.info(f"Sorting {len(todo)} files from {plan.source} to {plan.destination}")

    def work(item: Item) -> Optional[str]:
        return None if cancel.is_set() else transfer(item)

    try:
        with ThreadPoolExecutor(config.WORKERS) as pool:
            futures = {pool.submit(work, item): item for item in todo}
            try:
                for done, future in enumerate(as_completed(futures), 1):
                    item = futures[future]
                    record(result, item, future, cancel)
                    if progress:
                        progress(done, len(todo), item.dest)
            except BaseException:  # Ctrl+C: let running files finish cleanly, skip the queued ones
                cancel.set()
                raise
        result.cancelled = cancel.is_set() and not result.disk_full
        summary = f"{result.copied} copied, {result.converted} converted, {len(result.failed)} failed"
        logger.info(f"Finished: {summary}" + (" (cancelled)" if result.cancelled else ""))
    finally:
        stop_log(result.log_file)
    return result


def record(result: Result, item: Item, future, cancel: threading.Event) -> None:
    try:
        outcome = future.result()
    except OSError as err:
        if err.errno == errno.ENOSPC:
            result.disk_full = True
            cancel.set()  # no point in trying the rest
        result.failed.append((item.src, err.strerror or str(err)))
        logger.error(f"FAILED {item.src}: {err}")
        return
    except Exception as err:  # anything unexpected for one file must not stop the others
        result.failed.append((item.src, str(err)))
        logger.exception(f"FAILED {item.src}")
        return
    if outcome is None:
        return
    setattr(result, outcome, getattr(result, outcome) + 1)
    logger.debug(f"{outcome}: {item.src} -> {item.dest}")
