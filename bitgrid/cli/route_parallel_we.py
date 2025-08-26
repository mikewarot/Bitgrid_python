from __future__ import annotations

import argparse
import os
from typing import Dict, List

from ..program import Program
from ..router import ManhattanRouter
from ..lut_only import grid_from_program


def parse_rows(s: str) -> List[int]:
    return [int(x.strip()) for x in s.split(',') if x.strip() != '']


def parse_extras(s: str) -> Dict[int, int]:
    out: Dict[int, int] = {}
    if not s:
        return out
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        if '=' not in part:
            raise SystemExit(f"Invalid --extra spec: {part} (expected row=extra)")
        k, v = part.split('=', 1)
        out[int(k.strip())] = int(v.strip())
    return out


def main():
    ap = argparse.ArgumentParser(description='Route parallel West->East streams on chosen rows, with optional per-lane extra hops; print hop counts.')
    ap.add_argument('--width', type=int, default=6, help='Grid width (even)')
    ap.add_argument('--height', type=int, default=4, help='Grid height (even)')
    ap.add_argument('--rows', default='0,1', help='Comma-separated row indices (y) to route from W to E')
    ap.add_argument('--extra', default='', help='Per-row extra hops, e.g., 0=0,1=1')
    ap.add_argument('--out-grid', default='out/parallel_we.json', help='Output LUTGrid path')
    args = ap.parse_args()

    W, H = int(args.width), int(args.height)
    if W % 2 or H % 2:
        raise SystemExit('Width/Height must be even')
    rows = parse_rows(args.rows)
    for y in rows:
        if not (0 <= y < H):
            raise SystemExit(f"Row {y} is outside height {H}")
    extras = parse_extras(args.extra)

    prog = Program(width=W, height=H, cells=[], input_bits={}, output_bits={}, latency=0)
    r = ManhattanRouter(W, H)

    hop_report: List[str] = []
    for y in rows:
        extra_hops = int(extras.get(y, 0))
        cells, hops = r.wire_edge_to_edge('W', y, 'E', y, extra_hops=extra_hops)
        prog.cells.extend(cells)
        hop_report.append(f"W->E row {y}: hops={hops} (extra={extra_hops})")

    grid = grid_from_program(prog, strict=True)
    os.makedirs(os.path.dirname(args.out_grid) or '.', exist_ok=True)
    grid.save(args.out_grid)
    print(f"Saved LUTGrid to {args.out_grid} ({grid.W}x{grid.H})")
    for line in hop_report:
        print(line)


if __name__ == '__main__':
    main()
