"""Declarative engineering-diagram renderer.

Renders declarative diagram specs (JSON, inside fenced code blocks in the
markdown source) to PNGs suitable for embedding in a Word document. No
external binaries required (matplotlib only) -- Graphviz/mermaid are not
available on the build machine.

Four diagram kinds, each with its own fence tag and render() entry point:

  ```flow      -> render()          flowcharts and UML-ish state machines
  ```timeline  -> render_timeline() swimlane timing / sequencing charts
  ```sequence  -> render_sequence() UML-style sequence diagrams
  ```tasks     -> render_tasks()    RTOS task interaction / scheduler charts

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

============================================================================
RTOS TASK SEQUENCER  (render_tasks)
============================================================================

    {
      "title": "FreeRTOS control cycle",
      "duration_ms": 5,
      "tasks": [
        {"id":"isr",  "label":"ADC ISR",     "priority":"IRQ"},
        {"id":"ctrl", "label":"ControlTask", "priority":4},
        {"id":"comm", "label":"CommsTask",   "priority":2}
      ],
      "segments": [
        {"task":"isr",  "start":1.00, "end":1.08,
         "state":"running", "label":"ADC IRQ"},
        {"task":"ctrl", "start":1.08, "end":1.65,
         "state":"running", "label":"filter + PID"},
        {"task":"comm", "start":1.65, "end":2.10,
         "state":"running", "label":"publish"},
        {"task":"ctrl", "start":0.00, "end":1.00,
         "state":"blocked", "label":"wait notify"}
      ],
      "links": [
        {"from":{"task":"isr", "t":1.08},
         "to":{"task":"ctrl", "t":1.08},
         "label":"notify"}
      ],
      "events": [
        {"t":1.0, "label":"ADC interrupt", "style":"danger"}
      ]
    }

Task segments support the states ``running``, ``ready``, ``blocked``,
``suspended`` and ``isr``.  The renderer also derives a compact CPU strip
from all ``running``/``isr`` segments, making context switches obvious while
the per-task lanes explain why each task was runnable or blocked.  ``links``
connect task/time points and are useful for queue sends, semaphore gives,
notifications and wake-ups.
"""

import copy
import itertools
import json
import math
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path
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

FLOW_SHAPES = {"box", "terminal", "decision", "io", "note",
               "state", "start", "final"}
FLOW_ROUTES = {"", "left", "right", "self", "self-top",
               "self-left", "self-right"}
TASK_STATES = {"running", "ready", "blocked", "suspended", "isr"}


