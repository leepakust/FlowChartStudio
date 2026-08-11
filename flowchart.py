"""Diagram renderer for the Faraday firmware design documents.

Renders declarative diagram specs (JSON, inside fenced code blocks in the
markdown source) to PNGs suitable for embedding in a Word document. No
external binaries required (matplotlib only) -- Graphviz/mermaid are not
available on the build machine.

Three diagram kinds, each with its own fence tag and render() entry point:

  ```flow      -> render()          flowcharts and UML-ish state machines
  ```timeline  -> render_timeline() swimlane timing / sequencing charts
  ```sequence  -> render_sequence() UML-style sequence diagrams

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

  shift - slides BOTH endpoints along the node side they attach to (inches).
          Use it when several edges touch the same node: without it they all
          land on the node's mid-point and overdraw each other. For an
          A->B / B->A pair, give one +0.26 and the other -0.26 to get two
          clean parallel arrows.
  lane  - pushes a "left"/"right" routed rail further out, so two side-routed
          edges on the same flank do not share one track.

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

import json
import math
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import (FancyBboxPatch, Polygon, FancyArrowPatch,
                                Circle, Rectangle)

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


def _wrap(text, shape):
    width = 22 if shape == "decision" else 26
    lines = []
    for para in text.split("\n"):
        lines.extend(textwrap.wrap(para, width) or [""])
    return "\n".join(lines)


def _xy(node):
    return (node["col"] * COL_W, -node["row"] * ROW_H)


def _place_text(ax, node):
    """Pass 1: lay the label down so its true rendered size can be measured."""
    shape = node.get("shape", "box")
    if shape in MARKER_SHAPES:
        node["_txt"] = None         # pseudostates carry no interior label
        return

    x, y = _xy(node)
    label = _wrap(node["text"], shape)
    node["_txt"] = ax.text(
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


def _register_label_bounds(fig, txt, cx, cy, bounds, pad=0.08):
    """Push a just-created label's ACTUAL rendered size into bounds, centred
    on the (cx, cy) data-coordinate anchor it was drawn at.

    Same principle as node sizing in _measure(): measure the real rendered
    extent (inches, via the renderer) instead of guessing a fixed margin. A
    fixed margin is fine for a short one-line label but silently clips any
    label longer than whatever the margin's author tested with - multi-line
    self-loop and rail labels are exactly the case that breaks it. Works for
    rotated text too: get_window_extent() returns the axis-aligned box of the
    text AFTER rotation, so no separate rotation handling is needed here.
    """
    bb = txt.get_window_extent(renderer=fig.canvas.get_renderer())
    half_w = (bb.width / fig.dpi) / 2.0 + pad
    half_h = (bb.height / fig.dpi) / 2.0 + pad
    bounds["xs"] += [cx - half_w, cx + half_w]
    bounds["ys"] += [cy - half_h, cy + half_h]


def _draw_self_edge(ax, fig, node, label, route, bounds):
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
        txt = ax.text(lx, ly, label, fontsize=FONT - 0.8, ha="center",
                      va="center", rotation=rot, color="#333333",
                      bbox=dict(fc="white", ec="none", pad=1.0))
        _register_label_bounds(fig, txt, lx, ly, bounds)


def _draw_edge(ax, fig, src, dst, label="", route="", bounds=None, shift=0.0,
               lane=0.0):
    sx, sy = _xy(src)
    dx, dy = _xy(dst)

    if src is dst or route.startswith("self"):
        _draw_self_edge(ax, fig, src, label, route or "self", bounds)
        return

    if route in ("left", "right"):
        # Route around the side -- used for feedback/retry loops.
        side = "left" if route == "left" else "right"
        p0 = _anchor(src, side, shift)
        p1 = _anchor(dst, side, shift)
        # `lane` pushes this rail further out, so two side-routed edges on
        # the same flank run as separate lines instead of one overdrawn stripe.
        off = (0.62 + lane) * (-1 if route == "left" else 1)
        mid = (min(p0[0], p1[0]) + off) if route == "left" \
            else (max(p0[0], p1[0]) + off)
        ax.plot([p0[0], mid, mid, p1[0]], [p0[1], p0[1], p1[1], p1[1]],
                color="#555555", linewidth=1.1, zorder=1,
                solid_joinstyle="miter")
        ax.annotate("", xy=p1, xytext=(mid, p1[1]),
                    arrowprops=dict(arrowstyle="-|>", color="#555555", lw=1.1))
        # Feed the loop's outer rail into the axis-limit calculation, or it
        # gets clipped away and the connector renders as two stray stubs.
        if bounds is not None:
            bounds["xs"].append(mid + (-0.30 if route == "left" else 0.30))
        if label:
            lcy = (p0[1] + p1[1]) / 2
            txt = ax.text(mid, lcy, label, fontsize=FONT - 0.8, ha="center",
                          va="center", rotation=90, color="#333333",
                          bbox=dict(fc="white", ec="none", pad=1.0))
            if bounds is not None:
                _register_label_bounds(fig, txt, mid, lcy, bounds)
        return

    # Straight / elbow routing between the natural facing sides.
    if abs(dy - sy) < 1e-6:                       # same row -> horizontal
        s_side, d_side = ("right", "left") if dx > sx else ("left", "right")
    elif abs(dx - sx) < 1e-6:                     # same column -> vertical
        s_side, d_side = ("bottom", "top") if dy < sy else ("top", "bottom")
    else:                                         # diagonal -> elbow
        s_side = "bottom" if dy < sy else "top"
        d_side = "left" if dx > sx else "right"

    p0 = _anchor(src, s_side, shift)
    p1 = _anchor(dst, d_side, shift)

    if s_side in ("bottom", "top") and d_side in ("left", "right"):
        ax.plot([p0[0], p0[0]], [p0[1], p1[1]], color="#555555", lw=1.1, zorder=1)
        ax.annotate("", xy=p1, xytext=(p0[0], p1[1]),
                    arrowprops=dict(arrowstyle="-|>", color="#555555", lw=1.1))
        lx, ly = p0[0], (p0[1] + p1[1]) / 2
    else:
        ax.annotate("", xy=p1, xytext=p0,
                    arrowprops=dict(arrowstyle="-|>", color="#555555", lw=1.1))
        lx, ly = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2

    if label:
        txt = ax.text(lx, ly, label, fontsize=FONT - 0.8, ha="center",
                      va="center", color="#333333",
                      bbox=dict(fc="white", ec="none", pad=1.2))
        if bounds is not None:
            _register_label_bounds(fig, txt, lx, ly, bounds)


def render(spec, out_path):
    """Render a flowchart/state-machine spec dict (or JSON string) to a PNG."""
    if isinstance(spec, str):
        spec = json.loads(spec)

    nodes = {n["id"]: n for n in spec["nodes"]}

    fig, ax = plt.subplots(figsize=(1, 1), dpi=200)
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
    for n in spec["nodes"]:
        _draw_shape(ax, n)

    bounds = {"xs": [], "ys": []}
    for e in spec.get("edges", []):
        src, dst = nodes[e[0]], nodes[e[1]]
        label = e[2] if len(e) > 2 else ""
        route = e[3] if len(e) > 3 else ""
        shift = float(e[4]) if len(e) > 4 else 0.0
        lane = float(e[5]) if len(e) > 5 else 0.0
        _draw_edge(ax, fig, src, dst, label, route, bounds, shift, lane)

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

    lanes = spec["lanes"]
    lane_ix = {l["id"]: i for i, l in enumerate(lanes)}
    n_lanes = len(lanes)
    duration = float(spec["duration_ms"])

    ms_per_in = max(duration / 8.5, 12.0)     # keep the chart a sane width
    chart_w = duration / ms_per_in
    chart_h = n_lanes * TL_ROW_H

    title = spec.get("title")
    title_h = 0.32 if title else 0.0
    fig_w = TL_LABEL_W + chart_w + 0.3
    fig_h = title_h + TL_TOP_STRIP + chart_h + TL_AXIS_H

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
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
        ax.text(fig_w / 2, fig_h - title_h * 0.6, title, fontsize=FONT + 1.2,
                fontweight="bold", ha="center", va="center", color="#222222")

    # Lane bands (alternating tint) + labels.
    for lane in lanes:
        y = lane_y(lane["id"])
        band = "#FAFAFA" if (lane_ix[lane["id"]] % 2 == 0) else "#FFFFFF"
        ax.add_patch(Rectangle((TL_LABEL_W, y - TL_ROW_H), chart_w, TL_ROW_H,
                               facecolor=band, edgecolor="none", zorder=0))
        ax.plot([TL_LABEL_W, TL_LABEL_W + chart_w], [y - TL_ROW_H, y - TL_ROW_H],
                color="#DDDDDD", lw=0.8, zorder=1)
        ax.text(TL_LABEL_W - 0.08, y - TL_ROW_H / 2, lane["label"],
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
            ax.text(x0 + w / 2, y - TL_ROW_H / 2, label, fontsize=TL_FONT - 0.6,
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
            ax.text(x, top_y + 0.06, label, fontsize=TL_FONT - 0.4,
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
        ax.text(x, axis_y - 0.10, f"{t:g}", fontsize=TL_FONT - 1.0,
                ha="center", va="top", color="#333333")
        t += step
    ax.text(TL_LABEL_W + chart_w, axis_y - 0.28,
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

    actors = spec["actors"]
    actor_x = {a["id"]: (0.4 + SQ_ACTOR_W * i) for i, a in enumerate(actors)}
    n_actors = len(actors)
    messages = spec.get("messages", [])

    # Row heights are computed once, up front, so the figure height and every
    # row's y-position can be fixed before any drawing happens - the same
    # measure-then-lay-out order the flowchart renderer uses for node sizing.
    row_heights = [_sq_row_height(m) for m in messages]
    rows_total_h = sum(row_heights) + SQ_ROW_H * 0.6   # trailing breathing room

    title = spec.get("title")
    title_h = 0.34 if title else 0.0
    fig_w = 0.4 + SQ_ACTOR_W * (n_actors - 1) + 1.6
    fig_h = title_h + SQ_HEADER_H + rows_total_h

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    ax.set_aspect("equal")

    if title:
        ax.text(fig_w / 2, fig_h - title_h * 0.6, title, fontsize=FONT + 1.2,
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
        ax.text(x, top_y - SQ_HEADER_H / 2, a["label"], fontsize=SQ_FONT,
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
            ax.text(fig_w / 2, mid, msg["note"], fontsize=SQ_FONT - 0.4,
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
                ax.text(x0 + SQ_SELF_REACH + 0.06, mid, label,
                        fontsize=SQ_FONT - 0.8, ha="left", va="center",
                        color="#222222", linespacing=1.15)
        else:
            ax.annotate("", xy=(x1, mid), xytext=(x0, mid),
                        arrowprops=dict(arrowstyle="-|>", color="#555555",
                                        lw=1.1, linestyle=style))
            if label:
                lx = (x0 + x1) / 2
                ax.text(lx, mid + 0.05, label, fontsize=SQ_FONT - 0.8,
                        ha="center", va="bottom", color="#222222",
                        linespacing=1.15,
                        bbox=dict(fc="white", ec="none", pad=1.0))

    fig.savefig(out_path, bbox_inches="tight", pad_inches=0.06,
                facecolor="white")
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    # Usage: python flowchart.py [flow|timeline|sequence] spec.json out.png
    # The kind defaults to "flow" so existing callers (spec.json out.png,
    # two args) keep working unchanged.
    import sys

    RENDERERS = {"flow": render, "timeline": render_timeline,
                "sequence": render_sequence}

    args = sys.argv[1:]
    kind = args[0] if args and args[0] in RENDERERS else "flow"
    if args and args[0] in RENDERERS:
        args = args[1:]

    spec_path, out_path = args[0], args[1]
    spec = json.loads(open(spec_path, encoding="utf8").read())
    RENDERERS[kind](spec, out_path)
    print("wrote", out_path)
