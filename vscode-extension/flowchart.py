# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright 2026 Patrick Lee
"""Diagram renderer for the Faraday firmware design documents.

Renders declarative diagram specs (JSON, inside fenced code blocks in the
markdown source) to PNGs suitable for embedding in a Word document. No
external binaries required (matplotlib only) -- Graphviz/mermaid are not
available on the build machine.

Four diagram kinds, each with its own fence tag and render() entry point:

  ```flow      -> render()          flowcharts and UML-ish state machines
  ```timeline  -> render_timeline() swimlane timing / sequencing charts
  ```sequence  -> render_sequence() UML-style sequence diagrams
  ```fishbone  -> render_fishbone() cause-and-effect (Ishikawa) diagrams

TEXT FORMATTING (all chart types)
--------------------------------
Any display string may be replaced with a text object, for example:
  "label": {"text": "People", "font_size": 14, "bold": true,
            "italic": true, "underline": true, "color": "#000080"}
Size is in points (4-72). Bold, italic and underline are optional booleans.
Colors use the 16 main colors exposed by the Studio formatting toolbar.
A top-level "text_format" object supplies chart-wide defaults, including
timeline ruler numbers. Per-label options override these defaults. Plain
strings continue to work; formatting applies to all lines of a label.
In Studio, click in a text value and use the formatting toolbar. It updates
only that JSON value; Ctrl+Z undoes the edit. Enable Whole chart for defaults.

FISHBONE DIAGRAMS (render_fishbone)
---------------------------------
    {
      "title": "Root cause analysis",
      "effect": "Delayed delivery",
      "categories": [
        {"label": "People", "causes": [
          {"label": "Training gaps", "causes": ["No onboarding", "No mentoring"]},
          "Staff shortage"
        ]},
        {"label": "Methods", "style": "warn", "causes": ["Manual approval"]}
      ]
    }

Categories alternate above and below a horizontal spine pointing to the
effect. Each category has a non-empty label, an optional STYLE palette name,
and an optional causes list. A cause can be a string or an object with a
non-empty "label" and its own "causes" list, recursively. Labels wrap
automatically and the canvas grows to fit the content. There is no fixed limit
on categories, causes, or nesting depth, so 10 or more levels are supported.
Title is optional. At least one category is required; an empty causes list can
be used as a brainstorming placeholder.

============================================================================
FLOWCHARTS / STATE MACHINES  (render)
============================================================================

    {
      "w": 7.2,                     # figure width in inches (optional)
      "nodes": [
        {"id":"A", "col":0, "row":0, "text":"Start",   "shape":"terminal"},
        {"id":"B", "col":0, "row":1, "text":"Do work", "shape":"box"},
        {"id":"C", "col":0, "row":2, "text":"OK?",     "shape":"decision"}
      ],
      "edges": [
        ["A","B"],
        ["B","C"],
        ["C","D","yes"],
        ["C","B","no","left"],       # 4th field routes the edge around the side
        ["C","B","alt","left",0.25,0.5]
      ]
    }

Shapes: box (process), terminal (rounded, start/end), decision (diamond),
        io (parallelogram), note (dashed box).

Node field "style" (optional): overrides which STYLE palette entry a node's
outline uses, independent of its shape - e.g. {"shape":"state","style":"danger"}
draws a state-shaped node in the "danger" (red) palette. Defaults to the
shape name, exactly as before this field existed.

Edge fields: [src, dst, label, route, shift, lane]

  Routing is automatic, in the draw.io / mermaid style: connectors leave and
  enter each node on the side that faces the other node, orthogonal runs get
  rounded corners, and edges that share a node side are fanned out to
  separate anchor points instead of overprinting each other on the side's
  mid-point. A run that would print through an unrelated box is re-routed
  around it automatically (different branch exit, shelf or side lane). Edge
  labels auto-dodge other labels and node boxes. The optional fields
  fine-tune that:

  route - "" (automatic), or "left"/"right" to run a feedback/retry loop
          around the flank as a vertical rail. (Self-transitions use
          "self"/"self-left"/"self-right" as described below.)
  shift - forces BOTH endpoints to a fixed position along their side
          (inches). Rarely needed now that anchors spread themselves;
          kept for exact manual control.
  lane  - pushes a "left"/"right" routed rail further out, on top of the
          automatic collision push-off.

STATE MACHINE DIAGRAMS
-----------------------
The same spec renders UML-style state charts using three extra shapes and
self-transitions:

    {
      "nodes": [
        {"id":"I",    "col":0, "row":0, "shape":"start"},
        {"id":"RUN",  "col":0, "row":1, "text":"RUNNING", "shape":"state"},
        {"id":"STOP", "col":0, "row":2, "text":"HALTED",  "shape":"state",
         "style":"danger"}
      ],
      "edges": [
        ["I","RUN"],
        ["RUN","RUN","tick",  "self"],        # self-transition, loop on top
        ["RUN","RUN","retry", "self-right"],  # or self-left / self-right
        ["RUN","STOP","fault"]
      ]
    }

  state  - rounded rectangle, the resting condition of the machine
  start  - small filled disc, the initial pseudostate (no text)
  final  - ringed disc, a terminal state (no text)

A self-transition is any edge whose source and target are the same node,
with route "self" (or "self-top") looping above the state, "self-left" or
"self-right" looping out to that side. Use those when a state has an action
it repeats while remaining in that state. Repeated work that does NOT leave
a state usually reads better as a "do / ..." line inside the state box than
as a self-loop.

============================================================================
TIMELINE / SWIMLANE CHARTS  (render_timeline)
============================================================================

    {
      "title": "One successful turn",     # optional, drawn inside the image
      "duration_ms": 500,
      "lanes": [
        {"id":"seq", "label":"Motor sequencer"},
        {"id":"drv", "label":"TMC6300"}
      ],
      "bars": [
        {"lane":"seq", "start":0, "end":120, "label":"TURN\\nblanking",
         "style":"blank"},
        {"lane":"drv", "start":-1, "end":500, "label":"awake", "style":"turn"}
      ],
      "events": [
        {"t":45,  "label":"edge\\n(ignored)",  "style":"note"},
        {"t":300, "label":"edge\\n(accepted)", "style":"state"}
      ],
      "ticks": [ {"lane":"seq", "t":10}, {"lane":"seq", "t":20} ]
    }

A "bar" is one time-boxed segment inside one lane. An "event" is a vertical
marker spanning every lane at one instant, with its label in the strip above
the chart - use these for things that happen at a point in time and affect
the whole system (an interrupt, a request arriving), not one subsystem.
A "tick" is a small mark inside one lane with no label - for dense, mostly-
uninteresting activity (e.g. individual commutation steps) where only the
*rate* matters, not each instance.

"style" on a bar/event selects a STYLE palette entry exactly as for a flow
node; omit it for the default box colour.

============================================================================
SEQUENCE DIAGRAMS  (render_sequence)
============================================================================

    {
      "title": "Turn request",
      "actors": [
        {"id":"caller", "label":"MainTask"},
        {"id":"api",    "label":"MOTOR_\\nRequestPosition"}
      ],
      "messages": [
        {"from":"caller", "to":"api", "label":"RequestPosition(CW_END)"},
        {"from":"api", "to":"api", "label":"validate", "self":true},
        {"from":"api", "to":"caller", "label":"ACCEPTED", "dashed":true},
        {"note":"~10 ms later, on the task's own poll"}
      ]
    }

Actors become vertical lifelines in the given left-to-right order. Messages
are drawn top-to-bottom in list order (NOT to a real time scale - this is a
call-sequence diagram, not a timing chart; use render_timeline for that).
"dashed":true draws a return/async arrow instead of a synchronous call.
"self":true (or from == to) draws a small loop back to the same lifeline.
A {"note": "..."} entry (no from/to) draws a full-width divider with
centred text - use it to mark a phase change ("TURN - blanking 120 ms").
"""

import itertools
import json
import math
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.text import Text
from matplotlib.transforms import Affine2D
from text_format import OPTIONS, validate_options
from matplotlib.path import Path
from matplotlib.patches import (FancyBboxPatch, Polygon, FancyArrowPatch,
                                Circle, Rectangle)


class _StyledString(str):
    def __new__(cls, value, options):
        result = super().__new__(cls, value)
        result.options = options
        return result


def _keep_style(original, value):
    return _StyledString(value, original.options) if isinstance(original, _StyledString) else value


