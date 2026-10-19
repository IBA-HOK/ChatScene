"""Dynamic retrieval — Strata/qwen3.8-flash-next entry point."""

import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
_root = _here.parent
for p in (str(_root), str(_here)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from retrieve import main, parse_args  # type: ignore
except ImportError:
    import retrieve as _retrieve
    main = _retrieve.main  # type: ignore
    parse_args = _retrieve.parse_args  # type: ignore

if __name__ == '__main__':
    raise SystemExit(main())
