# Engineering Diagram Studio Preview

Renders ` ```flow `, ` ```timeline `, ` ```sequence `, and ` ```tasks ` fenced code blocks
(the Flowchart Studio JSON specs used by `flowchart.py`) inline in VS Code's
built-in Markdown preview — the same way the Mermaid extension renders
` ```mermaid ` blocks.

## How it works

This extension registers a `markdown-it` fence renderer for the `flow`,
`timeline`, and `sequence` languages. When the preview hits one of those
blocks it:

1. Hashes the block's kind, JSON content, and renderer script path.
2. If a PNG for that hash is already cached (in the extension's global
   storage), embeds it immediately as a base64 `data:` URI.
3. Otherwise, shells out to `flowchart.py <kind> spec.json out.png` to
   render the spec to a PNG, caches it, then embeds it.

It does not reimplement the renderer — it reuses `flowchart.py` as-is, so
diagrams look identical to the ones already embedded in your Word docs.

## Setup

1. Settings (`Ctrl+,` → search "Flowchart Studio"), both optional:
   - `flowchartStudio.pythonPath` — defaults to `python`.
   - `flowchartStudio.scriptPath` — defaults to blank, meaning "use the
     `flowchart.py` bundled in this extension's own folder". That copy is
     located from `extension.js`'s own directory, so it stays correct when
     the extension folder is renamed or version-bumped. Set this only to
     point at a different copy, e.g. one you're actively editing elsewhere.

     Do **not** put the version number in this setting. An earlier manifest
     hardcoded `…flowchart-studio-preview-0.1.0\flowchart.py` as the default;
     after the folder was bumped to `-0.4.0` the extension kept pointing at
     the old, now-deleted folder and silently rendered with a stale script.

2. Load the extension, either:

   **Permanent install** — copy this folder into your extensions
   directory and reload VS Code (keep the folder name's version in step
   with `"version"` in `package.json`):
   ```
   xcopy /E /I "<folder path>\vscode-extension" "%USERPROFILE%\.vscode\extensions\flowchart-studio-preview-0.4.0"
   ```
   Then run **Developer: Reload Window** from the Command Palette.

## Troubleshooting

**The preview shows an older rendering than running `flowchart.py` /
`flowchart_studio.py` directly.**

Open **View → Output → "Flowchart Studio"**. Each re-render logs the script
it used:

```
render flow block via C:\Users\...\flowchart-studio-preview-0.4.0\flowchart.py (49805 bytes)
```

Confirm that path and byte count match the `flowchart.py` you edited. If it
names a different file, `flowchartStudio.scriptPath` is set explicitly —
clear it to fall back to the bundled copy.

If no line is logged at all, the diagram came from cache. Rendered PNGs are
cached under
`%APPDATA%\Code\User\globalStorage\local.flowchart-studio-preview\render-cache`,
keyed by the diagram kind, the block's JSON, **and the contents of
`flowchart.py`** — so editing the renderer invalidates every cached diagram
automatically. Deleting that folder forces a full re-render.

## Notes / limitations

- Only works in VS Code's **built-in** Markdown preview (the one opened with
  `Ctrl+Shift+V` / "Open Preview"). Extensions like "Markdown Preview
  Enhanced" use their own rendering pipeline and won't pick this up.
- The first render of each unique diagram shells out to Python
  (matplotlib's import/startup is the main cost, roughly 1-2s). Unchanged
  diagrams are served from cache instantly. Editing a block's JSON
  invalidates only that block's cache entry.
- Requires Python with `matplotlib` importable via `flowchartStudio.pythonPath`.
- Render errors (bad JSON, matplotlib exceptions) show inline in the preview
  as a red box, with full stderr in the "Flowchart Studio" output channel.
