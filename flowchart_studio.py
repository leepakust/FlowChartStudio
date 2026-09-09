# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright 2026 Patrick Lee
"""Flowchart Studio -- a small desktop UI around flowchart.py.

Lets you write/edit a diagram JSON spec (flowchart/state-machine, timeline,
sequence, or fishbone diagram) and see the rendered PNG update live, without going
through mkdocx.py / build.py / a Word rebuild at all. Uses the exact same
render functions the design docs are built with, so what you see here is
byte-identical to what would land in a docx figure.

Editing in another editor (Notepad++, VS Code, ...) works too: open the spec
here once, then keep editing it externally. With "Auto-reload" ticked the
studio watches the file's timestamp and re-reads it the moment you save, so
the preview tracks your external editor with no clicks at all. Ctrl+R forces
a reload by hand.

The "Kind" selector picks which flowchart.py renderer is used - it must
match the spec you are editing (a ```timeline fence needs "Kind: timeline",
etc). Picking an example from the dropdown switches it automatically.

Run:
    python flowchart_studio.py

Shortcuts:
    F5 / Ctrl+Enter   render now
    Ctrl+O            open a .json spec
    Ctrl+R            reload the open spec from disk
    Ctrl+S            save the current spec
    Ctrl+Shift+S      export the current render as PNG
    Ctrl+C (in preview) copy the current render to the clipboard (paste
                        straight into Word/Outlook/Teams)
"""

import glob
import io
import json
import math
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

import flowchart
from text_format import COLORS, format_at_cursor, format_whole_chart

try:
    import win32clipboard
    HAVE_CLIPBOARD = True
except ImportError:
    HAVE_CLIPBOARD = False

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(os.path.dirname(HERE), "_src")
TMP_PNG = os.path.join(HERE, "_studio_preview.png")

# How often to check whether the open spec changed underneath us. Polling
# mtime rather than using a filesystem watcher keeps this dependency-free;
# sub-second is quick enough to feel instant when saving from Notepad++.
DISK_POLL_MS = 600

# Diagram kind -> (renderer, fenced-code language it corresponds to in the
# markdown source). Keep this in step with mkdocx.py's DIAGRAM_RENDERERS -
# both dispatch diagram kinds by the same fence names.
RENDERERS = {
    "flow":     (flowchart.render,          "flow"),
    "timeline": (flowchart.render_timeline, "timeline"),
    "sequence": (flowchart.render_sequence, "sequence"),
    "tasks":    (flowchart.render_tasks,    "tasks"),
    "fishbone": (flowchart.render_fishbone, "fishbone"),
}
KIND_LABELS = list(RENDERERS.keys())


def _detect_kind(spec):
    """Guess a spec's diagram kind from its own top-level keys.

    Without this, opening a file only loads its TEXT - the Kind selector is
    left wherever it happened to be (the default "flow", most of the time),
    so a timeline or sequence spec renders against the wrong function and
    fails with a confusing KeyError instead of a picture. The formats
    never share a top-level key, so detection is unambiguous whenever the
    spec is complete enough to identify; mid-edit/incomplete JSON returns
    None and the caller leaves the current selection alone.
    """
    if not isinstance(spec, dict):
        return None
    if "effect" in spec or "categories" in spec:
        return "fishbone"
    if "tasks" in spec and "segments" in spec:
        return "tasks"
    if "actors" in spec and "messages" in spec:
        return "sequence"
    if "lanes" in spec:
        return "timeline"
    if "nodes" in spec:
        return "flow"
    return None

