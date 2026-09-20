#!/usr/bin/env python3
"""Check packaged file hashes. This is integrity checking, not a signed release."""
from pathlib import Path
import hashlib
import json
import sys

root=Path(__file__).resolve().parent
manifest=root/'MANIFEST.sha256.json'
if not manifest.exists():
    raise SystemExit('Missing MANIFEST.sha256.json')
failed=[]
for name,expected in json.loads(manifest.read_text('utf-8')).items():
    path=root/name
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        failed.append(name);continue
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:failed.append(name)
if failed:
    print(json.dumps({'verified':False,'failed_files':failed},indent=2))
    sys.exit(1)
print(json.dumps({'verified':True,'checked_files':len(json.loads(manifest.read_text()))}))