def _prepare_text(value, defaults=None):
    if defaults is None:
        defaults = value.get("text_format", {}) if isinstance(value, dict) else {}
        if not isinstance(defaults, dict):
            raise ValueError("text_format must be an object")
        validate_options(defaults)
    if isinstance(value, dict):
        if "text" in value and set(value) <= OPTIONS | {"text"}:
            if not isinstance(value["text"], str):
                raise ValueError("Formatted text must contain a string in 'text'")
            options = {key: val for key, val in value.items() if key != "text"}
            validate_options(options)
            return _StyledString(value["text"], {**defaults, **options})
        return {key: val if key == "text_format" else _prepare_text(val, defaults)
                for key, val in value.items()}
    if isinstance(value, list):
        return [_prepare_text(val, defaults) for val in value]
    if isinstance(value, str) and defaults:
        return _StyledString(value, {**defaults, **getattr(value, "options", {})})
    return value


class _FormattedText(Text):
    """Render an underline for each actual laid-out line, including rotation."""
    def draw(self, renderer):
        super().draw(renderer)
        if not getattr(self, "underline", False) or not self.get_visible():
            return
        _, lines, _ = self._get_layout(renderer)
        x, y = self.get_transform().transform(self.get_position())
        angle = self.get_rotation()
        shift = renderer.points_to_pixels(self.get_fontsize() * 0.12)
        gc = renderer.new_gc()
        try:
            gc.set_foreground(self.get_color())
            gc.set_alpha(self.get_alpha())
            gc.set_linewidth(max(0.5, self.get_fontsize() / 16))
            for line in lines:
                # Matplotlib 3.11 groups the baseline coordinates; older
                # releases return them as two separate tuple members.
                if len(line) == 3:
                    _, metrics, (lx, ly) = line
                else:
                    _, metrics, lx, ly = line
                width = metrics[0]
                path = Path([(0, -shift), (width, -shift)])
                transform = Affine2D().rotate_deg(angle).translate(x + lx, y + ly)
                renderer.draw_path(gc, path, transform)
        finally:
            gc.restore()


def _text(ax, x, y, text, **kwargs):
    kwargs.setdefault("clip_on", False)
    options = {**getattr(ax, "_text_options", {}), **getattr(text, "options", {})}
    for key, target in (("font_size", "fontsize"), ("color", "color")):
        if key in options:
            kwargs[target] = options[key]
    if "bold" in options:
        kwargs["fontweight"] = "bold" if options["bold"] else "normal"
    if "italic" in options:
        kwargs.pop("style", None)
        kwargs["fontstyle"] = "italic" if options["italic"] else "normal"
    artist = _FormattedText(x, y, str(text), **kwargs)
    artist.underline = options.get("underline", False)
    ax.add_artist(artist)
    return artist


def _font_scale(value, base=7.0):
    """Reserve more space for explicitly enlarged text in fixed-grid charts."""
    if isinstance(value, _StyledString):
        return max(1.0, value.options.get("font_size", base) / base *
                   (1.1 if value.options.get("bold") else 1.0))
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
    return max([1.0] + [_font_scale(child, base) for child in children])

# ION Science-ish palette: restrained, prints legibly in mono.
STYLE = {
    "box":      {"fc": "#E8EEF7", "ec": "#2F5597", "lw": 1.4},
    "terminal": {"fc": "#D6E4D2", "ec": "#4A7A3C", "lw": 1.4},
    "decision": {"fc": "#FCF0D8", "ec": "#B8860B", "lw": 1.4},
    "io":       {"fc": "#EDE4F3", "ec": "#6B4A8F", "lw": 1.4},
    "note":     {"fc": "#F5F5F5", "ec": "#888888", "lw": 1.0},
    # State-chart shapes.
    "state":    {"fc": "#DCE9F5", "ec": "#1F4E79", "lw": 1.5},
    "start":    {"fc": "#333333", "ec": "#333333", "lw": 1.2},
    "final":    {"fc": "#333333", "ec": "#333333", "lw": 1.5},
    # Extra palette entries available to any node/bar/event via "style".
    "danger":   {"fc": "#F5D9D9", "ec": "#A33333", "lw": 1.5},   # fault/HALT
    "warn":     {"fc": "#FCEACB", "ec": "#B8860B", "lw": 1.4},   # escape/retry
    "ok":       {"fc": "#D9EFD9", "ec": "#3C7A4A", "lw": 1.4},   # success/done
    "idle":     {"fc": "#ECECEC", "ec": "#777777", "lw": 1.2},   # powered down
}

# Shapes drawn at a fixed size with no interior label (UML pseudostates).
MARKER_SHAPES = ("start", "final")
MARKER_D = 0.26           # pseudostate disc diameter (inches)

# One data unit == one inch on the final page. Keeping the two identical
# makes text measurement scale-stable: a label measured in inches can be
# turned straight into a box size without knowing the final figure extent.
COL_W = 2.62      # horizontal pitch between columns (inches)
ROW_H = 0.84      # vertical pitch between rows
BOX_W = 1.72      # minimum node width
BOX_H = 0.46      # minimum node height
FONT = 8.2

# Connector look-and-feel and automatic-routing constants (inches on the
# final page -- the same scale as COL_W/ROW_H).
EDGE_COLOR = "#555555"    # connector ink
EDGE_LW = 1.1
HEAD_SCALE = 11           # arrowhead size (FancyArrowPatch mutation_scale)
CORNER_R = 0.09           # rounding radius of orthogonal elbows
RAIL_CLEAR = 0.62         # base distance of a side rail from the node edge
RAIL_SEP = 0.50           # push step when a rail would overlap another rail
SPREAD_MAX_X = 0.34       # default fan-out on a node's top/bottom side
ALIGN_SPREAD = 0.16       # fan-out when several straight edges share a side


def _wrap(text, shape):
    width = 22 if shape == "decision" else 26
    lines = []
    for para in text.split("\n"):
        lines.extend(textwrap.wrap(para, width) or [""])
    return _keep_style(text, "\n".join(lines))


def _xy(node):
    return (node.get("_x", node["col"] * COL_W),
            node.get("_y", -node["row"] * ROW_H))


def _place_text(ax, node):
    """Pass 1: lay the label down so its true rendered size can be measured."""
    shape = node.get("shape", "box")
    if shape in MARKER_SHAPES:
        node["_txt"] = None         # pseudostates carry no interior label
        return

    x, y = _xy(node)
    label = _wrap(node["text"], shape)
    node["_txt"] = _text(ax,
        x, y, label, ha="center", va="center", fontsize=FONT,
        zorder=3, linespacing=1.35,
        fontweight="bold" if shape in ("terminal", "state") else "normal")


def _measure(ax, fig, node):
    """Pass 2: size the node from the text's actual rendered extent.

    Measured in INCHES (display pixels / dpi), not data units, so the result
    does not depend on the provisional axis limits in force at measure time.
    Guessing an average character width under-sizes boxes for wide glyphs
    (capitals, underscores) and the text overruns its outline.
    """
    shape = node.get("shape", "box")
    if shape in MARKER_SHAPES:
        node["_w"], node["_h"] = MARKER_D, MARKER_D
        return

    bb = node["_txt"].get_window_extent(renderer=fig.canvas.get_renderer())
    tw = bb.width / fig.dpi
    th = bb.height / fig.dpi

    pad_x, pad_y = 0.26, 0.20
    w = max(BOX_W, tw + pad_x)
    h = max(BOX_H, th + pad_y)
    if shape == "decision":
        w = max(w, tw * 1.45)           # diamond corners eat horizontal room
        h = max(h, th * 1.55, 0.62)
    node["_w"], node["_h"] = w, h


