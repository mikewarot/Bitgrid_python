from __future__ import annotations

import sys
from pathlib import Path
from ..program import Program
from ..validator import validate_program_connectivity


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python -m bitgrid.cli.validate_connectivity <program.json>")
        return 2
    path = Path(argv[0])
    if not path.exists():
        print(f"file not found: {path}")
        return 2
    prog = Program.load(str(path))
    issues = validate_program_connectivity(prog)
    if not issues:
        print("Connectivity: OK")
        return 0
    print("Connectivity issues:")
    for s in issues:
        print("- ", s)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
