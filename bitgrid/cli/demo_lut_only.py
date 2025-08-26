from __future__ import annotations

import argparse
from typing import List

from ..lut_only import LUTGrid, LUTOnlyEmulator
from ..program import passthrough_luts


def main():
    ap = argparse.ArgumentParser(description="Demo the LUT-only emulator with simple pass-through")
    ap.add_argument("--width", type=int, default=2)
    ap.add_argument("--height", type=int, default=1)
    args = ap.parse_args()

    g = LUTGrid(args.width, args.height)
    # Fill grid with ROUTE-style pass-through eastwards
    for x in range(args.width):
        for y in range(args.height):
            # Route W input to E output, and pass zeros otherwise
            luts = passthrough_luts('E')  # out E gets its E input; but we want W->E
            # Build correct mapping: out E equals W input, others 0
            from ..router import route_luts
            luts = route_luts('E', 'W')
            g.add_cell(x, y, luts)

    emu = LUTOnlyEmulator(g)
    # Drive west edge with pattern [1,0,1,0,...] vertically
    west = [1 if (y % 2 == 0) else 0 for y in range(args.height)]
    print("in W:", west)
    out1 = emu.step(edge_in={'W': west})
    print("step1 out E:", out1['E'])
    out2 = emu.step(edge_in={'W': [0]*args.height})
    print("step2 out E:", out2['E'])


if __name__ == "__main__":
    main()
