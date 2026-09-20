"""Optional loopback JSON API, deliberately not an HTTP MCP implementation."""
from __future__ import annotations
import hmac
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .core import Core
from .util import atomic_write, canonical, MAX_INPUT_BYTES

ALLOWED={"status","capture","retrieve","page_fault","hydrate","prune_plan","feature","pin","link"}


def make_server(home: Path, workspace: str, port: int, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass  # Do not log query/source bodies.
        def setup(self):
            super().setup()
            self.connection.settimeout(5)
        def send_json(self, code, data):
            body=canonical(data).encode()
            self.send_response(code)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            self.wfile.write(body)
        def do_POST(self):
            host=self.headers.get("Host","")
            expected={f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}
            if host not in expected or self.headers.get("Origin"):
                return self.send_json(403,{"error":"Host/origin rejected"})
            if not hmac.compare_digest(self.headers.get("Authorization",""),"Bearer "+token):
                return self.send_json(401,{"error":"Unauthorized"})
            if self.headers.get("Transfer-Encoding"):
                return self.send_json(400,{"error":"Chunked request bodies are unsupported"})
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0<length<=MAX_INPUT_BYTES: return self.send_json(413,{"error":"Invalid body size"})
                if self.headers.get("Content-Type","").split(";")[0]!="application/json":
                    return self.send_json(415,{"error":"application/json required"})
                operation=self.path.removeprefix("/v1/")
                if self.path!="/v1/"+operation or operation not in ALLOWED:
                    return self.send_json(404,{"error":"Unknown endpoint"})
                args=json.loads(self.rfile.read(length))
                # HTTP does not grant remote-model spend; that is a local CLI operation.
                if isinstance(args,dict) and args.get("use_jev"):
                    return self.send_json(403,{"error":"Remote reranking is CLI-only"})
                core=Core(home,workspace)
                try: data=core.dispatch(operation,args)
                finally: core.close()
                self.send_json(200,data)
            except Exception as exc:
                self.send_json(400,{"error":type(exc).__name__,"message":str(exc)[:300]})
    return ThreadingHTTPServer(("127.0.0.1",port),Handler)


def serve(home: Path, workspace: str, port: int):
    token_path=home/"http-token"
    if token_path.exists():
        if token_path.is_symlink(): raise ValueError("Refusing symlinked token")
        token=token_path.read_text().strip()
    else:
        token=secrets.token_urlsafe(32)
        atomic_write(token_path,(token+"\n").encode())
    if len(token)<32: raise ValueError("HTTP token is too short")
    server=make_server(home,workspace,port,token)
    print(f"Loopback JSON API listening on 127.0.0.1:{server.server_port}; bearer token file: {token_path}",flush=True)
    try: server.serve_forever()
    finally: server.server_close()
