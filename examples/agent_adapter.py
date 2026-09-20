"""Generic synchronous subprocess adapter. No package installation or model key needed."""
from __future__ import annotations
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class MemoryClient:
    runner: Path
    home: Path
    workspace: Path
    python: str = sys.executable
    timeout: float = 6.0

    def call(self, operation: str, **arguments) -> dict:
        body=json.dumps({'operation':operation,'arguments':arguments},ensure_ascii=False)
        if len(body.encode('utf-8'))>8*1024*1024:
            raise ValueError('Split the request into smaller source pages')
        result=subprocess.run([self.python,str(self.runner),'--home',str(self.home),
            '--workspace',str(self.workspace),'bridge'],input=body,text=True,encoding='utf-8',
            capture_output=True,timeout=self.timeout,check=False)
        if result.returncode:
            # Avoid propagating raw native diagnostics into a model prompt.
            raise RuntimeError('Memory bridge failed; retain the original context')
        payload=json.loads(result.stdout)
        if not isinstance(payload,dict):raise ValueError('Invalid bridge response')
        return payload

    def before_model(self, session: str, messages: list[dict], query: str) -> tuple[list[dict],str]:
        """Return the approved active view and evidence separately; do not change host policy."""
        try:
            view=self.call('prepare',session=session,harness='generic',messages=messages,query=query)
            evidence=self.call('event',session=session,harness='generic',kind='PRE_MODEL',content='',query=query)
            return view['messages'],evidence.get('context','')
        except (OSError,ValueError,KeyError,RuntimeError,subprocess.TimeoutExpired):
            return messages,''

    def after_tool(self, session: str, tool: str, result: str) -> dict:
        return self.call('event',kind='POST_TOOL',harness='generic',session=session,
                         origin=tool,content=result)
