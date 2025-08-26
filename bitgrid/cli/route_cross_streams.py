from __future__ import annotations

import argparse
import os
from typing import Tuple

from ..program import Program, Cell
from ..router import ManhattanRouter
from ..lut_only import grid_from_program


def main():
    ap = argparse.ArgumentParser(description='Route two crossing streams: North->South and West->East across a small grid.')
    ap.add_argument('--width', type=int, default=4, help='Grid width (even)')
    ap.add_argument('--height', type=int, default=4, help='Grid height (even)')
    ap.add_argument('--ns-pos', type=int, default=1, help='X position for N->S stream (0..W-1)')
    ap.add_argument('--we-pos', type=int, default=1, help='Y position for W->E stream (0..H-1)')
    ap.add_argument('--extra-ns', type=int, default=0, help='Extra detour hops for N->S')
    ap.add_argument('--extra-we', type=int, default=0, help='Extra detour hops for W->E')
    ap.add_argument('--out-grid', default='out/cross_grid.json', help='Output LUTGrid path')
    args = ap.parse_args()

    W, H = int(args.width), int(args.height)
    if W % 2 or H % 2:
        raise SystemExit('Width/Height must be even')
    ns_x = max(0, min(W - 1, int(args.ns_pos)))
    we_y = max(0, min(H - 1, int(args.we_pos)))

    prog = Program(width=W, height=H, cells=[], input_bits={}, output_bits={}, latency=0)
    r = ManhattanRouter(W, H)

    # Route N->S along column ns_x, from N edge pos=ns_x to S edge pos=ns_x
    cells_ns, hops_ns = r.wire_edge_to_edge('N', ns_x, 'S', ns_x, extra_hops=int(args.extra_ns))
    # Route W->E along row we_y, from W edge pos=we_y to E edge pos=we_y
    cells_we, hops_we = r.wire_edge_to_edge('W', we_y, 'E', we_y, extra_hops=int(args.extra_we))

    prog.cells.extend(cells_ns)
    prog.cells.extend(cells_we)

    grid = grid_from_program(prog, strict=True)
    os.makedirs(os.path.dirname(args.out_grid) or '.', exist_ok=True)
    grid.save(args.out_grid)
    print(f"Saved LUTGrid to {args.out_grid} ({grid.W}x{grid.H})")
    print(f"N->S hops: {hops_ns}; W->E hops: {hops_we}")


if __name__ == '__main__':
    main()
