from __future__ import annotations

import argparse
from typing import Optional

from ..program import Program
from ..router import route_program
from ..lut_only import LUTOnlyEmulator, grid_from_program


def main():
    ap = argparse.ArgumentParser(description='Run LUT-only emulator from a Program JSON with edge I/O')
    ap.add_argument('--program', required=True, help='Path to program.json')
    ap.add_argument('--route', action='store_true', help='Insert ROUTE4 hops before loading (enforce neighbor-only)')
    ap.add_argument('--steps', type=int, default=4, help='Number of subcycles to run')
    ap.add_argument('--west', help='Comma-separated H-length bits to drive on west edge for step 0 (e.g., 1,0,1)')
    args = ap.parse_args()

    prog = Program.load(args.program)
    if args.route:
        prog = route_program(prog)
    grid = grid_from_program(prog, strict=not args.route)
    emu = LUTOnlyEmulator(grid)

    west_bits = None
    if args.west:
        west_bits = [int(x) & 1 for x in args.west.split(',') if x.strip() != '']
        if len(west_bits) != grid.H:
            raise SystemExit(f"--west must have {grid.H} bits (got {len(west_bits)})")

    edge = {'W': west_bits} if west_bits is not None else None
    for i in range(args.steps):
        out = emu.step(edge_in=edge)
        print(f"step {i}: N={out['N']} E={out['E']} S={out['S']} W={out['W']}")
        # drive only on first step unless user wants to keep driving
        edge = None


if __name__ == '__main__':
    main()
