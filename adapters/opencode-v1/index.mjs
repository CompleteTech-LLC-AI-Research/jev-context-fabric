// V1 documented hooks. No compaction hook and no permission-policy mutation.
import { rpc } from "../bridge.mjs";
export default async function JevContext({ directory }) {
  const queries = new Map();
  const sid = (input, output) => input?.sessionID || output?.messages?.[0]?.info?.sessionID;
  const send = (session, kind, content = "", query = "") => session ? rpc(directory, "event", {
    harness: "opencode-v1", session, kind, content, query,
  }) : Promise.resolve(null);
  return {
    "chat.message": async (input, output) => {
      const session = input.sessionID;
      if (!session) return;
      const text = (output.parts || []).filter(p => p.type === "text").map(p => p.text).join("\n");
      if (text.trim().startsWith("/compact")) return;
      if (queries.size > 200) queries.delete(queries.keys().next().value);
      queries.set(session, text);
      await send(session, "USER_INPUT", text, text);
    },
    "experimental.chat.system.transform": async (input, output) => {
      const session = input.sessionID;
      if (!session || !Array.isArray(output.system)) return;
      if (output.system.some(p => typeof p === "string" && p.startsWith("[JEV_CONTEXT_EVIDENCE_V1]"))) return;
      const result = await send(session, "PRE_MODEL", "", queries.get(session) || "");
      if (result?.context) output.system.push(result.context);
    },
    "experimental.chat.messages.transform": async (input, output) => {
      const session = sid(input, output);
      if (!session || !Array.isArray(output.messages)) return;
      const result = await rpc(directory, "prepare", {
        session, harness: "opencode-v1", messages: output.messages, query: queries.get(session) || "",
      });
      if (Array.isArray(result?.messages)) output.messages = result.messages;
    },
    "tool.execute.before": async (input, output) => {
      if (String(input.tool || "").includes("jev_")) return;
      await send(input.sessionID, "PRE_TOOL", JSON.stringify({ tool: input.tool, args: output.args }));
    },
    "tool.execute.after": async (input, output) => {
      if (String(input.tool || "").includes("jev_")) return;
      await send(input.sessionID, "POST_TOOL", JSON.stringify({ tool: input.tool, result: output.output }));
    },
  };
}
