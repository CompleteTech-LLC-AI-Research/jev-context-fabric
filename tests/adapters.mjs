// Mock-host integration tests exercising the actual Node -> Python -> SQLite bridge.
// These tests do not launch an actual harness or certify host-version compatibility.
import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, writeFileSync, rmSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';
const root=resolve(fileURLToPath(new URL('..',import.meta.url)));
const python=process.env.PYTHON || (process.platform==='win32' ? 'python' : 'python3');
const temp=mkdtempSync(join(tmpdir(),'jev-adapter-test-'));
const workspace=join(temp,'workspace with spaces');mkdirSync(workspace);
const home=join(temp,'memory');
cpSync(join(root,'adapters'),join(temp,'adapters'),{recursive:true});
writeFileSync(join(temp,'adapters','adapter-config.json'),JSON.stringify({python,runner:join(root,'run.py'),home}));
const load=async p=>(await import(pathToFileURL(join(temp,'adapters',p)).href)).default;
const {rpc}=await import(pathToFileURL(join(temp,'adapters','bridge.mjs')).href);
let passed=0;
function check(name,fn){fn();passed++;console.log(`PASS ${name}`);}
function cli(...args){return JSON.parse(execFileSync(python,[join(root,'run.py'),'--home',home,'--workspace',workspace,...args],{encoding:'utf8'}));}
try {
  const captured=await rpc(workspace,'capture',{content:'authentication history 日本語 Δ café',session:'manual',harness:'test'});
  check('bridge stores Unicode source',()=>assert.ok(captured.ref));
  const hydrated=await rpc(workspace,'hydrate',{ref:captured.ref});
  check('bridge preserves Unicode across process boundary',()=>assert.match(hydrated.text,/日本語 Δ café/));
  const bad=await rpc(join(temp,'absent'),'status',{});
  check('bridge fails open for missing workspace',()=>assert.equal(bad,null));

  const plugin=await load('opencode-v1/index.mjs');
  const hooks=await plugin({directory:workspace});
  check('OpenCode V1 registers no compaction hook',()=>assert.ok(!Object.keys(hooks).some(k=>k.includes('compact'))));
  await hooks['chat.message']({sessionID:'v1'}, {parts:[{type:'text',text:'authentication'}]});
  const system={system:[]};await hooks['experimental.chat.system.transform']({sessionID:'v1'},system);
  check('OpenCode V1 returns source evidence',()=>assert.match(system.system.join(''),/JEV_CONTEXT_EVIDENCE_V1/));
  const native=[...Array(20)].map((_,i)=>({info:{id:`m${i}`,sessionID:'v1',role:'assistant'},parts:[{type:'text',text:`Old unrelated narrative ${i}. `+'detail '.repeat(20)}]}));
  native.push({info:{id:'last',sessionID:'v1',role:'user'},parts:[{type:'text',text:'Current user request'}]});
  const unchanged={messages:structuredClone(native)};
  await hooks['experimental.chat.messages.transform']({sessionID:'v1'},unchanged);
  check('OpenCode V1 does not prune without approval',()=>assert.equal(unchanged.messages.length,native.length));
  const plan=await rpc(workspace,'prune_plan',{session:'v1',harness:'opencode-v1',goal:'authentication',target_chars:100});
  cli('prune-apply',plan.plan_id,'--enable-native');
  const first={messages:structuredClone(native)};
  await hooks['experimental.chat.messages.transform']({sessionID:'v1'},first);
  check('OpenCode V1 applies approved persisted view',()=>assert.ok(first.messages.length<native.length));
  const next={messages:structuredClone(native)};
  await hooks['experimental.chat.messages.transform']({sessionID:'v1'},next);
  check('OpenCode V1 re-applies same view on next model call',()=>assert.deepEqual(next.messages,first.messages));

  const v2=await load('opencode-v2/index.mjs');const sessions={},tools={};
  await v2.setup({location:{directory:workspace},session:{hook:async(n,f)=>{sessions[n]=f;}},tool:{hook:async(n,f)=>{tools[n]=f;}}});
  check('OpenCode V2 separate context hook only',()=>assert.deepEqual(Object.keys(sessions),['context']));
  const event={sessionID:'v2',messages:[...Array(20)].map((_,i)=>({role:'assistant',content:`Historical narrative ${i} irrelevant detail.`})),system:[]};
  event.messages.push({role:'user',content:'authentication'});
  const v2native=structuredClone(event.messages);
  await sessions.context(event);
  check('OpenCode V2 source-backed system addition',()=>assert.equal(event.system[0].type,'text'));
  const v2plan=await rpc(workspace,'prune_plan',{session:'v2',harness:'opencode-v2',goal:'authentication',target_chars:20});
  cli('prune-apply',v2plan.plan_id,'--enable-native');
  const v2next={sessionID:'v2',messages:v2native,system:[]};await sessions.context(v2next);
  check('OpenCode V2 approved active-view mutation',()=>assert.ok(v2next.messages.length<v2native.length));
  await tools['execute.after']({sessionID:'v2',tool:'bash',status:'completed',result:{output:'benchmark passed unique-fixture'}});
  const evidence=await rpc(workspace,'retrieve',{query:'unique-fixture'});
  check('OpenCode V2 tool hook captures result',()=>assert.ok(evidence.evidence.length));

  const claw=await load('openclaw/index.mjs');const registered={},factories=[];
  claw.register({on:(name,fn,options)=>{registered[name]={fn,options};},registerTool:f=>factories.push(f)});
  check('OpenClaw registration is synchronous',()=>assert.equal(factories.length,3));
  check('OpenClaw enrichment requires finalized tool authority',()=>assert.equal(registered.before_prompt_build.options.requiresToolAuthority,true));
  const ctx={workspaceDir:workspace,sessionKey:'claw',toolAuthority:{allows:n=>n==='jev_retrieve',assertActive:()=>{}}};
  const recalled=await registered.before_prompt_build.fn({prompt:'authentication'},ctx);
  check('OpenClaw authorized prompt evidence returned',()=>assert.match(recalled.prependContext,/SOURCE/));
  const denied=await registered.before_prompt_build.fn({prompt:'authentication'},{...ctx,toolAuthority:{allows:()=>false}});
  check('OpenClaw denied memory permission not bypassed',()=>assert.equal(denied,undefined));
  const channel=await registered.before_prompt_build.fn({prompt:'authentication'},{...ctx,channel:'discord',senderId:'other'});
  check('OpenClaw channel memory sharing disabled',()=>assert.equal(channel,undefined));
  const compact=await registered.before_prompt_build.fn({prompt:'/compact'},ctx);
  check('OpenClaw native compact prompt skipped',()=>assert.equal(compact,undefined));
  const status=await factories[0](ctx).execute('call-1',{});
  check('OpenClaw native memory tool bridge',()=>assert.ok(JSON.parse(status.content[0].text).sources>0));
  console.log(JSON.stringify({passed,failed:0,live_harnesses_tested:false}));
} finally {rmSync(temp,{recursive:true,force:true});}
