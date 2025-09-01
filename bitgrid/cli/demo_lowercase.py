from __future__ import annotations

import argparse
from typing import List

from ..expr_to_graph import ExprToGraph
from ..mapper import Mapper
from ..emulator import Emulator


def build_lowercase_expr() -> str:
    """
    Return a single-assignment expression that maps 8-bit x -> out,
    converting ASCII 'A'..'Z' to lowercase by setting bit 5 conditionally.

    is_upper = (bit6==1) & (bit5==0) & (low5!=0) & (low5<27)
    where: bit6=(x>>6)&1, bit5=(x>>5)&1, low5=x&31.
    low5<27 is implemented as signbit((low5 + (~27 + 1))) == 1, then >>7 &1.
    out = x | (is_upper << 5)
    """
    # Inline the terms to keep parser simple
    low5 = "(x & 31)"
    b6 = "((x >> 6) & 1)"
    b5z = "(1 ^ ((x >> 5) & 1))"  # bit5 == 0
    # low5 < 27 => sign bit of (low5 - 27) is 1. Use 8-bit two's complement: low5 + ((27 ^ 255) + 1)
    lt27 = f"(((({low5} + ((27 ^ 255) + 1)) >> 7) & 1))"
    # low5 != 0: OR-reduce the five LSBs
    nz = (
        f"(({low5} & 1) | (({low5} >> 1) & 1) | (({low5} >> 2) & 1) | "
        f"(({low5} >> 3) & 1) | (({low5} >> 4) & 1))"
    )
    is_upper = f"(({b6} & {b5z} & {lt27} & {nz}))"
    expr = f"out = x | (({is_upper}) << 5)"
    return expr


def lowercase_text(text: str) -> str:
    # Build graph from expression
    e = build_lowercase_expr()
    etg = ExprToGraph(var_widths={'x': 8})
    g = etg.parse(e)
    # Map to a grid program
    mapper = Mapper(grid_width=64, grid_height=64)
    prog = mapper.map(g)
    # Run per character
    emu = Emulator(prog)
    out_bytes: List[int] = []
    for ch in text.encode('utf-8', errors='ignore'):
        res = emu.run([{'x': ch & 0xFF}])[0]
        out_val = res.get('out', 0) & 0xFF
        out_bytes.append(out_val)
    return bytes(out_bytes).decode('utf-8', errors='ignore')


def main():
    ap = argparse.ArgumentParser(description='Map and run an ASCII uppercase→lowercase transform on 8-bit stream.')
    ap.add_argument('--text', type=str, default='Hello, WORLD! 123_[]', help='Input text (UTF-8)')
    ap.add_argument('--save-graph', type=str, help='Optional path to save the built graph JSON')
    ap.add_argument('--save-program', type=str, help='Optional path to save the mapped Program JSON')
    args = ap.parse_args()

    expr = build_lowercase_expr()
    etg = ExprToGraph(var_widths={'x': 8})
    g = etg.parse(expr)
    if args.save_graph:
        g.save(args.save_graph)

    mapper = Mapper(grid_width=64, grid_height=64)
    prog = mapper.map(g)
    if args.save_program:
        prog.save(args.save_program)

    emu = Emulator(prog)
    out_chars: List[int] = []
    for ch in args.text.encode('utf-8', errors='ignore'):
        res = emu.run([{'x': ch & 0xFF}])[0]
        out_chars.append(res.get('out', 0) & 0xFF)
    out_text = bytes(out_chars).decode('utf-8', errors='ignore')
    print(f"in : {args.text}")
    print(f"out: {out_text}")


if __name__ == '__main__':
    main()
