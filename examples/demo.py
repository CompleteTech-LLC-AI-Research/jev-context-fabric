#!/usr/bin/env python3
"""Offline demonstration in a disposable directory; no host settings are modified."""
from pathlib import Path
import json
import sys
import tempfile
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from jev_context.core import Core
from jev_context import paging

with tempfile.TemporaryDirectory(prefix='jev-demo-') as folder:
    root=Path(folder);workspace=root/'worktree';workspace.mkdir()
    core=Core(root/'memory',workspace)
    try:
        source=core.capture('Decision: preserve canonical source evidence; keep compact separate.',
                            origin='demo:decision',session='demo',harness='generic')
        core.store.pin(core.workspace,source['ref'])
        pack=core.retrieve('architecture decision',2000)
        messages=[{'role':'system','content':'Original governing instruction'},
                  *[{'role':'assistant','content':f'Old narrative {i}. '+'irrelevant detail '*20} for i in range(18)],
                  {'role':'user','content':'Current authentication task'}]
        paging.prepare(core,'demo','generic',messages)
        plan=paging.plan(core,'demo','generic','authentication',300)
        # Explicit approval for this isolated synthetic demonstration only.
        core.config['native_prune_enabled']=True
        approved=paging.apply(core,plan['plan_id'])
        prepared=paging.prepare(core,'demo','generic',messages)
        print(json.dumps({'remote_calls':0,'source_ref':source['ref'],
            'evidence_characters':pack['characters'],'original_messages':len(messages),
            'active_messages':len(prepared['messages']),'removed':prepared['removed'],
            'canonical_sources':core.status()['sources'],
            'native_compaction_called':prepared['native_compaction_called'],
            'note':'Synthetic illustration, not a task-accuracy or token-reduction benchmark.'},indent=2))
    finally:core.close()
