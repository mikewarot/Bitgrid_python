from __future__ import annotations

import argparse
import csv
from ..float.f8_mul import build_f8_mul_graph
from ..mapper import Mapper
from ..emulator import Emulator


def main():
    ap = argparse.ArgumentParser(description='Run FP8 (E4M3) multiply on BitGrid')
    ap.add_argument('--inputs', required=True, help='CSV with columns a,b as 8-bit hex (e.g., 0x3C) or decimals 0..255')
    ap.add_argument('--outputs', required=True, help='Output CSV file')
    ap.add_argument('--grid-width', type=int, default=128, help='Grid width capacity for mapping (even)')
    ap.add_argument('--grid-height', type=int, default=64, help='Grid height capacity for mapping (even)')
    args = ap.parse_args()

    g = build_f8_mul_graph('a', 'b', 'prod')
    if args.grid_width % 2 or args.grid_height % 2:
        raise SystemExit('Grid width and height must be even.')
    prog = Mapper(grid_width=args.grid_width, grid_height=args.grid_height).map(g)

    def parse_byte(s: str) -> int:
        s = s.strip()
        if s.lower().startswith('0x'):
            return int(s, 16) & 0xFF
        return int(s, 10) & 0xFF

    vectors = []
    with open(args.inputs, 'r', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            vectors.append({'a': parse_byte(row['a']), 'b': parse_byte(row['b'])})

    emu = Emulator(prog)
    results = emu.run(vectors)

    with open(args.outputs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['prod'])
        w.writeheader()
        for res in results:
            w.writerow({'prod': f"0x{res['prod'] & 0xFF:02X}"})


if __name__ == '__main__':
    main()
