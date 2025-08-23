from __future__ import annotations

import argparse
import csv
from ..float.f32_mul import build_f32_mul_graph
from ..mapper import Mapper
from ..emulator import Emulator
from ..program import Program


def main():
    ap = argparse.ArgumentParser(description='Run f32 multiply on BitGrid')
    ap.add_argument('--inputs', required=True, help='CSV with columns a,b as 32-bit hex (e.g., 0x3F800000) or decimals')
    ap.add_argument('--outputs', required=True, help='Output CSV file')
    ap.add_argument('--grid-width', type=int, default=1024, help='Grid width capacity for mapping (default: 1024, must be even)')
    ap.add_argument('--grid-height', type=int, default=256, help='Grid height capacity for mapping (default: 256, must be even)')
    args = ap.parse_args()

    g = build_f32_mul_graph('a', 'b', 'prod')
    if args.grid_width % 2 or args.grid_height % 2:
        raise SystemExit('Grid width and height must be even.')
    prog = Mapper(grid_width=args.grid_width, grid_height=args.grid_height).map(g)

    # Load inputs
    def parse_int(s: str) -> int:
        s = s.strip()
        if s.lower().startswith('0x'):
            return int(s, 16)
        return int(s, 10)

    vectors = []
    with open(args.inputs, 'r', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            vectors.append({'a': parse_int(row['a']), 'b': parse_int(row['b'])})

    emu = Emulator(prog)
    results = emu.run(vectors)

    with open(args.outputs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['prod'])
        w.writeheader()
        for res in results:
            w.writerow({'prod': f"0x{res['prod']:08X}"})


if __name__ == '__main__':
    main()
