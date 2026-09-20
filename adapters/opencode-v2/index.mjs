// V2 structural plugin contract: default export { id, setup }. No SDK dependency.
// This package is the jev-bus CARRIER for OpenCode: it owns the context hook and pipes
// the message array through every registered stage in priority order, its own included.
import { rpc } from "../bridge.mjs";
import { runChain } from "../bus.mjs";
export default {
  id: "jev-context",
  async setup(ctx) {
    const workspace = ctx.location?.directory;
    await ctx.session.hook("context", async (event) => {
      const session = event.sessionID || event.session?.id;
      if (!workspace || !session || !Array.isArray(event.messages)) return;
      const lastUser = [...event.messages].reverse().find(m => m.role === "user" || m.info?.role === "user");
      const query = typeof lastUser?.content === "string" ? lastUser.content : "";
      // V2 exposes event.system in this same hook, so stages may return a system append
      // and the carrier places it; nothing is ever smuggled into the message list.
      const hasSystem = Array.isArray(event.system);
      const { messages, notes, systemAppends } = await runChain("opencode", event.messages, {
        session, workspace, api: "v2", goal: query, acceptsSystemAppend: hasSystem,
      });
      // The bus is ADDITIVE, never a prerequisite: if it contributed no stage of ours -- an
      // unreadable registry, or plain standalone use -- fall back to this package's own
      // direct prepare and evidence pack, exactly as before jev-bus existed.
      if (!notes.some(n => String(n.stage || "").startsWith("jev-context."))) {
        const prepared = await rpc(workspace, "prepare", { session, harness: "opencode-v2", messages: event.messages, query });
        if (Array.isArray(prepared?.messages)) event.messages = prepared.messages;
        const pack = await rpc(workspace, "event", { session, harness: "opencode-v2", kind: "PRE_MODEL", content: "", query });
        if (pack?.context && hasSystem && !event.system.some(p => p?.text?.startsWith("[JEV_CONTEXT_EVIDENCE_V1]"))) {
          event.system.push({ type: "text", text: pack.context });
        }
        return;
      }
      if (Array.isArray(messages)) event.messages = messages;
      if (hasSystem) {
        for (const text of systemAppends) {
          if (!event.system.some(p => p?.text?.startsWith("[JEV_CONTEXT_EVIDENCE_V1]"))) {
            event.system.push({ type: "text", text });
          }
        }
      }
    });
    await ctx.tool.hook("execute.after", async (event) => {
      const session = event.sessionID || event.session?.id;
      if (!session || !workspace) return;
      const tool = typeof event.tool === "string" ? event.tool : event.tool?.name || event.toolID || "tool";
      if (String(tool).includes("jev_")) return;
      await rpc(workspace,"event", {session,harness:"opencode-v2",kind:"POST_TOOL",
        content:JSON.stringify({tool,result:event.result ?? event.output ?? event.error})});
    });
  },
};