def _draw_shape(ax, node):
    """Pass 3: draw the outline behind the already-placed text."""
    shape = node.get("shape", "box")
    st = STYLE.get(node.get("style", shape), STYLE.get(shape, STYLE["box"]))
    x, y = _xy(node)
    w, h = node["_w"], node["_h"]

    if shape == "start":
        ax.add_patch(Circle((x, y), MARKER_D / 2, facecolor=st["fc"],
                            edgecolor=st["ec"], linewidth=st["lw"], zorder=2))
    elif shape == "final":
        # UML final state: open ring with a filled bullseye.
        ax.add_patch(Circle((x, y), MARKER_D / 2, facecolor="white",
                            edgecolor=st["ec"], linewidth=st["lw"], zorder=2))
        ax.add_patch(Circle((x, y), MARKER_D / 2 * 0.55, facecolor=st["fc"],
                            edgecolor="none", zorder=3))
    elif shape == "decision":
        pts = [(x, y + h / 2), (x + w / 2, y), (x, y - h / 2), (x - w / 2, y)]
        ax.add_patch(Polygon(pts, closed=True, facecolor=st["fc"],
                             edgecolor=st["ec"], linewidth=st["lw"], zorder=2))
    elif shape == "io":
        sk = 0.16
        pts = [(x - w / 2 + sk, y + h / 2), (x + w / 2, y + h / 2),
               (x + w / 2 - sk, y - h / 2), (x - w / 2, y - h / 2)]
        ax.add_patch(Polygon(pts, closed=True, facecolor=st["fc"],
                             edgecolor=st["ec"], linewidth=st["lw"], zorder=2))
    else:
        rounding = 0.30 if shape in ("terminal", "state") else 0.04
        ax.add_patch(FancyBboxPatch(
            (x - w / 2, y - h / 2), w, h,
            boxstyle=f"round,pad=0,rounding_size={rounding}",
            facecolor=st["fc"], edgecolor=st["ec"], linewidth=st["lw"],
            linestyle="--" if shape == "note" else "-", zorder=2))


def _anchor(node, side, shift=0.0):
    """Connection point on one side of a node.

    `shift` slides the point ALONG that side (inches): vertically for the
    left/right sides, horizontally for top/bottom. Without it every edge
    touching a node lands on the same mid-point, so several connections to
    one state collapse into a single line and the diagram becomes unreadable.
    """
    x, y = _xy(node)
    w, h = node["_w"], node["_h"]
    return {
        "top":    (x + shift, y + h / 2),
        "bottom": (x + shift, y - h / 2),
        "left":   (x - w / 2, y + shift),
        "right":  (x + w / 2, y + shift),
    }[side]


def _bbox(node, pad=0.0):
    """Node's rectangle in data inches, optionally inflated by `pad`."""
    x, y = _xy(node)
    return (x - node["_w"] / 2 - pad, y - node["_h"] / 2 - pad,
            x + node["_w"] / 2 + pad, y + node["_h"] / 2 + pad)


def _seg_hits_box(x0, y0, x1, y1, box):
    """Axis-aligned segment vs rectangle. Strict interior: a run that only
    touches a border counts as clear, so legal attachments don't trip it."""
    bx0, by0, bx1, by1 = box
    if abs(y1 - y0) < 1e-9:                       # horizontal run
        lo, hi = (x0, x1) if x0 <= x1 else (x1, x0)
        return by0 < y0 < by1 and hi > bx0 and lo < bx1
    if abs(x1 - x0) < 1e-9:                       # vertical run
        lo, hi = (y0, y1) if y0 <= y1 else (y1, y0)
        return bx0 < x0 < bx1 and hi > by0 and lo < by1
    return False


def _path_hits_boxes(pts, boxes):
    return any(_seg_hits_box(a[0], a[1], b[0], b[1], box)
               for a, b in zip(pts, pts[1:]) for box in boxes)


def _clean_pts(pts):
    """Drop duplicate vertices so corner rounding never divides by zero."""
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    if len(out) == 1:
        out.append((out[0][0] + 1e-6, out[0][1]))
    return out


def _rounded_path(pts, r=CORNER_R):
    """Orthogonal polyline with every interior corner replaced by a small
    quadratic arc -- the difference between a wireframe sketch and the
    rounded orthogonal connectors draw.io / mermaid draw."""
    verts, codes = [pts[0]], [Path.MOVETO]
    for i in range(1, len(pts) - 1):
        px, py = pts[i - 1]
        vx, vy = pts[i]
        nx, ny = pts[i + 1]
        d1 = math.hypot(vx - px, vy - py)
        d2 = math.hypot(nx - vx, ny - vy)
        r1, r2 = min(r, d1 / 2), min(r, d2 / 2)
        verts += [(vx - (vx - px) / d1 * r1, vy - (vy - py) / d1 * r1),
                  (vx, vy),
                  (vx + (nx - vx) / d2 * r2, vy + (ny - vy) / d2 * r2)]
        codes += [Path.LINETO, Path.CURVE3, Path.CURVE3]
    verts.append(pts[-1])
    codes.append(Path.LINETO)
    return Path(verts, codes)


def _stroke(ax, pts, head=True):
    """One clean connector: rounded orthogonal path plus a single arrowhead
    seated flush on the final segment."""
    pts = _clean_pts(pts)
    if len(pts) == 2:
        patch = FancyArrowPatch(pts[0], pts[1],
                                arrowstyle="-|>" if head else "-",
                                mutation_scale=HEAD_SCALE, color=EDGE_COLOR,
                                lw=EDGE_LW, shrinkA=0, shrinkB=0, zorder=1)
    else:
        patch = FancyArrowPatch(path=_rounded_path(pts),
                                arrowstyle="-|>" if head else "-",
                                mutation_scale=HEAD_SCALE, color=EDGE_COLOR,
                                lw=EDGE_LW, zorder=1)
    ax.add_patch(patch)


class _LabelSpace:
    """Places edge labels on the first candidate spot that does not print on
    top of an earlier label or a node box.

    This is what stops a busy state chart from stacking its transition
    captions: every edge offers a few sensible spots (midpoints of its own
    segments first, then small slides along and across the longest segment)
    and the first free one wins. Nothing to configure - specs whose labels
    never compete render exactly where they did before.
    """

    def __init__(self, ax, fig, nodes):
        self.ax = ax
        self.fig = fig
        self.nodes = [_bbox(n, 0.02) for n in nodes]
        self.taken = []

    def _extent(self, cx, cy, txt):
        # Measure the ACTUAL rendered extent (inches, via the renderer) the
        # same way node sizing does -- never guess a per-character width.
        # get_window_extent() returns the axis-aligned box AFTER rotation,
        # so rotated self-loop labels need no special handling here.
        bb = txt.get_window_extent(renderer=self.fig.canvas.get_renderer())
        hw = bb.width / self.fig.dpi / 2 + 0.04
        hh = bb.height / self.fig.dpi / 2 + 0.04
        return (cx - hw, cy - hh, cx + hw, cy + hh)

    @staticmethod
    def _hits(box, boxes):
        x0, y0, x1, y1 = box
        return any(x0 < b[2] and x1 > b[0] and y0 < b[3] and y1 > b[1]
                   for b in boxes)

    def _try(self, text, cx, cy, fontsize, rotation):
        txt = _text(self.ax, cx, cy, text, fontsize=fontsize, ha="center",
                           va="center", rotation=rotation, color="#333333",
                           zorder=4, linespacing=1.2,
                           bbox=dict(fc="white", ec="none", pad=1.2))
        return txt, self._extent(cx, cy, txt)

    def place(self, text, candidates, fontsize, rotation=0):
        """Draw at the first candidate clear of other labels AND nodes; if
        every candidate grazes a node, still prefer one clear of other
        labels; if everything is taken, fall back to the first candidate so
        the label always appears."""
        best = None
        for cx, cy in candidates:
            txt, box = self._try(text, cx, cy, fontsize, rotation)
            hits_labels = self._hits(box, self.taken)
            hits_nodes = self._hits(box, self.nodes)
            if not hits_labels and not hits_nodes:
                self.taken.append(box)
                return txt, box, cx, cy
            txt.remove()
            if best is None and not hits_labels:
                best = (cx, cy)
        cx, cy = best if best is not None else candidates[0]
        txt, box = self._try(text, cx, cy, fontsize, rotation)
        self.taken.append(box)
        return txt, box, cx, cy


def _label_candidates(pts):
    """Spots to try for an edge label: every segment's midpoint (longest
    first -- a caption belongs on the run that has room for it), then slides
    along and across that longest segment."""
    segs = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (b[0] - a[0], b[1] - a[1]))
            for a, b in zip(pts, pts[1:])]
    segs.sort(key=lambda s: -math.hypot(*s[2]))
    cands = [(mx, my) for mx, my, _ in segs]
    mx, my, (dx, dy) = segs[0]
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    for d in (0.18, -0.18, 0.38, -0.38):
        cands.append((mx + ux * d, my + uy * d))      # along the run
    for d in (0.16, -0.16):
        cands.append((mx - uy * d, my + ux * d))      # across it
    return cands


