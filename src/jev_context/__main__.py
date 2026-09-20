from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from .config import default_home, load_config, save_config
from .core import Core
from .util import canonical, MAX_INPUT_BYTES
from . import paging


def read_json():
    raw=sys.stdin.buffer.read(MAX_INPUT_BYTES+1)
    if len(raw)>MAX_INPUT_BYTES: raise ValueError("Input exceeds 8 MiB; split it into smaller pages")
    data=json.loads(raw)
    if not isinstance(data,dict): raise ValueError("Expected JSON object")
    return data


def parser():
    p=argparse.ArgumentParser(description="JEV Context Fabric: source-backed memory, retrieval and reversible active views")
    p.add_argument("--home",type=Path,default=default_home())
    p.add_argument("--workspace",default=os.getcwd())
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("mcp")
    sub.add_parser("bridge")
    sub.add_parser("bus-stage", help="Serve one jev-bus.stage.v1 request on stdin (carrier-invoked)")
    cap=sub.add_parser("capture")
    group=cap.add_mutually_exclusive_group(required=True)
    group.add_argument("--text"); group.add_argument("--file",type=Path)
    cap.add_argument("--origin",default="manual")
    cap.add_argument("--session",default="manual"); cap.add_argument("--harness",default="manual")
    ret=sub.add_parser("retrieve")
    ret.add_argument("query",nargs="?",default="")
    ret.add_argument("--max-chars",type=int,default=6000)
    ret.add_argument("--jev",action="store_true",help="Explicitly request paid remote reranking; requires prior opt-in")
    hyd=sub.add_parser("hydrate")
    hyd.add_argument("ref"); hyd.add_argument("--offset",type=int,default=0)
    hyd.add_argument("--max-chars",type=int,default=6000); hyd.add_argument("--verbatim",action="store_true")
    enc=sub.add_parser("enrich"); enc.add_argument("--limit",type=int,default=10)
    hk=sub.add_parser("hook"); hk.add_argument("--harness",required=True); hk.add_argument("--event",required=True)
    config=sub.add_parser("config")
    config.add_argument("--enable-typesafe",action="store_true"); config.add_argument("--allow-remote",action="store_true")
    config.add_argument("--disable-typesafe",action="store_true"); config.add_argument("--model",default="jev-1.13.0")
    config.add_argument("--disable-capture",action="store_true"); config.add_argument("--enable-capture",action="store_true")
    config.add_argument("--disable-injection",action="store_true"); config.add_argument("--enable-injection",action="store_true")
    pl=sub.add_parser("prune-plan")
    pl.add_argument("--session",required=True); pl.add_argument("--harness",required=True)
    pl.add_argument("--goal",required=True); pl.add_argument("--target-chars",type=int,default=12000)
    ap=sub.add_parser("prune-apply"); ap.add_argument("plan_id"); ap.add_argument("--enable-native",action="store_true",required=True)
    rs=sub.add_parser("prune-reset"); rs.add_argument("--session",required=True); rs.add_argument("--harness",required=True)
    hs=sub.add_parser("serve-http"); hs.add_argument("--port",type=int,default=8769)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    core=None
    try:
        if args.command=="hook":
            from .hooks import run_hook
            print(canonical(run_hook(args.home,args.workspace,args.harness,args.event,read_json())))
            return 0
        if args.command=="config":
            changes={}
            if args.enable_typesafe:
                if not args.allow_remote: raise ValueError("--enable-typesafe requires --allow-remote; source excerpts leave the machine")
                if args.disable_typesafe: raise ValueError("Choose enable or disable")
                changes.update(backend="typesafe",allow_remote=True,model=args.model)
            if args.disable_typesafe: changes.update(backend="local",allow_remote=False)
            if args.disable_capture: changes["capture_enabled"]=False
            if args.enable_capture: changes["capture_enabled"]=True
            if args.disable_injection: changes["inject_enabled"]=False
            if args.enable_injection: changes["inject_enabled"]=True
            data=save_config(args.home,changes) if changes else load_config(args.home)
            print(json.dumps(data,indent=2)); return 0
        if args.command=="serve-http":
            from .http_api import serve
            serve(args.home,str(Path(args.workspace).resolve()),args.port); return 0
        if args.command=="bus-stage":
            # A carrier in another package invoked us. Never break the host's turn: on any
            # error, decline explicitly so the bus keeps this stage's input unchanged.
            from . import bus
            stage_core=None
            try:
                request=bus.read_stage_request()
                stage_core=Core(args.home,request.get("workspace") or args.workspace)
                print(canonical(paging.bus_stage(stage_core,request)))
            except Exception as exc:
                print(canonical({"ok":False,"error":type(exc).__name__,"message":str(exc)[:300]}))
            finally:
                if stage_core is not None: stage_core.close()
            return 0
        core=Core(args.home,args.workspace)
        if args.command=="mcp":
            from .mcp import serve
            serve(core); return 0
        if args.command=="bridge":
            value=read_json()
            data=core.dispatch(value.get("operation",""),value.get("arguments",{}))
        elif args.command=="capture":
            text=args.file.read_bytes().decode("utf-8") if args.file else args.text
            data=core.capture(text,args.origin,args.session,args.harness)
        elif args.command=="retrieve": data=core.retrieve(args.query,args.max_chars,args.jev)
        elif args.command=="hydrate": data=core.hydrate(args.ref,args.offset,args.max_chars,verbatim=args.verbatim)
        elif args.command=="enrich": data=core.enrich(args.limit)
        elif args.command=="prune-plan": data=paging.plan(core,args.session,args.harness,args.goal,args.target_chars)
        elif args.command=="prune-apply":
            # Enabling native views is an explicit local CLI action, not an MCP capability.
            old=core.config["native_prune_enabled"]
            core.config["native_prune_enabled"]=True
            data=paging.apply(core,args.plan_id)
            if data.get("applied"): save_config(args.home,{"native_prune_enabled":True})
            else: core.config["native_prune_enabled"]=old
        elif args.command=="prune-reset": data=paging.reset(core,args.session,args.harness)
        elif args.command=="doctor":
            import shutil
            data={**core.status(),"python":sys.version.split()[0],"python_executable":sys.executable,
                  "typesafe_key_present":bool(os.environ.get("TYPESAFE_API_KEY")),
                  "native_binaries":{name:shutil.which(name) for name in ["openclaw","hermes","opencode","codex","claude","gemini","cursor","copilot"]},
                  "live_harness_compatibility":"Not established by this diagnostic; trigger real hooks and inspect captured sessions",
                  "note":"MCP is bound to the server launch directory. Different harnesses must use the same explicit worktree path for shared retrieval."}
        else: data=core.status()
        print(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False))
        return 0
    except Exception as exc:
        if args.command=="hook":
            print("{}")
            print(f"jev-context hook skipped: {type(exc).__name__}",file=sys.stderr)
            return 0  # Memory is fail-open, not an authorization boundary.
        print(canonical({"error":type(exc).__name__,"message":str(exc)[:600]}),file=sys.stderr)
        return 1
    finally:
        if core is not None: core.close()


if __name__=="__main__":
    raise SystemExit(main())
