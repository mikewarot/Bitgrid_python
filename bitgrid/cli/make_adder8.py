from __future__ import annotations

import argparse
import os

from ..graph import Graph, Node
from ..mapper import Mapper
from ..router import route_program
from ..lut_only import grid_from_program


def build_adder8_program() -> str:
    g = Graph()
    g.add_input('a', 8)
    g.add_input('b', 8)
    g.add_node(Node(id='add', op='ADD', inputs=['a', 'b'], width=8))
    g.set_output('sum', 'add', 8)
    m = Mapper()
    prog = m.map(g)
    return prog.to_json()


def main():
    ap = argparse.ArgumentParser(description='Build an 8-bit adder Program and optionally export as LUTGrid.')
    ap.add_argument('--program', default='out/adder8_program.json', help='Path to write Program JSON')
    ap.add_argument('--grid', default='out/adder8_grid.json', help='Path to write LUTGrid JSON')
    ap.add_argument('--route', action='store_true', help='Insert ROUTE4 hops before exporting the LUTGrid')
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.program) or '.', exist_ok=True)
    os.makedirs(os.path.dirname(args.grid) or '.', exist_ok=True)

    # Build and save Program
    g = Graph()
    g.add_input('a', 8)
    g.add_input('b', 8)
    g.add_node(Node(id='add', op='ADD', inputs=['a', 'b'], width=8))
    g.set_output('sum', 'add', 8)
    m = Mapper()
    prog = m.map(g)
    prog.save(args.program)
    print(f"Wrote Program: {args.program} ({prog.width}x{prog.height}, cells={len(prog.cells)})")

    # Optional routing, then export LUTGrid
    p2 = route_program(prog) if args.route else prog
    grid = grid_from_program(p2, strict=not args.route)
    grid.save(args.grid)
    print(f"Wrote LUTGrid: {args.grid} ({grid.W}x{grid.H})")


if __name__ == '__main__':
    main()
