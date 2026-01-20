import logging
import os
import sys
from pathlib import Path
from typing import List, Tuple

from modules.config import config

logger = logging.getLogger(__name__)


def count_files_with_extensions(directory: Path, extensions: Tuple[str, ...]) -> int:
    """Count files matching given extensions in directory tree."""
    count = 0
    for root, _, files in os.walk(directory):
        for file in files:
            if any(file.lower().endswith(ext) for ext in extensions):
                count += 1
    return count


def check_file_counts(
    source_path: Path,
    dest_path: Path,
    extensions: Tuple[str, ...]
) -> bool:
    """
    Verify source and destination have matching file counts.

    Returns:
        True if counts match, False otherwise
    """
    logger.info("=" * 50)
    logger.info("Checking Image File Count Integrity")
    logger.info("=" * 50)

    source_count = count_files_with_extensions(source_path, extensions)
    dest_count = count_files_with_extensions(dest_path, extensions)

    logger.info(f"Source file count: {source_count}")
    logger.info(f"Destination file count: {dest_count}")

    if source_count == dest_count:
        logger.info("File count matches")
        return True
    else:
        logger.error("File count mismatch detected")
        return False


def check_file_formats(dest_path: Path, extensions: Tuple[str, ...]) -> List[Path]:
    """
    Check for unexpected file formats in Images directory.

    Returns:
        List of files with unexpected formats
    """
    logger.info("=" * 50)
    logger.info("Checking File Format Integrity")
    logger.info("=" * 50)

    allowed = {ext.lower() for ext in extensions}
    images_root = dest_path / config.IMAGES_DIR
    unexpected_files = []

    if not images_root.exists():
        logger.warning(f"Images directory not found: {images_root}")
        return unexpected_files

    for root, _, files in os.walk(images_root):
        for file in files:
            file_path = Path(root) / file
            ext = file_path.suffix.lower()

            if ext and ext not in allowed:
                unexpected_files.append(file_path)

    if unexpected_files:
        logger.warning(f"Found {len(unexpected_files)} unexpected file(s):")
        for file_path in unexpected_files:
            logger.warning(f"  - {file_path}")
    else:
        logger.info("All files match expected formats")

    return unexpected_files


def integrity_check(
    source_path: str,
    destination_path: str,
    IMAGE_EXTENSIONS: Tuple[str, ...]
) -> None:
    """
    Run integrity checks on organized files.

    Verifies file counts match and checks for unexpected formats.
    Exits with error if file counts don't match.
    """
    src = Path(source_path)
    dst = Path(destination_path)

    if not check_file_counts(src, dst, IMAGE_EXTENSIONS):
        logger.error("Integrity check failed: File count mismatch")
        sys.exit(1)

    check_file_formats(dst, IMAGE_EXTENSIONS)
    logger.info("Integrity check complete")
