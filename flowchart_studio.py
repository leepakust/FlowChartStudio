"""Engineering Diagram Studio -- a desktop UI around flowchart.py.

Lets you write/edit a diagram JSON spec (flowchart/state-machine, timeline,
sequence diagram, or RTOS task sequencer) and see the rendered preview update live, without going
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
import os
import re
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

import flowchart

try:
    import win32clipboard
    HAVE_CLIPBOARD = True
except ImportError:
    HAVE_CLIPBOARD = False

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(os.path.dirname(HERE), "_src")
# Each process owns its preview; installed application resources are read-only.
_PREVIEW_DIR = tempfile.TemporaryDirectory(prefix="EngineeringDiagramStudio-")
TMP_PNG = os.path.join(_PREVIEW_DIR.name, "preview.png")

# How often to check whether the open spec changed underneath us. Polling
# mtime rather than using a filesystem watcher keeps this dependency-free;
# sub-second is quick enough to feel instant when saving from Notepad++.
DISK_POLL_MS = 600

# Diagram kind -> (renderer, fenced-code language it corresponds to in the
# markdown source). Keep this in step with mkdocx.py's DIAGRAM_RENDERERS -
# both dispatch the same three kinds by the same fence names.
RENDERERS = {
    "flow":     (flowchart.render,          "flow"),
    "timeline": (flowchart.render_timeline, "timeline"),
    "sequence": (flowchart.render_sequence, "sequence"),
    "tasks":    (flowchart.render_tasks,    "tasks"),
}
KIND_LABELS = list(RENDERERS.keys())


def _detect_kind(spec):
    """Guess a spec's diagram kind from its own top-level keys.

    Without this, opening a file only loads its TEXT - the Kind selector is
    left wherever it happened to be (the default "flow", most of the time),
    so a timeline or sequence spec renders against the wrong function and
    fails with a confusing KeyError instead of a picture. The three formats
    never share a top-level key, so detection is unambiguous whenever the
    spec is complete enough to identify; mid-edit/incomplete JSON returns
    None and the caller leaves the current selection alone.
    """
    return flowchart.detect_kind(spec)

DEFAULT_SPECS = {
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
    {"id":"comm", "label":"CommsTask",   "priority":2},
    {"id":"idle", "label":"IdleTask",    "priority":0}
  ],
  "segments": [
    {"task":"ctrl", "start":0.00, "end":1.00, "state":"blocked", "label":"wait notify"},
    {"task":"idle", "start":0.00, "end":1.00, "state":"running", "label":"idle"},
    {"task":"isr",  "start":1.00, "end":1.08, "state":"isr",     "label":"ADC IRQ"},
    {"task":"ctrl", "start":1.08, "end":1.70, "state":"running", "label":"filter + PID"},
    {"task":"comm", "start":1.70, "end":2.10, "state":"running", "label":"publish"},
    {"task":"idle", "start":2.10, "end":5.00, "state":"running", "label":"idle"}
  ],
  "links": [
    {"from":{"task":"isr","t":1.08}, "to":{"task":"ctrl","t":1.08}, "label":"notify"},
    {"from":{"task":"ctrl","t":1.70}, "to":{"task":"comm","t":1.70}, "label":"queue"}
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
        self.title("Engineering Diagram Studio")
        self.geometry("1280x800")

        self._render_after_id = None
        self._current_image = None      # full-res PIL image, last good render
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
        self.bind_all("<Control-Shift-F>", lambda e: self.format_json())
        self.editor.bind("<<Modified>>", self._on_modified)
        self.preview_canvas.bind("<Control-c>", lambda e: self.copy_image())
        self.bind("<Configure>", self._on_resize, add="+")

        self.after(150, self.render_now)
        self.after(DISK_POLL_MS, self._poll_disk)

    # -- UI construction -----------------------------------------------
    def _build_menu(self):
        m = tk.Menu(self)
        filem = tk.Menu(m, tearoff=0)
        filem.add_command(label="New", command=self.new_spec)
        filem.add_command(label="Open spec...  (Ctrl+O)", command=self.open_spec)
        filem.add_command(label="Open Markdown diagrams...",
                          command=self.open_markdown)
        filem.add_command(label="Reload from disk  (Ctrl+R)",
                          command=self.reload_spec)
        filem.add_command(label="Save spec...  (Ctrl+S)", command=self.save_spec)
        filem.add_separator()
        filem.add_command(label="Export PNG...  (Ctrl+Shift+S)",
                          command=self.export_png)
        filem.add_command(label="Export SVG...", command=self.export_svg)
        filem.add_command(label="Export PDF...", command=self.export_pdf)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)
        m.add_cascade(label="File", menu=filem)

        toolm = tk.Menu(m, tearoff=0)
        toolm.add_command(label="Validate specification",
                          command=self.validate_current)
        toolm.add_command(label="Format JSON  (Ctrl+Shift+F)",
                          command=self.format_json)
        m.add_cascade(label="Tools", menu=toolm)

        helpm = tk.Menu(m, tearoff=0)
        helpm.add_command(label="Spec format...", command=self._show_help)
        m.add_cascade(label="Help", menu=helpm)
        self.config(menu=m)

    def _build_toolbar(self):
        bar = ttk.Frame(self, padding=(6, 6))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="Render (F5)", command=self.render_now).pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Button(bar, text="Validate", command=self.validate_current).pack(
            side=tk.LEFT, padx=(0, 8))
        ttk.Button(bar, text="Format JSON", command=self.format_json).pack(
            side=tk.LEFT, padx=(0, 10))
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
                                values=["Fit", "50%", "100%", "150%", "200%"])
        zoom_box.pack(side=tk.LEFT, padx=(4, 12))
        zoom_box.bind("<<ComboboxSelected>>", lambda e: self._refresh_preview())

        ttk.Button(bar, text="Export...", command=self.export_any).pack(
            side=tk.LEFT, padx=(0, 8))
        if HAVE_CLIPBOARD:
            ttk.Button(bar, text="Copy image", command=self.copy_image).pack(
                side=tk.LEFT)

    def _build_body(self):
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned)
        ttk.Label(left, text="Spec (JSON)", padding=(6, 4)).pack(
            side=tk.TOP, anchor="w")
        editor_frame = ttk.Frame(left)
        editor_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.editor = tk.Text(editor_frame, wrap="none", undo=True,
                              font=("Consolas", 10), padx=8, pady=6)
        yscroll = ttk.Scrollbar(editor_frame, orient=tk.VERTICAL,
                                command=self.editor.yview)
        xscroll = ttk.Scrollbar(editor_frame, orient=tk.HORIZONTAL,
                                command=self.editor.xview)
        self.editor.configure(yscrollcommand=yscroll.set,
                              xscrollcommand=xscroll.set)
        self.editor.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)
        paned.add(left, weight=1)

        right = ttk.Frame(paned)
        ttk.Label(right, text="Preview", padding=(6, 4)).pack(
            side=tk.TOP, anchor="w")
        canvas_frame = ttk.Frame(right)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.preview_canvas = tk.Canvas(canvas_frame, background="#FFFFFF",
                                        highlightthickness=0)
        pv_yscroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL,
                                   command=self.preview_canvas.yview)
        pv_xscroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL,
                                   command=self.preview_canvas.xview)
        self.preview_canvas.configure(yscrollcommand=pv_yscroll.set,
                                      xscrollcommand=pv_xscroll.set)
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

    # -- Examples --------------------------------------------------------
    def _load_examples(self):
        """Load built-in examples, then augment them from documentation."""
        pattern = os.path.join(SRC_DIR, "*.md")
        fence_re = re.compile(
            r"```(flow|timeline|sequence|tasks)\s*\n(.*?)```", re.S)
        found = [(f"Built-in [{kind}]", (text.strip(), kind))
                 for kind, text in DEFAULT_SPECS.items()]
        for path in sorted(glob.glob(os.path.join(HERE, "examples", "*.json"))):
            try:
                with open(path, encoding="utf-8") as example_file:
                    text = example_file.read()
                spec = json.loads(text)
                kind = _detect_kind(spec)
                if kind in RENDERERS:
                    found.append((f"{os.path.basename(path)} [{kind}]", (text, kind)))
            except (OSError, ValueError):
                continue
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
        self.status.set(f"Ready. {len(found)} example diagrams available.")

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
            if self._auto.get():
                if self._render_after_id is not None:
                    self.after_cancel(self._render_after_id)
                self._render_after_id = self.after(500, self.render_now)

    def _mark_clean(self):
        self.editor.edit_modified(False)

    def _on_resize(self, _event=None):
        if self._zoom.get() == "Fit":
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
                                                   ("Markdown", "*.md"),
                                                   ("All files", "*.*")])
        if not path:
            return
        if path.lower().endswith(".md"):
            self._open_markdown_path(path)
            return
        if not os.path.exists(path):
            messagebox.showerror("Open failed", f"No such file:\n{path}")
            return
        self._path = path
        if not self._load_from_disk():
            self._path = None
            self._set_title()

    def open_markdown(self):
        path = filedialog.askopenfilename(
            title="Open Markdown document",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")])
        if path:
            self._open_markdown_path(path)

    def _open_markdown_path(self, path):
        try:
            text = open(path, encoding="utf8").read()
        except OSError as exc:
            messagebox.showerror("Open failed", str(exc))
            return
        fence_re = re.compile(
            r"```(flow|timeline|sequence|tasks)\s*\n(.*?)```", re.S)
        blocks = []
        counters = {}
        for kind, raw in fence_re.findall(text):
            raw = raw.strip()
            try:
                spec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            counters[kind] = counters.get(kind, 0) + 1
            name = spec.get("title") or spec.get("caption") \
                or f"{kind} {counters[kind]}"
            blocks.append((f"[{kind}] {name}", raw, kind))
        if not blocks:
            messagebox.showinfo(
                "No diagrams found",
                "No valid ```flow, ```timeline, ```sequence or ```tasks "
                "JSON blocks were found in this Markdown file.")
            return
        if len(blocks) == 1:
            self._load_markdown_block(blocks[0], path)
            return

        chooser = tk.Toplevel(self)
        chooser.title(f"Choose diagram - {os.path.basename(path)}")
        chooser.geometry("560x360")
        ttk.Label(chooser, text="Diagrams in this Markdown document:",
                  padding=(10, 10)).pack(anchor="w")
        lb = tk.Listbox(chooser, font=("Segoe UI", 10))
        lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))
        for label, _raw, _kind in blocks:
            lb.insert(tk.END, label)
        lb.selection_set(0)

        def accept(_event=None):
            sel = lb.curselection()
            if not sel:
                return
            self._load_markdown_block(blocks[sel[0]], path)
            chooser.destroy()

        buttons = ttk.Frame(chooser, padding=(10, 0, 10, 10))
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Open", command=accept).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancel", command=chooser.destroy).pack(
            side=tk.RIGHT, padx=(0, 8))
        lb.bind("<Double-1>", accept)

    def _load_markdown_block(self, block, source_path):
        label, raw, kind = block
        self._kind.set(kind)
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", raw)
        # Imported blocks are deliberately detached: Save writes a JSON spec
        # rather than silently editing a fenced region inside Markdown.
        self._path = None
        self._disk_mtime = None
        self._set_title()
        self._mark_clean()
        self.render_now()
        self.status.set(f"Imported {label} from {os.path.basename(source_path)}. "
                        "Save creates a standalone JSON spec.")

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
            self.title(f"Engineering Diagram Studio - {os.path.basename(self._path)}")
        else:
            self.title("Engineering Diagram Studio")

    def save_spec(self):
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

    def _export_vector(self, ext, label):
        parsed = self._parse_and_validate(show_dialog=True)
        if parsed is None:
            return
        spec, kind, _report = parsed
        path = filedialog.asksaveasfilename(
            title=f"Export {label}", defaultextension=f".{ext}",
            filetypes=[(f"{label} file", f"*.{ext}")])
        if not path:
            return
        render_fn, _fence = RENDERERS[kind]
        try:
            render_fn(spec, path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(f"Export {label} failed", str(exc))
            return
        self.status.set(f"Exported {label} to {path}")

    def export_svg(self):
        self._export_vector("svg", "SVG")

    def export_pdf(self):
        self._export_vector("pdf", "PDF")

    def export_any(self):
        parsed = self._parse_and_validate(show_dialog=True)
        if parsed is None:
            return
        spec, kind, _report = parsed
        path = filedialog.asksaveasfilename(
            title="Export diagram",
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("SVG vector", "*.svg"),
                       ("PDF vector", "*.pdf")])
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".png":
            # Re-render instead of saving the preview bitmap so the export
            # path always uses the renderer's native output settings.
            render_fn, _fence = RENDERERS[kind]
            render_fn(spec, path)
        elif ext in (".svg", ".pdf"):
            render_fn, _fence = RENDERERS[kind]
            render_fn(spec, path)
        else:
            messagebox.showerror("Unsupported format",
                                 "Choose PNG, SVG or PDF.")
            return
        self.status.set(f"Exported {ext[1:].upper()} to {path}")

    def _clear_error_highlight(self):
        self.editor.tag_remove("json_error", "1.0", tk.END)

    def _highlight_error_line(self, lineno):
        self._clear_error_highlight()
        self.editor.tag_configure("json_error", background="#FFE4E4")
        self.editor.tag_add("json_error", f"{lineno}.0", f"{lineno}.end")
        self.editor.see(f"{lineno}.0")

    def _parse_and_validate(self, show_dialog=False):
        raw = self.editor.get("1.0", "end-1c")
        self._clear_error_highlight()
        try:
            spec = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._highlight_error_line(exc.lineno)
            msg = f"JSON line {exc.lineno}, column {exc.colno}: {exc.msg}"
            self.status.set(msg)
            if show_dialog:
                messagebox.showerror("Invalid JSON", msg)
            return None

        detected = _detect_kind(spec)
        if detected is not None:
            self._kind.set(detected)
        kind = self._kind.get()
        try:
            report = flowchart.validate_spec(spec, kind)
        except flowchart.SpecValidationError as exc:
            msg = "Specification error: " + " | ".join(exc.errors[:3])
            if len(exc.errors) > 3:
                msg += f" (+{len(exc.errors) - 3} more)"
            self.status.set(msg)
            if show_dialog:
                messagebox.showerror("Invalid specification",
                                     "\n\n".join(exc.errors))
            return None
        return spec, kind, report

    def validate_current(self):
        parsed = self._parse_and_validate(show_dialog=True)
        if parsed is None:
            return False
        _spec, kind, report = parsed
        if report["warnings"]:
            messagebox.showwarning("Specification valid with warnings",
                                   "\n".join(report["warnings"]))
            self.status.set(f"Valid {kind} spec with {len(report['warnings'])} warning(s).")
        else:
            self.status.set(f"Specification valid ({kind}).")
        return True

    def format_json(self):
        raw = self.editor.get("1.0", "end-1c")
        try:
            spec = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._highlight_error_line(exc.lineno)
            self.status.set(f"Cannot format: JSON line {exc.lineno}: {exc.msg}")
            return
        yview = self.editor.yview()[0]
        formatted = json.dumps(spec, indent=2, ensure_ascii=False)
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", formatted + "\n")
        self.editor.yview_moveto(yview)
        self.editor.edit_modified(True)
        self.status.set("JSON formatted.")

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

        parsed = self._parse_and_validate(show_dialog=False)
        if parsed is None:
            return
        spec, kind, report = parsed
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
        suffix = (f" — {len(report['warnings'])} warning(s)"
                  if report["warnings"] else "")
        self.status.set(f"Rendered OK ({kind}) — {w}x{h}px{suffix}.")

    def _refresh_preview(self):
        if self._current_image is None:
            return
        img = self._current_image
        zoom = self._zoom.get()

        if zoom == "Fit":
            cw = max(self.preview_canvas.winfo_width(), 50)
            ch = max(self.preview_canvas.winfo_height(), 50)
            scale = min(cw / img.width, ch / img.height, 1.0)
        else:
            scale = float(zoom.rstrip("%")) / 100.0

        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        resample = Image.LANCZOS if scale < 1.0 else Image.NEAREST
        display_img = img.resize((new_w, new_h), resample)

        self._photo = ImageTk.PhotoImage(display_img)   # keep a reference
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.preview_canvas.configure(scrollregion=(0, 0, new_w, new_h))

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
