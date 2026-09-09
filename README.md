# FlowChartStudio

## License

Copyright © 2026 Patrick Lee. This project is source-available under the
[PolyForm Noncommercial License 1.0.0](LICENSE). Personal use, educational
institutions, and public research organizations may use it under that license.
Commercial use requires a separate written license; see
[Commercial licensing](COMMERCIAL-LICENSE.md). This is not an open-source
license because commercial use is restricted.

Desktop JSON diagram editor with live preview and PNG export. Supports
flowcharts, timelines, sequence diagrams, RTOS task charts, and fishbone
(Ishikawa) diagrams.

Run `python flowchart_studio.py` with matplotlib and Pillow installed.

## Text formatting (all chart types)

Click inside a label's JSON string, then use **Apply size**, **Bold**,
**Italic**, **Underline**, or one of the 16 color swatches. The toolbar inserts
formatting on that label's line and merges further edits into the same object.
Ctrl+Z undoes the edit. The spec must be valid JSON before applying formatting.
When a line has several labels, click inside the specific label you want.

For example, `"label": "People"` becomes:

```json
"label": {"text": "People", "font_size": 14, "bold": true, "italic": true, "underline": true, "color": "#000080"}
```

The same text object works for flowchart node text and edge labels, timeline
lane/bar/event labels, sequence actors/messages/notes, task labels/segments/
events/links, and fishbone headings, effects and causes. It formats the entire
label, including every wrapped line.
Font sizes are 4–72 points. The palette contains black, white, gray, silver,
red, maroon, yellow, olive, lime, green, aqua, teal, blue, navy, fuchsia and purple.

Enable **Whole chart** to set defaults for every label, including generated
timeline ruler numbers. These are stored in a top-level `text_format` object.
Individual label options override those defaults. Existing plain strings still
work. Larger fonts expand flowchart spacing, timeline/sequence spacing and
fishbone layout. Timeline bars still represent their actual time intervals.

Keep `text_format.py` alongside `flowchart.py` and `flowchart_studio.py` when
copying or installing the tools. The VS Code bundle includes all three files.

The Studio JSON editor includes a synchronized line-number gutter. The current
cursor line is highlighted, and the gutter updates while editing, scrolling,
opening, or reloading a diagram.

## Preview navigation

Move the mouse over the right-hand preview and roll the wheel to zoom in or
out around the pointer (1–800%). Hold the left mouse button and drag to pan
in any direction, like a PDF hand tool. The scrollbars and Zoom dropdown also
work; choose **Fit** to recenter and fit the diagram in the preview. Only the
visible portion is resized, so high zoom does not create a huge temporary
bitmap. Zoom and panning do not change the exported PNG.

## Fishbone diagrams

Choose **Example → Built-in [fishbone]** to start a cause-and-effect diagram.
Edit the effect, categories, and causes in the JSON editor. Opening a fishbone
JSON file also selects the correct renderer automatically. Use **Export PNG**
to save the result.

```fishbone
{
  "title": "Root cause analysis",
  "effect": "Delayed delivery",
  "categories": [
    {"label": "People", "causes": [
      {
        "label": "Training gaps",
        "causes": ["No onboarding", "No mentoring"]
      },
      "Staff shortage"
    ]},
    {"label": "Methods", "style": "warn", "causes": ["Manual approval"]},
    {"label": "Machines", "causes": ["Equipment downtime"]},
    {"label": "Materials", "causes": ["Supplier delays", "Missing parts"]}
  ]
}
```

`effect` and each category `label` must be non-empty strings. Supply at least
one category. Each entry in `causes` can be a simple string or an object with
its own `label` and nested `causes`. This can repeat recursively for 10 or more
levels. Leave a causes list empty for a brainstorming template. `title` and
category `style` are optional.
Styles use the existing palette (for example `box`, `warn`, `danger`, `ok`).
Categories alternate above and below the spine in list order. The canvas
expands and labels wrap automatically to fit the content. There is no fixed
category, cause, or nesting limit: 10 or more main branches and 10 or more
nested cause levels are supported. Very large diagrams produce correspondingly
wide or tall PNG files.

Nested causes are arranged as horizontal bones along a shared diagonal,
parallel to the category branch. Spacing uses measured label sizes and the
full size of each subtree, including branches below the spine. You do not
need to specify positions. See `examples/fishbone-nested.json` for an example.

For command-line rendering, save the JSON as `fishbone.json` and run:

```shell
python flowchart.py fishbone fishbone.json fishbone.png
```

The VS Code extension also renders `fishbone` Markdown fences. Recopy the
updated extension folder and reload VS Code if it is already installed.
