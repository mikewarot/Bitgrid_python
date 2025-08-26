from __future__ import annotations

import argparse
from ..lut_logic import compile_expr_to_lut


def main():
    ap = argparse.ArgumentParser(description="Compile boolean expr (N,E,S,W) to 16-bit LUT")
    ap.add_argument("expr", help="Expression using N,E,S,W and &,|,^,!,~,and,or,not,()")
    args = ap.parse_args()
    lut = compile_expr_to_lut(args.expr)
    print(f"0x{lut:04X}")


if __name__ == "__main__":
    main()
