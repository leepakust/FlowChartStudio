"""Flowchart renderer for the Faraday firmware design documents.

Renders a declarative flowchart spec to a PNG suitable for embedding in a Word
document. No external binaries required (matplotlib only) -- Graphviz/mermaid
are not available on the build machine.

Spec format (JSON, inside a ```flow fence in the markdown source):

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
        ["C","B","no","left"],      # 4th field routes the edge around the side
        ["C","B","alt","left",0.25,0.5]
      ]
    }

Edge fields: [src, dst, label, route, shift, lane]

  shift - slides BOTH endpoints along the node side they attach to (inches).
          Use it when several edges touch the same node: without it they all
          land on the node's mid-point and overdraw each other.
  lane  - pushes a "left"/"right" routed rail further out, so two side-routed
          edges on the same flank stay visually separate.

Shapes: box (process), terminal (rounded, start/end), decision (diamond),
        io (parallelogram), note (dashed box).

STATE MACHINE DIAGRAMS
----------------------
The same spec renders UML-style state charts using three extra shapes and
self-transitions:

    {
      "nodes": [
        {"id":"I",    "col":0, "row":0, "shape":"start"},
        {"id":"RUN",  "col":0, "row":1, "text":"RUNNING", "shape":"state"},
        {"id":"STOP", "col":0, "row":2, "text":"HALTED",  "shape":"final"}
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

A self-transition is any edge whose source and destination are the same node;
route "self" (or "self-top") loops above the state, "self-left" / "self-right"
loop out to that side. Use those when a state has an action it repeats while
remaining in that state.
"""

import json
import math
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import (FancyBboxPatch, Polygon, FancyArrowPatch,
                                Circle)

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
    st = STYLE.get(shape, STYLE["box"])
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


def _draw_self_edge(ax, node, label, route, bounds):
    """A state that transitions to itself: loop out and back on one side.

    Drawn as a single curved arrow between two points on the same edge of the
    node, so it reads as a transition rather than a decoration. The loop's far
    side is fed into the extent lists or it renders clipped.
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
        ax.text(lx, ly, label, fontsize=FONT - 0.8, ha="center", va="center",
                rotation=rot, color="#333333",
                bbox=dict(fc="white", ec="none", pad=1.0))


def _draw_edge(ax, src, dst, label="", route="", bounds=None, shift=0.0,
               lane=0.0):
    sx, sy = _xy(src)
    dx, dy = _xy(dst)

    if src is dst or route.startswith("self"):
        _draw_self_edge(ax, src, label, route or "self", bounds)
        return

    if route in ("left", "right"):
        # Route around the side -- used for feedback/retry loops.
        side = "left" if route == "left" else "right"
        p0 = _anchor(src, side, shift)
        p1 = _anchor(dst, side, shift)
        # `lane` pushes this rail further out so two side-routed edges on the
        # same flank run as separate lines instead of one overdrawn stripe.
        off = (0.62 + lane) * (-1 if route == "left" else 1)
        mid = (min(p0[0], p1[0]) + off) if route == "left" \
            else (max(p0[0], p1[0]) + off)
        ax.plot([p0[0], mid, mid, p1[0]], [p0[1], p0[1], p1[1], p1[1]],
                color="#555555", linewidth=1.1, zorder=1,
                solid_joinstyle="miter")
        ax.annotate("", xy=p1, xytext=(mid, p1[1]),
                    arrowprops=dict(arrowstyle="-|>", color="#555555", lw=1.1))
        if label:
            ax.text(mid, (p0[1] + p1[1]) / 2, label, fontsize=FONT - 0.8,
                    ha="center", va="center", rotation=90, color="#333333",
                    bbox=dict(fc="white", ec="none", pad=1.0))
        # Feed the loop's outer rail into the axis-limit calculation, or it
        # gets clipped away and the connector renders as two stray stubs.
        if bounds is not None:
            bounds["xs"].append(mid + (-0.30 if route == "left" else 0.30))
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
        ax.text(lx, ly, label, fontsize=FONT - 0.8, ha="center", va="center",
                color="#333333", bbox=dict(fc="white", ec="none", pad=1.2))


def render(spec, out_path):
    """Render a spec dict (or JSON string) to a PNG at out_path."""
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
        _draw_edge(ax, src, dst, label, route, bounds, shift, lane)

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


if __name__ == "__main__":
    import sys
    render(open(sys.argv[1], encoding="utf8").read(), sys.argv[2])
    print("wrote", sys.argv[2])
