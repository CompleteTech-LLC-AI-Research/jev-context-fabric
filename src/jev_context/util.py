from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

MAX_INPUT_BYTES = 8 * 1024 * 1024


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    """Replace a regular file atomically. Never follow a final-component symlink."""
    if path.is_symlink():
        raise ValueError(f"Refusing symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".jev-tmp-", dir=path.parent)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def redact(text: str) -> str:
    """Best-effort credential redaction, NOT a data-loss-prevention guarantee."""
    patterns = [
        (r"(?is)-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", "[REDACTED PRIVATE KEY]"),
        (r"(?i)\bBearer\s+[A-Za-z0-9_./+=-]+", "Bearer [REDACTED]"),
        (r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b", "[REDACTED TOKEN]"),
        (r'''(?i)((?:api[_-]?key|password|passwd|secret|access[_-]?token|refresh[_-]?token)["']?\s*[:=]\s*["']?)([^\s,"';}]+)''', r"\1[REDACTED]"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def require_text(value: Any, name: str, max_chars: int = 2_000_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    if len(value) > max_chars:
        raise ValueError(f"{name} exceeds {max_chars} characters; submit smaller pages")
    return value


def bounded_int(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def workspace_key(path: str | Path) -> str:
    """Use the worktree directory, not a guessed remote URL or shared repository name."""
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise ValueError(f"Workspace is not a directory: {p}")
    return str(p)
