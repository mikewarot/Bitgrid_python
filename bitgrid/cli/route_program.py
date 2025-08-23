from __future__ import annotations

import argparse
from ..program import Program
from ..router import route_program


def main():
    ap = argparse.ArgumentParser(description='Insert ROUTE4 hops to enforce neighbor-only routing in a program JSON')
    ap.add_argument('--in', dest='inp', required=True, help='input program.json')
    ap.add_argument('--out', dest='out', required=True, help='output program.json with inserted ROUTE4 hops')
    args = ap.parse_args()

    prog = Program.load(args.inp)
    routed = route_program(prog)
    routed.save(args.out)
    print(f"Saved routed program to {args.out}")


if __name__ == '__main__':
    main()
