#!/usr/bin/env python3
import sys
from pathlib import Path
sys.dont_write_bytecode = True
if sys.version_info < (3,11): raise SystemExit("Python 3.11+ required")
sys.path.insert(0,str(Path(__file__).resolve().parent/"src"))
from jev_context.__main__ import main
if __name__ == "__main__": raise SystemExit(main())
