from __future__ import annotations

import sys
import os
import glob
from pathlib import Path

from ..program import Program
from ..lut_only import LUTGrid
from ..validator import validate_program_connectivity, validate_lutgrid_connectivity


def find_latest_program_json(search_root: Path) -> Path | None:
    # Look under out/ by default
    out_dir = search_root / 'out'
    candidates: list[Path] = []
    for pat in ('routed_*.json', '*.json'):
        candidates.extend(out_dir.glob(pat))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(argv[0]).resolve() if argv else Path.cwd()
    latest = find_latest_program_json(root)
    if latest is None:
        print("No out/*.json found to validate. You can run: py -m bitgrid.cli.validate_connectivity <program.json>")
        return 0
    print(f"Validating: {latest}")
    # Detect file type by presence of 'format': 'lutgrid-v1' or by cell schema
    text = latest.read_text(encoding='utf-8')
    is_lutgrid = '"format"' in text and 'lutgrid-v1' in text
    issues: list[str]
    if is_lutgrid:
        grid = LUTGrid.from_json(text)
        issues = validate_lutgrid_connectivity(grid)
    else:
        prog = Program.from_json(text)
        issues = validate_program_connectivity(prog)
    if not issues:
        print("Connectivity: OK")
        return 0
    print(f"Connectivity issues ({len(issues)}):")
    for s in issues[:200]:
        print(f"- {s}")
    if len(issues) > 200:
        print("... (truncated)")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