def _draw_self_edge(ax, fig, node, label, route, bounds, space):
    """A state that transitions to itself: loop out and back on one side.

    Drawn as a single curved arrow between two points on the same edge of the
    node, so it reads as a transition rather than a decoration. The loop's far
    side (and, when present, the label's real measured extent) is fed into
    the bounds lists or it renders clipped off the edge of the figure.
    """
    x, y = _xy(node)
    w, h = node["_w"], node["_h"]
    side = route.replace("self", "").lstrip("-") or "top"

    if side == "left":
        p0, p1 = (x - w / 2, y + h * 0.22), (x - w / 2, y - h * 0.22)
        rad, reach = 1.5, x - w / 2 - 0.42
        lx, ly, rot = reach - 0.06, y, 90
        bounds["xs"].append(reach - 0.12)
    elif side == "right":
        p0, p1 = (x + w / 2, y - h * 0.22), (x + w / 2, y + h * 0.22)
        rad, reach = 1.5, x + w / 2 + 0.42
        lx, ly, rot = reach + 0.06, y, 90
        bounds["xs"].append(reach + 0.12)
    else:                                   # top
        p0, p1 = (x - w * 0.20, y + h / 2), (x + w * 0.20, y + h / 2)
        rad, reach = -1.5, y + h / 2 + 0.34
        lx, ly, rot = x, reach + 0.10, 0
        bounds["ys"].append(reach + 0.22)

    ax.add_patch(FancyArrowPatch(
        p0, p1, connectionstyle=f"arc3,rad={rad}", arrowstyle="-|>",
        mutation_scale=11, color="#555555", lw=1.1, zorder=1))

    if label:
        _, box, _, _ = space.place(label, [(lx, ly)], FONT - 0.8,
                                   rotation=rot)
        bounds["xs"] += [box[0], box[2]]
        bounds["ys"] += [box[1], box[3]]


def _edge_sides(src, dst, route):
    """Which sides of src/dst an edge connects to. Same geometry the original
    renderer used, so simple diagrams keep their exact old shapes."""
    sx, sy = _xy(src)
    dx, dy = _xy(dst)
    if route in ("left", "right"):
        return route, route
    if abs(dy - sy) < 1e-6:                       # same row -> horizontal
        s = "right" if dx > sx else "left"
        return s, "left" if s == "right" else "right"
    if abs(dx - sx) < 1e-6:                       # same column -> vertical
        s = "bottom" if dy < sy else "top"
        return s, "top" if s == "bottom" else "bottom"
    s = "bottom" if dy < sy else "top"            # diagonal -> elbow
    return s, "left" if dx > sx else "right"


def _linspace(a, b, n):
    if n == 1:
        return [(a + b) / 2]
    step = (b - a) / (n - 1)
    return [a + step * i for i in range(n)]


def _fan(members, coord, center, limit):
    """Offsets for the edges sharing a node side, ordered by where each edge
    is headed so the fan opens outwards and never crosses itself."""
    ms = sorted(members, key=coord)
    if len(ms) == 1:
        d = min(SPREAD_MAX_X, limit)
        return {ms[0]: d if coord(ms[0]) >= center else -d}
    cap = min(0.50, limit)
    return dict(zip(ms, _linspace(-cap, cap, len(ms))))


def _diag_candidates(src, dst):
    """Route options for a diagonal hop, most direct first. Each entry is
    (style, src side, dst side); the style's two letters give the exit and
    entry orientation -- V leaves/enters a top/bottom side, H a left/right
    side. The first that probes clear of other nodes wins."""
    sx, sy = _xy(src)
    dx, dy = _xy(dst)
    v_out = "bottom" if dy < sy else "top"
    v_in = "top" if dy < sy else "bottom"
    h_out = "right" if dx > sx else "left"
    h_in = "left" if dx > sx else "right"
    return [("VH", v_out, h_in),    # out the facing side, in the facing side
            ("HV", h_out, v_in),    # out the side, drop into top/bottom
            ("VV", v_out, v_in),    # vertical out, shelf across, vertical in
            ("HH", h_out, h_in)]    # horizontal out, riser, horizontal in


def _style_pts(style, p0, p1):
    """Anchor pair -> orthogonal polyline for a diagonal route style."""
    if style == "VH":
        return [p0, (p0[0], p1[1]), p1]
    if style == "HV":
        return [p0, (p1[0], p0[1]), p1]
    if style == "VV":
        shelf = (p0[1] + p1[1]) / 2
        return [p0, (p0[0], shelf), (p1[0], shelf), p1]
    riser = (p0[0] + p1[0]) / 2                   # HH
    return [p0, (riser, p0[1]), (riser, p1[1]), p1]


def _first_clear(cands, boxes):
    """First candidate polyline that does not run through an unrelated node,
    or the first candidate at all when every lane is blocked."""
    cands = list(cands)               # generators are single-shot
    for pts in cands:
        if not _path_hits_boxes(pts, boxes):
            return pts
    return cands[0]


def _land_lanes(p0, p1, dst, axis):
    """Around-the-blocker landings for a straight run whose target face is
    walled off: cross to a clear lane in the gap beside the blocker, run
    down/slide along it, and land on the target -- on the blocked face when
    the lane can reach it, otherwise swinging in through a flank face."""
    dx0, dy0 = _xy(dst)
    if axis == "x":                               # vertical run
        half = max(0.10, dst["_w"] / 2 - 0.15)
        span = p1[1] - p0[1]
        for k in range(1, 7):
            for sgn in (1, -1):
                lx = min(half, max(-half, p0[0] + sgn * 0.5 * k))
                if abs(lx - p0[0]) < 0.05:
                    continue
                for f in (0.08, 0.2, 0.35, 0.5, 0.65, 0.8, 0.92):
                    gy = p0[1] + span * f
                    yield [p0, (p0[0], gy), (lx, gy), (lx, p1[1])]
        for k in range(1, 7):                     # flank: enter a side face
            for sgn in (1, -1):
                lx = p0[0] + sgn * 0.5 * k
                side = dx0 + dst["_w"] / 2 if lx > dx0 else dx0 - dst["_w"] / 2
                for f in (0.08, 0.2, 0.5, 0.8, 0.92):
                    gy = p0[1] + span * f
                    yield [p0, (p0[0], gy), (lx, gy), (lx, dy0), (side, dy0)]
    else:                                         # horizontal run
        half = max(0.10, dst["_h"] / 2 - 0.12)
        span = p1[0] - p0[0]
        for k in range(1, 7):
            for sgn in (1, -1):
                ly = min(half, max(-half, p0[1] + sgn * 0.35 * k))
                if abs(ly - p0[1]) < 0.05:
                    continue
                for f in (0.08, 0.2, 0.35, 0.5, 0.65, 0.8, 0.92):
                    gx = p0[0] + span * f
                    yield [p0, (gx, p0[1]), (gx, ly), (p1[0], ly)]
        for k in range(1, 7):                     # flank: enter top/bottom
            for sgn in (1, -1):
                ly = p0[1] + sgn * 0.35 * k
                side = dy0 + dst["_h"] / 2 if ly > dy0 else dy0 - dst["_h"] / 2
                for f in (0.08, 0.2, 0.5, 0.8, 0.92):
                    gx = p0[0] + span * f
                    yield [p0, (gx, p0[1]), (gx, ly), (dx0, ly), (dx0, side)]


def _shelf_jogs(p0, p1):
    """S-jogs for a parallel but offset (fanned) anchor pair: the cross-over
    shelf sits at 50% of the span, then off-centre if that is blocked."""
    if abs(p0[1] - p1[1]) < 1e-9:     # horizontal pair: vertical shelf
        for f in (0.5, 0.22, 0.78):
            sx = p0[0] + (p1[0] - p0[0]) * f
            yield [p0, (sx, p0[1]), (sx, p1[1]), p1]
    else:                             # vertical pair: horizontal shelf
        for f in (0.5, 0.22, 0.78):
            sy = p0[1] + (p1[1] - p0[1]) * f
            yield [p0, (p0[0], sy), (p1[0], sy), p1]


