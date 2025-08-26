from __future__ import annotations

import argparse

from ..lut_only import LUTGrid
from ..lut_logic import decompile_lut_to_expr


def main():
    ap = argparse.ArgumentParser(description='View LUTGrid cells as per-output expressions (NESW).')
    ap.add_argument('--in', dest='inp', required=True, help='input LUTGrid JSON')
    ap.add_argument('--grid', action='store_true', help='Render as a grid summary (per cell)')
    ap.add_argument('--dirs', default='NESW', help='Filter which directions to show (subset of NESW), default NESW')
    ap.add_argument('--truncate', type=int, default=0, help='Truncate each cell string to N chars (0 = no truncation)')
    ap.add_argument('--cell-width', type=int, default=0, help='Fixed cell width (0 = auto per column)')
    args = ap.parse_args()

    g = LUTGrid.load(args.inp)
    if args.grid:
        dirs = ''.join([d for d in args.dirs.upper() if d in 'NESW']) or 'NESW'
        dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
        # Build cell strings matrix
        cells: list[list[str]] = [["" for _ in range(g.W)] for _ in range(g.H)]
        for y in range(g.H):
            for x in range(g.W):
                c = g.cells[y][x]
                parts = []
                for d in dirs:
                    i = dir_to_idx[d]
                    v = c.luts[i]
                    if v:
                        parts.append(f"{d}={decompile_lut_to_expr(v)}")
                s = ','.join(parts)
                if args.truncate and len(s) > args.truncate:
                    s = s[:max(1, args.truncate-1)] + '…'
                # Keep coordinate prefix only when there is content
                cells[y][x] = (f"({x},{y}):" + s) if s else ""
        # Determine column widths
        widths = [0]*g.W
        for x in range(g.W):
            if args.cell_width > 0:
                widths[x] = args.cell_width
            else:
                widths[x] = max((len(cells[y][x]) for y in range(g.H)), default=0)
        # Print rows with padding; center each cell like your original
        for y in range(g.H):
            row_strs = []
            for x in range(g.W):
                w = widths[x]
                s = cells[y][x]
                if w > 0:
                    s = s.center(w)
                row_strs.append(s)
            line = ' :: '.join(row_strs).rstrip()
            if any(cells[y]):
                print(line)
    else:
        for y in range(g.H):
            for x in range(g.W):
                c = g.cells[y][x]
                exprs = [decompile_lut_to_expr(c.luts[i]) if c.luts[i] else '0' for i in range(4)]
                if any(v != '0' for v in exprs):
                    print(f"Cell ({x},{y})")
                    for d, e in zip('NESW', exprs):
                        if e != '0':
                            print(f"  {d}: {e}")


if __name__ == '__main__':
    main()