DEFAULT_SPECS = {
    "fishbone": """{
  "title": "Root cause analysis",
  "effect": "Delayed delivery",
  "categories": [
    {"label": "People", "causes": [
      {"label": "Training needed", "causes": ["No onboarding", "No mentoring"]},
      "Staff shortage"
    ]},
    {"label": "Process", "causes": ["Slow approvals", "Unclear requirements"]},
    {"label": "Technology", "causes": ["System downtime", "Outdated tools"]}
  ]
}
""",
    "flow": """{
  "w": 5.0,
  "nodes": [
    {"id":"A","col":0,"row":0,"text":"Start",   "shape":"terminal"},
    {"id":"B","col":0,"row":1,"text":"Do work", "shape":"box"},
    {"id":"C","col":0,"row":2,"text":"OK?",     "shape":"decision"},
    {"id":"D","col":1,"row":2,"text":"Handle error","shape":"note"}
  ],
  "edges": [
    ["A","B"],
    ["B","C"],
    ["C","D","no"],
    ["D","B","retry","right"]
  ]
}
""",
    "timeline": """{
  "title": "Example timeline",
  "duration_ms": 300,
  "lanes": [
    {"id":"a", "label":"Lane A"},
    {"id":"b", "label":"Lane B"}
  ],
  "bars": [
    {"lane":"a", "start":0,   "end":120, "label":"busy", "style":"warn"},
    {"lane":"b", "start":0,   "end":300, "label":"awake", "style":"ok"}
  ],
  "events": [
    {"t":150, "label":"something\\nhappens", "style":"state"}
  ],
  "ticks": [
    {"lane":"a", "t":10}, {"lane":"a", "t":20}, {"lane":"a", "t":30}
  ]
}
""",
    "sequence": """{
  "title": "Example sequence",
  "actors": [
    {"id":"a", "label":"Caller"},
    {"id":"b", "label":"Callee"}
  ],
  "messages": [
    {"from":"a", "to":"b", "label":"call()"},
    {"from":"b", "to":"b", "label":"self-check", "self":true},
    {"from":"b", "to":"a", "label":"return", "dashed":true},
    {"note":"~10 ms later"}
  ]
}
""",
    "tasks": """{
  "title": "FreeRTOS control cycle",
  "duration_ms": 5,
  "tasks": [
    {"id":"isr",  "label":"ADC ISR",     "priority":"IRQ"},
    {"id":"ctrl", "label":"ControlTask", "priority":4},
    {"id":"idle", "label":"IdleTask",    "priority":0}
  ],
  "segments": [
    {"task":"ctrl", "start":0.00, "end":1.00, "state":"blocked", "label":"wait notify"},
    {"task":"idle", "start":0.00, "end":1.00, "state":"running", "label":"idle"},
    {"task":"isr",  "start":1.00, "end":1.08, "state":"isr",     "label":"ADC IRQ"},
    {"task":"ctrl", "start":1.08, "end":1.70, "state":"running", "label":"filter + PID"},
    {"task":"idle", "start":1.70, "end":5.00, "state":"running", "label":"idle"}
  ],
  "links": [
    {"from":{"task":"isr","t":1.08}, "to":{"task":"ctrl","t":1.08}, "label":"notify"}
  ],
  "events": [
    {"t":1.0, "label":"ADC interrupt", "style":"danger"}
  ]
}
""",
}

# The studio's help is just flowchart.py's own module docstring - showing it
# verbatim (rather than a hand-maintained copy) means the two files cannot
# drift out of sync the way the old static HELP_TEXT eventually would.
HELP_TEXT = flowchart.__doc__ or "(no docstring found on flowchart.py)"


class FlowchartStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Flowchart Studio")
        self.geometry("1280x800")

        self._render_after_id = None
        self._current_image = None      # full-res PIL image, last good render
        self._preview_scale = None
        self._preview_draw_id = None
        self._zoom = tk.StringVar(value="Fit")
        self._auto = tk.BooleanVar(value=True)
        self._kind = tk.StringVar(value="flow")
        self._examples = {}              # label -> (json text, kind)

        self._path = None               # spec file currently open, if any
        self._disk_mtime = None         # its mtime when we last read/wrote it
        self._autoreload = tk.BooleanVar(value=True)

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_statusbar()

        self._load_examples()
        self.editor.insert("1.0", DEFAULT_SPECS["flow"])
        self._mark_clean()

        self.bind_all("<F5>", lambda e: self.render_now())
        self.bind_all("<Control-Return>", lambda e: self.render_now())
        self.bind_all("<Control-o>", lambda e: self.open_spec())
        self.bind_all("<Control-r>", lambda e: self.reload_spec())
        self.bind_all("<Control-s>", lambda e: self.save_spec())
        self.bind_all("<Control-S>", lambda e: self.export_png())
        self.editor.bind("<<Modified>>", self._on_modified)
        self.preview_canvas.bind("<Control-c>", lambda e: self.copy_image())
        self.preview_canvas.bind("<Configure>", self._on_resize, add="+")

        self.after(150, self.render_now)
        self.after(DISK_POLL_MS, self._poll_disk)

    # -- UI construction -----------------------------------------------
    def _build_menu(self):
        m = tk.Menu(self)
        filem = tk.Menu(m, tearoff=0)
        filem.add_command(label="New", command=self.new_spec)
        filem.add_command(label="Open spec...  (Ctrl+O)", command=self.open_spec)
        filem.add_command(label="Reload from disk  (Ctrl+R)",
                          command=self.reload_spec)
        filem.add_command(label="Save spec  (Ctrl+S)", command=self.save_spec)
        filem.add_command(label="Save spec as...", command=self.save_spec_as)
        filem.add_separator()
        filem.add_command(label="Export PNG...  (Ctrl+Shift+S)",
                          command=self.export_png)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)
        m.add_cascade(label="File", menu=filem)

        helpm = tk.Menu(m, tearoff=0)
        helpm.add_command(label="Spec format...", command=self._show_help)
        m.add_cascade(label="Help", menu=helpm)
        self.config(menu=m)

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(6, 6))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="Render (F5)", command=self.render_now).pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(bar, text="Auto-render", variable=self._auto).pack(
            side=tk.LEFT, padx=(0, 12))

        ttk.Label(bar, text="Kind:").pack(side=tk.LEFT)
        kind_box = ttk.Combobox(bar, width=10, state="readonly",
                                textvariable=self._kind, values=KIND_LABELS)
        kind_box.pack(side=tk.LEFT, padx=(4, 12))
        kind_box.bind("<<ComboboxSelected>>", lambda e: self.render_now())

        ttk.Separator(bar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        ttk.Button(bar, text="Reload (Ctrl+R)", command=self.reload_spec).pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(bar, text="Auto-reload",
                        variable=self._autoreload).pack(
            side=tk.LEFT, padx=(0, 12))

        ttk.Label(bar, text="Example:").pack(side=tk.LEFT)
        self.example_box = ttk.Combobox(bar, width=44, state="readonly")
        self.example_box.pack(side=tk.LEFT, padx=(4, 12))
        self.example_box.bind("<<ComboboxSelected>>", self._on_example_pick)

        ttk.Label(bar, text="Zoom:").pack(side=tk.LEFT)
        zoom_box = ttk.Combobox(bar, width=8, state="readonly",
                                textvariable=self._zoom,
                                values=["Fit", "25%", "50%", "100%", "150%", "200%", "400%", "800%"])
        zoom_box.pack(side=tk.LEFT, padx=(4, 12))
        zoom_box.bind("<<ComboboxSelected>>", lambda e: self._refresh_preview())

        ttk.Button(bar, text="Export PNG...", command=self.export_png).pack(
            side=tk.LEFT, padx=(0, 8))
        if HAVE_CLIPBOARD:
            ttk.Button(bar, text="Copy image", command=self.copy_image).pack(
                side=tk.LEFT)

        formatting = ttk.Frame(self, padding=(6, 3))
        formatting.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(formatting, text="Format text at cursor:").pack(side=tk.LEFT)
        self._font_size = tk.StringVar(value="10")
        size = ttk.Spinbox(formatting, from_=4, to=72, increment=1,
                           width=5, textvariable=self._font_size)
        size.pack(side=tk.LEFT, padx=(8, 3))
        size.bind("<Return>", lambda event: self._apply_font_size())
        ttk.Button(formatting, text="Apply size", command=self._apply_font_size).pack(
            side=tk.LEFT, padx=(0, 8))
        self._font_flags = {}
        for option, caption in (("bold", "Bold"), ("italic", "Italic"),
                                ("underline", "Underline")):
            variable = tk.BooleanVar(value=False)
            self._font_flags[option] = variable
            ttk.Checkbutton(formatting, text=caption, variable=variable,
                            command=lambda key=option, var=variable:
                            self._format_current_text({key: var.get()})).pack(
                                side=tk.LEFT, padx=3)
        ttk.Label(formatting, text="Color:").pack(side=tk.LEFT, padx=(10, 4))
        self._text_color = tk.StringVar(value="Black")
        color = ttk.Combobox(formatting, state="readonly", width=9,
                             textvariable=self._text_color, values=list(COLORS))
        color.pack(side=tk.LEFT, padx=(0, 6))
        color.bind("<<ComboboxSelected>>", lambda event:
                   self._format_current_text({"color": COLORS[self._text_color.get()]}))
        for name, value in COLORS.items():
            tk.Button(formatting, width=2, background=value, relief="raised",
                      takefocus=False, command=lambda n=name: self._apply_text_color(n)).pack(
                          side=tk.LEFT, padx=1)
        self._format_whole = tk.BooleanVar(value=False)
        ttk.Checkbutton(formatting, text="Whole chart", variable=self._format_whole,
                        command=self._sync_format_controls).pack(
            side=tk.LEFT, padx=8)

    def _apply_text_color(self, name):
        self._text_color.set(name)
        self._format_current_text({"color": COLORS[name]})

    def _apply_font_size(self):
        try:
            value = float(self._font_size.get())
        except ValueError:
            self.status.set("Font size must be a number from 4 to 72 points.")
            return
        self._format_current_text({"font_size": value})

    def _format_current_text(self, options):
        raw = self.editor.get("1.0", "end-1c")
        cursor = len(self.editor.get("1.0", "insert"))
        try:
            if self._format_whole.get():
                start, end, replacement = format_whole_chart(raw, options)
            else:
                start, end, replacement = format_at_cursor(raw, cursor, options)
        except (ValueError, TypeError) as exc:
            self.status.set(f"Formatting: {exc}")
            return
        # Use line/column indices instead of Tcl character counts so non-BMP
        # Unicode characters before the edited label do not shift the target.
        def index(offset):
            prefix = raw[:offset]
            column = self.editor.tk.call("string", "length", prefix.rsplit("\n", 1)[-1])
            return f"{prefix.count(chr(10)) + 1}.{column}"
        self.editor.edit_separator()
        self.editor.delete(index(start), index(end))
        self.editor.insert(index(start), replacement)
        self.editor.edit_separator()
        self.editor.mark_set("insert", index(start))
        self.editor.focus_set()
        self.render_now()

    def _scroll_editor(self, *args):
        self.editor.yview(*args)
        self.after_idle(self._redraw_line_numbers)

    def _on_editor_scroll(self, first, last):
        self._editor_yscroll.set(first, last)
        self.after_idle(self._redraw_line_numbers)

    def _redraw_line_numbers(self, _event=None):
        """Draw numbers for the editor's currently visible logical lines."""
        if not hasattr(self, "line_numbers"):
            return
        gutter = self.line_numbers
        gutter.delete("all")
        total = int(self.editor.index("end-1c").split(".")[0])
        width = max(38, 17 + len(str(total)) * 8)
        gutter.configure(width=width)
        current = int(self.editor.index("insert").split(".")[0])
        index = self.editor.index("@0,0")
        while True:
            info = self.editor.dlineinfo(index)
            if info is None:
                break
            line = int(index.split(".")[0])
            gutter.create_text(
                width - 7, info[1], text=str(line), anchor="ne",
                font=("Consolas", 10, "bold" if line == current else "normal"),
                fill="#1F4E79" if line == current else "#666666")
            index = f"{line + 1}.0"

    def _build_body(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned)
        ttk.Label(left, text="Spec (JSON)", padding=(6, 4)).pack(
            side=tk.TOP, anchor="w")
        editor_frame = ttk.Frame(left)
        editor_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.line_numbers = tk.Canvas(
            editor_frame, width=38, background="#F2F2F2",
            highlightthickness=0, borderwidth=0, takefocus=False)
        self.editor = tk.Text(editor_frame, wrap="none", undo=True,
                              font=("Consolas", 10), padx=8, pady=6)
        self.editor.bind("<ButtonRelease-1>", self._sync_format_controls)
        self.editor.bind("<KeyRelease>", self._sync_format_controls)
        self.editor.bind("<ButtonRelease-1>", self._redraw_line_numbers, add="+")
        self.editor.bind("<KeyRelease>", self._redraw_line_numbers, add="+")
        self.editor.bind("<Configure>", self._redraw_line_numbers, add="+")
        self._editor_yscroll = ttk.Scrollbar(
            editor_frame, orient=tk.VERTICAL, command=self._scroll_editor)
        xscroll = ttk.Scrollbar(editor_frame, orient=tk.HORIZONTAL,
                                command=self.editor.xview)
        self.editor.configure(yscrollcommand=self._on_editor_scroll,
                              xscrollcommand=xscroll.set)
        self.line_numbers.grid(row=0, column=0, sticky="ns")
        self.editor.grid(row=0, column=1, sticky="nsew")
        self._editor_yscroll.grid(row=0, column=2, sticky="ns")
        xscroll.grid(row=1, column=1, sticky="ew")
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(1, weight=1)
        paned.add(left, weight=1)

        right = ttk.Frame(paned)
        ttk.Label(right, text="Preview — wheel to zoom · left-drag to pan", padding=(6, 4)).pack(
            side=tk.TOP, anchor="w")
        canvas_frame = ttk.Frame(right)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.preview_canvas = tk.Canvas(canvas_frame, background="#FFFFFF",
                                        highlightthickness=0, cursor="hand2")
        pv_yscroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL,
                                   command=self.preview_canvas.yview)
        pv_xscroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL,
                                   command=self.preview_canvas.xview)
        def scrolled(scrollbar, first, last):
            scrollbar.set(first, last)
            self._queue_preview_draw()
        self.preview_canvas.configure(
            yscrollcommand=lambda a, b: scrolled(pv_yscroll, a, b),
            xscrollcommand=lambda a, b: scrolled(pv_xscroll, a, b))
        self.preview_canvas.bind("<MouseWheel>", self._zoom_preview_wheel)
        self.preview_canvas.bind("<Button-4>", self._zoom_preview_wheel)
        self.preview_canvas.bind("<Button-5>", self._zoom_preview_wheel)
        self.preview_canvas.bind("<ButtonPress-1>", self._start_preview_pan)
        self.preview_canvas.bind("<B1-Motion>", self._drag_preview_pan)
        self.preview_canvas.bind("<ButtonRelease-1>", self._end_preview_pan)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        pv_yscroll.grid(row=0, column=1, sticky="ns")
        pv_xscroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        paned.add(right, weight=1)

        self._canvas_image_id = None

    def _build_statusbar(self):
        self.status = tk.StringVar(value="Ready.")
        bar = ttk.Frame(self, padding=(6, 2))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(bar, textvariable=self.status, anchor="w").pack(
            side=tk.LEFT, fill=tk.X, expand=True)

    def _sync_format_controls(self, _event=None):
        raw = self.editor.get("1.0", "end-1c")
        try:
            defaults = json.loads(raw).get("text_format", {})
            if self._format_whole.get():
                options = defaults
            else:
                _, _, replacement = format_at_cursor(
                    raw, len(self.editor.get("1.0", "insert")), {})
                options = {**defaults, **json.loads(replacement)}
            self._font_size.set(str(options.get("font_size", 8.2)))
            for key, variable in self._font_flags.items():
                variable.set(options.get(key, False))
            color = options.get("color", COLORS["Black"])
            self._text_color.set(next((name for name, value in COLORS.items()
                                       if value == color), "Black"))
        except (ValueError, TypeError, AttributeError):
            pass  # Incomplete JSON and structural lines have no text target.

    # -- Examples --------------------------------------------------------
    def _load_examples(self):
        """Scan _src/*.md for every supported fenced diagram
        block flowchart.py can render, so all kinds get real,
        already-in-the-docs examples rather than just the one built-in
        default per kind.
        """
        pattern = os.path.join(SRC_DIR, "*.md")
        fence_re = re.compile(
            r"```(" + "|".join(RENDERERS) + r")\s*\n(.*?)```", re.S)
        found = [(f"Built-in [{kind}]", (spec, kind))
                 for kind, spec in DEFAULT_SPECS.items()]
        for path in sorted(glob.glob(pattern)):
            name = os.path.basename(path)
            try:
                text = open(path, encoding="utf8").read()
            except OSError:
                continue
            counters = {}
            for kind, block in fence_re.findall(text):
                block = block.strip()
                try:
                    spec = json.loads(block)
                except json.JSONDecodeError:
                    continue
                counters[kind] = counters.get(kind, 0) + 1
                caption = spec.get("caption") or spec.get("title") \
                    or f"{kind} {counters[kind]}"
                label = f"{name} [{kind}] - {caption}"
                found.append((label, (block, kind)))
        self._examples = dict(found)
        self.example_box["values"] = list(self._examples.keys())
        self.status.set(f"Ready. {len(found)} examples available (built-in and _src/*.md).")

    def _on_example_pick(self, _event):
        label = self.example_box.get()
        entry = self._examples.get(label)
        if entry is None:
            return
        spec_text, kind = entry
        self._kind.set(kind)
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", spec_text)
        # Examples come out of a .md block, not a spec file - drop any file
        # we were watching so Reload cannot pull an unrelated diagram back.
        self._path = None
        self._disk_mtime = None
        self._set_title()
        self._mark_clean()
        self.render_now()

    # -- Editing / auto-render -------------------------------------------
    def _on_modified(self, _event=None):
        if self.editor.edit_modified():
            self.editor.edit_modified(False)
            self.after_idle(self._redraw_line_numbers)
            if self._auto.get():
                if self._render_after_id is not None:
                    self.after_cancel(self._render_after_id)
                self._render_after_id = self.after(500, self.render_now)

    def _mark_clean(self):
        self.editor.edit_modified(False)

    def _on_resize(self, _event=None):
        self._refresh_preview()

    # -- File operations ---------------------------------------------------
    def new_spec(self):
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", DEFAULT_SPECS[self._kind.get()])
        # No longer tied to a file - stop watching the previous one.
        self._path = None
        self._disk_mtime = None
        self._set_title()
        self._mark_clean()
        self.render_now()

    def open_spec(self):
        path = filedialog.askopenfilename(
            title="Open diagram spec", filetypes=[("JSON", "*.json"),
                                                   ("All files", "*.*")])
        if not path:
            return
        if not os.path.exists(path):
            messagebox.showerror("Open failed", f"No such file:\n{path}")
            return
        self._path = path
        if not self._load_from_disk():
            self._path = None
            self._set_title()

    def reload_spec(self):
        """Re-read the open spec from disk (Ctrl+R / toolbar button).

        For the "edit in Notepad++, preview here" workflow: nothing needs
        closing and reopening, and the file dialog is skipped entirely.
        """
        if not self._path:
            messagebox.showinfo(
                "Nothing to reload",
                "No spec file is open.\n\nUse File > Open spec (Ctrl+O) "
                "first; after that Reload re-reads that same file.")
            return
        if self.editor.edit_modified() and not messagebox.askyesno(
                "Discard editor changes?",
                f"{os.path.basename(self._path)} will be re-read from disk "
                "and the unsaved edits in this window will be lost.\n\n"
                "Reload anyway?"):
            return
        self._load_from_disk()

    def _load_from_disk(self):
        """Pull the file into the editor and re-render. True if it worked."""
        try:
            text = open(self._path, encoding="utf8").read()
            mtime = os.path.getmtime(self._path)
        except OSError as exc:
            self.status.set(f"Reload failed: {exc}")
            return False

        # An editor mid-save can momentarily present an empty file. Treat
        # that as "not ready" rather than wiping the preview -- the next
        # poll picks up the real content a fraction of a second later.
        if not text.strip():
            self.status.set("File is empty on disk - waiting for the save "
                            "to finish.")
            return False

        # Keep the scroll position: an external edit should not throw the
        # view back to the top every time it is saved.
        yview = self.editor.yview()[0]
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", text)
        self.editor.yview_moveto(yview)

        self._disk_mtime = mtime
        self._mark_clean()
        self._set_title()
        self.render_now()
        return True

    def _poll_disk(self):
        """Watch the open spec for external edits; reload when it changes."""
        try:
            if (self._path is not None) and self._autoreload.get():
                mtime = os.path.getmtime(self._path)
                if (self._disk_mtime is not None) and (mtime > self._disk_mtime):
                    if self.editor.edit_modified():
                        # Never silently destroy unsaved work - say so and
                        # let the user decide via Ctrl+R.
                        self._disk_mtime = mtime
                        self.status.set(
                            f"{os.path.basename(self._path)} changed on disk, "
                            "but this window has unsaved edits - Ctrl+R to "
                            "take the disk copy.")
                    else:
                        self._load_from_disk()
        except OSError:
            pass                # file temporarily gone mid-save; try again
        self.after(DISK_POLL_MS, self._poll_disk)

    def _set_title(self):
        if self._path:
            self.title(f"Flowchart Studio - {os.path.basename(self._path)}")
        else:
            self.title("Flowchart Studio")

    def save_spec(self, save_as=False):
        """Save to the open file, asking for a path only for new/Save As."""
        path = None if save_as else self._path
        if not path:
            path = filedialog.asksaveasfilename(
                title="Save diagram spec", defaultextension=".json",
                filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf8") as f:
                f.write(self.editor.get("1.0", "end-1c"))
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc))
            return

        # Adopt this file as the open one, so Reload / auto-reload now track
        # it and our own write is not mistaken for an external edit.
        self._path = path
        try:
            self._disk_mtime = os.path.getmtime(path)
        except OSError:
            self._disk_mtime = None
        self._mark_clean()
        self._set_title()
        self.status.set(f"Saved spec to {path}")

    def save_spec_as(self):
        self.save_spec(save_as=True)

    def export_png(self):
        if self._current_image is None:
            messagebox.showinfo("Nothing to export", "Render a diagram first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export PNG", defaultextension=".png",
            filetypes=[("PNG image", "*.png")])
        if not path:
            return
        self._current_image.save(path)
        self.status.set(f"Exported PNG to {path}")

    def copy_image(self):
        if not HAVE_CLIPBOARD:
            messagebox.showinfo("Not available",
                                "pywin32 is not installed, so clipboard copy "
                                "is not available. Use Export PNG instead.")
            return
        if self._current_image is None:
            return
        buf = io.BytesIO()
        self._current_image.convert("RGB").save(buf, "BMP")
        dib = buf.getvalue()[14:]      # strip the 14-byte BMP file header
        buf.close()
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
        finally:
            win32clipboard.CloseClipboard()
        self.status.set("Copied to clipboard — paste into Word, "
                        "Outlook, Teams, etc.")

    # -- Rendering ---------------------------------------------------------
    def render_now(self):
        if self._render_after_id is not None:
            self.after_cancel(self._render_after_id)
            self._render_after_id = None

        raw = self.editor.get("1.0", "end-1c")
        try:
            spec = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.status.set(f"JSON error: {exc}")
            return

        # Keep the Kind selector truthful: whatever is actually in the editor
        # decides which renderer runs, not whichever kind happened to be
        # selected before this file/paste/edit arrived.
        detected = _detect_kind(spec)
        if detected is not None:
            self._kind.set(detected)

        kind = self._kind.get()
        render_fn, _fence = RENDERERS.get(kind, RENDERERS["flow"])

        try:
            render_fn(spec, TMP_PNG)
        except Exception as exc:                       # noqa: BLE001
            self.status.set(f"Render error ({kind}): {exc}")
            return

        try:
            self._current_image = Image.open(TMP_PNG).copy()
        except OSError as exc:
            self.status.set(f"Could not load rendered PNG: {exc}")
            return

        self._refresh_preview()
        w, h = self._current_image.size
        self.status.set(f"Rendered OK ({kind}) — {w}x{h}px.")

    def _zoom_preview_wheel(self, event):
        if self._current_image is None:
            return "break"
        if getattr(event, "num", None) in (4, 5):
            steps = 1 if event.num == 4 else -1
        else:
            steps = getattr(event, "delta", 0) / 120.0
        if not steps:
            return "break"
        if self._preview_scale is None:
            self._refresh_preview()
        # Fractional deltas preserve precision from high-resolution wheels.
        scale = min(8.0, max(0.01, self._preview_scale * 1.15 ** max(-20, min(20, steps))))
        self._zoom.set(f"{scale * 100:.4f}%")
        self._refresh_preview(anchor=(event.x, event.y))
        return "break"

    def _start_preview_pan(self, event):
        self.preview_canvas.focus_set()
        self.preview_canvas.scan_mark(event.x, event.y)
        self.preview_canvas.configure(cursor="fleur")
        return "break"

    def _drag_preview_pan(self, event):
        self.preview_canvas.scan_dragto(event.x, event.y, gain=1)
        self._queue_preview_draw()
        return "break"

    def _end_preview_pan(self, _event):
        self.preview_canvas.configure(cursor="hand2")
        return "break"

    def _queue_preview_draw(self):
        if self._preview_draw_id is None:
            self._preview_draw_id = self.after_idle(self._draw_preview_viewport)

    def _refresh_preview(self, anchor=None):
        if self._current_image is None:
            return
        img = self._current_image
        zoom = self._zoom.get()
        canvas = self.preview_canvas
        cw, ch = max(canvas.winfo_width(), 1), max(canvas.winfo_height(), 1)
        px, py = anchor if anchor is not None else (cw / 2, ch / 2)
        old_scale = self._preview_scale
        source_x = canvas.canvasx(px) / old_scale if old_scale else img.width / 2
        source_y = canvas.canvasy(py) / old_scale if old_scale else img.height / 2

        if zoom == "Fit":
            scale = min(cw / img.width, ch / img.height, 1.0)
            source_x, source_y = img.width / 2, img.height / 2
        else:
            scale = float(zoom.rstrip("%")) / 100.0
        self._preview_scale = scale
        width, height = img.width * scale, img.height * scale
        # A viewport of padding on every side permits hand-tool movement
        # even when the image is smaller than the preview window.
        canvas.configure(scrollregion=(-cw, -ch, width + cw, height + ch))
        canvas.xview_moveto((source_x * scale - px + cw) / (width + 2 * cw))
        canvas.yview_moveto((source_y * scale - py + ch) / (height + 2 * ch))
        self._queue_preview_draw()

    def _draw_preview_viewport(self):
        self._preview_draw_id = None
        img, scale = self._current_image, self._preview_scale
        if img is None or scale is None:
            return
        canvas = self.preview_canvas
        # Resize only the visible image area, so zooming a large chart to
        # 800% does not allocate an enormous full-image bitmap.
        left = max(0, math.floor(canvas.canvasx(0)))
        top = max(0, math.floor(canvas.canvasy(0)))
        right = min(math.ceil(img.width * scale),
                    math.ceil(canvas.canvasx(canvas.winfo_width())))
        bottom = min(math.ceil(img.height * scale),
                     math.ceil(canvas.canvasy(canvas.winfo_height())))
        if right <= left or bottom <= top:
            if self._canvas_image_id is not None:
                canvas.itemconfigure(self._canvas_image_id, state="hidden")
            return
        display_img = img.transform(
            (right - left, bottom - top), Image.Transform.EXTENT,
            (left / scale, top / scale, right / scale, bottom / scale),
            resample=Image.Resampling.BICUBIC)
        self._photo = ImageTk.PhotoImage(display_img)
        if self._canvas_image_id is None:
            self._canvas_image_id = canvas.create_image(
                left, top, anchor="nw", image=self._photo)
        else:
            canvas.coords(self._canvas_image_id, left, top)
            canvas.itemconfigure(self._canvas_image_id, image=self._photo, state="normal")

    def _show_help(self):
        win = tk.Toplevel(self)
        win.title("Spec format")
        win.geometry("720x640")
        text = tk.Text(win, wrap="word", font=("Consolas", 10), padx=10,
                       pady=10)
        text.insert("1.0", HELP_TEXT)
        text.configure(state="disabled")
        text.pack(fill=tk.BOTH, expand=True)


if __name__ == "__main__":
    app = FlowchartStudio()
    app.mainloop()
