// V2 structural plugin contract: default export { id, setup }. No SDK dependency.
import { rpc } from "../bridge.mjs";
export default {
  id: "jev-context",
  async setup(ctx) {
    const workspace = ctx.location?.directory;
    await ctx.session.hook("context", async (event) => {
      const session = event.sessionID || event.session?.id;
      if (!workspace || !session || !Array.isArray(event.messages)) return;
      const lastUser = [...event.messages].reverse().find(m => m.role === "user" || m.info?.role === "user");
      const query = typeof lastUser?.content === "string" ? lastUser.content : "";
      const prepared = await rpc(workspace, "prepare", { session, harness: "opencode-v2", messages: event.messages, query });
      if (Array.isArray(prepared?.messages)) event.messages = prepared.messages;
      const pack = await rpc(workspace, "event", {session, harness:"opencode-v2", kind:"PRE_MODEL", content:"", query});
      if (pack?.context && Array.isArray(event.system) && !event.system.some(p => p?.text?.startsWith("[JEV_CONTEXT_EVIDENCE_V1]"))) {
        event.system.push({ type:"text", text:pack.context });
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
