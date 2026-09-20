import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
const config = JSON.parse(readFileSync(new URL("./adapter-config.json", import.meta.url), "utf8"));

export function rpc(workspace, operation, args) {
  if (typeof workspace !== "string" || !workspace) return Promise.resolve(null);
  return new Promise((resolve) => {
    const child = spawn(config.python, [config.runner, "--home", config.home, "--workspace", workspace, "bridge"], {
      shell: false, windowsHide: true, stdio: ["pipe", "pipe", "pipe"],
    });
    const chunks = [];
    let bytes = 0, settled = false;
    const finish = (value) => { if (!settled) { settled = true; clearTimeout(timer); resolve(value); } };
    const timer = setTimeout(() => { child.kill(); finish(null); }, 6000);
    child.stdout.on("data", (chunk) => {
      bytes += chunk.length;
      if (bytes > 16 * 1024 * 1024) { child.kill(); finish(null); }
      else chunks.push(chunk);
    });
    // Drain, but do not forward possibly sensitive native diagnostics.
    child.stderr.on("data", () => {});
    child.on("error", () => finish(null));
    child.stdin.on("error", () => finish(null));
    child.on("close", (code) => {
      if (code !== 0) return finish(null);
      try { const result = JSON.parse(Buffer.concat(chunks).toString("utf8")); finish(result.error ? null : result); }
      catch { finish(null); }
    });
    try {
      const body = JSON.stringify({ operation, arguments: args });
      if (Buffer.byteLength(body, "utf8") > 8 * 1024 * 1024) { child.kill(); return finish(null); }
      child.stdin.end(body);
    } catch { child.kill(); finish(null); }
  });
}
