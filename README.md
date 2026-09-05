# Engineering Diagram Studio

A standalone, declarative diagram renderer and desktop workbench for software,
firmware, embedded-systems and systems-engineering documentation.

Write compact JSON and render publication-ready engineering diagrams without
Graphviz, Node.js, Mermaid CLI, or a cloud service.

## Diagram types

- **Flowchart / state machine** — process flows, firmware states, retry paths,
  start/final pseudostates, self-transitions, obstacle-aware connectors.
- **Timeline** — time-scaled swimlanes for interrupts, hardware activity,
  control loops and sequencing.
- **Sequence diagram** — call/message order between software components or
  tasks, including returns, async messages, notes and self-calls.
- **RTOS task sequencer** — task state over time, priorities, CPU ownership,
  ISR execution and task-to-task wake-up/queue/notification links.

## Why it is useful for firmware teams

- Fully offline rendering for restricted or air-gapped engineering systems.
- Deterministic JSON specs that can live beside source code and be code-reviewed.
- PNG **and** vector SVG/PDF export for Word, design specifications and reviews.
- Automatic connector collision avoidance and label dodging.
- Optional automatic layout for common control-flow/state diagrams.
- Friendly semantic validation instead of raw `KeyError`/Matplotlib tracebacks.
- JSON Schema files for VS Code/IDE autocomplete and static validation.
- Desktop live preview plus CLI automation for build/document pipelines.
- Markdown fence integration through the included VS Code preview extension.

## Quick start

### Windows users (no Python required)

Open `release\EngineeringDiagramStudio-Setup.exe`, click **Install**, and
the app opens automatically. Setup installs for your Windows account without
administrator rights and adds desktop and Start menu shortcuts. All runtime
dependencies are bundled; installation and use work offline. Uninstall through
Windows Settings > Apps > Installed apps.

Supported: Windows 10/11, x64. The installer is currently unsigned; Windows may
show an unknown-publisher/SmartScreen prompt. Public distribution should use a
trusted code-signing certificate for the app and installer.

### Developers running from source

```bash
python -m pip install -r requirements.txt
python flowchart_studio.py
```

The `.bat` launchers prefer the installed/built executable. Source mode still
requires Python and the dependencies above. End users should use the installer.

### Building the Windows installer

On a Windows x64 build machine with Python 3.12 (including Tcl/Tk) and Inno Setup 6:

```powershell
powershell -ExecutionPolicy Bypass -File .\build-windows.ps1
```

Use `-Python C:\path\python.exe` and `-Iscc C:\path\ISCC.exe` if needed.
The script creates an isolated build environment, bundles the runtime with
PyInstaller, tests the packaged GUI and all four renderers in PNG/SVG/PDF, and
creates `release\EngineeringDiagramStudio-Setup.exe`. Only developers need these
tools. Keep the complete `dist\EngineeringDiagramStudio` folder together if
distributing the portable build; its executable needs the adjacent `_internal`
folder. Increment `AppVersion` in `installer\setup.iss` for releases; keep AppId
stable so upgrades replace the existing installation.

## CLI

Render with automatic kind detection:

```bash
python flowchart.py examples/tasks.json tasks.svg
```

Validate only:

```bash
python flowchart.py examples/tasks.json --validate
```

Force a kind:

```bash
python flowchart.py examples/timeline.json timeline.pdf --kind timeline
```

The legacy command used by older integrations is still supported:

```bash
python flowchart.py timeline examples/timeline.json timeline.png
```

## 1. Flowchart / state machine

Coordinates are optional. Use `"layout": "auto"` (or omit `col` / `row`) for a
stable top-down layout:

```json
{
  "title": "Sensor acquisition flow",
  "layout": "auto",
  "nodes": [
    {"id":"A", "text":"Task start", "shape":"terminal"},
    {"id":"B", "text":"Read ADC", "shape":"io"},
    {"id":"C", "text":"Sample valid?", "shape":"decision"},
    {"id":"D", "text":"Filter sample", "shape":"box"}
  ],
  "edges": [
    ["A","B"],
    ["B","C"],
    ["C","D","yes"],
    ["C","B","retry","right"]
  ]
}
```

Supported shapes:

`box`, `terminal`, `decision`, `io`, `note`, `state`, `start`, `final`

Edge format:

