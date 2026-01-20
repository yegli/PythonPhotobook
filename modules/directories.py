import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def validate_paths(source_path: str, destination_path: str) -> None:
    """
    Validate source and destination paths.

    Args:
        source_path: Source directory path
        destination_path: Destination directory path

    Raises:
        FileNotFoundError: If source path doesn't exist
        PermissionError: If paths aren't accessible
    """
    src = Path(source_path)
    dst = Path(destination_path)

    if not src.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")

    if not src.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_path}")

    if not dst.exists():
        try:
            dst.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created destination directory: {destination_path}")
        except PermissionError as e:
            raise PermissionError(
                f"Cannot create destination path: {destination_path}"
            ) from e
    else:
        logger.debug(f"Destination directory exists: {destination_path}")

    if not os.access(src, os.R_OK):
        raise PermissionError(f"Source path not readable: {source_path}")

    if not os.access(dst, os.W_OK):
        raise PermissionError(f"Destination path not writable: {destination_path}")