class SpecValidationError(ValueError):
    """Human-readable semantic errors in a diagram specification."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


def detect_kind(spec):
    """Return ``flow``, ``timeline``, ``sequence`` or ``tasks`` when clear."""
    if not isinstance(spec, dict):
        return None
    if "tasks" in spec and "segments" in spec:
        return "tasks"
    if "actors" in spec and "messages" in spec:
        return "sequence"
    if "lanes" in spec:
        return "timeline"
    if "nodes" in spec:
        return "flow"
    return None


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(float(v))


def validate_spec(spec, kind=None):
    """Validate a spec before rendering.

    Returns a small report containing the detected kind and non-fatal
    warnings.  Semantic problems are collected and raised together as
    :class:`SpecValidationError` so a GUI/CLI user gets actionable feedback
    rather than the first cryptic ``KeyError`` or Matplotlib traceback.
    """
    errors, warnings = [], []
    if not isinstance(spec, dict):
        raise SpecValidationError(["Top level must be a JSON object."])

    detected = detect_kind(spec)
    kind = detected if kind in (None, "auto") else kind
    if kind is None:
        errors.append("Could not detect diagram kind. Expected nodes, lanes, "
                      "actors/messages, or tasks/segments.")
        raise SpecValidationError(errors)
    if detected and kind != detected:
        warnings.append(f"Selected kind '{kind}' differs from detected "
                        f"kind '{detected}'.")

    if kind == "flow":
        nodes = spec.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            errors.append("'nodes' must be a non-empty array.")
            nodes = []
        ids = set()
        auto_layout = spec.get("layout") == "auto" or any(
            isinstance(n, dict) and ("col" not in n or "row" not in n)
            for n in nodes)
        for i, n in enumerate(nodes):
            p = f"nodes[{i}]"
            if not isinstance(n, dict):
                errors.append(f"{p} must be an object.")
                continue
            nid = n.get("id")
            if not isinstance(nid, str) or not nid.strip():
                errors.append(f"{p}.id must be a non-empty string.")
            elif nid in ids:
                errors.append(f"Duplicate node id '{nid}'.")
            else:
                ids.add(nid)
            shape = n.get("shape", "box")
            if shape not in FLOW_SHAPES:
                errors.append(f"{p}.shape '{shape}' is unknown. Allowed: "
                              f"{', '.join(sorted(FLOW_SHAPES))}.")
            if shape not in MARKER_SHAPES and not isinstance(n.get("text"), str):
                errors.append(f"{p}.text must be a string for shape '{shape}'.")
            if not auto_layout:
                if not _is_num(n.get("col")) or not _is_num(n.get("row")):
                    errors.append(f"{p} needs numeric col/row, or set "
                                  "top-level layout to 'auto'.")
            style = n.get("style")
            if style is not None and style not in STYLE:
                warnings.append(f"{p}.style '{style}' is unknown; default "
                                "shape styling will be used.")

        edges = spec.get("edges", [])
        if not isinstance(edges, list):
            errors.append("'edges' must be an array.")
            edges = []
        for i, e in enumerate(edges):
            p = f"edges[{i}]"
            if not isinstance(e, (list, tuple)) or not 2 <= len(e) <= 6:
                errors.append(f"{p} must contain 2..6 fields: "
                              "[src, dst, label, route, shift, lane].")
                continue
            if e[0] not in ids:
                errors.append(f"{p} references unknown source node '{e[0]}'.")
            if e[1] not in ids:
                errors.append(f"{p} references unknown target node '{e[1]}'.")
            route = e[3] if len(e) > 3 else ""
            if route not in FLOW_ROUTES:
                errors.append(f"{p} route '{route}' is invalid. Allowed: "
                              f"{', '.join(sorted(FLOW_ROUTES))}.")
            if len(e) > 4 and not _is_num(e[4]):
                errors.append(f"{p} shift must be numeric.")
            if len(e) > 5 and not _is_num(e[5]):
                errors.append(f"{p} lane must be numeric.")

    elif kind == "timeline":
        lanes = spec.get("lanes")
        if not isinstance(lanes, list) or not lanes:
            errors.append("'lanes' must be a non-empty array.")
            lanes = []
        lane_ids = set()
        for i, lane in enumerate(lanes):
            p = f"lanes[{i}]"
            if not isinstance(lane, dict):
                errors.append(f"{p} must be an object.")
                continue
            lid = lane.get("id")
            if not isinstance(lid, str) or not lid:
                errors.append(f"{p}.id must be a non-empty string.")
            elif lid in lane_ids:
                errors.append(f"Duplicate lane id '{lid}'.")
            else:
                lane_ids.add(lid)
            if not isinstance(lane.get("label"), str):
                errors.append(f"{p}.label must be a string.")
        duration = spec.get("duration_ms")
        if not _is_num(duration) or float(duration) <= 0:
            errors.append("duration_ms must be a positive number.")
            duration = 0
        for group, require_end in (("bars", True), ("events", False),
                                   ("ticks", False)):
            items = spec.get(group, [])
            if not isinstance(items, list):
                errors.append(f"'{group}' must be an array.")
                continue
            for i, item in enumerate(items):
                p = f"{group}[{i}]"
                if not isinstance(item, dict):
                    errors.append(f"{p} must be an object.")
                    continue
                if group != "events" and item.get("lane") not in lane_ids:
                    errors.append(f"{p} references unknown lane "
                                  f"'{item.get('lane')}'.")
                if group == "bars":
                    if not _is_num(item.get("start")) or not _is_num(item.get("end")):
                        errors.append(f"{p}.start/end must be numeric.")
                    elif float(item["end"]) <= float(item["start"]):
                        errors.append(f"{p}.end must be greater than start.")
                    elif duration and (float(item["start"]) < 0 or
                                       float(item["end"]) > float(duration)):
                        warnings.append(f"{p} extends outside 0..duration_ms and "
                                        "will be clipped.")
                else:
                    if not _is_num(item.get("t")):
                        errors.append(f"{p}.t must be numeric.")
                    elif duration and not 0 <= float(item["t"]) <= float(duration):
                        warnings.append(f"{p}.t is outside 0..duration_ms.")

    elif kind == "sequence":
        actors = spec.get("actors")
        if not isinstance(actors, list) or not actors:
            errors.append("'actors' must be a non-empty array.")
            actors = []
        actor_ids = set()
        for i, actor in enumerate(actors):
            p = f"actors[{i}]"
            if not isinstance(actor, dict):
                errors.append(f"{p} must be an object.")
                continue
            aid = actor.get("id")
            if not isinstance(aid, str) or not aid:
                errors.append(f"{p}.id must be a non-empty string.")
            elif aid in actor_ids:
                errors.append(f"Duplicate actor id '{aid}'.")
            else:
                actor_ids.add(aid)
            if not isinstance(actor.get("label"), str):
                errors.append(f"{p}.label must be a string.")
        messages = spec.get("messages", [])
        if not isinstance(messages, list):
            errors.append("'messages' must be an array.")
            messages = []
        for i, msg in enumerate(messages):
            p = f"messages[{i}]"
            if not isinstance(msg, dict):
                errors.append(f"{p} must be an object.")
                continue
            if "note" in msg:
                if not isinstance(msg["note"], str):
                    errors.append(f"{p}.note must be a string.")
                continue
            if msg.get("from") not in actor_ids:
                errors.append(f"{p} references unknown 'from' actor "
                              f"'{msg.get('from')}'.")
            if msg.get("to") not in actor_ids:
                errors.append(f"{p} references unknown 'to' actor "
                              f"'{msg.get('to')}'.")

    elif kind == "tasks":
        tasks = spec.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            errors.append("'tasks' must be a non-empty array.")
            tasks = []
        task_ids = set()
        for i, task in enumerate(tasks):
            p = f"tasks[{i}]"
            if not isinstance(task, dict):
                errors.append(f"{p} must be an object.")
                continue
            tid = task.get("id")
            if not isinstance(tid, str) or not tid:
                errors.append(f"{p}.id must be a non-empty string.")
            elif tid in task_ids:
                errors.append(f"Duplicate task id '{tid}'.")
            else:
                task_ids.add(tid)
            if not isinstance(task.get("label"), str):
                errors.append(f"{p}.label must be a string.")
        duration = spec.get("duration_ms")
        if not _is_num(duration) or float(duration) <= 0:
            errors.append("duration_ms must be a positive number.")
        segments = spec.get("segments")
        if not isinstance(segments, list):
            errors.append("'segments' must be an array.")
            segments = []
        for i, seg in enumerate(segments):
            p = f"segments[{i}]"
            if not isinstance(seg, dict):
                errors.append(f"{p} must be an object.")
                continue
            if seg.get("task") not in task_ids:
                errors.append(f"{p} references unknown task '{seg.get('task')}'.")
            if not _is_num(seg.get("start")) or not _is_num(seg.get("end")):
                errors.append(f"{p}.start/end must be numeric.")
            elif float(seg["end"]) <= float(seg["start"]):
                errors.append(f"{p}.end must be greater than start.")
            elif _is_num(duration) and float(duration) > 0 and (
                    float(seg["start"]) < 0 or float(seg["end"]) > float(duration)):
                warnings.append(f"{p} extends outside 0..duration_ms and will "
                                "be clipped.")
            state = seg.get("state", "running")
            if state not in TASK_STATES:
                errors.append(f"{p}.state '{state}' is invalid. Allowed: "
                              f"{', '.join(sorted(TASK_STATES))}.")
        for i, link in enumerate(spec.get("links", [])):
            p = f"links[{i}]"
            if not isinstance(link, dict):
                errors.append(f"{p} must be an object.")
                continue
            for side in ("from", "to"):
                point = link.get(side)
                if not isinstance(point, dict):
                    errors.append(f"{p}.{side} must be an object with task/t.")
                    continue
                if point.get("task") not in task_ids:
                    errors.append(f"{p}.{side} references unknown task "
                                  f"'{point.get('task')}'.")
                if not _is_num(point.get("t")):
                    errors.append(f"{p}.{side}.t must be numeric.")
                elif _is_num(duration) and float(duration) > 0 and not (
                        0 <= float(point["t"]) <= float(duration)):
                    warnings.append(f"{p}.{side}.t is outside 0..duration_ms.")

        # Catch impossible double-booking without rejecting intentionally
        # overlaid ISR pre-emption. Two ordinary tasks cannot own one CPU at
        # the same time, and one task cannot be in two states simultaneously.
        valid_segments = [s for s in segments if isinstance(s, dict)
                          and s.get("task") in task_ids
                          and _is_num(s.get("start")) and _is_num(s.get("end"))
                          and float(s["end"]) > float(s["start"])]
        by_task = {}
        for s in valid_segments:
            by_task.setdefault(s["task"], []).append(s)
        for tid, segs in by_task.items():
            segs = sorted(segs, key=lambda s: (float(s["start"]), float(s["end"])))
            for a, b in zip(segs, segs[1:]):
                if float(b["start"]) < float(a["end"]) - 1e-9:
                    warnings.append(
                        f"Task '{tid}' has overlapping state segments "
                        f"({a['start']}..{a['end']} and {b['start']}..{b['end']}).")
        running = sorted([s for s in valid_segments
                          if s.get("state", "running") == "running"],
                         key=lambda s: (float(s["start"]), float(s["end"])))
        for i, a in enumerate(running):
            for b in running[i + 1:]:
                if float(b["start"]) >= float(a["end"]) - 1e-9:
                    break
                if a["task"] != b["task"]:
                    warnings.append(
                        f"CPU overlap: tasks '{a['task']}' and '{b['task']}' "
                        f"are both marked running around t={max(float(a['start']), float(b['start'])):g}.")

    else:
        errors.append(f"Unknown diagram kind '{kind}'.")

    if errors:
        raise SpecValidationError(errors)
    return {"kind": kind, "warnings": warnings}


def _auto_layout(spec):
    """Assign deterministic rows/columns to a flow spec.

    This deliberately stays simpler than a general graph-layout engine.  It
    is optimised for engineering control-flow/state diagrams: roots at the
    top, graph distance as rows, sibling branches spread horizontally, and
    explicit coordinates remain available when exact placement matters.
    """
    nodes = spec["nodes"]
    ids = [n["id"] for n in nodes]
    outgoing = {nid: [] for nid in ids}
    incoming = {nid: [] for nid in ids}
    for e in spec.get("edges", []):
        if len(e) < 2 or e[0] == e[1] or e[0] not in outgoing or e[1] not in outgoing:
            continue
        outgoing[e[0]].append(e[1])
        incoming[e[1]].append(e[0])

    roots = [nid for nid in ids if not incoming[nid]] or ids[:1]
    depth = {nid: None for nid in ids}
    queue = list(roots)
    for root in roots:
        depth[root] = 0
    # Shortest-path layering is cycle-safe and produces a stable visual tree.
    qi = 0
    while qi < len(queue):
        src = queue[qi]
        qi += 1
        for dst in outgoing[src]:
            proposed = depth[src] + 1
            if depth[dst] is None:
                depth[dst] = proposed
                queue.append(dst)
    # Disconnected/cyclic components get their own deterministic mini-root.
    max_depth = max((d for d in depth.values() if d is not None), default=-1)
    for nid in ids:
        if depth[nid] is not None:
            continue
        max_depth += 1
        depth[nid] = max_depth
        queue = [nid]
        qj = 0
        while qj < len(queue):
            src = queue[qj]
            qj += 1
            for dst in outgoing[src]:
                if depth[dst] is None:
                    depth[dst] = depth[src] + 1
                    queue.append(dst)

    rows = {}
    order = {nid: i for i, nid in enumerate(ids)}
    for nid in ids:
        rows.setdefault(depth[nid], []).append(nid)
    positions = {}
    for row in sorted(rows):
        members = rows[row]
        # Prefer branches near the average horizontal position of parents.
        def sort_key(nid):
            parents = [p for p in incoming[nid] if p in positions]
            if parents:
                return (sum(positions[p] for p in parents) / len(parents),
                        order[nid])
            return (0.0, order[nid])
        members.sort(key=sort_key)
        cols = [i - (len(members) - 1) / 2 for i in range(len(members))]
        for nid, col in zip(members, cols):
            positions[nid] = col
            node = next(n for n in nodes if n["id"] == nid)
            node["col"] = col
            node["row"] = row


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
        txt = self.ax.text(cx, cy, text, fontsize=fontsize, ha="center",
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
        lx, ly, rot = reach - 0.13, y, 0
        bounds["xs"].append(reach - 0.12)
    elif side == "right":
        p0, p1 = (x + w / 2, y - h * 0.22), (x + w / 2, y + h * 0.22)
        rad, reach = 1.5, x + w / 2 + 0.42
        lx, ly, rot = reach + 0.13, y, 0
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
    """Render a flowchart/state-machine spec to PNG, SVG or PDF.

    The caller's dictionary is never mutated; measurement-only fields are
    added to an internal deep copy.  Set ``"layout": "auto"`` (or simply
    omit col/row from any node) to request deterministic automatic placement.
    """
    if isinstance(spec, str):
        spec = json.loads(spec)
    validate_spec(spec, "flow")
    spec = copy.deepcopy(spec)
    if spec.get("layout") == "auto" or any(
            "col" not in n or "row" not in n for n in spec["nodes"]):
        _auto_layout(spec)

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

    # Optional in-figure title for exported design-review images.  ``caption``
    # remains metadata for document builders; ``title`` is deliberately
    # explicit because some teams want the caption outside the figure.
    title = spec.get("title")
    if title:
        tx = (min(xs) + max(xs)) / 2
        ty = max(ys) + 0.34
        ax.text(tx, ty, title, fontsize=FONT + 1.4, fontweight="bold",
                ha="center", va="bottom", color="#222222", zorder=5)
        ys.append(ty + 0.24)

    # ``w`` used to be accepted by specs but silently ignored.  Treat it as
    # a minimum physical page width (inches), adding balanced whitespace
    # without changing the 1 data-unit == 1 inch scale invariant.
    requested_w = spec.get("w")
    if _is_num(requested_w) and float(requested_w) > 0:
        span = max(xs) - min(xs)
        if float(requested_w) > span:
            extra = (float(requested_w) - span) / 2
            xs += [min(xs) - extra, max(xs) + extra]
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
TL_DEFAULT_CHART_W = 8.5


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


def _estimate_text_width(text, fontsize=TL_FONT):
    """Conservative width estimate in inches for collision planning."""
    longest = max((len(line) for line in str(text).split("\n")), default=0)
    return max(0.35, longest * fontsize * 0.0062 + 0.18)


def _event_label_levels(events, t_to_local_x):
    """Greedily stagger event labels so near-simultaneous markers stay legible."""
    occupied = []
    levels = []
    for ev in events:
        label = ev.get("label", "")
        if not label:
            levels.append(0)
            continue
        x = t_to_local_x(float(ev["t"]))
        hw = _estimate_text_width(label, TL_FONT - 0.4) / 2
        interval = (x - hw, x + hw)
        level = 0
        while True:
            if level == len(occupied):
                occupied.append([])
            if not any(interval[0] < b and interval[1] > a
                       for a, b in occupied[level]):
                occupied[level].append(interval)
                break
            level += 1
        levels.append(level)
    return levels


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
    validate_spec(spec, "timeline")
    spec = copy.deepcopy(spec)

    lanes = spec["lanes"]
    lane_ix = {l["id"]: i for i, l in enumerate(lanes)}
    n_lanes = len(lanes)
    duration = float(spec["duration_ms"])
    label_w = max(TL_LABEL_W,
                  max((_estimate_text_width(l["label"], TL_FONT) + 0.14
                       for l in lanes), default=TL_LABEL_W))
    label_w = min(label_w, 3.6)

    # Keep the plot physically useful for both 10 us and 10 s traces.  The
    # previous density formula collapsed short timelines to <1 inch, making
    # labels unreadable.  A fixed physical width is a better default because
    # the ruler already carries the time scale.
    chart_w = float(spec.get("chart_width", TL_DEFAULT_CHART_W))
    chart_w = min(max(chart_w, 5.5), 12.0)
    ms_per_in = duration / chart_w
    chart_h = n_lanes * TL_ROW_H

    events = spec.get("events", [])
    event_levels = _event_label_levels(events, lambda t: t / ms_per_in)
    max_event_level = max(event_levels, default=0)

    title = spec.get("title")
    title_h = 0.32 if title else 0.0
    top_strip_h = 0.50 + 0.34 * (max_event_level + 1 if events else 0)
    fig_w = label_w + chart_w + 0.3
    fig_h = title_h + top_strip_h + chart_h + TL_AXIS_H

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    ax.set_aspect("equal")

    def lane_y(lid):
        """Top-of-lane y coordinate, lane 0 at the top."""
        return fig_h - title_h - top_strip_h - TL_ROW_H * lane_ix[lid]

    def t_x(t_ms):
        return label_w + (t_ms / ms_per_in)

    if title:
        ax.text(fig_w / 2, fig_h - title_h * 0.6, title, fontsize=FONT + 1.2,
                fontweight="bold", ha="center", va="center", color="#222222")

    # Lane bands (alternating tint) + labels.
    for lane in lanes:
        y = lane_y(lane["id"])
        band = "#FAFAFA" if (lane_ix[lane["id"]] % 2 == 0) else "#FFFFFF"
        ax.add_patch(Rectangle((label_w, y - TL_ROW_H), chart_w, TL_ROW_H,
                               facecolor=band, edgecolor="none", zorder=0))
        ax.plot([label_w, label_w + chart_w], [y - TL_ROW_H, y - TL_ROW_H],
                color="#DDDDDD", lw=0.8, zorder=1)
        ax.text(label_w - 0.08, y - TL_ROW_H / 2, lane["label"],
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
            fs = TL_FONT - 0.6
            need = _estimate_text_width(label, fs)
            if w >= need:
                ax.text(x0 + w / 2, y - TL_ROW_H / 2, label, fontsize=fs,
                        ha="center", va="center", color="#222222", zorder=3,
                        linespacing=1.2)
            else:
                # Very short ISR/critical sections are common in firmware.
                # Put the label just outside instead of squeezing it into an
                # unreadable sliver or letting it overprint the lane label.
                if x1 + 1.0 < label_w + chart_w:
                    lx, ha = x1 + 0.05, "left"
                else:
                    lx, ha = x0 - 0.05, "right"
                ax.text(lx, y - TL_ROW_H / 2, label,
                        fontsize=fs - 0.4, ha=ha, va="center",
                        color="#222222", zorder=4, linespacing=1.15,
                        bbox=dict(fc="white", ec="none", pad=0.6))

    # Ticks: small dense marks, no label.
    for tick in spec.get("ticks", []):
        y = lane_y(tick["lane"])
        x = t_x(tick["t"])
        ax.plot([x, x], [y - TL_ROW_H * 0.72, y - TL_ROW_H * 0.28],
                color="#777777", lw=0.9, zorder=3)

    # Events: full-height vertical marker + label in the top strip.
    top_y = fig_h - title_h - top_strip_h
    bottom_y = top_y - chart_h
    for ev, level in zip(events, event_levels):
        x = t_x(ev["t"])
        st = STYLE.get(ev.get("style", "box"), STYLE["box"])
        ax.plot([x, x], [bottom_y, top_y], color=st["ec"], lw=1.2,
                linestyle="--", zorder=1, alpha=0.85)
        ax.plot([x], [top_y], marker="v", color=st["ec"], markersize=5,
                zorder=4)
        label = ev.get("label", "")
        if label:
            ax.text(x, top_y + 0.08 + level * 0.34, label,
                    fontsize=TL_FONT - 0.4,
                    ha="center", va="bottom", color=st["ec"], zorder=4,
                    linespacing=1.15,
                    bbox=dict(fc="white", ec=st["ec"], lw=0.6, pad=1.4))

    # Time ruler.
    axis_y = bottom_y
    ax.plot([label_w, label_w + chart_w], [axis_y, axis_y],
            color="#333333", lw=1.0, zorder=2)
    step = _tl_nice_step(duration)
    t = 0.0
    while t <= duration + 1e-6:
        x = t_x(t)
        ax.plot([x, x], [axis_y, axis_y - 0.05], color="#333333", lw=0.8)
        ax.text(x, axis_y - 0.10, f"{t:g}", fontsize=TL_FONT - 1.0,
                ha="center", va="top", color="#333333")
        t += step
    ax.text(label_w + chart_w, axis_y - 0.28,
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
    validate_spec(spec, "sequence")
    spec = copy.deepcopy(spec)

    actors = spec["actors"]
    n_actors = len(actors)
    messages = spec.get("messages", [])

    # Give the first/last participant enough page margin for their header.
    # The old fixed x=0.4 clipped the first actor box on export.
    actor_header_w = {}
    for a in actors:
        longest = max((len(line) for line in a["label"].split("\n")), default=1)
        actor_header_w[a["id"]] = min(2.25, max(1.35, longest * 0.075 + 0.55))
    side_margin = max(0.78, max(actor_header_w.values()) / 2 + 0.12)
    actor_x = {}
    x = side_margin
    previous = None
    for actor in actors:
        if previous is not None:
            min_gap = (actor_header_w[previous["id"]] +
                       actor_header_w[actor["id"]]) / 2 + 0.34
            x += max(SQ_ACTOR_W, min_gap)
        actor_x[actor["id"]] = x
        previous = actor

    # Row heights are computed once, up front, so the figure height and every
    # row's y-position can be fixed before any drawing happens - the same
    # measure-then-lay-out order the flowchart renderer uses for node sizing.
    row_heights = [_sq_row_height(m) for m in messages]
    rows_total_h = sum(row_heights) + SQ_ROW_H * 0.6   # trailing breathing room

    title = spec.get("title")
    title_h = 0.34 if title else 0.0
    fig_w = (max(actor_x.values()) + side_margin) if actor_x else side_margin * 2
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
        hw = actor_header_w[a["id"]]
        ax.add_patch(FancyBboxPatch(
            (x - hw / 2, top_y - SQ_HEADER_H),
            hw, SQ_HEADER_H,
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
        msg_style = STYLE.get(msg.get("style", "box"), STYLE["box"])
        msg_color = msg_style["ec"] if msg.get("style") else "#555555"

        if x0 == x1:
            # Orthogonal self-call: much easier to read than the old tiny
            # curl, especially in firmware traces with validate/enqueue work.
            dy = min(0.16, row_h * 0.24)
            p0 = (x0, mid + dy)
            reach = x0 + SQ_SELF_REACH
            p3 = (x0, mid - dy)
            pts = [p0, (reach, p0[1]), (reach, p3[1]), p3]
            patch = FancyArrowPatch(
                path=_rounded_path(pts, r=0.05), arrowstyle="-|>",
                mutation_scale=9, color=msg_color, lw=1.0,
                linestyle=style, zorder=2)
            ax.add_patch(patch)
            if label:
                ax.text(reach + 0.06, mid, label,
                        fontsize=SQ_FONT - 0.8, ha="left", va="center",
                        color="#222222", linespacing=1.15)
        else:
            arrow_style = "->" if msg.get("async") else "-|>"
            ax.annotate("", xy=(x1, mid), xytext=(x0, mid),
                        arrowprops=dict(arrowstyle=arrow_style, color=msg_color,
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


# ============================================================================
# RTOS TASK SEQUENCER
# ============================================================================

TS_LABEL_W = 2.25
TS_ROW_H = 0.64
TS_CPU_H = 0.46
TS_AXIS_H = 0.42
TS_FONT = 7.8

TASK_STATE_STYLE = {
    "running":   ("state", 1.00, "-"),
    "isr":       ("warn", 1.00, "-"),
    "ready":     ("ok", 0.58, "-"),
    "blocked":   ("idle", 0.55, "--"),
    "suspended": ("note", 0.42, ":"),
}


def render_tasks(spec, out_path):
    """Render an RTOS task interaction / scheduler chart.

    Unlike a generic timeline, this view has RTOS semantics: task priority,
    task state, a derived CPU ownership strip, and explicit inter-task links
    for notifications/queues/semaphores.  It is intentionally descriptive,
    not a scheduler simulator; the JSON records what happened or what the
    design intends to happen.
    """
    if isinstance(spec, str):
        spec = json.loads(spec)
    validate_spec(spec, "tasks")
    spec = copy.deepcopy(spec)

    tasks = spec["tasks"]
    segments = spec.get("segments", [])
    duration = float(spec["duration_ms"])
    task_ix = {t["id"]: i for i, t in enumerate(tasks)}
    task_map = {t["id"]: t for t in tasks}

    def display_task_label(task):
        pri = task.get("priority")
        if pri is None:
            return task["label"]
        return (f"{task['label']}  [P{pri}]" if str(pri).isdigit()
                else f"{task['label']}  [{pri}]")

    label_w = max(TS_LABEL_W,
                  max((_estimate_text_width(display_task_label(t), TS_FONT) + 0.14
                       for t in tasks), default=TS_LABEL_W))
    label_w = min(label_w, 4.0)

    chart_w = float(spec.get("chart_width", TL_DEFAULT_CHART_W))
    chart_w = min(max(chart_w, 5.5), 12.0)
    ms_per_in = duration / chart_w

    events = spec.get("events", [])
    event_levels = _event_label_levels(events, lambda t: t / ms_per_in)
    max_event_level = max(event_levels, default=0)
    event_strip_h = 0.44 + 0.34 * (max_event_level + 1 if events else 0)
    title = spec.get("title")
    title_h = 0.34 if title else 0.0

    rows_h = len(tasks) * TS_ROW_H
    fig_w = label_w + chart_w + 0.35
    fig_h = title_h + event_strip_h + TS_CPU_H + rows_h + TS_AXIS_H

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=200)
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis("off")
    ax.set_aspect("equal")

    def t_x(t):
        return label_w + float(t) / ms_per_in

    top = fig_h - title_h
    event_base_y = top - event_strip_h
    cpu_top = event_base_y
    cpu_bottom = cpu_top - TS_CPU_H
    task_top = cpu_bottom
    axis_y = task_top - rows_h

    if title:
        ax.text(fig_w / 2, fig_h - title_h * 0.6, title,
                fontsize=FONT + 1.2, fontweight="bold",
                ha="center", va="center", color="#222222")

    # Event markers span CPU + task area; labels are staggered above it.
    for ev, level in zip(events, event_levels):
        x = t_x(ev["t"])
        st = STYLE.get(ev.get("style", "box"), STYLE["box"])
        ax.plot([x, x], [axis_y, cpu_top], color=st["ec"], lw=1.0,
                linestyle="--", alpha=0.75, zorder=1)
        ax.plot([x], [cpu_top], marker="v", color=st["ec"], markersize=5,
                zorder=5)
        if ev.get("label"):
            ax.text(x, cpu_top + 0.08 + level * 0.34, ev["label"],
                    fontsize=TS_FONT - 0.3, ha="center", va="bottom",
                    color=st["ec"], zorder=6, linespacing=1.1,
                    bbox=dict(fc="white", ec=st["ec"], lw=0.6, pad=1.3))

    # CPU ownership summary - derived, so a reviewer can immediately see
    # pre-emption/context switches without mentally combining task rows.
    ax.text(label_w - 0.08, (cpu_top + cpu_bottom) / 2, "CPU",
            fontsize=TS_FONT, fontweight="bold", ha="right", va="center",
            color="#333333")
    ax.add_patch(Rectangle((label_w, cpu_bottom), chart_w, TS_CPU_H,
                           facecolor="#FAFAFA", edgecolor="#D0D0D0",
                           linewidth=0.8, zorder=0))
    cpu_segments = [s for s in segments
                    if s.get("state", "running") in ("running", "isr")]
    for seg in sorted(cpu_segments, key=lambda s: (float(s["start"]), task_ix[s["task"]])):
        x0 = t_x(max(0.0, float(seg["start"])))
        x1 = t_x(min(duration, float(seg["end"])))
        if x1 <= x0:
            continue
        state = seg.get("state", "running")
        style_name, alpha, _ls = TASK_STATE_STYLE[state]
        st = STYLE[style_name]
        ax.add_patch(Rectangle((x0, cpu_bottom + 0.05), x1 - x0,
                               TS_CPU_H - 0.10, facecolor=st["fc"],
                               edgecolor=st["ec"], linewidth=1.0,
                               alpha=alpha, zorder=2))
        task_label = task_map[seg["task"]]["label"]
        short = task_label.split("\n")[0]
        if x1 - x0 >= _estimate_text_width(short, TS_FONT - 1.0):
            ax.text((x0 + x1) / 2, (cpu_top + cpu_bottom) / 2, short,
                    fontsize=TS_FONT - 1.0, ha="center", va="center",
                    color="#222222", zorder=3)

    # Task lanes and state segments.
    def task_center(tid):
        i = task_ix[tid]
        return task_top - TS_ROW_H * i - TS_ROW_H / 2

    for task in tasks:
        i = task_ix[task["id"]]
        y_top = task_top - TS_ROW_H * i
        y0 = y_top - TS_ROW_H
        band = "#FAFAFA" if i % 2 == 0 else "#FFFFFF"
        ax.add_patch(Rectangle((label_w, y0), chart_w, TS_ROW_H,
                               facecolor=band, edgecolor="none", zorder=0))
        ax.plot([label_w, label_w + chart_w], [y0, y0],
                color="#DDDDDD", lw=0.8, zorder=1)
        label = display_task_label(task)
        ax.text(label_w - 0.08, y0 + TS_ROW_H / 2, label,
                fontsize=TS_FONT, ha="right", va="center", color="#333333")

    for seg in segments:
        x0 = t_x(max(0.0, float(seg["start"])))
        x1 = t_x(min(duration, float(seg["end"])))
        if x1 <= x0:
            continue
        yc = task_center(seg["task"])
        h = TS_ROW_H * 0.66
        state = seg.get("state", "running")
        style_name, alpha, ls = TASK_STATE_STYLE[state]
        st = STYLE[style_name]
        patch = FancyBboxPatch(
            (x0, yc - h / 2), x1 - x0, h,
            boxstyle="round,pad=0,rounding_size=0.04",
            facecolor=st["fc"], edgecolor=st["ec"], linewidth=st["lw"],
            linestyle=ls, alpha=alpha, zorder=2)
        ax.add_patch(patch)
        label = seg.get("label", "")
        if label:
            fs = TS_FONT - 0.7
            if (x1 - x0) >= _estimate_text_width(label, fs):
                ax.text((x0 + x1) / 2, yc, label, fontsize=fs,
                        ha="center", va="center", color="#222222",
                        zorder=3, linespacing=1.1)
            else:
                # Tiny ISR/critical sections get an external label. Choose
                # the side with more remaining room so end-of-window labels
                # do not fall off the page.
                if x1 + 1.0 < label_w + chart_w:
                    lx, ha = x1 + 0.04, "left"
                else:
                    lx, ha = x0 - 0.04, "right"
                ax.text(lx, yc, label, fontsize=fs - 0.3, ha=ha, va="center",
                        color="#222222", zorder=4,
                        bbox=dict(fc="white", ec="none", pad=0.5))

    # Inter-task synchronisation / message links.
    for link in spec.get("links", []):
        fp, tp = link["from"], link["to"]
        x0, y0 = t_x(fp["t"]), task_center(fp["task"])
        x1, y1 = t_x(tp["t"]), task_center(tp["task"])
        st = STYLE.get(link.get("style", "state"), STYLE["state"])
        ax.add_patch(FancyArrowPatch(
            (x0, y0), (x1, y1), arrowstyle="->", mutation_scale=10,
            color=st["ec"], lw=1.0,
            linestyle="--" if link.get("dashed") else "-",
            connectionstyle="arc3,rad=0" if abs(x1 - x0) > 1e-6 else "arc3,rad=0.08",
            zorder=5))
        if link.get("label"):
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            ax.text(mx + 0.04, my, link["label"], fontsize=TS_FONT - 1.0,
                    ha="left", va="center", color=st["ec"], zorder=6,
                    bbox=dict(fc="white", ec="none", pad=0.5))

    # State legend. Keep it compact and inside the event strip's left side.
    legend_y = cpu_top + 0.08
    lx = 0.08
    for state in ("running", "ready", "blocked"):
        style_name, alpha, ls = TASK_STATE_STYLE[state]
        st = STYLE[style_name]
        ax.add_patch(Rectangle((lx, legend_y), 0.16, 0.10,
                               facecolor=st["fc"], edgecolor=st["ec"],
                               linewidth=0.8, linestyle=ls, alpha=alpha,
                               zorder=4))
        ax.text(lx + 0.20, legend_y + 0.05, state, fontsize=TS_FONT - 1.2,
                ha="left", va="center", color="#555555")
        lx += 0.62

    # Time ruler.
    ax.plot([label_w, label_w + chart_w], [axis_y, axis_y],
            color="#333333", lw=1.0, zorder=2)
    step = _tl_nice_step(duration)
    t = 0.0
    while t <= duration + 1e-9:
        x = t_x(t)
        ax.plot([x, x], [axis_y, axis_y - 0.05], color="#333333", lw=0.8)
        ax.text(x, axis_y - 0.10, f"{t:g}", fontsize=TS_FONT - 1.0,
                ha="center", va="top", color="#333333")
        t += step
    ax.text(label_w + chart_w, axis_y - 0.28,
            spec.get("unit_label", "ms"), fontsize=TS_FONT - 1.0,
            ha="right", va="top", color="#666666", style="italic")

    fig.savefig(out_path, bbox_inches="tight", pad_inches=0.06,
                facecolor="white")
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    import argparse
    import sys

    RENDERERS = {"flow": render, "timeline": render_timeline,
                 "sequence": render_sequence, "tasks": render_tasks}

    # Backward-compatible positional CLI used by the existing VS Code
    # extension: ``flowchart.py flow spec.json out.png``.  Keep accepting it
    # while the richer argparse CLI below becomes the documented interface.
    legacy = sys.argv[1:]
    if (len(legacy) == 3 and legacy[0] in RENDERERS):
        legacy_kind, legacy_spec, legacy_out = legacy
        with open(legacy_spec, encoding="utf8") as f:
            legacy_data = json.load(f)
        validate_spec(legacy_data, legacy_kind)
        RENDERERS[legacy_kind](legacy_data, legacy_out)
        print("wrote", legacy_out)
        raise SystemExit(0)
    if (len(legacy) == 2 and not legacy[0].startswith("-")
            and not legacy[1].startswith("-")):
        # Original two-argument form defaulted to flow.
        legacy_spec, legacy_out = legacy
        with open(legacy_spec, encoding="utf8") as f:
            legacy_data = json.load(f)
        legacy_kind = detect_kind(legacy_data) or "flow"
        validate_spec(legacy_data, legacy_kind)
        RENDERERS[legacy_kind](legacy_data, legacy_out)
        print("wrote", legacy_out)
        raise SystemExit(0)

    parser = argparse.ArgumentParser(
        description="Render declarative engineering diagrams to PNG/SVG/PDF.")
    parser.add_argument("spec", help="input JSON specification")
    parser.add_argument("output", nargs="?",
                        help="output .png/.svg/.pdf (omit with --validate)")
    parser.add_argument("--kind", choices=["auto"] + sorted(RENDERERS),
                        default="auto")
    parser.add_argument("--validate", action="store_true",
                        help="validate only; do not render")
    ns = parser.parse_args()

    with open(ns.spec, encoding="utf8") as f:
        spec = json.load(f)
    kind = detect_kind(spec) if ns.kind == "auto" else ns.kind
    report = validate_spec(spec, kind)
    if ns.validate:
        print(f"OK: {report['kind']}")
        for warning in report["warnings"]:
            print("warning:", warning)
    else:
        if not ns.output:
            parser.error("output is required unless --validate is used")
        RENDERERS[report["kind"]](spec, ns.output)
        print("wrote", ns.output)
