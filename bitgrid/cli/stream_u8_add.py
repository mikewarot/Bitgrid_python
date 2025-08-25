from __future__ import annotations

import argparse
import csv
import os
import random
from ..int.u8_add import build_u8_add_graph
from ..mapper import Mapper
from ..emulator import Emulator


def load_csv(path: str, col: str) -> list[int]:
    def parse_b(s: str) -> int:
        s = s.strip()
        if s.lower().startswith('0x'):
            return int(s, 16) & 0xFF
        return int(s, 10) & 0xFF
    out = []
    with open(path, 'r', newline='') as f:
        r = csv.DictReader(f)
        if not r.fieldnames or (col not in r.fieldnames):
            raise SystemExit(f"Missing column '{col}' in {path}")
        for row in r:
            out.append(parse_b(row[col]))
    return out


def main():
    ap = argparse.ArgumentParser(description='Stream 8-bit unsigned add: feeds one a,b per cycle and outputs sum per cycle after pipeline fill')
    ap.add_argument('--a', help='CSV with column a')
    ap.add_argument('--b', help='CSV with column b')
    ap.add_argument('--count', type=int, default=256, help='If CSVs omitted, generate this many random pairs')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--outputs', required=True, help='Output CSV (sum)')
    ap.add_argument('--grid-width', type=int, default=512)
    ap.add_argument('--grid-height', type=int, default=128)
    args = ap.parse_args()

    if args.grid_width % 2 or args.grid_height % 2:
        raise SystemExit('Grid width and height must be even.')

    g = build_u8_add_graph('a', 'b', 's')
    prog = Mapper(grid_width=args.grid_width, grid_height=args.grid_height).map(g)
    emu = Emulator(prog)
    latency = prog.latency

    if args.a and args.b:
        A = load_csv(args.a, 'a')
        B = load_csv(args.b, 'b')
        n = min(len(A), len(B))
        A = A[:n]; B = B[:n]
    else:
        rng = random.Random(args.seed)
        A = [rng.randrange(0,256) for _ in range(args.count)]
        B = [rng.randrange(0,256) for _ in range(args.count)]

    steps = []
    for i in range(len(A)):
        steps.append({'a': A[i], 'b': B[i]})
    # drain
    for _ in range(latency):
        steps.append({'a': 0, 'b': 0})

    outs = emu.run_stream(steps, cycles_per_step=1, reset=True)

    os.makedirs(os.path.dirname(args.outputs) or '.', exist_ok=True)
    with open(args.outputs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['s'])
        w.writeheader()
        for i in range(len(A)):
            oidx = i + latency
            if oidx >= len(outs):
                break
            s = outs[oidx].get('s', 0) & 0xFF
            w.writerow({'s': f"0x{s:02X}"})


if __name__ == '__main__':
    main()
