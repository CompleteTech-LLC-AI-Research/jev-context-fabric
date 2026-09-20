"""Offline unit/integration tests. No live harness binary or model credential required."""
from __future__ import annotations
import copy
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor')]
from jev_context.core import Core
from jev_context.config import DEFAULTS,save_config,load_config
from jev_context.provider import TypeSafe,QUESTIONS,validate_answer,NoRedirect
from jev_context.util import digest,redact,atomic_write,canonical
from jev_context import paging
from jev_context.hooks import run_hook
from jev_context.mcp import MCP,serve
from jev_context.installer import Plan,HARNESSES,roots_for,uninstall,Conflict,read_document
from jev_context.http_api import make_server

class Base(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='jev-test-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.workspace=self.root/'workspace';self.workspace.mkdir()
        self.home=self.root/'memory'
        self.core=Core(self.home,self.workspace)
        self.addCleanup(lambda:self.core.close())

class CoreTests(Base):
    def test_capture_roundtrip_unicode_and_newlines(self):
        text='alpha\r\n日本語 Δ café\nfinal'
        record=self.core.capture(text)
        self.assertEqual(self.core.hydrate(record['ref'],verbatim=True)['text'],text)
        self.assertEqual(record['sha256'],digest(text))
    def test_dedup_same_source(self):
        a=self.core.capture('same');b=self.core.capture('same')
        self.assertEqual(a['ref'],b['ref']);self.assertTrue(b['duplicate'])
        self.assertEqual(self.core.status()['sources'],1)
    def test_changed_source_new_identity(self):
        self.assertNotEqual(self.core.capture('a')['ref'],self.core.capture('b')['ref'])
    def test_session_identity_distinguishes_sources(self):
        self.assertNotEqual(self.core.capture('a',session='1')['ref'],self.core.capture('a',session='2')['ref'])
    def test_workspace_isolation(self):
        ref=self.core.capture('private-workspace-evidence')['ref']
        other=self.root/'other';other.mkdir()
        c=Core(self.home,other)
        try:
            self.assertEqual(c.retrieve('private')['evidence'],[])
            with self.assertRaises(KeyError):c.hydrate(ref)
        finally:c.close()
    def test_source_hash_tampering_detected(self):
        ref=self.core.capture('original')['ref']
        self.core.store.db.execute('UPDATE sources SET content=? WHERE id=?',('tampered',ref))
        self.core.store.db.commit()
        with self.assertRaises(ValueError):self.core.hydrate(ref)
    def test_redaction_default_and_explicit_raw(self):
        text='password=secret123 Authorization: Bearer abcdefghijklmn'
        ref=self.core.capture(text)['ref']
        self.assertNotIn('secret123',self.core.hydrate(ref)['text'])
        self.assertEqual(self.core.hydrate(ref,verbatim=True)['text'],text)
        with self.assertRaises(PermissionError):self.core.dispatch('hydrate',{'ref':ref,'verbatim':True})
    def test_budget_and_paging(self):
        ref=self.core.capture('authentication evidence '*2000)['ref']
        pack=self.core.retrieve('authentication',512)
        self.assertLessEqual(pack['characters'],512)
        page=self.core.hydrate(ref,100,100)
        self.assertEqual(len(page['text']),100);self.assertTrue(page['has_more'])
    def test_pins_retrieve_unmatched_sources(self):
        ref=self.core.capture('a prior requirement')['ref'];self.core.store.pin(self.core.workspace,ref)
        pack=self.core.retrieve('xyzzy')
        self.assertEqual(pack['evidence'][0]['ref'],ref)
        self.core.store.pin(self.core.workspace,ref,False)
        self.assertEqual(self.core.retrieve('xyzzy')['evidence'],[])
    def test_source_persistence(self):
        ref=self.core.capture('retained across processes')['ref']
        c=Core(self.home,self.workspace)
        try:self.assertEqual(c.hydrate(ref)['text'],'retained across processes')
        finally:c.close()
    def test_capture_disabled(self):
        self.core.config['capture_enabled']=False
        self.core.event({'kind':'POST_TOOL','content':'not saved'})
        self.assertEqual(self.core.status()['sources'],0)
    def test_injection_disabled(self):
        self.core.capture('reference');self.core.config['inject_enabled']=False
        self.assertEqual(self.core.event({'kind':'SESSION_START'})['context'],'')
    def test_empty_source_rejected(self):
        with self.assertRaises(ValueError):self.core.capture(' ')
    def test_invalid_numeric_config_rejected(self):
        with self.assertRaises(ValueError):save_config(self.home,{'max_evidence_chars':True})
        self.assertFalse((self.home/'config.json').exists())
    def test_fts_query_escaped(self):
        self.core.capture('authentication expires')
        for q in ['" ) OR *','auth:NEAR(foo)','\x00','日本語']:
            self.assertIsInstance(self.core.retrieve(q)['evidence'],list)
    def test_lexical_fallback_without_fts(self):
        self.core.capture('authentication fix');self.core.store.fts=False
        self.assertEqual(len(self.core.retrieve('authentication')['evidence']),1)
    def test_explicit_graph_neighbor_retrieved(self):
        a=self.core.capture('authentication regression')['ref']
        b=self.core.capture('opaque experimental result')['ref']
        self.core.link(a,b,'resulted_in')
        pack=self.core.retrieve('authentication')
        self.assertTrue(any(e['ref']==b and e['explicit_graph_neighbor'] for e in pack['evidence']))
    def test_graph_cross_workspace_link_rejected(self):
        a=self.core.capture('a')['ref']
        with self.assertRaises(KeyError):self.core.link(a,'src_unknown','supports')
    def test_cached_typed_routing(self):
        ref=self.core.capture('opaque statement with no lexical match')['ref']
        sha=self.core.store.get(self.core.workspace,ref)['sha256']
        feature={'question_version':'semantic-memory-v1','source_sha256':sha,
                 'answers':{'kind':{'probabilities':{'decision':.95,'background':.05}}}}
        self.core.store.put_feature(ref,feature)
        evidence=self.core.retrieve('decision')['evidence']
        self.assertEqual(evidence[0]['ref'],ref)
        self.assertEqual(evidence[0]['cached_kind_distribution']['decision'],.95)
    def test_cached_feature_wrong_hash_not_routed(self):
        ref=self.core.capture('opaque evidence')['ref']
        self.core.store.put_feature(ref,{'question_version':'semantic-memory-v1','source_sha256':'invalid',
                                        'answers':{'kind':{'probabilities':{'decision':1}}}})
        self.assertEqual(self.core.retrieve('decision')['evidence'],[])
    def test_retrieval_without_opt_in_never_opens_network(self):
        self.core.capture('authentication evidence')
        with patch('urllib.request.build_opener') as opening:
            result=self.core.retrieve('authentication',use_jev=True)
            opening.assert_not_called();self.assertTrue(result['warnings'])
    def test_api_cannot_apply_prune(self):
        with self.assertRaises(ValueError):self.core.dispatch('prune_apply',{'plan_id':'x'})

class PagingTests(Base):
    def messages(self):
        return [{'role':'system','content':'System instructions'},
                {'role':'user','content':'User requirements'},
                *[{'role':'assistant','content':f'Old unrelated narrative {i}. '+'details '*25} for i in range(18)],
                {'role':'user','content':'Current task'}]
    def plan(self,messages=None):
        messages=messages or self.messages()
        paging.prepare(self.core,'s','generic',messages)
        return paging.plan(self.core,'s','generic','authentication',100)
    def test_capture_disabled_skips_native_snapshot(self):
        self.core.config['capture_enabled']=False
        out=paging.prepare(self.core,'s','generic',self.messages())
        self.assertEqual(out['removed'],0)
        self.assertEqual(self.core.status()['sources'],0)
        self.assertEqual(self.core.store.db.execute('SELECT count(*) FROM snapshots').fetchone()[0],0)
    def test_default_prepare_does_not_remove(self):
        m=self.messages();out=paging.prepare(self.core,'s','generic',m)
        self.assertEqual(out['messages'],m);self.assertEqual(out['removed'],0)
    def test_unsupported_harness_reports_no_pruning(self):
        for harness in ['codex','claude-code','hermes','openclaw']:
            self.assertFalse(paging.plan(self.core,'s',harness,'goal')['supported'])
    def test_apply_requires_cli_enable(self):
        plan=self.plan()
        with self.assertRaises(PermissionError):paging.apply(self.core,plan['plan_id'])
    def test_persisted_view_and_reset(self):
        messages=self.messages();plan=self.plan(messages)
        self.core.config['native_prune_enabled']=True
        paging.apply(self.core,plan['plan_id']);save_config(self.home,{'native_prune_enabled':True})
        c=Core(self.home,self.workspace)
        try:
            out=paging.prepare(c,'s','generic',messages)
            self.assertGreater(out['removed'],0);self.assertFalse(out['native_compaction_called'])
            self.assertIn(messages[0],out['messages']);self.assertIn(messages[1],out['messages'])
            self.assertTrue(all(m in out['messages'] for m in messages[-8:]))
            paging.reset(c,'s','generic')
            self.assertEqual(paging.prepare(c,'s','generic',messages)['removed'],0)
        finally:c.close()
    def test_stale_plan_rejected(self):
        messages=self.messages();plan=self.plan(messages)
        paging.prepare(self.core,'s','generic',messages+[{'role':'user','content':'new'}])
        self.core.config['native_prune_enabled']=True
        with self.assertRaises(ValueError):paging.apply(self.core,plan['plan_id'])
    def test_tool_thinking_media_and_constraints_protected(self):
        protected=[{'role':'assistant','tool_calls':[],'content':'tool call'},
            {'role':'assistant','content':[{'type':'tool_use','id':'1'}]},
            {'role':'assistant','reasoning':'private','content':'reasoning'},
            {'role':'assistant','content':'Never discard this decision.'},
            {'role':'assistant','parts':[{'type':'image','url':'data:'}]}]
        m=protected+self.messages();p=self.plan(m)
        self.assertTrue(all(c['index']>=len(protected) for c in p['candidates']))
    def test_duplicate_recent_text_not_removed(self):
        m=self.messages();m[2]={'role':'assistant','content':'Repeated old narrative.'}
        m[-2]=dict(m[2]);p=self.plan(m)
        self.core.config['native_prune_enabled']=True;paging.apply(self.core,p['plan_id'])
        out=paging.prepare(self.core,'s','generic',m)
        self.assertIn(m[-2],out['messages'])
        self.assertNotEqual(paging.message_key(m[2],2),paging.message_key(m[-2],len(m)-2))
    def test_pin_after_plan_reprotects_message(self):
        m=self.messages();p=self.plan(m)
        self.core.config['native_prune_enabled']=True;paging.apply(self.core,p['plan_id'])
        origin='native-message:'+p['candidates'][0]['key']
        ref=self.core.store.db.execute('SELECT id FROM sources WHERE origin=?',(origin,)).fetchone()[0]
        self.core.store.pin(self.core.workspace,ref)
        self.assertEqual(paging.prepare(self.core,'s','generic',m)['removed'],0)
    def test_noop_has_no_compaction_fallback(self):
        m=[{'role':'user','content':'Only user text'}]
        p=self.plan(m);self.assertFalse(p['sufficient'])
        self.assertFalse(paging.apply(self.core,p['plan_id'])['native_compaction_called'])
    def test_repeated_plan_skips_already_excluded(self):
        m=self.messages();p=self.plan(m)
        self.core.config['native_prune_enabled']=True;paging.apply(self.core,p['plan_id'])
        second=paging.plan(self.core,'s','generic','authentication',100)
        self.assertNotEqual(p['candidates'][0]['key'],second['candidates'][0]['key'])

class HookTests(Base):
    def test_compact_bypasses_even_missing_workspace(self):
        with patch('jev_context.hooks.Core') as ctor:
            for event,payload in [('PreCompact',{}),('PostCompact',{}),('UserPromptSubmit',{'prompt':'/compact explain'}),('SessionStart',{'source':'compact'})]:
                self.assertEqual(run_hook(self.home,'/not-real','codex',event,payload),{})
            ctor.assert_not_called()
    def test_claude_context_envelope(self):
        self.core.capture('authentication historical evidence')
        value=run_hook(self.home,str(self.workspace),'claude-code','UserPromptSubmit',{'cwd':str(self.workspace),'session_id':'s','prompt':'authentication'})
        self.assertIn('SOURCE',value['hookSpecificOutput']['additionalContext'])
        self.assertEqual(value['hookSpecificOutput']['hookEventName'],'UserPromptSubmit')
    def test_hermes_extra_envelope(self):
        self.core.capture('authentication previous result')
        value=run_hook(self.home,str(self.workspace),'hermes','pre_llm_call',{'session_id':'h','cwd':str(self.workspace),'extra':{'user_message':'authentication'}})
        self.assertIn('SOURCE',value['context'])
    def test_memory_tool_output_not_recaptured(self):
        before=self.core.status()['sources']
        run_hook(self.home,str(self.workspace),'codex','PostToolUse',{'session_id':'s','tool_name':'mcp__jev-context__jev_retrieve','tool_response':'x'})
        self.assertEqual(before,self.core.status()['sources'])
    def test_missing_session_ignored(self):
        self.assertEqual(run_hook(self.home,str(self.workspace),'codex','UserPromptSubmit',{'prompt':'ignored'}),{})
    def test_hook_never_calls_remote_even_when_enabled(self):
        save_config(self.home,{'backend':'typesafe','allow_remote':True})
        with patch('urllib.request.build_opener') as opener:
            run_hook(self.home,str(self.workspace),'codex','UserPromptSubmit',{'session_id':'s','prompt':'test'})
            opener.assert_not_called()

class ProviderTests(unittest.TestCase):
    def config(self):return {**DEFAULTS,'backend':'typesafe','allow_remote':True}
    def response(self):
        kinds=list(QUESTIONS['kind']['criteria'])
        return {'model':'jev-1.13.0','answers':{'kind':{'type':'choice','choice':'constraint','confidence':.9,
            'probabilities':{k:1.0 if k=='constraint' else 0.0 for k in kinds}},
            'unresolved':{'type':'noul','noul':.2},'injection_signal':{'type':'noul','noul':.1}},'usage':{'input_tokens':12}}
    def call_mock(self,response,text='test'):
        opener=MagicMock();opener.open.return_value.__enter__.return_value.read.return_value=json.dumps(response).encode()
        with patch.dict(os.environ,{'TYPESAFE_API_KEY':'test-only-placeholder'}),patch('urllib.request.build_opener',return_value=opener):
            result=TypeSafe(self.config()).classify(text)
        return result,opener
    def test_request_matches_documented_contract(self):
        result,opener=self.call_mock(self.response(),'password=do-not-send')
        req=opener.open.call_args.args[0];body=json.loads(req.data)
        self.assertEqual(req.full_url,'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(body['questions'],QUESTIONS);self.assertNotIn('do-not-send',body['state'])
        self.assertEqual(result['answers']['kind']['probabilities'],self.response()['answers']['kind']['probabilities'])
    def test_missing_consent_stops_before_network(self):
        with patch('urllib.request.build_opener') as opener:
            with self.assertRaises(PermissionError):TypeSafe(DEFAULTS).classify('source')
            opener.assert_not_called()
    def test_missing_key_stops_before_network(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError):TypeSafe(self.config()).classify('source')
    def test_bad_noul_rejected(self):
        for value in [True,-1,1.1,float('nan'),'0.2']:
            with self.assertRaises(ValueError):validate_answer({'type':'noul','noul':value},'noul')
    def test_bad_distribution_rejected(self):
        with self.assertRaises(ValueError):validate_answer({'type':'choice','choice':'x','probabilities':{'x':.1}},'choice')
    def test_wrong_ontology_rejected(self):
        response=self.response();response['answers']['kind']={'type':'choice','choice':'made-up','probabilities':{'made-up':1}}
        with self.assertRaises(ValueError):self.call_mock(response)
    def test_redirect_rejected(self):
        with self.assertRaises(ValueError):NoRedirect().redirect_request(None,None,302,'redirect',{},'https://elsewhere.invalid')

class MCPTests(Base):
    def server(self):
        server=MCP(self.core)
        server.handle({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}})
        return server
    def test_initialize_tools_and_notification(self):
        server=self.server()
        self.assertIsNone(server.handle({'jsonrpc':'2.0','method':'notifications/initialized'}))
        reply=server.handle({'jsonrpc':'2.0','id':2,'method':'tools/list'})
        names={t['name'] for t in reply['result']['tools']}
        self.assertIn('jev_page_fault',names);self.assertNotIn('jev_prune_apply',names)
    def test_rpc_capture_retrieve(self):
        server=self.server()
        def call(name,args):return server.handle({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':name,'arguments':args}})['result']
        ref=call('jev_capture',{'content':'authentication evidence'})['structuredContent']['ref']
        self.assertEqual(call('jev_retrieve',{'query':'authentication'})['structuredContent']['evidence'][0]['ref'],ref)
    def test_tool_validation_errors_are_tool_results(self):
        server=self.server()
        result=server.handle({'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'jev_hydrate','arguments':{'ref':'x','verbatim':True}}})
        self.assertTrue(result['result']['isError'])
    def test_protocol_requires_initialization(self):
        result=MCP(self.core).handle({'jsonrpc':'2.0','id':1,'method':'tools/list'})
        self.assertEqual(result['error']['code'],-32000)
    def test_stream_parsing_and_no_log_pollution(self):
        incoming=io.BytesIO(b'not-json\n'+canonical({'jsonrpc':'2.0','id':1,'method':'initialize'}).encode()+b'\n')
        outgoing=io.StringIO();serve(self.core,incoming,outgoing)
        lines=[json.loads(l) for l in outgoing.getvalue().splitlines()]
        self.assertEqual(lines[0]['error']['code'],-32700);self.assertIn('serverInfo',lines[1]['result'])
    def test_subprocess_stdio_roundtrip(self):
        payload='\n'.join(canonical(m) for m in [
            {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18'}},
            {'jsonrpc':'2.0','method':'notifications/initialized'},
            {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'jev_capture','arguments':{'content':'real subprocess evidence'}}},
            {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'jev_retrieve','arguments':{'query':'subprocess'}}}])+'\n'
        result=subprocess.run([sys.executable,str(ROOT/'run.py'),'--home',str(self.home),'--workspace',str(self.workspace),'mcp'],input=payload,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stderr,'')
        replies=[json.loads(l) for l in result.stdout.splitlines()]
        self.assertEqual(len(replies),3);self.assertTrue(replies[-1]['result']['structuredContent']['evidence'])

class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='jev-install-test-');self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)/'user with spaces';self.home.mkdir()
        self.prefix=self.home/'.jev-context-fabric';self.roots=roots_for(self.home,False)
    def plan(self,names=HARNESSES,api='v1'):
        p=Plan(ROOT,self.home,self.prefix);p.base()
        for n in names:p.install_harness(n,self.roots,api)
        return p
    def test_explicit_workspace_pinning(self):
        workspace=self.home/'worktree';workspace.mkdir()
        p=Plan(ROOT,self.home,self.prefix,workspace);p.base()
        p.install_harness('codex',self.roots);p.commit()
        args=read_document(self.roots['codex']/'config.toml')['mcp_servers']['jev-context']['args']
        self.assertIn('--workspace',args);self.assertIn(str(workspace),args)
    def test_plan_dry_run_has_no_writes(self):
        result=self.plan().preview();self.assertEqual(len(result['harnesses']),8)
        self.assertEqual(list(self.home.iterdir()),[])
    def test_install_all_and_repeat_idempotent(self):
        first=self.plan().commit();self.assertGreater(first['changed_files'],30)
        self.assertEqual(self.plan().commit()['changed_files'],0)
        self.assertTrue((self.roots['opencode']/'plugins/jev-context.js').exists())
    def test_merge_existing_json_toml_yaml(self):
        originals={self.home/'.claude.json':'{"custom":42,"mcpServers":{"other":{"command":"other"}}}',
                   self.roots['codex']/'config.toml':'# keep this comment\nmodel = "existing-model"\n',
                   self.roots['hermes']/'config.yaml':'# keep YAML comment\nmodel: existing-model\n'}
        for p,text in originals.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        self.plan().commit()
        self.assertEqual(read_document(self.home/'.claude.json')['custom'],42)
        self.assertIn('other',read_document(self.home/'.claude.json')['mcpServers'])
        self.assertIn('# keep this comment',(self.roots['codex']/'config.toml').read_text())
        self.assertIn('# keep YAML comment',(self.roots['hermes']/'config.yaml').read_text())
    def test_existing_permission_disables_preserved(self):
        paths={self.roots['claude-code']/'settings.json':'{"disableAllHooks":true}',
               self.roots['codex']/'config.toml':'[features]\nhooks = false\n',
               self.roots['openclaw']/'openclaw.json':'{"plugins":{"allow":["other"],"deny":["jev-context"]}}'}
        for p,text in paths.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        self.plan().commit()
        self.assertTrue(read_document(self.roots['claude-code']/'settings.json')['disableAllHooks'])
        self.assertFalse((self.roots['codex']/'hooks.json').exists())
        self.assertEqual(read_document(self.roots['openclaw']/'openclaw.json')['plugins']['allow'],['other'])
    def test_mcp_collision_aborts_before_writes(self):
        p=self.home/'.claude.json';p.write_text('{"mcpServers":{"jev-context":{"command":"unrelated","args":[]}}}')
        with self.assertRaises(Conflict):self.plan()
        self.assertFalse(self.prefix.exists())
    def test_invalid_config_aborts_before_writes(self):
        p=self.roots['hermes']/'config.yaml';p.parent.mkdir();p.write_text('x: [broken')
        with self.assertRaises(Exception):self.plan()
        self.assertFalse(self.prefix.exists())
    @unittest.skipUnless(hasattr(os,'symlink'),'symlinks unavailable')
    def test_symlink_output_refused(self):
        original=self.home/'outside';original.write_text('{}')
        p=self.home/'.claude.json';p.symlink_to(original)
        with self.assertRaises(Conflict):self.plan()
        self.assertEqual(original.read_text(),'{}')
    def test_compare_and_swap_detects_concurrent_change(self):
        p=self.plan();target=self.home/'.claude.json';target.write_text('{"changed":true}')
        with self.assertRaises(Conflict):p.commit()
        self.assertEqual(target.read_text(),'{"changed":true}')
        self.assertFalse((self.prefix/'runner.py').exists())
        self.assertFalse((self.prefix/'.installer.lock').exists())
    def test_ordinary_write_failure_rolls_back(self):
        p=self.plan();target=self.home/'.claude.json'
        real=atomic_write
        def fail(path,data,mode=0o600):
            if path==target:raise OSError('injected write error')
            return real(path,data,mode)
        with patch('jev_context.installer.atomic_write',side_effect=fail):
            with self.assertRaises(OSError):p.commit()
        self.assertFalse((self.prefix/'runner.py').exists())
        self.assertFalse((self.prefix/'.installer.lock').exists())
    def test_uninstall_restores_exact_original_and_loader(self):
        original=b'{ "keep" : true }\r\n';p=self.home/'.claude.json';p.write_bytes(original)
        self.plan().commit();result=uninstall(self.prefix)
        self.assertTrue(result['uninstalled']);self.assertEqual(p.read_bytes(),original)
        self.assertFalse((self.roots['opencode']/'plugins/jev-context.js').exists())
        self.assertTrue((self.prefix/'runner.py').exists())
    def test_uninstall_dry_run_and_modified_conflict(self):
        self.plan().commit();p=self.home/'.claude.json';p.write_text('{"user-changed":true}')
        result=uninstall(self.prefix,True);self.assertFalse(result['uninstalled'])
        self.assertTrue((self.roots['opencode']/'plugins/jev-context.js').exists())
        result=uninstall(self.prefix);self.assertFalse(result['uninstalled'])
        self.assertEqual(p.read_text(),'{"user-changed":true}')
    def test_repeat_uninstall_then_reinstall(self):
        self.plan().commit();self.assertTrue(uninstall(self.prefix)['uninstalled'])
        self.assertTrue(uninstall(self.prefix)['uninstalled'])
        self.assertTrue(self.plan().commit()['installed'])
    def test_v2_uses_plural_plugins(self):
        self.plan(['opencode'],api='v2').commit()
        doc=read_document(self.roots['opencode']/'opencode.json')
        self.assertIn(str(self.prefix/'adapters/opencode-v2'),doc['plugins'])
        self.assertFalse((self.roots['opencode']/'plugins/jev-context.js').exists())
    def test_v1_to_v2_requires_uninstall(self):
        self.plan(['opencode']).commit()
        with self.assertRaises(Conflict):self.plan(['opencode'],api='v2')
    def test_hooks_do_not_register_compaction(self):
        self.plan(['codex','claude-code']).commit()
        for p in [self.roots['codex']/'hooks.json',self.roots['claude-code']/'settings.json']:
            hooks=read_document(p)['hooks']
            self.assertNotIn('PreCompact',hooks);self.assertNotIn('PostCompact',hooks)

class HTTPTests(Base):
    def test_loopback_auth_and_capability_boundaries(self):
        server=make_server(self.home,str(self.workspace),0,'a'*40)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join()))
        def req(path='/v1/status',data=None,authorized=True,extra=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            headers={'Content-Type':'application/json'}
            if authorized:headers['Authorization']='Bearer '+'a'*40
            headers.update(extra or {})
            conn.request('POST',path,json.dumps(data or {}),headers)
            result=conn.getresponse();status=result.status;body=json.loads(result.read());conn.close()
            return status,body
        self.assertEqual(req(authorized=False)[0],401)
        self.assertEqual(req(extra={'Origin':'https://hostile.invalid'})[0],403)
        self.assertEqual(req(extra={'Host':'hostile.invalid'})[0],403)
        self.assertEqual(req()[0],200)
        self.assertEqual(req('/v1/retrieve',{'query':'a','use_jev':True})[0],403)
        self.assertEqual(req('/v1/prune_apply',{'plan_id':'x'})[0],404)
        code,record=req('/v1/capture',{'content':'loopback captured evidence'})
        self.assertEqual(code,200)
        code,data=req('/v1/hydrate',{'ref':record['ref'],'verbatim':True})
        self.assertEqual(code,400)

if __name__=='__main__':unittest.main(verbosity=2)
