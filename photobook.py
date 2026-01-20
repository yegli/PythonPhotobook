import argparse
import sys
from datetime import datetime
from pathlib import Path

from modules.config import config
from modules.directories import validate_paths
from modules.integrity import integrity_check
from modules.logger import setup_logger
from modules.sorting import organize_files


def main():
    parser = argparse.ArgumentParser(
        description="Organize photos by date and manage image files"
    )
    parser.add_argument(
        "-s", "--source",
        required=True,
        help="Source directory containing files to organize"
    )
    parser.add_argument(
        "-d", "--destination",
        required=True,
        help="Destination directory for organized files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without moving files"
    )
    parser.add_argument(
        "-c", "--convert",
        action="store_true",
        help="Convert HEIC files to JPEG"
    )
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Write logs to file in destination directory"
    )
    parser.add_argument(
        "-i", "--integrity-check",
        action="store_true",
        help="Verify file counts match between source and destination"
    )

    args = parser.parse_args()

    log_file = None
    if args.log_to_file:
        timestamp = datetime.now().strftime(config.LOG_TIMESTAMP_FORMAT)
        log_file = Path(args.destination) / f"photobook_{timestamp}.log"

    logger = setup_logger("photobook", log_file)

    try:
        validate_paths(args.source, args.destination)
        logger.info("Path validation successful")

        if args.integrity_check:
            logger.info("Running integrity check")
            integrity_check(args.source, args.destination, config.IMAGE_EXTENSIONS)
        else:
            logger.info("Starting file organization")
            organize_files(
                args.source,
                args.destination,
                dry_run=args.dry_run,
                convert_heic=args.convert,
            )

        logger.info("Operation completed successfully")

    except (FileNotFoundError, PermissionError, NotADirectoryError) as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.exception("Unexpected error occurred")
        sys.exit(1)


if __name__ == "__main__":
    main()
