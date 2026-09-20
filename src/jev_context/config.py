from __future__ import annotations

import json
import os
from pathlib import Path
from .util import atomic_write, bounded_int

DEFAULTS = {
    "schema_version": 1,
    "backend": "local",
    "allow_remote": False,
    "model": "jev-1.13.0",
    "request_timeout_seconds": 4,
    "max_remote_chars": 16000,
    "max_evidence_chars": 6000,
    "capture_enabled": True,
    "inject_enabled": True,
    "native_prune_enabled": False,
    "retained_recent_messages": 8,
}


def default_home() -> Path:
    return Path(os.environ.get("JEV_CONTEXT_HOME", str(Path.home() / ".jev-context-fabric"))).expanduser().resolve()


def load_config(home: Path) -> dict:
    path = home / "config.json"
    value = json.loads(path.read_text("utf-8")) if path.exists() else {}
    if not isinstance(value, dict):
        raise ValueError("config.json must contain an object")
    return validate_config({**DEFAULTS, **value})


def validate_config(result: dict) -> dict:
    if result["backend"] not in ("local", "typesafe"):
        raise ValueError("backend must be local or typesafe")
    for key in ("allow_remote", "capture_enabled", "inject_enabled", "native_prune_enabled"):
        if type(result[key]) is not bool:
            raise ValueError(f"{key} must be a JSON boolean")
    bounded_int(result["max_remote_chars"], "max_remote_chars", 512, 100000)
    bounded_int(result["max_evidence_chars"], "max_evidence_chars", 512, 100000)
    bounded_int(result["retained_recent_messages"], "retained_recent_messages", 2, 10000)
    bounded_int(result["request_timeout_seconds"], "request_timeout_seconds", 1, 60)
    if not isinstance(result["model"],str) or not result["model"].strip():
        raise ValueError("model must be a nonempty string")
    return result


def save_config(home: Path, changes: dict) -> dict:
    value = validate_config({**load_config(home), **changes})
    atomic_write(home / "config.json", (json.dumps(value, indent=2) + "\n").encode())
    return value
