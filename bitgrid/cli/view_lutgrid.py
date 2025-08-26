from __future__ import annotations

import argparse

from ..lut_only import LUTGrid
from ..lut_logic import decompile_lut_to_expr


def main():
    ap = argparse.ArgumentParser(description='View LUTGrid cells as per-output expressions (NESW).')
    ap.add_argument('--in', dest='inp', required=True, help='input LUTGrid JSON')
    ap.add_argument('--grid', action='store_true', help='Render as a grid summary (per cell)')
    args = ap.parse_args()

    g = LUTGrid.load(args.inp)
    if args.grid:
        for y in range(g.H):
            row = []
            for x in range(g.W):
                c = g.cells[y][x]
                exprs = [decompile_lut_to_expr(c.luts[i]) if c.luts[i] else '0' for i in range(4)]
                # Short summary: show only non-zero outputs per cell
                nonzero = [(d, e) for d, e in zip('NESW', exprs) if e != '0']
                if nonzero:
                    row.append(f"({x},{y}):" + ','.join([f"{d}={e}" for d, e in nonzero]))
            if row:
                print(' | '.join(row))
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
