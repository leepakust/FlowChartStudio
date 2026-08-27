"use strict";

const vscode = require("vscode");
const { spawnSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

let cacheDir;
let outputChannel;

function activate(context) {
  cacheDir = path.join(context.globalStorageUri.fsPath, "render-cache");
  fs.mkdirSync(cacheDir, { recursive: true });
  outputChannel = vscode.window.createOutputChannel("Flowchart Studio");
  context.subscriptions.push(outputChannel);
  outputChannel.appendLine(`Activated. Render cache: ${cacheDir}`);

  // VS Code sets `extension.exports` to activate()'s RETURN VALUE, not to
  // module.exports. The Markdown preview looks for extendMarkdownIt there,
  // so it must be returned from here or the fence rule is never installed.
  return { extendMarkdownIt };
}

function deactivate() {}

// Fence languages flowchart.py can render, one per RENDERERS entry on its
// CLI (see the __main__ block at the bottom of flowchart.py).
const FLOW_KINDS = ["flow", "timeline", "sequence"];

// Called by the built-in Markdown preview extension once this extension has
// activated (triggered by the "markdown.markdownItPlugins" contribution).
function extendMarkdownIt(md) {
  const defaultFence =
    md.renderer.rules.fence ||
    function (tokens, idx, options, env, self) {
      return self.renderToken(tokens, idx, options);
    };

  md.renderer.rules.fence = (tokens, idx, options, env, self) => {
    const token = tokens[idx];
    const lang = token.info.trim().split(/\s+/)[0];
    if (!FLOW_KINDS.includes(lang)) {
      return defaultFence(tokens, idx, options, env, self);
    }
    return renderFlowBlock(lang, token.content);
  };

  return md;
}

// Resolve which flowchart.py to run.
//
// The bundled copy sitting next to this extension.js is the default, and it
// wins unless the user has EXPLICITLY set flowchartStudio.scriptPath. Only
// user/workspace values count as explicit - a value coming from package.json's
// own "default" is ignored. That distinction matters: an earlier manifest
// hardcoded the version number into the default path
// (…flowchart-studio-preview-0.1.0\flowchart.py), so bumping the extension
// folder to 0.3.0 left the extension silently running a flowchart.py from a
// folder that no longer existed. Deriving the path from __dirname instead
// makes the renderer always travel with the extension.
function resolveScriptPath(config) {
  const info = config.inspect("scriptPath") || {};
  const explicit =
    info.workspaceFolderValue || info.workspaceValue || info.globalValue || "";
  if (!explicit) {
    return path.join(__dirname, "flowchart.py");
  }
  // "${userHome}" is not expanded by VS Code for custom extension settings
  // (only for built-ins like launch.json/tasks.json), so expand it here.
  return explicit.replace(/\$\{userHome\}/g, os.homedir());
}

function renderFlowBlock(kind, spec) {
  const config = vscode.workspace.getConfiguration("flowchartStudio");
  const pythonPath = config.get("pythonPath", "python");
  const scriptPath = resolveScriptPath(config);

  if (!scriptPath || !fs.existsSync(scriptPath)) {
    return errorBlock(
      `flowchart.py not found at "${scriptPath}". ` +
        `Clear flowchartStudio.scriptPath in Settings to use the copy bundled ` +
        `with this extension, or point it at a valid flowchart.py.`
    );
  }

  // Cache key covers the kind, spec text, and the renderer script's actual
  // *content* (not just its path) - hashing only the path meant editing
  // flowchart.py while iterating on it never invalidated the cache, so the
  // preview kept showing PNGs rendered by the old code until the markdown
  // block's own JSON text also happened to change.
  let scriptContent;
  try {
    scriptContent = fs.readFileSync(scriptPath);
  } catch (e) {
    return errorBlock(`Failed to read flowchart.py at "${scriptPath}": ${e.message}`);
  }
  const hash = crypto
    .createHash("sha256")
    .update(kind)
    .update(spec)
    .update(scriptContent)
    .digest("hex");
  const cachedPng = path.join(cacheDir, `${hash}.png`);

  if (fs.existsSync(cachedPng)) {
    return imgTag(cachedPng);
  }

  try {
    JSON.parse(spec);
  } catch (e) {
    return errorBlock(`Invalid JSON in \`\`\`${kind} block: ${e.message}`);
  }

  const specFile = path.join(os.tmpdir(), `flow-${hash}.json`);
  fs.writeFileSync(specFile, spec, "utf8");

  // Cache miss, so this block really is being re-rendered. Log which script
  // is doing it - when the preview disagrees with a direct run of
  // flowchart.py, the first thing to check is that both are the same file.
  outputChannel.appendLine(
    `render ${kind} block via ${scriptPath} (${scriptContent.length} bytes)`
  );

  const result = spawnSync(
    pythonPath,
    [scriptPath, kind, specFile, cachedPng],
    { encoding: "utf8", timeout: 30000 }
  );

  try {
    fs.unlinkSync(specFile);
  } catch (e) {
    // best-effort cleanup
  }

  if (result.error) {
    return errorBlock(`Failed to launch "${pythonPath}": ${result.error.message}`);
  }
  if (result.status !== 0) {
    outputChannel.appendLine(`--- ${kind} block render failed (${new Date().toISOString()}) ---`);
    outputChannel.appendLine(result.stderr || result.stdout || "(no output)");
    outputChannel.show(true);
    return errorBlock(
      `flowchart.py exited with code ${result.status}. See the "Flowchart Studio" output channel for details.`
    );
  }
  if (!fs.existsSync(cachedPng)) {
    return errorBlock("flowchart.py reported success but produced no output file.");
  }

  return imgTag(cachedPng);
}

function imgTag(pngPath) {
  const data = fs.readFileSync(pngPath).toString("base64");
  return `<img src="data:image/png;base64,${data}" alt="flowchart" style="max-width:100%;" />\n`;
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function errorBlock(message) {
  return (
    `<pre style="border:1px solid #c33;background:#fee;color:#900;padding:8px;white-space:pre-wrap;">` +
    `Flowchart Studio: ${escapeHtml(message)}</pre>\n`
  );
}

module.exports = { activate, deactivate, extendMarkdownIt };
