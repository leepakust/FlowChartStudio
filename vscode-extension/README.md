# Flowchart Studio Preview

Renders ` ```flow ` fenced code blocks (the Flowchart Studio JSON spec used by
`flowchart.py`) inline in VS Code's built-in Markdown preview — the same way
the Mermaid extension renders ` ```mermaid ` blocks.

## How it works

This extension registers a `markdown-it` fence renderer for the `flow`
language. When the preview hits a ` ```flow ` block it:

1. Hashes the block's JSON content.
2. If a PNG for that hash is already cached (in the extension's global
   storage), embeds it immediately as a base64 `data:` URI.
3. Otherwise, shells out to `flowchart.py` to render the spec to a PNG,
   caches it, then embeds it.

It does not reimplement the renderer — it reuses `flowchart.py` as-is, so
diagrams look identical to the ones already embedded in your Word docs.

## Setup

1. Confirm settings (defaults already point at your machine's paths):
   - `flowchartStudio.pythonPath` — defaults to `python`.
   - `flowchartStudio.scriptPath` — defaults to
     <your flowchart.py full path>.

   Change these in **Settings** (`Ctrl+,` → search "Flowchart Studio") if
   your Python or script location differs.

2. Load the extension, either:

   **Permanent install** — copy this folder into your extensions
   directory and reload VS Code:
   ```
   xcopy /E /I "<folder path>\vscode-extension" "%USERPROFILE%\.vscode\extensions\flowchart-studio-preview-0.1.0"
   ```
   Then run **Developer: Reload Window** from the Command Palette.

## Notes / limitations

- Only works in VS Code's **built-in** Markdown preview (the one opened with
  `Ctrl+Shift+V` / "Open Preview"). Extensions like "Markdown Preview
  Enhanced" use their own rendering pipeline and won't pick this up.
- The first render of each unique diagram shells out to Python
  (matplotlib's import/startup is the main cost, roughly 1-2s). Unchanged
  diagrams are served from cache instantly. Editing a `flow` block's JSON
  invalidates only that block's cache entry.
- Requires Python with `matplotlib` importable via `flowchartStudio.pythonPath`.
- Render errors (bad JSON, matplotlib exceptions) show inline in the preview
  as a red box, with full stderr in the "Flowchart Studio" output channel.
