from __future__ import annotations

import argparse
from typing import List, Tuple
from ..expr_to_graph import ExprToGraph
from ..mapper import Mapper
from ..program import Program
from ..emulator import Emulator
from ..router import route_program


def parse_pairs(s: str) -> List[Tuple[int,int]]:
    pairs: List[Tuple[int,int]] = []
    tok = ''
    for part in s.split(')'):
        part = part.strip()
        if not part:
            continue
        part = part.strip(',').strip('(').strip()
        if not part:
            continue
        a, b = part.split(',')
        pairs.append((int(a, 0) & 0xFF, int(b, 0) & 0xFF))
    return pairs


def main():
    ap = argparse.ArgumentParser(description='Correctness-first: 8-bit sum using routed program, non-streaming per vector')
    ap.add_argument('--width', type=int, default=64)
    ap.add_argument('--height', type=int, default=64)
    ap.add_argument('--pairs', type=str, default='(1,2),(3,4),(10,20),(255,1)')
    args = ap.parse_args()

    if args.width % 2 or args.height % 2:
        raise SystemExit('Grid width and height must be even.')

    # Build 8-bit adder graph and map
    etg = ExprToGraph({'a':8,'b':8}, {'a':False,'b':False})
    g = etg.parse('sum = a + b')
    mapper = Mapper(grid_width=args.width, grid_height=args.height)
    prog = mapper.map(g)

    # Enforce neighbor-only via routing pass
    routed = route_program(prog)

    # Evaluate each pair as a separate vector
    emu = Emulator(routed)
    pairs = parse_pairs(args.pairs)
    vectors = [{ 'a': a, 'b': b } for (a,b) in pairs]
    results = emu.run(vectors)
    for (a,b), out in zip(pairs, results):
        print(f"a={a:3d} b={b:3d} -> sum=0x{out.get('sum',0):02X} ({out.get('sum',0)})")


if __name__ == '__main__':
    main()
