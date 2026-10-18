"""Safety tests, plus a demo folder to play with.

    python test_photobook.py                 run the tests
    python test_photobook.py --demo FOLDER   create a folder of sample photos to try the app on
"""

import errno
import hashlib
import os
import random
import struct
import sys
import tempfile
import unicodedata
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from modules import config, executor
from modules.dates import filename_date, taken_date, video_date
from modules.executor import run_plan
from modules.planner import FolderError, make_plan


def photo(path: Path, taken: datetime = None, color=(200, 80, 60), size=(640, 480), label="", orientation=1) -> Path:
    """A small JPEG/PNG/HEIC with an optional EXIF date taken."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    for y in range(0, size[1], 8):  # soft gradient so thumbnails look like something
        draw.line([(0, y), (size[0], y)], fill=tuple(min(255, c + y // 6) for c in color))
    draw.text((20, 20), label or path.name, fill="white", font_size=36)
    exif = Image.Exif()
    if taken:
        exif.get_ifd(0x8769)[36867] = taken.strftime("%Y:%m:%d %H:%M:%S")
    exif[0x0112] = orientation
    img.save(path, exif=exif.tobytes())
    return path


def video(path: Path, taken: datetime) -> Path:
    """A fake .mp4 that only holds the header atoms we read the date from."""
    seconds = int((taken.astimezone(timezone.utc) - datetime(1904, 1, 1, tzinfo=timezone.utc)).total_seconds())
    mvhd_body = struct.pack(">I I I I I", 0, seconds, seconds, 600, 6000) + bytes(80)
    mvhd = struct.pack(">I4s", 8 + len(mvhd_body), b"mvhd") + mvhd_body
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    ftyp = struct.pack(">I4s", 16, b"ftyp") + b"isom" + bytes(4)
    mdat = struct.pack(">I4s", 8 + 1000, b"mdat") + os.urandom(1000)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ftyp + mdat + moov)  # moov after mdat, like most phones
    return path


def make_sample(src: Path) -> None:
    """Every tricky case in one folder."""
    day = datetime(2024, 7, 14, 10, 0)
    photo(src / "Phone/IMG_0001.JPG", day)
    photo(src / "Phone/IMG_0002.HEIC", day, color=(40, 120, 200), orientation=6)  # rotated iPhone photo
    photo(src / "Camera/IMG_0001.JPG", day, color=(30, 160, 90))           # same name, different photo
    (src / "Backup").mkdir()
    (src / "Backup/IMG_0001.JPG").write_bytes((src / "Phone/IMG_0001.JPG").read_bytes())  # exact duplicate
    photo(src / "WhatsApp/IMG-20231224-WA0001.jpg")                        # no EXIF, date in name
    photo(src / "Screenshots/Screenshot 2025-01-20 at 15.30.00.png")
    video(src / "Videos/clip.mp4", datetime(2022, 6, 1, 18, 30))
    old = photo(src / "old_scan.jpg")                                      # no date at all
    os.utime(old, (datetime(2015, 3, 3).timestamp(),) * 2)
    (src / "broken.heic").write_bytes(b"this is not really a photo")       # can't be converted
    os.utime(src / "broken.heic", (datetime(2015, 3, 3).timestamp(),) * 2)
    (src / "docs").mkdir()
    (src / "docs/letter.pdf").write_bytes(b"%PDF-1.4 fake")
    (src / "docs/README").write_text("no extension")
    (src / ".DS_Store").write_bytes(b"junk")
    (src / "Phone/._IMG_0001.JPG").write_bytes(b"junk")
    (src / "Thumbs.db").write_bytes(b"junk")
    photo(src / ".hidden/secret.jpg", day)
    photo(src / "My.photoslibrary/originals/A/library_photo.jpg", day)
    photo(src / "My.photoslibrary/resources/derivatives/thumbnail.jpg", day)


def snapshot(folder: Path) -> dict:
    """Content, time and permissions of every file, to prove nothing was touched."""
    return {p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns, p.stat().st_mode)
            for p in folder.rglob("*") if p.is_file()}


def files_in(folder: Path) -> set:
    return {str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file() and config.LOG_DIR not in p.parts}


class DateTests(unittest.TestCase):
    def test_filename_dates(self):
        self.assertEqual(filename_date("IMG_20250120_153000.jpg"), datetime(2025, 1, 20))
        self.assertEqual(filename_date("PXL_20230101_000000.jpg"), datetime(2023, 1, 1))
        self.assertEqual(filename_date("Screenshot 2025-01-20 at 15.30.00.png"), datetime(2025, 1, 20))
        self.assertEqual(filename_date("IMG-20231224-WA0001.jpg"), datetime(2023, 12, 24))
        self.assertIsNone(filename_date("IMG_0001.JPG"))
        self.assertIsNone(filename_date("2023-02-30.jpg"))          # impossible date
        self.assertIsNone(filename_date("1612020120123.jpg"))       # digits inside a longer number
        self.assertIsNone(filename_date("20990101.jpg"))            # future
        self.assertIsNone(filename_date("VID_202401010_x.mov"))     # digits continue on the right
        self.assertEqual(filename_date("IMG20250120153000.jpg"), datetime(2025, 1, 20))  # glued-on time

    def test_photo_and_video_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.assertEqual(taken_date(photo(tmp / "a.jpg", datetime(2020, 5, 6, 7, 8, 9))),
                             (datetime(2020, 5, 6, 7, 8, 9), "photo"))
            self.assertEqual(taken_date(photo(tmp / "b.heic", datetime(2021, 1, 2))), (datetime(2021, 1, 2), "photo"))
            self.assertEqual(video_date(video(tmp / "c.mov", datetime(2022, 6, 1, 18, 30))), datetime(2022, 6, 1, 18, 30))
            (tmp / "d.mp4").write_bytes(b"garbage" * 10)
            self.assertIsNone(video_date(tmp / "d.mp4"))
            self.assertEqual(taken_date(photo(tmp / "IMG_20190304.jpg"))[1], "name")
            self.assertEqual(taken_date(photo(tmp / "plain.jpg"))[1], "file")
            exif = Image.Exif()
            exif.get_ifd(0x8769)[36867] = b"2020:05:06 07:08:09\x00"  # date stored as bytes
            Image.new("RGB", (8, 8)).save(tmp / "e.jpg", exif=exif.tobytes())
            self.assertEqual(taken_date(tmp / "e.jpg"), (datetime(2020, 5, 6, 7, 8, 9), "photo"))


class SortingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.src = Path(self._tmp.name) / "src"
        self.dst = Path(self._tmp.name) / "dst"
        make_sample(self.src)

    def tearDown(self):
        self._tmp.cleanup()

    def sort(self, convert=True):
        before = snapshot(self.src)
        plan = make_plan(self.src, self.dst, convert)
        result = run_plan(plan)
        self.assertEqual(snapshot(self.src), before, "the source folder must never change")
        self.assertEqual([p for p in self.dst.rglob("*") if config.TEMP_SUFFIX in p.name], [])
        return plan, result

    def test_preview_writes_nothing(self):
        make_plan(self.src, self.dst, True)
        self.assertFalse(self.dst.exists())

    def test_sorts_everything_and_rerun_is_a_no_op(self):
        plan, result = self.sort()
        day = "Images/202407_July/2024-07-14/"
        self.assertEqual(files_in(self.dst), {
            day + "IMG_0001.JPG",
            day + "IMG_0001 (2).JPG",                 # name clash: kept both
            day + "IMG_0002.jpg",                     # converted
            day + "library_photo.jpg",                # only originals from a Photos library
            "Images/202312_December/2023-12-24/IMG-20231224-WA0001.jpg",
            "Images/202501_January/2025-01-20/Screenshot 2025-01-20 at 15.30.00.png",
            "Images/202206_June/2022-06-01/clip.mp4",
            "Images/201503_March/2015-03-03/old_scan.jpg",
            "Images/201503_March/2015-03-03/broken.heic",      # conversion failed: original kept
            "Unsorted_Files/PDF/letter.pdf",
            "Unsorted_Files/NO_EXT/README",
        })
        self.assertEqual((result.copied, result.converted, result.kept_heic, result.failed), (10, 1, 0, []))
        self.assertEqual(plan.count(action="duplicate"), 1)
        self.assertEqual((self.dst / day / "IMG_0001.JPG").read_bytes(), (self.src / "Phone/IMG_0001.JPG").read_bytes())

        with Image.open(self.dst / day / "IMG_0002.jpg") as converted:
            self.assertEqual(converted.size, (480, 640), "rotated photo is stored upright")
            self.assertEqual(converted.getexif().get(0x0112), 1)
            self.assertEqual(converted.getexif().get_ifd(0x8769).get(36867), "2024:07:14 10:00:00", "EXIF kept")

        again = make_plan(self.src, self.dst, True)
        self.assertEqual(again.todo, [], "second run finds everything already there")

    def test_never_overwrites_existing_files(self):
        existing = photo(self.dst / "Images/202407_July/2024-07-14/IMG_0001.JPG", color=(0, 0, 0))
        mine = existing.read_bytes()
        self.sort()
        self.assertEqual(existing.read_bytes(), mine)
        self.assertTrue((existing.parent / "IMG_0001 (3).JPG").exists())

    def test_recognises_files_from_older_versions(self):
        # The old version converted HEIC without EXIF or tag, and sorted by file time into other folders.
        with Image.open(self.src / "Phone/IMG_0002.HEIC") as heic:
            old = photo(self.dst / "Images/202601_January/2026-01-05/IMG_0002.jpg")
            heic.convert("RGB").save(old, quality=95)
        st = (self.src / "Phone/IMG_0002.HEIC").stat()
        os.utime(old, (st.st_atime, st.st_mtime))  # the old version kept the HEIC's file time
        old_copy = self.dst / "Images/202601_January/2026-01-05/IMG_0001.JPG"
        executor.shutil.copy2(self.src / "Phone/IMG_0001.JPG", old_copy)
        _, result = self.sort()
        day = self.dst / "Images/202407_July/2024-07-14"
        self.assertFalse((day / "IMG_0002.jpg").exists(), "old conversion recognised")
        self.assertEqual((day / "IMG_0001.JPG").read_bytes(), (self.src / "Camera/IMG_0001.JPG").read_bytes(),
                         "old copy recognised, so only the different photo with that name is new")
        self.assertFalse((day / "IMG_0001 (2).JPG").exists())

    def test_different_picture_with_same_name_is_not_skipped(self):
        photo(self.dst / "Images/202407_July/2024-07-14/IMG_0002.jpg", color=(250, 250, 0))
        self.sort()
        self.assertTrue((self.dst / "Images/202407_July/2024-07-14/IMG_0002 (2).jpg").exists())

    def test_failed_conversion_keeps_the_original(self):
        with mock.patch.object(executor, "convert_to_jpeg", side_effect=ValueError("decoder broke")):
            _, result = self.sort()
        self.assertEqual(result.kept_heic, 1)
        kept = self.dst / "Images/202407_July/2024-07-14/IMG_0002.HEIC"
        self.assertEqual(kept.read_bytes(), (self.src / "Phone/IMG_0002.HEIC").read_bytes())
        self.assertEqual(make_plan(self.src, self.dst, True).todo, [], "kept original recognised on re-run")

    def test_cancel_copies_nothing_more(self):
        cancel = executor.threading.Event()
        cancel.set()
        result = run_plan(make_plan(self.src, self.dst, True), cancel=cancel)
        self.assertTrue(result.cancelled)
        self.assertEqual(files_in(self.dst), set())

    def test_names_that_differ_only_in_accent_encoding_or_case(self):
        nfc, nfd = unicodedata.normalize("NFC", "café_20240101.mov"), unicodedata.normalize("NFD", "café_20240101.mov")
        (self.src / "A").mkdir()
        (self.src / "B").mkdir()
        (self.src / "A" / nfc).write_bytes(b"A" * 50_000)
        (self.src / "B" / nfd).write_bytes(b"B" * 50_000)
        (self.src / "A/Strasse_20240101.txt").write_bytes(b"one")
        (self.src / "B/STRASSE_20240101.txt").write_bytes(b"two")
        _, result = self.sort()
        self.assertEqual(result.failed, [])
        movies = sorted(p.read_bytes()[:1] for p in self.dst.rglob("caf*_20240101*.mov"))
        self.assertEqual(movies, [b"A", b"B"], "both kept, neither corrupted")
        self.assertEqual(sorted(p.read_bytes() for p in self.dst.rglob("*_20240101*.txt")), [b"one", b"two"])

    def test_no_overwrite_without_hard_links(self):
        target = self.dst / "x" / "IMG.jpg"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"precious")
        tmp = target.parent / ".tmp"
        tmp.write_bytes(b"new")
        with mock.patch.object(executor.os, "link", side_effect=PermissionError("no hard links on exFAT")):
            final = executor.place(tmp, target)
        self.assertEqual(target.read_bytes(), b"precious")
        self.assertEqual((final.name, final.read_bytes()), ("IMG (2).jpg", b"new"))

    def test_similar_photo_with_same_name_from_another_day_is_copied(self):
        with Image.open(self.src / "Phone/IMG_0002.HEIC") as heic:  # looks the same, but other day and time
            other = photo(self.dst / "Images/201901_January/2019-01-05/IMG_0002.jpg")
            heic.convert("RGB").save(other, quality=95)
        os.utime(other, (datetime(2019, 1, 5).timestamp(),) * 2)
        self.sort()
        self.assertTrue((self.dst / "Images/202407_July/2024-07-14/IMG_0002.jpg").exists())

    def test_odd_files_are_reported_not_fatal(self):
        (self.dst / "Images/x").mkdir(parents=True)
        (self.dst / "Images/x/IMG-20231224-WA0001.jpg").symlink_to(self.dst / "missing.jpg")  # broken link
        photo(self.src / "Phone/IMG_0003.jpg").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 50)   # lies about type
        Image.new("RGB", (8, 8)).save(self.dst / "Images/x/IMG_0002.jpg", "PNG", pnginfo=None)
        _, result = self.sort()
        self.assertEqual(result.failed, [])
        self.assertTrue((self.dst / "Images/202312_December/2023-12-24/IMG-20231224-WA0001.jpg").exists())

    def test_linked_folders_are_followed_once(self):
        os.symlink(self.src / "Phone", self.src / "Phone link")
        os.symlink(self.src, self.src / "Phone/loop")
        plan = make_plan(self.src, self.dst, True)
        self.assertEqual(sum(i.src.name == "IMG_0002.HEIC" for i in plan.items), 1)

    def test_same_name_size_and_time_but_different_content(self):
        a, b = self.src / "cam1/DSCF0001.RAF", self.dst / "Images/x/DSCF0001.RAF"
        for path, fill in ((a, b"A"), (b, b"B")):
            path.parent.mkdir(parents=True)
            path.write_bytes(b"same header" + fill * 200_000)
            os.utime(path, (1e9, 1e9))
        plan = make_plan(self.src, self.dst, True)
        self.assertEqual(next(i.action for i in plan.items if i.src == a), "copy")

    def test_refuses_dangerous_folders(self):
        with self.assertRaises(FolderError):
            make_plan(self.src, self.src, False)
        with self.assertRaises(FolderError):
            make_plan(self.src, self.src / "sorted", False)
        with self.assertRaises(FolderError):
            make_plan(self.src / "missing", self.dst, False)
        if (Path(str(self.src).upper())).exists():  # case-insensitive drive (macOS/Windows default)
            with self.assertRaises(FolderError):
                make_plan(self.src, Path(str(self.src).upper()) / "Sorted", False)

    def test_disk_full_stops_cleanly(self):
        def full(*_):
            raise OSError(errno.ENOSPC, "No space left on device")
        with mock.patch.object(executor.shutil, "copyfile", full), mock.patch.object(executor, "convert_to_jpeg", full):
            _, result = self.sort()
        self.assertTrue(result.disk_full)
        self.assertEqual(files_in(self.dst), set())
        _, result = self.sort()  # once there is space again, everything gets sorted
        self.assertEqual(result.failed, [])
        self.assertEqual(result.copied + result.converted + result.kept_heic, 11)


class TimeLeftTests(unittest.TestCase):
    def test_time_left(self):
        from modules.gui import time_left
        self.assertEqual(time_left(1, 10, 100), "")                      # too early to guess
        self.assertEqual(time_left(10, 2, 100), "")
        self.assertEqual(time_left(10, 100, 100), "")                    # finished
        self.assertEqual(time_left(10, 50, 100), " · less than a minute left")
        self.assertEqual(time_left(60, 10, 110), " · about 10 min left")
        self.assertEqual(time_left(60, 10, 1810), " · about 3.0 hours left")


def make_demo(folder: Path, count: int = 400) -> None:
    """A playground: a few hundred colourful photos spread over two years, plus all the tricky cases."""
    make_sample(folder / "Tricky cases")
    rng = random.Random(42)
    start = datetime(2024, 1, 1)
    for n in range(count):
        taken = start + timedelta(days=rng.randrange(600), hours=rng.randrange(8, 20))
        color = tuple(rng.randrange(40, 200) for _ in range(3))
        ext = rng.choice([".jpg", ".jpg", ".jpg", ".heic", ".png"])
        photo(folder / rng.choice(["iPhone", "Camera", "Downloads"]) / f"IMG_{n:04d}{ext}", taken, color,
              size=(1200, 900), label=f"{taken:%d %B %Y}")
    print(f"Demo photos created in {folder}")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--demo":
        make_demo(Path(sys.argv[2]).expanduser())
    else:
        unittest.main()
