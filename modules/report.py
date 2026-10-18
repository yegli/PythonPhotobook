"""Plain-language summaries for the window and the command line."""

from collections import Counter
from datetime import datetime
from typing import List

from modules import config
from modules.executor import Result
from modules.planner import ALREADY_THERE, DUPLICATE, Plan


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def size_text(n: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "bytes" else f"{n:,.1f} {unit}"
        n /= 1024
    return ""


def plan_summary(plan: Plan) -> List[str]:
    todo = plan.todo
    kinds = Counter(i.kind for i in todo)
    lines = [f"{plural(kinds['photo'], 'photo')} and {plural(kinds['video'], 'video')} "
             f"to sort into {plural(len(plan.days()), 'day')}"]
    if kinds["other"]:
        lines.append(f"{plural(kinds['other'], 'other file')} go to {config.UNSORTED_DIR}")
    if n := plan.count(action=ALREADY_THERE):
        lines.append(f"{plural(n, 'file')} already in the destination (skipped)")
    if n := plan.count(action=DUPLICATE):
        lines.append(f"{plural(n, 'exact duplicate')} in the photo folder (copied only once)")
    if n := sum(i.date_source == "file" for i in todo):
        lines.append(f"{plural(n, 'file')} without a date inside: sorted by file date, which may be off")
    lines.append(f"Needs about {size_text(plan.needed_bytes)} — {size_text(plan.free_bytes)} free")
    if not plan.enough_space:
        lines.append("⚠ Not enough space on the destination drive!")
    lines += [f"⚠ {p}" for p in plan.problems]
    return lines


def fun_facts(plan: Plan) -> List[str]:
    """Oldest photo, busiest day and a little bar chart per year."""
    days = plan.days()
    if not days:
        return []
    def nice(day: str) -> str:
        d = datetime.strptime(day, config.DAY_FORMAT)
        return f"{d.day} {config.MONTHS[d.month - 1]} {d.year}"
    busiest, most = days.most_common(1)[0]
    lines = [f"Oldest: {nice(min(days))}   Newest: {nice(max(days))}",
             f"Busiest day: {nice(busiest)} with {plural(most, 'photo')}", ""]
    years = Counter()
    for day, n in days.items():
        years[day[:4]] += n
    top = max(years.values())
    lines += [f"{year}  {'█' * max(1, round(28 * n / top))} {n:,}" for year, n in sorted(years.items())]
    return lines


def result_summary(result: Result) -> List[str]:
    lines = [f"✅ {plural(result.copied + result.converted + result.kept_heic, 'file')} sorted"
             + (f" ({result.converted:,} converted to JPG)" if result.converted else "")]
    if result.kept_heic:
        lines.append(f"{plural(result.kept_heic, 'HEIC photo')} couldn't be converted, the originals were copied")
    if result.disk_full:
        lines.append("⚠ Stopped: the destination drive is full. Free up space and run again.")
    elif result.cancelled:
        lines.append("Stopped early. Run again any time to continue where you left off.")
    if result.failed:
        lines.append(f"⚠ {plural(len(result.failed), 'file')} couldn't be copied (your originals are fine):")
        lines += [f"    {path.name}: {error}" for path, error in result.failed[:20]]
    lines.append(f"Full list of what happened: {result.log_file}")
    return lines
