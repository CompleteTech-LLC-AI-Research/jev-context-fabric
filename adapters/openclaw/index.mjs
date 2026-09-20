// OpenClaw typed hooks. Never changes tool arguments, host permissions, or compaction.
import { rpc } from "../bridge.mjs";
export default {
  id: "jev-context",
  name: "JEV Context Fabric",
  register(api) {
    // This alpha shares memory within an owner's worktree, not across channel principals.
    const scope = ctx => (ctx?.channel || ctx?.senderId || ctx?.chatId)
      ? {} : {workspace:ctx?.workspaceDir,session:ctx?.sessionKey || ctx?.sessionId};
    api.on("before_prompt_build", async (event, ctx) => {
      const {workspace,session}=scope(ctx);
      if (!workspace || !session || !ctx.toolAuthority?.allows("jev_retrieve")) return;
      const current = event.currentUserMessage !== undefined ? event.currentUserMessage : event.prompt;
      const query=typeof current === "string" ? current : "";
      if (query.trim().startsWith("/compact")) return;
      const result=await rpc(workspace,"event",{harness:"openclaw",session,kind:"PRE_MODEL",content:query,query});
      ctx.toolAuthority.assertActive();
      ctx.hookInvocation?.assertActive();
      if (result?.context) return { prependContext:result.context };
    }, { requiresToolAuthority:true });
    api.on("after_tool_call", async (event, ctx) => {
      const {workspace,session}=scope(ctx);
      if (!workspace || !session || String(event.toolName).includes("jev_")) return;
      await rpc(workspace,"event",{harness:"openclaw",session,kind:"POST_TOOL",
        content:JSON.stringify({tool:event.toolName,input:event.params,result:event.result,error:event.error})});
    });
    api.on("agent_end", async (event, ctx) => {
      const {workspace,session}=scope(ctx);
      if (!workspace || !session) return;
      const last=Array.isArray(event.messages) ? event.messages.at(-1) : null;
      await rpc(workspace,"event",{harness:"openclaw",session,kind:"TURN_END",content:last ? JSON.stringify(last) : ""});
    });
    if (typeof api.registerTool === "function") {
      for (const [name, operation, description, properties, required] of [
        ["jev_status","status","Inspect local source-backed memory",{},[]],
        ["jev_retrieve","retrieve","Retrieve historical evidence as untrusted data",{query:{type:"string"},max_chars:{type:"integer",minimum:512,maximum:100000}},[]],
        ["jev_hydrate","hydrate","Read a redacted stored source excerpt",{ref:{type:"string"},offset:{type:"integer",minimum:0},max_chars:{type:"integer",minimum:1,maximum:100000}},["ref"]],
      ]) {
        api.registerTool((ctx) => ({ name, description, parameters:{type:"object",properties,required,additionalProperties:false},
          async execute(_callId, params) {
            const result=await rpc(scope(ctx).workspace,operation,params);
            return {content:[{type:"text",text:JSON.stringify(result || {error:"Workspace unavailable or memory service failed"})}]};
          },
        }));
      }
    }
  },
};