def _plan_anchors(nodes, edges):
    """Per-edge along-side anchor offsets -- the heart of the fix for arrows
    welding themselves together.

    Left alone, every connection touching a node lands on the same side
    mid-point and the arrows overprint each other. This spreads them:

    - one edge on a side keeps offset 0 (simple diagrams are unchanged);
    - a STRAIGHT edge among several keeps 0 too -- the one line that can run
      dead straight does, and the rest fan out around it, ordered by where
      they are headed so nothing crosses;
    - reciprocal A->B / B->A pairs sort identically on BOTH nodes, so they
      come out as two clean parallel rails with no manual `shift` needed;
    - an explicit `shift` always wins and is never auto-moved.

    Returns {edge index: {"so": src offset, "do": dst offset}}.
    """
    plan = {}
    groups = {}
    for i, e in enumerate(edges):
        src, dst = e["src"], e["dst"]
        if src is dst or e["route"].startswith("self"):
            plan[i] = None
            continue
        s_side, d_side = _edge_sides(src, dst, e["route"])
        plan[i] = {"so": e["shift"], "do": e["shift"],
                   "style": None, "ss": s_side, "ds": d_side}
        vert = ("top", "bottom")
        if (s_side in vert) != (d_side in vert):
            # Diagonal hop: probe the candidate routings against the other
            # nodes and take the first clear one, so a branch leaving a
            # decision never prints straight through the box below it.
            boxes = [_bbox(n, 0.05) for n in nodes.values()
                     if n is not src and n is not dst]
            chosen = None
            for style, ss, ds in _diag_candidates(src, dst):
                probe = _style_pts(style, _anchor(src, ss, 0.0),
                                   _anchor(dst, ds, 0.0))
                if not _path_hits_boxes(probe, boxes):
                    chosen = (style, ss, ds)
                    break
            if chosen is None:
                chosen = _diag_candidates(src, dst)[0]
            plan[i]["style"], plan[i]["ss"], plan[i]["ds"] = chosen
            s_side, d_side = chosen[1], chosen[2]
        auto = abs(e["shift"]) < 1e-9
        if auto:
            groups.setdefault((src["id"], s_side), []).append((i, "so"))
            groups.setdefault((dst["id"], d_side), []).append((i, "do"))
    for (nid, side), members in groups.items():
        node = nodes[nid]
        along_x = side in ("top", "bottom")
        limit = max(0.14, (node["_w"] if along_x else node["_h"]) / 2 - 0.20)
        nx, ny = _xy(node)
        center = nx if along_x else ny

        def far(m):
            other = edges[m[0]]["dst" if m[1] == "so" else "src"]
            fx, fy = _xy(other)
            return fx if along_x else fy

        aligned = [m for m in members
                   if edges[m[0]]["route"] not in ("left", "right")
                   and abs(far(m) - center) < 1e-6]
        others = [m for m in members if m not in aligned]

        if len(members) == 1:
            off = {members[0]: 0.0}
        elif not others:                       # several straight edges only
            spread = min(ALIGN_SPREAD, limit)
            off = dict(zip(sorted(members, key=far),
                           _linspace(-spread, spread, len(members))))
        elif len(aligned) == 1:
            off = {aligned[0]: 0.0}
            off.update(_fan(others, far, center, limit))
        else:
            off = _fan(members, far, center, limit)

        for (i, key), v in off.items():
            plan[i][key] = v
    return plan


def _plan_rails(nodes, edges, plan):
    """Rail x for each left/right-routed edge.

    The rail starts at the flank's clear distance (plus the edge's own
    `lane`, as before) and is pushed outward while it would run through an
    unrelated node or share a track with another rail on the same flank --
    so two feedback loops no longer overdraw because they picked the same
    lane by accident.
    """
    rails = {}
    used = {"left": [], "right": []}
    for i, e in enumerate(edges):
        p = plan[i]
        if p is None or e["route"] not in ("left", "right"):
            continue
        src, dst = e["src"], e["dst"]
        p0 = _anchor(src, e["route"], p["so"])
        p1 = _anchor(dst, e["route"], p["do"])
        d = -1.0 if e["route"] == "left" else 1.0
        edge_x = min(p0[0], p1[0]) if d < 0 else max(p0[0], p1[0])
        x = edge_x + (RAIL_CLEAR + e["lane"]) * d
        boxes = [_bbox(n, 0.05) for n in nodes.values()
                 if n is not src and n is not dst]
        for _ in range(12):
            pts = [p0, (x, p0[1]), (x, p1[1]), p1]
            busy = any(abs(x - u) < 0.45 for u in used[e["route"]])
            if not busy and not _path_hits_boxes(pts, boxes):
                break
            x += RAIL_SEP * d
        used[e["route"]].append(x)
        rails[i] = x
    return rails


def _draw_edge(ax, fig, e, bounds, space, p, rail_x, nodes):
    src, dst, label, route = e["src"], e["dst"], e["label"], e["route"]

    if src is dst or route.startswith("self"):
        _draw_self_edge(ax, fig, src, label, route or "self", bounds, space)
        return

    so, do = p["so"], p["do"]
    sx, sy = _xy(src)
    dx, dy = _xy(dst)

    if route in ("left", "right"):
        # Route around the side -- used for feedback/retry loops.
        p0 = _anchor(src, route, so)
        p1 = _anchor(dst, route, do)
        pts = [p0, (rail_x, p0[1]), (rail_x, p1[1]), p1]
        _stroke(ax, pts)
        # Feed the loop's outer rail into the axis-limit calculation, or it
        # gets clipped away and the connector renders as two stray stubs.
        bounds["xs"].append(rail_x + (0.30 if route == "right" else -0.30))
        if label:
            _, box, _, _ = space.place(label, _label_candidates(pts),
                                       FONT - 0.8)
            bounds["xs"] += [box[0], box[2]]
            bounds["ys"] += [box[1], box[3]]
        return

    if abs(dy - sy) < 1e-6:                       # same row -> horizontal
        s_side = "right" if dx > sx else "left"
        d_side = "left" if s_side == "right" else "right"
        p0 = _anchor(src, s_side, so)
        p1 = _anchor(dst, d_side, do)
        boxes = [_bbox(n, 0.05) for n in nodes.values()
                 if n is not src and n is not dst]
        if abs(p0[1] - p1[1]) < 1e-6:
            pts = _first_clear(itertools.chain(
                [[p0, p1]], _shelf_jogs(p0, p1),
                _land_lanes(p0, p1, dst, "y")), boxes)
        else:                                     # fanned anchors -> S-jog
            pts = _first_clear(itertools.chain(
                _shelf_jogs(p0, p1), _land_lanes(p0, p1, dst, "y")), boxes)
    elif abs(dx - sx) < 1e-6:                     # same column -> vertical
        s_side = "bottom" if dy < sy else "top"
        d_side = "top" if s_side == "bottom" else "bottom"
        p0 = _anchor(src, s_side, so)
        p1 = _anchor(dst, d_side, do)
        boxes = [_bbox(n, 0.05) for n in nodes.values()
                 if n is not src and n is not dst]
        if abs(p0[0] - p1[0]) < 1e-6:
            # A node sits in the gap: swing the run through the nearest
            # clear lane instead of printing through its middle.
            pts = _first_clear(itertools.chain(
                [[p0, p1]], _shelf_jogs(p0, p1),
                _land_lanes(p0, p1, dst, "x")), boxes)
        else:
            pts = _first_clear(itertools.chain(
                _shelf_jogs(p0, p1), _land_lanes(p0, p1, dst, "x")), boxes)
    else:                                         # diagonal -> route search
        boxes = [_bbox(n, 0.05) for n in nodes.values()
                 if n is not src and n is not dst]
        cands = _diag_candidates(src, dst)
        planned = (p["style"], p["ss"], p["ds"])
        routes = [(_style_pts(st, _anchor(src, ss, so),
                              _anchor(dst, ds, do)), (st, ss, ds))
                  for st, ss, ds in cands]
        routes.sort(key=lambda rc: rc[1] != planned)   # planned route first
        pts = _first_clear([rc[0] for rc in routes], boxes)

    _stroke(ax, pts)
    if label:
        _, box, _, _ = space.place(label, _label_candidates(pts), FONT - 0.8)
        bounds["xs"] += [box[0], box[2]]
        bounds["ys"] += [box[1], box[3]]


