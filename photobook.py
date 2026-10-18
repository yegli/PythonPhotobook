"""Photobook: sort photos and videos into folders by date. Run without arguments for the window."""

import argparse
import logging
import multiprocessing
import sys
from pathlib import Path

from tqdm import tqdm

from modules.executor import run_plan
from modules.planner import FolderError, make_plan
from modules.report import fun_facts, plan_summary, result_summary

logger = logging.getLogger("photobook")


def run_cli(args: argparse.Namespace) -> int:
    with tqdm(desc="Scanning", unit=" files") as bar:
        def scanned(done: int, total: int, _: Path) -> None:
            bar.total = total
            bar.update(done - bar.n)
        plan = make_plan(Path(args.source), Path(args.destination), args.convert, scanned)
    for line in plan_summary(plan) + [""] + fun_facts(plan):
        logger.info(line)
    if args.dry_run or not plan.todo:
        logger.info("Nothing was changed." if args.dry_run else "Everything is already sorted.")
        return 0
    if not plan.enough_space:
        return 1
    with tqdm(total=len(plan.todo), desc="Sorting", unit=" files") as bar:
        result = run_plan(plan, lambda done, total, path: bar.update(done - bar.n))
    for line in result_summary(result):
        logger.info(line)
    return 1 if result.failed or result.cancelled else 0


def main() -> int:
    if sys.version_info < (3, 9):
        sys.exit("Photobook needs Python 3.9 or newer: https://www.python.org/downloads/")
    if len(sys.argv) == 1:
        from modules.gui import run_gui
        run_gui()
        return 0
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)  # per-file details only go to the log file
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[console])

    parser = argparse.ArgumentParser(description="Sort photos and videos into folders by date. "
                                     "Never changes or deletes the originals. Run without options for a window.")
    parser.add_argument("-s", "--source", required=True, help="folder with the photos to sort")
    parser.add_argument("-d", "--destination", required=True, help="folder to put the sorted photos in")
    parser.add_argument("-c", "--convert", action="store_true", help="convert HEIC photos to JPG")
    parser.add_argument("--dry-run", "-i", "--integrity-check", action="store_true",
                        help="only show what would happen (also shows anything not yet copied)")
    args = parser.parse_args()
    try:
        return run_cli(args)
    except FolderError as err:
        logger.error(str(err))
        return 1
    except KeyboardInterrupt:
        logger.warning("Cancelled. Nothing half-copied was left behind; run again to continue.")
        return 130


if __name__ == "__main__":
    multiprocessing.freeze_support()  # needed by the standalone app (PyInstaller)
    sys.exit(main())
