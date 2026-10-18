"""All constants in one place."""

PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".heic", ".heif", ".webp", ".tif", ".tiff",
    ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf",
}
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".3gp", ".avi", ".mts", ".m2ts", ".mkv"}
# Videos whose header holds a QuickTime/MP4 creation time we can read.
QUICKTIME_EXTENSIONS = {".mov", ".mp4", ".m4v", ".3gp"}

IMAGES_DIR = "Images"
UNSORTED_DIR = "Unsorted_Files"
LOG_DIR = "Photobook_Logs"

# Hardcoded so folder names don't change with the computer's language.
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
DAY_FORMAT = "%Y-%m-%d"
LOG_TIMESTAMP_FORMAT = "%Y-%m-%d_%H%M%S"

# Never imported: system clutter from macOS, Windows and NAS boxes.
JUNK_FILES = {"thumbs.db", "desktop.ini", "icon\r"}
JUNK_DIRS = {"@eadir", "$recycle.bin", "system volume information", "#recycle"}
# Inside an Apple Photos library only the originals are real photos.
PHOTOS_LIBRARY_ORIGINALS = ("originals", "Masters")

JPEG_QUALITY = 95
# A JPEG without our tag counts as a conversion of a same-named HEIC if, in 128x128 grey versions,
# less than 0.5% of the pixels differ by more than 24 (of 255). JPEG re-encoding stays far below that.
LOOKS_SAME_SIZE = 128
LOOKS_SAME_PIXEL_DIFF = 24
LOOKS_SAME_MAX_SHARE = 0.005
# Files whose times differ less than this count as "same time" (FAT/exFAT store times in 2-second steps).
SAME_TIME_SECONDS = 2
# Files with the same name, size and time: compare this much at the start and the end.
QUICK_COMPARE_BYTES = 64 * 1024
CONVERTED_TAG = b"photobook-source-sha256:"
TEMP_SUFFIX = ".photobook-tmp"
# Converted JPEGs are usually larger than the HEIC they come from.
CONVERT_SIZE_FACTOR = 2
SPACE_MARGIN_BYTES = 200 * 1024 * 1024
WORKERS = 4