def render(spec, out_path):
    """Render a flowchart/state-machine spec dict (or JSON string) to a PNG."""
    if isinstance(spec, str):
        spec = json.loads(spec)
    spec = _prepare_text(spec)

    nodes = {n["id"]: n for n in spec["nodes"]}

    fig, ax = plt.subplots(figsize=(1, 1), dpi=200)
    ax._text_options = spec.get("text_format", {})
    ax.set_aspect("equal")
    ax.axis("off")

    # Three passes: place text -> measure it -> draw outlines that fit it.
    for n in spec["nodes"]:
        _place_text(ax, n)

    xs0, ys0 = [], []
    for n in spec["nodes"]:
        x, y = _xy(n)
        xs0 += [x - 1.6, x + 1.6]
        ys0 += [y - 0.6, y + 0.6]
    ax.set_xlim(min(xs0), max(xs0))
    ax.set_ylim(min(ys0), max(ys0))
    # Lock 1 data unit == 1 inch for the measuring pass as well.
    fig.set_size_inches(max(xs0) - min(xs0), max(ys0) - min(ys0))
    ax.set_position([0, 0, 1, 1])
    fig.canvas.draw()

    for n in spec["nodes"]:
        _measure(ax, fig, n)
    # Keep enlarged labels and their outlines separated on the grid.
    for coord, size, pitch, dest, direction in (
            ("col", "_w", COL_W, "_x", 1),
            ("row", "_h", ROW_H, "_y", -1)):
        values = sorted({n[coord] for n in nodes.values()})
        extents = {v: max(n[size] for n in nodes.values() if n[coord] == v)
                   for v in values}
        positions = {values[0]: values[0] * pitch}
        for previous, current in zip(values, values[1:]):
            positions[current] = positions[previous] + max(
                (current - previous) * pitch,
                (extents[previous] + extents[current]) / 2 + 0.35)
        for n in nodes.values():
            n[dest] = direction * positions[n[coord]]
    for n in spec["nodes"]:
        if n.get("_txt") is not None:
            n["_txt"].set_position(_xy(n))
        _draw_shape(ax, n)

    edges = [{"src": nodes[e[0]], "dst": nodes[e[1]],
              "label": e[2] if len(e) > 2 else "",
              "route": e[3] if len(e) > 3 else "",
              "shift": float(e[4]) if len(e) > 4 else 0.0,
              "lane": float(e[5]) if len(e) > 5 else 0.0}
             for e in spec.get("edges", [])]

    plan = _plan_anchors(nodes, edges)
    rails = _plan_rails(nodes, edges, plan)
    space = _LabelSpace(ax, fig, nodes.values())

    bounds = {"xs": [], "ys": []}
    for i, e in enumerate(edges):
        _draw_edge(ax, fig, e, bounds, space, plan[i], rails.get(i, 0.0),
                   nodes)

    xs, ys = list(bounds["xs"]), list(bounds["ys"])
    for n in spec["nodes"]:
        x, y = _xy(n)
        xs += [x - n["_w"] / 2 - 0.18, x + n["_w"] / 2 + 0.18]
        ys += [y - n["_h"] / 2 - 0.12, y + n["_h"] / 2 + 0.12]
    ax.set_xlim(min(xs), max(xs))
    ax.set_ylim(min(ys), max(ys))

    # Data units are inches, so the figure must be exactly as many inches
    # across as the axes span -- that is what keeps the measured text sizes
    # in pass 2 valid at final render.
    span_x = max(xs) - min(xs)
    span_y = max(ys) - min(ys)
    fig.set_size_inches(span_x, span_y)
    ax.set_position([0, 0, 1, 1])

    fig.savefig(out_path, bbox_inches="tight", pad_inches=0.04,
                facecolor="white")
    plt.close(fig)
    return out_path


# ============================================================================
# TIMELINE / SWIMLANE CHARTS
# ============================================================================

TL_LABEL_W = 1.9        # inches reserved for the lane-label column
TL_ROW_H = 0.62          # inches per lane row
TL_TOP_STRIP = 0.85      # inches reserved above the lanes for event labels
TL_AXIS_H = 0.42         # inches reserved below the lanes for the ms ruler
TL_FONT = 8.0


def _tl_nice_step(span_ms):
    """Pick a round gridline step so the axis never gets a crowded ruler."""
    if span_ms <= 0:
        return 100
    raw = span_ms / 8.0
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 5, 10):
        step = mult * mag
        if step >= raw:
            return step
    return raw


def render_timeline(spec, out_path):
    """Render a swimlane timing chart (see module docstring) to a PNG.

    Time runs left to right in milliseconds; one horizontal band per lane.
    Bars are time-boxed activity within a lane; events are instants that
    matter to every lane at once (drawn as a full-height marker with its
    label in the strip above); ticks are dense, low-information activity
    inside one lane (a mark with no label).
    """
    if isinstance(spec, str):
        spec = json.loads(spec)
    spec = _prepare_text(spec)
    scale = _font_scale(spec)
    TL_LABEL_W, TL_ROW_H = 1.9 * scale, 0.62 * scale
    TL_TOP_STRIP, TL_AXIS_H = 0.85 * scale, 0.42 * scale

    lanes = spec["lanes"]
    lane_ix = {l["id"]: i for i, l in enumerate(lanes)}
    n_lanes = len(lanes)
    duration = float(spec["duration_ms"])

    ms_per_in = max(duration / 8.5, 12.0)     # keep the chart a sane width
    chart_w = duration / ms_per_in * scale
    ms_per_in /= scale
    chart_h = n_lanes * TL_ROW_H

    title = spec.get("title")
    title_h = 0.32 * scale if title else 0.0
    fig_w = TL_LABEL_W + chart_w + 0.3
    fig_h = title_h + TL_TOP_STRIP + chart_h + TL_AXIS_H

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    ax._text_options = spec.get("text_format", {})
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    ax.set_aspect("equal")

    def lane_y(lid):
        """Top-of-lane y coordinate, lane 0 at the top."""
        return fig_h - title_h - TL_TOP_STRIP - TL_ROW_H * lane_ix[lid]

    def t_x(t_ms):
        return TL_LABEL_W + (t_ms / ms_per_in)

    if title:
        _text(ax, fig_w / 2, fig_h - title_h * 0.6, title, fontsize=FONT + 1.2,
                fontweight="bold", ha="center", va="center", color="#222222")

    # Lane bands (alternating tint) + labels.
    for lane in lanes:
        y = lane_y(lane["id"])
        band = "#FAFAFA" if (lane_ix[lane["id"]] % 2 == 0) else "#FFFFFF"
        ax.add_patch(Rectangle((TL_LABEL_W, y - TL_ROW_H), chart_w, TL_ROW_H,
                               facecolor=band, edgecolor="none", zorder=0))
        ax.plot([TL_LABEL_W, TL_LABEL_W + chart_w], [y - TL_ROW_H, y - TL_ROW_H],
                color="#DDDDDD", lw=0.8, zorder=1)
        _text(ax, TL_LABEL_W - 0.08, y - TL_ROW_H / 2, lane["label"],
                fontsize=TL_FONT, ha="right", va="center", color="#333333")

    # Bars.
    for bar in spec.get("bars", []):
        y = lane_y(bar["lane"])
        st = STYLE.get(bar.get("style", "box"), STYLE["box"])
        x0 = t_x(max(bar["start"], 0.0))
        x1 = t_x(min(bar["end"], duration))
        w = max(x1 - x0, 0.02)
        h = TL_ROW_H * 0.72
        ax.add_patch(FancyBboxPatch(
            (x0, y - TL_ROW_H / 2 - h / 2), w, h,
            boxstyle="round,pad=0,rounding_size=0.05",
            facecolor=st["fc"], edgecolor=st["ec"], linewidth=st["lw"],
            zorder=2))
        label = bar.get("label", "")
        if label:
            _text(ax, x0 + w / 2, y - TL_ROW_H / 2, label, fontsize=TL_FONT - 0.6,
                    ha="center", va="center", color="#222222", zorder=3,
                    linespacing=1.2)

    # Ticks: small dense marks, no label.
    for tick in spec.get("ticks", []):
        y = lane_y(tick["lane"])
        x = t_x(tick["t"])
        ax.plot([x, x], [y - TL_ROW_H * 0.72, y - TL_ROW_H * 0.28],
                color="#777777", lw=0.9, zorder=3)

    # Events: full-height vertical marker + label in the top strip.
    top_y = fig_h - title_h - TL_TOP_STRIP
    bottom_y = top_y - chart_h
    for ev in spec.get("events", []):
        x = t_x(ev["t"])
        st = STYLE.get(ev.get("style", "box"), STYLE["box"])
        ax.plot([x, x], [bottom_y, top_y], color=st["ec"], lw=1.2,
                linestyle="--", zorder=1, alpha=0.85)
        ax.plot([x], [top_y], marker="v", color=st["ec"], markersize=5,
                zorder=4)
        label = ev.get("label", "")
        if label:
            _text(ax, x, top_y + 0.06, label, fontsize=TL_FONT - 0.4,
                    ha="center", va="bottom", color=st["ec"], zorder=4,
                    linespacing=1.15,
                    bbox=dict(fc="white", ec=st["ec"], lw=0.6, pad=1.4))

    # Time ruler.
    axis_y = bottom_y
    ax.plot([TL_LABEL_W, TL_LABEL_W + chart_w], [axis_y, axis_y],
            color="#333333", lw=1.0, zorder=2)
    step = _tl_nice_step(duration)
    t = 0.0
    while t <= duration + 1e-6:
        x = t_x(t)
        ax.plot([x, x], [axis_y, axis_y - 0.05], color="#333333", lw=0.8)
        _text(ax, x, axis_y - 0.10 * scale, f"{t:g}", fontsize=TL_FONT - 1.0,
                ha="center", va="top", color="#333333")
        t += step
    _text(ax, TL_LABEL_W + chart_w, axis_y - 0.28 * scale,
            spec.get("unit_label", "ms"), fontsize=TL_FONT - 1.0,
            ha="right", va="top", color="#666666", style="italic")

    fig.savefig(out_path, bbox_inches="tight", pad_inches=0.06,
                facecolor="white")
    plt.close(fig)
    return out_path


