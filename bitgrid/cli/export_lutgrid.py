from __future__ import annotations

import argparse
import os

from ..program import Program
from ..router import route_program
from ..lut_only import grid_from_program, LUTGrid


def main():
    ap = argparse.ArgumentParser(description='Export a Program JSON to a LUTGrid JSON (editable LUT-only format).')
    ap.add_argument('--in', dest='inp', required=True, help='input Program JSON')
    ap.add_argument('--out', dest='out', required=True, help='output LUTGrid JSON')
    ap.add_argument('--route', action='store_true', help='Insert ROUTE4 hops first to enforce neighbor-only')
    args = ap.parse_args()

    prog = Program.load(args.inp)
    if args.route:
        prog = route_program(prog)
    grid = grid_from_program(prog, strict=not args.route)
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    grid.save(args.out)
    print(f"Saved LUTGrid to {args.out} ({grid.W}x{grid.H})")


if __name__ == '__main__':
    main()
