"""Frozen entry point. Kept separate from run_lumina.py so the bundle does not
carry the dev sys.path shim."""
from lumina.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