# ============================================================================
# SEQUENCE DIAGRAMS
# ============================================================================

SQ_ACTOR_W = 2.0          # inches pitch between lifelines
SQ_HEADER_H = 0.55
SQ_ROW_H = 0.52           # row height for a short (<=2 line) label
SQ_LINE_H = 0.16           # extra inches per label line beyond that
SQ_LABEL_PAD = 0.18
SQ_FONT = 8.0
SQ_SELF_REACH = 0.55


def _sq_row_height(msg):
    """Row height for one message, grown to fit a multi-line label.

    A fixed row height is fine for the common one/two-line case, but a
    self-message documenting several guard conditions (as motor request
    validation does) easily runs to 4 lines - centred text at a fixed row
    height then bleeds into the row above and below it. Same principle as
    the flowchart tool's node sizing: measure the content, don't guess a
    margin that only happens to fit whatever was tested first.
    """
    text = msg.get("note") or msg.get("label") or ""
    n_lines = text.count("\n") + 1 if text else 0
    if n_lines <= 0:
        return SQ_ROW_H
    return max(SQ_ROW_H, n_lines * SQ_LINE_H + SQ_LABEL_PAD)


def render_sequence(spec, out_path):
    """Render a UML-ish sequence diagram (see module docstring) to a PNG.

    Not time-scaled: messages are drawn top-to-bottom in list order, one row
    each, spaced evenly. Use render_timeline instead when real durations
    matter to the explanation.
    """
    if isinstance(spec, str):
        spec = json.loads(spec)
    spec = _prepare_text(spec)
    scale = _font_scale(spec)
    SQ_ACTOR_W, SQ_HEADER_H = 2.0 * scale, 0.55 * scale

    actors = spec["actors"]
    actor_margin = 0.2 + SQ_ACTOR_W * 0.34
    actor_x = {a["id"]: (actor_margin + SQ_ACTOR_W * i) for i, a in enumerate(actors)}
    n_actors = len(actors)
    messages = spec.get("messages", [])

    # Row heights are computed once, up front, so the figure height and every
    # row's y-position can be fixed before any drawing happens - the same
    # measure-then-lay-out order the flowchart renderer uses for node sizing.
    row_heights = [_sq_row_height(m) * scale for m in messages]
    rows_total_h = sum(row_heights) + SQ_ROW_H * 0.6   # trailing breathing room

    title = spec.get("title")
    title_h = 0.34 * scale if title else 0.0
    fig_w = actor_margin + SQ_ACTOR_W * (n_actors - 1) + max(1.6, actor_margin)
    fig_h = title_h + SQ_HEADER_H + rows_total_h

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    ax._text_options = spec.get("text_format", {})
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    ax.set_aspect("equal")

    if title:
        _text(ax, fig_w / 2, fig_h - title_h * 0.6, title, fontsize=FONT + 1.2,
                fontweight="bold", ha="center", va="center", color="#222222")

    top_y = fig_h - title_h
    bottom_y = top_y - SQ_HEADER_H - sum(row_heights)

    # Actor headers + lifelines.
    st = STYLE["box"]
    for a in actors:
        x = actor_x[a["id"]]
        ax.add_patch(FancyBboxPatch(
            (x - SQ_ACTOR_W * 0.34, top_y - SQ_HEADER_H),
            SQ_ACTOR_W * 0.68, SQ_HEADER_H,
            boxstyle="round,pad=0,rounding_size=0.05",
            facecolor=st["fc"], edgecolor=st["ec"], linewidth=st["lw"],
            zorder=3))
        _text(ax, x, top_y - SQ_HEADER_H / 2, a["label"], fontsize=SQ_FONT,
                fontweight="bold", ha="center", va="center", zorder=4,
                linespacing=1.15)
        ax.plot([x, x], [top_y - SQ_HEADER_H, bottom_y], color="#AAAAAA",
                lw=1.0, linestyle=":", zorder=1)

    # Messages, one per row (row heights already computed above), top to
    # bottom.
    y = top_y - SQ_HEADER_H
    for msg, row_h in zip(messages, row_heights):
        y -= row_h
        mid = y + row_h * 0.5

        if "note" in msg:
            ax.plot([0.15, fig_w - 0.15], [mid, mid], color="#CCCCCC",
                    lw=0.8, zorder=1)
            _text(ax, fig_w / 2, mid, msg["note"], fontsize=SQ_FONT - 0.4,
                    ha="center", va="center", style="italic", color="#555555",
                    zorder=3, bbox=dict(fc="#FFFDE7", ec="#CCCCCC", lw=0.8,
                                        pad=2.2))
            continue

        x0 = actor_x[msg["from"]]
        x1 = actor_x[msg["to"]]
        dashed = bool(msg.get("dashed"))
        style = "--" if dashed else "-"
        label = msg.get("label", "")

        if x0 == x1:
            # Self-message: small loop to the right of the lifeline. Loop
            # size stays tied to the base row height (it is a fixed visual
            # element, not label content), only the label's own vertical
            # centring benefits from a taller row.
            p0 = (x0, mid + SQ_ROW_H * 0.16)
            p1 = (x0, mid - SQ_ROW_H * 0.16)
            ax.add_patch(FancyArrowPatch(
                p0, p1, connectionstyle=f"arc3,rad=-1.3", arrowstyle="-|>",
                mutation_scale=9, color="#555555", lw=1.0, linestyle=style,
                zorder=2))
            if label:
                _text(ax, x0 + SQ_SELF_REACH + 0.06, mid, label,
                        fontsize=SQ_FONT - 0.8, ha="left", va="center",
                        color="#222222", linespacing=1.15)
        else:
            ax.annotate("", xy=(x1, mid), xytext=(x0, mid),
                        arrowprops=dict(arrowstyle="-|>", color="#555555",
                                        lw=1.1, linestyle=style))
            if label:
                lx = (x0 + x1) / 2
                _text(ax, lx, mid + 0.05, label, fontsize=SQ_FONT - 0.8,
                        ha="center", va="bottom", color="#222222",
                        linespacing=1.15,
                        bbox=dict(fc="white", ec="none", pad=1.0))

    fig.savefig(out_path, bbox_inches="tight", pad_inches=0.06,
                facecolor="white")
    plt.close(fig)
    return out_path


