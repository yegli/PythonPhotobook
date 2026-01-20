import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from tqdm import tqdm

from modules.config import config
from modules.convert import convert_heic_to_jpeg

logger = logging.getLogger(__name__)


def get_earliest_date(file_path: Path) -> datetime:
    """Get earliest timestamp from file metadata."""
    try:
        stat_info = file_path.stat()
        modified_time = stat_info.st_mtime
        created_time = getattr(stat_info, "st_birthtime", stat_info.st_ctime)
        earliest_time = min(modified_time, created_time)
        return datetime.fromtimestamp(earliest_time)
    except FileNotFoundError:
        logger.warning(f"File not found: {file_path}, using current time")
        return datetime.now()


def extract_date_from_filename(file_name: str) -> Optional[datetime]:
    """Extract date from filename with format YYYYMMDD_*."""
    try:
        date_part = file_name.split('_')[0]
        return datetime.strptime(date_part, config.FILENAME_DATE_FORMAT)
    except (ValueError, IndexError):
        return None


def update_file_date(file_path: Path, date: datetime) -> bool:
    """Update file modification time to match extracted date."""
    try:
        mod_time = time.mktime(date.timetuple())
        os.utime(file_path, (mod_time, mod_time))
        logger.debug(f"Updated date for {file_path.name} to {date:%Y-%m-%d}")
        return True
    except OSError as e:
        logger.warning(f"Failed to update date for {file_path.name}: {e}")
        return False


def get_file_date(file_path: Path, allow_update: bool = True) -> datetime:
    """
    Get the appropriate date for a file.

    If file date is today, tries to extract from filename.
    If allow_update is True, updates the file's modification time.
    """
    earliest_time = get_earliest_date(file_path)

    if earliest_time.date() == datetime.now().date():
        extracted_date = extract_date_from_filename(file_path.name)

        if extracted_date:
            if allow_update:
                update_file_date(file_path, extracted_date)
            return extracted_date
        else:
            if allow_update:
                logger.debug(f"No date in filename, using current date: {file_path.name}")

    return earliest_time


def build_destination_path(
    file_path: Path,
    dest_dir: Path,
    allow_update: bool = True,
    dest_basename: Optional[str] = None
) -> Optional[Path]:
    """
    Build destination path based on file date.

    Returns path like: dest_dir/Images/YYYYMM_Month/YYYY-MM-DD/filename
    """
    file_date = get_file_date(file_path, allow_update)

    year_month = file_date.strftime(config.YEAR_MONTH_FORMAT)
    date_folder = file_date.strftime(config.DATE_FORMAT)
    file_name = dest_basename or file_path.name

    return dest_dir / config.IMAGES_DIR / year_month / date_folder / file_name


def should_convert_file(file_path: Path, convert_enabled: bool) -> bool:
    """Check if file should be converted from HEIC to JPEG."""
    return file_path.suffix.lower() == ".heic" and convert_enabled


def get_destination_for_file(
    file_path: Path,
    dest_dir: Path,
    is_image: bool,
    convert_enabled: bool,
    allow_update: bool = False
) -> Tuple[Path, Optional[str]]:
    """
    Determine destination path for a file.

    Returns:
        Tuple of (destination_path, converted_basename or None)
    """
    dest_basename = None

    if is_image:
        if should_convert_file(file_path, convert_enabled):
            dest_basename = file_path.stem + ".jpg"

        dest_path = build_destination_path(
            file_path,
            dest_dir,
            allow_update=allow_update,
            dest_basename=dest_basename
        )
    else:
        ext_folder = file_path.suffix[1:].upper() or "NO_EXT"
        dest_path = dest_dir / config.UNSORTED_DIR / ext_folder / file_path.name

    return dest_path, dest_basename


def collect_files_to_process(
    source_dir: Path,
    dest_dir: Path,
    convert_enabled: bool
) -> int:
    """Count how many files need to be processed."""
    count = 0
    image_exts = set(config.IMAGE_EXTENSIONS)

    for root, _, files in os.walk(source_dir):
        for file in files:
            if file.startswith('.'):
                continue

            file_path = Path(root) / file
            is_image = file_path.suffix.lower() in image_exts

            dest_path, _ = get_destination_for_file(
                file_path, dest_dir, is_image, convert_enabled, allow_update=False
            )

            if dest_path and not dest_path.exists():
                count += 1

    return count


def process_file(
    src_path: Path,
    dest_path: Path,
    dry_run: bool,
    convert_enabled: bool
) -> bool:
    """
    Process a single file (convert if needed, copy to destination).

    Returns:
        True if file was processed, False otherwise
    """
    if dest_path.exists():
        logger.debug(f"File already exists, skipping: {dest_path.name}")
        return False

    current_src = src_path

    if should_convert_file(src_path, convert_enabled):
        converted = convert_heic_to_jpeg(src_path, delete_original=not dry_run)
        if not converted:
            logger.warning(f"Conversion failed: {src_path.name}")
            return False
        current_src = converted

    if dry_run:
        logger.info(f"DRY RUN: Would copy {current_src.name} to {dest_path}")
    else:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_src, dest_path)

    return True


def organize_files(
    source_dir: str,
    dest_dir: str,
    dry_run: bool = False,
    convert_heic: bool = False
) -> None:
    """
    Organize files from source to destination directory.

    Images are sorted by date, other files go to Unsorted_Files.
    """
    src_path = Path(source_dir)
    dst_path = Path(dest_dir)
    image_exts = set(config.IMAGE_EXTENSIONS)

    unsorted_dir = dst_path / config.UNSORTED_DIR
    unsorted_dir.mkdir(exist_ok=True)

    logger.info("Counting files to process...")
    total_files = collect_files_to_process(src_path, dst_path, convert_heic)

    if total_files == 0:
        logger.info("No new files to process")
        return

    logger.info(f"Processing {total_files} files...")

    with tqdm(total=total_files, desc="Organizing files") as pbar:
        for root, _, files in os.walk(src_path):
            for file in files:
                if file.startswith('.'):
                    continue

                file_path = Path(root) / file
                is_image = file_path.suffix.lower() in image_exts

                try:
                    dest_path, _ = get_destination_for_file(
                        file_path,
                        dst_path,
                        is_image,
                        convert_heic,
                        allow_update=not dry_run
                    )

                    if process_file(file_path, dest_path, dry_run, convert_heic):
                        pbar.update(1)

                except FileNotFoundError:
                    logger.warning(f"File disappeared: {file_path}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing {file_path.name}: {e}")
                    continue

    logger.info("File organization complete")


# Legacy function name for backwards compatibility
def image_sorting(
    source_directory: str,
    destination_directory: str,
    IMAGE_EXTENSIONS: Tuple[str, ...],
    dry_run: bool = False,
    convertor: bool = False
) -> None:
    """Legacy wrapper for organize_files (kept for compatibility)."""
    organize_files(source_directory, destination_directory, dry_run, convertor)