```text
[src, dst, label?, route?, shift?, lane?]
```

`route` can be `left`, `right`, `self`, `self-top`, `self-left`, or
`self-right`. Leave it blank for automatic routing.

## 2. Timeline

Use this when horizontal distance must represent real time:

```json
{
  "title": "1 kHz control loop",
  "duration_ms": 10,
  "lanes": [
    {"id":"isr", "label":"ADC ISR"},
    {"id":"ctrl", "label":"ControlTask"}
  ],
  "bars": [
    {"lane":"isr", "start":0.0, "end":0.15, "label":"sample", "style":"warn"},
    {"lane":"ctrl", "start":0.18, "end":0.75, "label":"filter + PID", "style":"state"}
  ],
  "events": [
    {"t":0.0, "label":"timer IRQ", "style":"danger"},
    {"t":0.18, "label":"notify", "style":"state"}
  ]
}
```

Near-simultaneous event labels are automatically staggered. Very short bars
place their label outside the bar rather than crushing the text.

## 3. Sequence diagram

```json
{
  "title": "Command path",
  "actors": [
    {"id":"app", "label":"Application"},
    {"id":"api", "label":"Control API"},
    {"id":"task", "label":"ControlTask"}
  ],
  "messages": [
    {"from":"app", "to":"api", "label":"set_target()"},
    {"from":"api", "to":"api", "label":"validate + enqueue"},
    {"from":"api", "to":"app", "label":"ACCEPTED", "dashed":true},
    {"note":"Next scheduler wake"},
    {"from":"task", "to":"api", "label":"dequeue()"}
  ]
}
```

Use `"async": true` for an open async arrow and `"dashed": true` for a
return/response style.

## 4. RTOS task sequencer

This view is designed specifically to explain how RTOS tasks cooperate:

```json
{
  "title": "FreeRTOS control cycle",
  "duration_ms": 5,
  "tasks": [
    {"id":"isr", "label":"ADC ISR", "priority":"IRQ"},
    {"id":"ctrl", "label":"ControlTask", "priority":4},
    {"id":"comm", "label":"CommsTask", "priority":2}
  ],
  "segments": [
    {"task":"isr", "start":1.00, "end":1.08, "state":"isr", "label":"ADC IRQ"},
    {"task":"ctrl", "start":1.08, "end":1.70, "state":"running", "label":"filter + PID"},
    {"task":"comm", "start":1.70, "end":2.10, "state":"running", "label":"publish"}
  ],
  "links": [
    {
      "from":{"task":"isr", "t":1.08},
      "to":{"task":"ctrl", "t":1.08},
      "label":"notify"
    }
  ]
}
```

Task states:

- `running`
- `ready`
- `blocked`
- `suspended`
- `isr`

The CPU strip is derived from `running` and `isr` segments and makes context
switches visible at a glance.

## Desktop Studio features

- live debounced rendering
- automatic diagram-kind detection
- semantic validation
- JSON formatting
- built-in examples for all diagram types
- external file auto-reload
- zoom/fit preview
- PNG, SVG and PDF export
- Windows clipboard copy when `pywin32` is available

## JSON Schema / IDE autocomplete

The `schemas/` folder contains Draft 2020-12 schemas for all four diagram
formats. Add a `$schema` field to a standalone spec to get property hints and
validation in editors such as VS Code:

```json
{
  "$schema": "../schemas/tasks.schema.json",
  "title": "FreeRTOS control cycle",
  "duration_ms": 5,
  "tasks": [],
  "segments": []
}
```

The files under `examples/` already reference the appropriate local schema.

## Markdown fences

The renderer is designed to work with fenced JSON blocks:

````markdown
```flow
{ ... }
```

```timeline
{ ... }
```

```sequence
{ ... }
```

```tasks
{ ... }
```
````

The `vscode-extension/` folder contains a Markdown preview extension for these
four fence types.

## Testing

```bash
python -m unittest discover -s tests -v
```

The smoke tests cover all renderers, vector output, validation, and the
non-mutation guarantee for flow specs.

## Notes

- The renderer is descriptive, not a scheduler simulator or UML conformance
  checker.
- Automatic flow layout intentionally targets common engineering control-flow
  diagrams rather than attempting general graph optimisation.
- Manual `col` / `row`, routes, shifts and lanes remain available when a design
  review requires exact placement.