def render_fishbone(spec, out_path):
    """Render a cause-and-effect diagram to PNG and return out_path."""
    spec = _prepare_text(json.loads(spec) if isinstance(spec, str) else spec)
    def label(value, field, width):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        return _keep_style(value, "\n".join(
            textwrap.fill(line, width=width) for line in value.splitlines()))

    def parse_cause(value, field):
        if isinstance(value, str):
            return {"label": label(value, field, 26), "causes": []}
        if not isinstance(value, dict):
            raise ValueError(f"{field} must be a string or cause object")
        text = label(value.get("label"), f"{field}.label", 26)
        children = value.get("causes", [])
        if not isinstance(children, list):
            raise ValueError(f"{field}.causes must be a list")
        return {"label": text,
                "causes": [parse_cause(child, f"{field}.causes[{i}]")
                           for i, child in enumerate(children)]}

    if not isinstance(spec, dict):
        raise ValueError("fishbone spec must be an object")
    effect = label(spec.get("effect"), "effect", 22)
    categories = spec.get("categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError("categories must be a non-empty list")
    title = spec.get("title", "")
    if not isinstance(title, str):
        raise ValueError("title must be a string")
    prepared = []
    for i, category in enumerate(categories):
        field = f"categories[{i}]"
        if not isinstance(category, dict):
            raise ValueError(f"{field} must be an object")
        heading = label(category.get("label"), f"{field}.label", 24)
        causes = category.get("causes", [])
        if not isinstance(causes, list):
            raise ValueError(f"{field}.causes must be a list")
        causes = [parse_cause(c, f"{field}.causes[{j}]")
                  for j, c in enumerate(causes)]
        style = category.get("style", "box")
        if not isinstance(style, str) or style not in STYLE:
            raise ValueError(f"{field}.style must name a STYLE palette entry")
        prepared.append((heading, causes, STYLE[style]))

    # Measure actual glyphs at the final font size. Every subtree reserves its
    # full bounds before placement, including wrapped labels and descendants.
    fig, ax = plt.subplots(figsize=(1, 1), dpi=180)
    ax._text_options = spec.get("text_format", {})
    try:
        renderer = fig.canvas.get_renderer()
        font_size = FONT - 0.5

        def measure(text, bold=False):
            artist = _text(ax, 0, 0, text, fontsize=FONT if bold else font_size,
                             fontweight="bold" if bold else "normal",
                             linespacing=1.15)
            bounds = artist.get_window_extent(renderer)
            artist.remove()
            return bounds.width / fig.dpi, bounds.height / fig.dpi

        slope = 0.55
        gap = 0.22

        def plan(cause):
            width, height = measure(cause["label"])
            cause["line_w"] = max(1.65, width + 0.63 + slope * (height + 0.04))
            cause["height"] = height + 0.08
            cause["width"] = cause["line_w"]
            cursor = height + gap
            for child in cause["causes"]:
                plan(child)
                child["offset"] = cursor
                cause["width"] = max(cause["width"],
                                       0.45 + slope * cursor + child["width"])
                cursor += child["height"] + gap
            if cause["causes"]:
                cause["height"] = cursor - gap

        layouts = []
        for heading, causes, st in prepared:
            cursor = 0.38
            left = 0.0
            for cause in causes:
                plan(cause)
                cause["offset"] = cursor
                left = min(left, -slope * cursor - cause["width"])
                cursor += cause["height"] + gap
            branch_h = max(0.9, cursor + 0.12)
            heading_w, heading_h = measure(heading, bold=True)
            heading_w = max(1.9, heading_w + 0.32)
            heading_h += 0.24
            tip_x = -slope * branch_h
            left = min(left, tip_x - heading_w / 2)
            right = max(0, tip_x + heading_w / 2)
            layouts.append(dict(heading=heading, causes=causes, style=st,
                                branch_h=branch_h, heading_w=heading_w,
                                heading_h=heading_h, left=left, right=right,
                                height=branch_h + 0.08 + heading_h))

        # Pair upper/lower categories into separate columns. Each pair gets
        # enough width for its own widest subtree rather than a global pad.
        cursor = 0.25
        for i in range(0, len(layouts), 2):
            pair = layouts[i:i + 2]
            left = min(item["left"] for item in pair)
            right = max(item["right"] for item in pair)
            for item in pair:
                item["root_x"] = cursor - left
            cursor += right - left + 0.45
        effect_w, effect_h = measure(effect, bold=True)
        effect_w = max(1.8, effect_w + 0.35)
        effect_h = max(0.65, effect_h + 0.28)
        effect_x = cursor
        fig_w = effect_x + effect_w + 0.25
        top_h = max(effect_h / 2, *(item["height"] for item in layouts[::2]))
        bottom_h = max([effect_h / 2] + [item["height"] for item in layouts[1::2]])
        title = _keep_style(title, textwrap.fill(title, width=max(30, int(fig_w * 10 / _font_scale(title)))))
        title_h = measure(title, bold=True)[1] + 0.3 if title else 0
        spine_y = bottom_h + 0.20
        fig_h = spine_y + top_h + title_h + 0.20
        fig.set_size_inches(fig_w, fig_h)
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        ax.set(xlim=(0, fig_w), ylim=(0, fig_h), aspect="equal")
        ax.axis("off")
        if title:
            _text(ax, fig_w / 2, fig_h - 0.12, title, ha="center", va="top",
                    fontsize=FONT, fontweight="bold")
        ax.add_patch(FancyArrowPatch(
            (0.15, spine_y), (effect_x, spine_y), arrowstyle="-|>",
            mutation_scale=14, color=EDGE_COLOR, lw=1.7))
        st = STYLE["danger"]
        ax.add_patch(FancyBboxPatch(
            (effect_x, spine_y - effect_h / 2), effect_w, effect_h,
            boxstyle="round,pad=0,rounding_size=0.08",
            facecolor=st["fc"], edgecolor=st["ec"], linewidth=st["lw"]))
        _text(ax, effect_x + effect_w / 2, spine_y, effect, ha="center", va="center",
                fontsize=FONT, fontweight="bold")
        for i, layout in enumerate(layouts):
            st = layout["style"]
            direction = 1 if i % 2 == 0 else -1
            root_x = layout["root_x"]
            tip_x = root_x - slope * layout["branch_h"]
            tip_y = spine_y + direction * layout["branch_h"]
            heading_h = layout["heading_h"]
            heading_w = layout["heading_w"]
            ax.plot([tip_x, root_x], [tip_y, spine_y],
                    color=st["ec"], lw=1.5)
            ax.add_patch(FancyBboxPatch(
                (tip_x - heading_w / 2, tip_y + (0.08 if direction > 0 else -heading_h - 0.08)),
                heading_w, heading_h, boxstyle="round,pad=0,rounding_size=0.05",
                facecolor=st["fc"], edgecolor=st["ec"], linewidth=st["lw"]))
            _text(ax, tip_x, tip_y + direction * (heading_h / 2 + 0.08),
                    layout["heading"], ha="center", va="center", fontsize=FONT,
                    fontweight="bold")

            def draw_cause(cause, x, y):
                ax.plot([x - cause["line_w"], x], [y, y], color=st["ec"], lw=0.9)
                _text(ax, x - cause["line_w"] + 0.03, y + direction * 0.04,
                        cause["label"], ha="left",
                        va="bottom" if direction > 0 else "top",
                        fontsize=FONT - 0.5, linespacing=1.15)
                children = cause["causes"]
                if children:
                    # One parallel diagonal gathers all immediate children.
                    # Its root sits beyond the parent's label, avoiding ink
                    # through the text even for a wrapped parent label.
                    root = x - 0.45
                    end = children[-1]["offset"] + 0.10
                    ax.plot([root, root - slope * end],
                            [y, y + direction * end], color=st["ec"], lw=0.9)
                    for child in children:
                        offset = child["offset"]
                        draw_cause(child, root - slope * offset,
                                   y + direction * offset)

            for cause in layout["causes"]:
                offset = cause["offset"]
                draw_cause(cause, root_x - slope * offset,
                           spine_y + direction * offset)
        fig.savefig(out_path, facecolor="white")
    finally:
        plt.close(fig)
    return out_path


if __name__ == "__main__":
    # Usage: python flowchart.py [flow|timeline|sequence|fishbone] spec.json out.png
    # The kind defaults to "flow" so existing callers (spec.json out.png,
    # two args) keep working unchanged.
    import sys

    RENDERERS = {"flow": render, "timeline": render_timeline,
                "sequence": render_sequence, "fishbone": render_fishbone}

    args = sys.argv[1:]
    kind = args[0] if args and args[0] in RENDERERS else "flow"
    if args and args[0] in RENDERERS:
        args = args[1:]

    spec_path, out_path = args[0], args[1]
    spec = json.loads(open(spec_path, encoding="utf8").read())
    RENDERERS[kind](spec, out_path)
    print("wrote", out_path)
