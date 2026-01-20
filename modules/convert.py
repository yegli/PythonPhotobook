import logging
import os
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError
from pillow_heif import register_heif_opener

from modules.config import config

register_heif_opener()
logger = logging.getLogger(__name__)


def convert_heic_to_jpeg(
    src_path: Path,
    delete_original: bool = True
) -> Optional[Path]:
    """
    Convert HEIC file to JPEG format.

    Args:
        src_path: Path to HEIC file
        delete_original: Whether to delete the original file after conversion

    Returns:
        Path to converted JPEG file, or None if conversion failed
    """
    src_path = Path(src_path)
    dest_path = src_path.with_suffix(".jpg")

    if dest_path.exists():
        logger.info(f"JPEG already exists: {dest_path.name}")
        return dest_path

    try:
        original_mtime = src_path.stat().st_mtime

        with Image.open(src_path) as img:
            img.convert("RGB").save(dest_path, "JPEG", quality=config.JPEG_QUALITY)

        os.utime(dest_path, (original_mtime, original_mtime))
        logger.info(f"Converted {src_path.name} to JPEG")

        if delete_original:
            src_path.unlink()
            logger.debug(f"Deleted original: {src_path.name}")

        return dest_path

    except UnidentifiedImageError as e:
        logger.error(f"Invalid HEIC file: {src_path.name}")
        return None
    except OSError as e:
        logger.error(f"File operation failed for {src_path.name}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error converting {src_path.name}")
        return None
