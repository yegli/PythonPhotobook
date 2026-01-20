from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Config:
    """Configuration constants for photobook organization."""

    IMAGE_EXTENSIONS: Tuple[str, ...] = (
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".webp"
    )

    IMAGES_DIR: str = "Images"
    UNSORTED_DIR: str = "Unsorted_Files"

    YEAR_MONTH_FORMAT: str = "%Y%m_%B"
    DATE_FORMAT: str = "%Y-%m-%d"
    LOG_TIMESTAMP_FORMAT: str = "%Y%m%d_%H%M%S"
    FILENAME_DATE_FORMAT: str = "%Y%m%d"

    JPEG_QUALITY: int = 95


config = Config()
