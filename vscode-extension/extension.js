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
    if (lang !== "flow") {
      return defaultFence(tokens, idx, options, env, self);
    }
    return renderFlowBlock(token.content);
  };

  return md;
}

function renderFlowBlock(spec) {
  const config = vscode.workspace.getConfiguration("flowchartStudio");
  const pythonPath = config.get("pythonPath", "python");
  const scriptPath = config.get("scriptPath", "");

  if (!scriptPath || !fs.existsSync(scriptPath)) {
    return errorBlock(
      `flowchartStudio.scriptPath is not set or does not exist: "${scriptPath}". ` +
        `Set it in Settings to the full path of flowchart.py.`
    );
  }

  // Cache key covers the spec text and the renderer script, so an edit to
  // either one invalidates the cached image instead of showing a stale chart.
  const hash = crypto
    .createHash("sha256")
    .update(spec)
    .update(scriptPath)
    .digest("hex");
  const cachedPng = path.join(cacheDir, `${hash}.png`);

  if (fs.existsSync(cachedPng)) {
    return imgTag(cachedPng);
  }

  try {
    JSON.parse(spec);
  } catch (e) {
    return errorBlock(`Invalid JSON in \`\`\`flow block: ${e.message}`);
  }

  const specFile = path.join(os.tmpdir(), `flow-${hash}.json`);
  fs.writeFileSync(specFile, spec, "utf8");

  const result = spawnSync(pythonPath, [scriptPath, specFile, cachedPng], {
    encoding: "utf8",
    timeout: 30000,
  });

  try {
    fs.unlinkSync(specFile);
  } catch (e) {
    // best-effort cleanup
  }

  if (result.error) {
    return errorBlock(`Failed to launch "${pythonPath}": ${result.error.message}`);
  }
  if (result.status !== 0) {
    outputChannel.appendLine(`--- flow block render failed (${new Date().toISOString()}) ---`);
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
