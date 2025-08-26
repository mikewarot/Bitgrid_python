from __future__ import annotations

import argparse
import os

from ..program import Program
from ..physicalize import physicalize_to_edges
from ..lut_only import grid_from_program


def main():
    ap = argparse.ArgumentParser(description='Physicalize a Program: map logical I/O to edges using ROUTE4, output neighbor-only Program and optional LUTGrid.')
    ap.add_argument('--in', dest='inp', required=True, help='input Program JSON')
    ap.add_argument('--out-program', required=True, help='output physicalized Program JSON')
    ap.add_argument('--out-grid', help='optional output LUTGrid JSON')
    ap.add_argument('--input-side', choices=['N','E','S','W'], default='W', help='Default edge to drive inputs from')
    ap.add_argument('--input-map', help='Optional per-bus side mapping, e.g. a=W,b=E')
    ap.add_argument('--output-side', choices=['N','E','S','W'], default='E', help='Default edge to expose outputs on')
    ap.add_argument('--output-map', help='Optional per-bus output side mapping, e.g. sum=E,cout=S')
    ap.add_argument('--output-extra-hops', help='Optional per-bus extra detour hops for outputs, e.g. sum=1,cout=2')
    args = ap.parse_args()

    prog = Program.load(args.inp)
    # Parse optional input map
    input_map = None
    if args.input_map:
        input_map = {}
        for pair in args.input_map.split(','):
            if not pair:
                continue
            if '=' not in pair:
                raise SystemExit(f"Invalid --input-map entry: {pair}")
            k, v = pair.split('=', 1)
            v = v.strip().upper()
            if v not in ('N','E','S','W'):
                raise SystemExit(f"Invalid side '{v}' for input '{k}' in --input-map")
            input_map[k.strip()] = v
    # Parse optional output map and extra hops
    output_map = None
    if args.output_map:
        output_map = {}
        for pair in args.output_map.split(','):
            if not pair:
                continue
            if '=' not in pair:
                raise SystemExit(f"Invalid --output-map entry: {pair}")
            k, v = pair.split('=', 1)
            v = v.strip().upper()
            if v not in ('N','E','S','W'):
                raise SystemExit(f"Invalid side '{v}' for output '{k}' in --output-map")
            output_map[k.strip()] = v
    extra_hops = None
    if args.output_extra_hops:
        extra_hops = {}
        for pair in args.output_extra_hops.split(','):
            if not pair:
                continue
            if '=' not in pair:
                raise SystemExit(f"Invalid --output-extra-hops entry: {pair}")
            k, v = pair.split('=', 1)
            try:
                extra_hops[k.strip()] = int(v.strip())
            except Exception:
                raise SystemExit(f"Invalid hops value for '{k}': {v}")

    phys = physicalize_to_edges(prog, input_side=args.input_side, output_side=args.output_side, input_side_map=input_map, output_side_map=output_map, output_extra_hops=extra_hops)
    os.makedirs(os.path.dirname(args.out_program) or '.', exist_ok=True)
    phys.save(args.out_program)
    print(f"Saved physicalized Program to {args.out_program}")

    if args.out_grid:
        grid = grid_from_program(phys, strict=True)
        os.makedirs(os.path.dirname(args.out_grid) or '.', exist_ok=True)
        grid.save(args.out_grid)
        print(f"Saved LUTGrid to {args.out_grid} ({grid.W}x{grid.H})")


if __name__ == '__main__':
    main()
