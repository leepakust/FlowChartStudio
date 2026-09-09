# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright 2026 Patrick Lee
"""Shared text options and source-preserving JSON formatting edits."""
import json
import math

COLORS = {
    "Black": "#000000", "White": "#FFFFFF", "Gray": "#808080",
    "Silver": "#C0C0C0", "Red": "#FF0000", "Maroon": "#800000",
    "Yellow": "#FFFF00", "Olive": "#808000", "Lime": "#00FF00",
    "Green": "#008000", "Aqua": "#00FFFF", "Teal": "#008080",
    "Blue": "#0000FF", "Navy": "#000080", "Fuchsia": "#FF00FF",
    "Purple": "#800080",
}
OPTIONS = {"font_size", "bold", "italic", "underline", "color"}


def validate_options(options):
    for key, value in options.items():
        if key == "font_size":
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 4 <= value <= 72):
                raise ValueError("Font size must be between 4 and 72 points")
        elif key in ("bold", "italic", "underline"):
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false")
        elif key == "color":
            if value not in COLORS.values():
                raise ValueError("Choose a color from the 16-color palette")
        else:
            raise ValueError(f"Unknown text option: {key}")


def format_at_cursor(source, cursor, options):
    """Replace only the selected label value, preserving all other bytes.

    Cursor inside a display string wins; otherwise choose the nearest display
    string on that same line. Identifiers, routes and shape/style names never
    become formatting targets. Existing formatting is merged, not duplicated.
    """
    validate_options(options)
    json.loads(source)  # Never try to repair or rewrite incomplete JSON.
    decoder = json.JSONDecoder()
    targets = []

    def space(pos):
        while pos < len(source) and source[pos].isspace():
            pos += 1
        return pos

    def walk(pos, path):
        pos = space(pos)
        start = pos
        value, end = decoder.raw_decode(source, pos)
        display = (path and path[-1] in {"text", "label", "title", "effect", "note", "unit_label"})
        display = display or (len(path) >= 2 and path[-2] == "causes" and isinstance(path[-1], int))
        display = display or (len(path) == 3 and path[0] == "edges" and path[-1] == 2)
        rich = (isinstance(value, dict) and "text" in value
                and set(value) <= OPTIONS | {"text"})
        if display and (isinstance(value, str) or rich):
            targets.append((start, end, value))
            return end
        if isinstance(value, dict):
            pos = space(pos + 1)
            while source[pos] != "}":
                key, pos = decoder.raw_decode(source, pos)
                pos = space(pos)
                pos = walk(pos + 1, path + [key])
                pos = space(pos)
                if source[pos] == ",":
                    pos = space(pos + 1)
        elif isinstance(value, list):
            pos = space(pos + 1)
            index = 0
            while source[pos] != "]":
                pos = space(walk(pos, path + [index]))
                index += 1
                if source[pos] == ",":
                    pos = space(pos + 1)
        return end

    walk(0, [])
    matches = [target for target in targets if target[0] <= cursor <= target[1]]
    if not matches:
        line_start = source.rfind("\n", 0, cursor) + 1
        line_end = source.find("\n", cursor)
        if line_end < 0:
            line_end = len(source)
        matches = [target for target in targets
                   if line_start <= target[0] < line_end]
    if not matches:
        raise ValueError("Place the cursor on a text, label, title, effect, note, cause or edge-label line")
    start, end, value = min(matches, key=lambda item: min(abs(cursor - item[0]), abs(cursor - item[1])))
    value = dict(value) if isinstance(value, dict) else {"text": value}
    value.update(options)
    return start, end, json.dumps(value, ensure_ascii=False)


def format_whole_chart(source, options):
    validate_options(options)
    spec = json.loads(source)
    if not isinstance(spec, dict):
        raise ValueError("The diagram spec must be an object")
    decoder = json.JSONDecoder()
    pos = source.index("{") + 1
    while source[pos:].lstrip() and source[pos:].lstrip()[0] != "}":
        pos += len(source[pos:]) - len(source[pos:].lstrip())
        key, pos = decoder.raw_decode(source, pos)
        pos = source.index(":", pos) + 1
        pos += len(source[pos:]) - len(source[pos:].lstrip())
        value, end = decoder.raw_decode(source, pos)
        if key == "text_format":
            if not isinstance(value, dict):
                raise ValueError("text_format must be an object")
            return pos, end, json.dumps({**value, **options})
        pos = end
        pos += len(source[pos:]) - len(source[pos:].lstrip())
        if source[pos] == ",":
            pos += 1
    end = source.rfind("}")
    start = len(source[:end].rstrip())
    prefix = "," if spec else ""
    return start, end, prefix + '\n  "text_format": ' + json.dumps(options) + "\n"
