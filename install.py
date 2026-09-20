#!/usr/bin/env python3
"""Offline bootstrap: vendored pure-Python config parsers; no pip or API calls."""
import sys
from pathlib import Path
sys.dont_write_bytecode = True
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required. No configuration was changed.")
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"vendor"))
sys.path.insert(0,str(ROOT/"src"))
from jev_context.installer import main
if __name__ == "__main__":
    raise SystemExit(main(ROOT))
