"""The Photobook window: pick two folders, preview, sort. Work runs in a background thread."""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from PIL import Image, ImageTk

from modules.executor import run_plan
from modules.planner import Cancelled, FolderError, Plan, kind_of, make_plan
from modules.report import fun_facts, plan_summary, result_summary

logger = logging.getLogger(__name__)

SETTINGS = Path.home() / ".photobook.json"
THUMB_SIZE = (260, 200)
THUMB_EVERY = 0.35  # seconds between preview pictures while sorting


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    try:
        SETTINGS.write_text(json.dumps(settings))
    except OSError:
        pass  # remembering folders is a convenience, never a reason to fail


def open_folder(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])


def thumbnail(path: Path) -> Optional[Image.Image]:
    try:
        with Image.open(path) as img:
            img.draft("RGB", THUMB_SIZE)  # JPEGs decode at reduced size: fast
            img.thumbnail(THUMB_SIZE)
            return img.convert("RGB")
    except Exception:  # a preview picture is decoration; skip anything odd
        return None


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.plan: Optional[Plan] = None
        self.busy = False
        self.closing = False
        settings = load_settings()
        self.source = tk.StringVar(value=settings.get("source", ""))
        self.destination = tk.StringVar(value=settings.get("destination", ""))
        self.convert = tk.BooleanVar(value=settings.get("convert", True))
        self.status = tk.StringVar()
        self.build()
        for var in (self.source, self.destination, self.convert):
            var.trace_add("write", lambda *_: self.reset())
        self.reset()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll()

    # ---- layout -------------------------------------------------------------------------------------------

    def build(self) -> None:
        self.root.title("Photobook")
        self.root.minsize(720, 600)
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="Photobook", font=("", 24, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(frame, text="Sorts your photos and videos into folders by date.\n"
                              "Your original files are never changed, moved or deleted.",
                  foreground="gray").grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))

        self.pickers = []
        for row, (text, var, title) in enumerate([
            ("1. Photos to sort", self.source, "Choose the folder with your photos"),
            ("2. Save sorted photos to", self.destination, "Choose where the sorted photos should go"),
        ], start=2):
            ttk.Label(frame, text=text, font=("", 13, "bold")).grid(row=row, column=0, sticky="w", padx=(0, 10))
            ttk.Entry(frame, textvariable=var, state="readonly").grid(row=row, column=1, sticky="ew", pady=4)
            button = ttk.Button(frame, text="Choose…", command=lambda v=var, t=title: self.choose(v, t))
            button.grid(row=row, column=2, padx=(8, 0))
            self.pickers.append(button)

        self.convert_box = ttk.Checkbutton(frame, variable=self.convert,
                                           text="Convert iPhone photos (HEIC) to JPG so they open everywhere")
        self.convert_box.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 10))

        middle = ttk.Frame(frame)
        middle.grid(row=5, column=0, columnspan=3, sticky="nsew")
        middle.columnconfigure(0, weight=1)
        middle.columnconfigure(1, minsize=THUMB_SIZE[0] + 20)  # fixed: changing pictures must not resize the window
        middle.rowconfigure(0, weight=1)
        self.text = tk.Text(middle, height=14, wrap="word", relief="flat", padx=12, pady=10,
                            font=("Menlo" if sys.platform == "darwin" else "Consolas", 12))
        self.text.grid(row=0, column=0, sticky="nsew")
        self.picture = ttk.Label(middle, anchor="center")
        self.picture.grid(row=0, column=1, sticky="n", padx=(12, 0))

        self.bar = ttk.Progressbar(frame, mode="determinate")
        self.bar.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 4))
        ttk.Label(frame, textvariable=self.status).grid(row=7, column=0, columnspan=3, sticky="w")

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(12, 0))
        self.open_button = ttk.Button(buttons, text="Open sorted folder", command=self.open_destination)
        self.open_button.pack(side="left", padx=(0, 8))
        self.main_button = ttk.Button(buttons, text="Preview", command=self.on_main, width=16)
        self.main_button.pack(side="left")
        self.root.bind("<Return>", lambda _: self.on_main())

    def show(self, lines: list) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", "\n".join(lines))
        self.text.configure(state="disabled")

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in (*self.pickers, self.convert_box):
            widget.configure(state=state)

    # ---- actions ------------------------------------------------------------------------------------------

    def choose(self, var: tk.StringVar, title: str) -> None:
        folder = filedialog.askdirectory(title=title, initialdir=var.get() or Path.home())
        if folder:
            var.set(folder)

    def reset(self) -> None:
        """Back to the start: something changed, so any earlier preview is outdated."""
        if self.busy:
            return
        self.plan = None
        self.bar.configure(value=0)
        self.picture.configure(image="")
        ready = bool(self.source.get() and self.destination.get())
        self.main_button.configure(text="Preview", state="normal" if ready else "disabled")
        destination = self.destination.get()
        self.open_button.configure(state="normal" if destination and Path(destination).is_dir() else "disabled")
        self.status.set("Click Preview to see what will happen. Nothing is copied yet."
                        if ready else "Choose the two folders to start.")
        self.show(["How it works:", "",
                   "1. Choose the folder with your photos (for example your phone backup or a USB stick).",
                   "2. Choose where the sorted photos should go.",
                   "3. Click Preview. You'll see what will happen; nothing is copied yet.",
                   "4. Click Start sorting.", "",
                   "Photos end up in folders like Images/202501_January/2025-01-20/",
                   "Running it again later only adds what's new."])
        save_settings({"source": self.source.get(), "destination": self.destination.get(),
                       "convert": self.convert.get()})

    def on_main(self) -> None:
        if str(self.main_button["state"]) == "disabled":  # Enter key while the button is greyed out
            return
        if self.busy:
            self.cancel.set()
            self.main_button.configure(state="disabled")
            self.status.set("Stopping after the current files…")
        elif self.plan and self.plan.todo and self.plan.enough_space:
            self.start_sorting()
        else:
            self.start_preview()

    def start_preview(self) -> None:
        source, destination, convert = Path(self.source.get()), Path(self.destination.get()), self.convert.get()
        self.show(["Looking at your photos…"])
        self.background(lambda: make_plan(source, destination, convert, self.progress_scan, self.cancel), "plan")

    def start_sorting(self) -> None:
        plan = self.plan
        self.background(lambda: run_plan(plan, self.progress_sort, self.cancel), "result")

    def background(self, work: Callable, event: str) -> None:
        self.cancel.clear()
        self.last_thumb = 0.0
        self.set_busy(True)
        self.main_button.configure(text="Cancel", state="normal")

        def run() -> None:
            try:
                self.events.put((event, work()))
            except Cancelled:
                self.events.put(("cancelled", None))
            except FolderError as err:
                self.events.put(("problem", str(err)))
            except Exception as err:  # show anything unexpected instead of silently dying
                logger.exception("Unexpected error")
                self.events.put(("problem", f"Something went wrong: {err}"))
        threading.Thread(target=run, daemon=True).start()

    # Called from the worker thread: only put events on the queue, never touch widgets.
    def progress_scan(self, done: int, total: int, path: Path) -> None:
        self.events.put(("progress", (done, total, f"Looking at {done:,} of {total:,}: {path.name}")))
        self.maybe_thumbnail(path)

    def progress_sort(self, done: int, total: int, path: Path) -> None:
        self.events.put(("progress", (done, total, f"Sorted {done:,} of {total:,}: {path.name}")))
        self.maybe_thumbnail(path)

    def maybe_thumbnail(self, path: Path) -> None:
        if time.monotonic() - self.last_thumb > THUMB_EVERY and kind_of(path) == "photo":
            self.last_thumb = time.monotonic()
            if img := thumbnail(path):
                self.events.put(("thumb", img))

    # ---- events from the worker ---------------------------------------------------------------------------

    def poll(self) -> None:
        try:
            while True:
                event, value = self.events.get_nowait()
                getattr(self, f"on_{event}")(value)
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.root.destroy()
            return
        self.root.after(50, self.poll)

    def on_progress(self, value: tuple) -> None:
        done, total, text = value
        self.bar.configure(maximum=max(total, 1), value=done)
        self.status.set(text)

    def on_thumb(self, img: Image.Image) -> None:
        self.photo = ImageTk.PhotoImage(img)  # keep a reference or Tk shows nothing
        self.picture.configure(image=self.photo)

    def on_plan(self, plan: Plan) -> None:
        self.finish()
        self.plan = plan
        self.show(plan_summary(plan) + [""] + fun_facts(plan))
        if not plan.todo:
            self.status.set("Everything is already sorted. Nothing to do ✨")
        elif not plan.enough_space:
            self.status.set("Not enough space on the destination drive.")
        else:
            self.status.set("Happy with this? Click Start sorting.")
            self.main_button.configure(text="Start sorting")

    def on_result(self, result) -> None:
        self.finish()
        self.plan = None
        self.show(result_summary(result))
        self.status.set("Done ✨" if not (result.failed or result.cancelled) else "Finished with notes, see above.")
        self.open_button.configure(state="normal")

    def on_cancelled(self, _) -> None:
        self.finish()
        self.reset()
        self.status.set("Cancelled. Nothing was changed.")

    def on_problem(self, message: str) -> None:
        self.finish()
        self.reset()
        messagebox.showwarning("Photobook", message)

    def finish(self) -> None:
        self.set_busy(False)
        self.main_button.configure(text="Preview", state="normal")

    def open_destination(self) -> None:
        if Path(self.destination.get()).is_dir():
            open_folder(Path(self.destination.get()))

    def on_close(self) -> None:
        if not self.busy:
            self.root.destroy()
        elif messagebox.askyesno("Photobook", "Photobook is still working. Stop and close?\n"
                                              "Files already copied stay where they are."):
            self.closing = True
            self.cancel.set()


def run_gui() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
