from __future__ import annotations

import argparse
import os

from ..program import Program, Cell
from ..physicalize import physicalize_to_edges
from ..lut_only import grid_from_program


def build_full_adder1_program() -> Program:
    # 2x2 grid to keep dimensions even; place compute at (1,0)
    width, height = 2, 2
    x, y = 1, 0
    # Inputs mapping to pins: N=cin, E=b, S=0, W=a
    inputs = [
        {"type": "input", "name": "cin", "bit": 0},  # N
        {"type": "input", "name": "b", "bit": 0},    # E
        {"type": "const", "value": 0},                  # S
        {"type": "input", "name": "a", "bit": 0},    # W
    ]
    # Build LUTs: outputs E=sum (out1), S=carry (out2)
    def lut_bits_from_fn(fn):
        v = 0
        for idx in range(16):
            n = (idx >> 0) & 1
            e = (idx >> 1) & 1
            s = (idx >> 2) & 1
            w = (idx >> 3) & 1
            if fn(n, e, s, w):
                v |= (1 << idx)
        return v & 0xFFFF

    l_sum = lut_bits_from_fn(lambda n, e, s, w: (w ^ e) ^ n)
    l_carry = lut_bits_from_fn(lambda n, e, s, w: (w & e) | (w & n) | (e & n))
    cell = Cell(x=x, y=y, inputs=inputs, op='LUT', params={'luts': [0, l_sum, l_carry, 0]})

    input_bits = {
        'a': [{"type": "input", "name": "a", "bit": 0}],
        'b': [{"type": "input", "name": "b", "bit": 0}],
        'cin': [{"type": "input", "name": "cin", "bit": 0}],
    }
    output_bits = {
        'sum': [{"type": "cell", "x": x, "y": y, "out": 1}],
        'cout': [{"type": "cell", "x": x, "y": y, "out": 2}],
    }
    # crude latency estimate
    latency = width + height
    return Program(width=width, height=height, cells=[cell], input_bits=input_bits, output_bits=output_bits, latency=latency)


def main():
    ap = argparse.ArgumentParser(description='Build a 1-bit full adder Program and optionally physicalize/export as LUTGrid.')
    ap.add_argument('--program', default='out/fa1_program.json', help='Path to write Program JSON')
    ap.add_argument('--grid', help='Optional path to write pre-physicalized LUTGrid JSON (strict neighbor-only will fail)')
    ap.add_argument('--phys-program', default='out/fa1_phys.json', help='Path to write physicalized Program JSON')
    ap.add_argument('--phys-grid', default='out/fa1_phys_grid.json', help='Path to write physicalized LUTGrid JSON')
    ap.add_argument('--input-map', default='a=W,b=E,cin=N', help='Per-bus side mapping, e.g., a=W,b=E,cin=N')
    ap.add_argument('--output-side', choices=['N','E','S','W'], default='E', help='Default edge to expose outputs on')
    ap.add_argument('--output-map', help='Per-bus output side mapping, e.g., sum=E,cout=S; overrides --output-side for those buses')
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.program) or '.', exist_ok=True)
    prog = build_full_adder1_program()
    prog.save(args.program)
    print(f"Wrote Program: {args.program} ({prog.width}x{prog.height}, cells={len(prog.cells)})")

    if args.grid:
        try:
            grid = grid_from_program(prog, strict=True)
            os.makedirs(os.path.dirname(args.grid) or '.', exist_ok=True)
            grid.save(args.grid)
            print(f"Wrote LUTGrid: {args.grid} ({grid.W}x{grid.H})")
        except Exception as e:
            print(f"Skipping strict grid export (expected for non-physicalized Program): {e}")

    # Parse input map
    input_map = {}
    if args.input_map:
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

    # Parse output map
    output_map = {}
    if args.output_map:
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

    phys = physicalize_to_edges(prog, input_side='W', output_side=args.output_side, input_side_map=input_map, output_side_map=output_map)
    os.makedirs(os.path.dirname(args.phys_program) or '.', exist_ok=True)
    phys.save(args.phys_program)
    print(f"Wrote physicalized Program: {args.phys_program}")

    grid = grid_from_program(phys, strict=True)
    os.makedirs(os.path.dirname(args.phys_grid) or '.', exist_ok=True)
    grid.save(args.phys_grid)
    print(f"Wrote physicalized LUTGrid: {args.phys_grid} ({grid.W}x{grid.H})")


if __name__ == '__main__':
    main()
