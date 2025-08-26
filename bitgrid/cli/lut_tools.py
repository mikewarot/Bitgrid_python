from __future__ import annotations

import argparse
from ..lut_logic import compile_expr_to_lut, decompile_lut_to_expr


def main():
    ap = argparse.ArgumentParser(description="Compile or decompile LUT/expr for BitGrid cells")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("-e", "--expr", help="Expression using N,E,S,W and &,|,^,!,~,and,or,not,()")
    g.add_argument("-l", "--lut", help="Hex LUT like 0xF00F to decompile to expression")
    args = ap.parse_args()
    if args.expr:
        lut = compile_expr_to_lut(args.expr)
        print(f"0x{lut:04X}")
    else:
        val = int(args.lut, 16)
        print(decompile_lut_to_expr(val))


if __name__ == "__main__":
    main()
