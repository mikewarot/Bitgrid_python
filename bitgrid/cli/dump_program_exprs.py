from __future__ import annotations

import argparse
from typing import Dict, List, Tuple

from ..program import Program, Cell
from ..lut_logic import decompile_lut_to_expr


PIN_NAMES = ('N','E','S','W')


def _src_label(src: Dict) -> str:
    t = src.get('type')
    if t == 'const':
        return str(int(src.get('value', 0)) & 1)
    if t == 'input':
        return f"input:{src.get('name')}[{int(src.get('bit',0))}]"
    if t == 'cell':
        return f"cell({int(src.get('x',0))},{int(src.get('y',0))}).o{int(src.get('out',0))}"
    return 'undef'


def _cell_exprs(c: Cell) -> List[Tuple[int, str]]:
    lparam = c.params.get('luts', c.params.get('lut'))
    exprs: List[Tuple[int, str]] = []
    if isinstance(lparam, (list, tuple)):
        for oi, lut in enumerate(lparam):
            val = int(lut)
            if val != 0:
                exprs.append((oi, decompile_lut_to_expr(val)))
    else:
        lut = int(lparam) if lparam is not None else 0
        if lut != 0:
            exprs.append((0, decompile_lut_to_expr(lut)))
    return exprs


def dump_list(prog: Program, only_nonzero: bool = True, only_op: str | None = None):
    cells = sorted(prog.cells, key=lambda c: (c.y, c.x))
    for c in cells:
        if only_op and c.op != only_op:
            continue
        exprs = _cell_exprs(c)
        if only_nonzero and not exprs:
            continue
        print(f"({c.x},{c.y}) op={c.op}")
        # inputs
        for i in range(4):
            pin = PIN_NAMES[i]
            if i < len(c.inputs):
                print(f"  in{i}({pin}) = {_src_label(c.inputs[i])}")
            else:
                print(f"  in{i}({pin}) = 0")
        # outputs
        if exprs:
            for oi, e in exprs:
                print(f"  out{oi} = {e}")
        else:
            print("  (no active outputs)")


def dump_grid(prog: Program, only_op: str | None = None):
    # Build quick lookup
    by_xy: Dict[Tuple[int,int], Cell] = {(c.x, c.y): c for c in prog.cells}
    for y in range(prog.height):
        line_parts: List[str] = []
        for x in range(prog.width):
            c = by_xy.get((x, y))
            if not c:
                line_parts.append(" . ")
                continue
            if only_op and c.op != only_op:
                line_parts.append(" - ")
                continue
            exprs = _cell_exprs(c)
            if not exprs:
                line_parts.append(f"[{c.op}:∅]")
            else:
                # Compact: show up to 2 outputs' short forms; full details available in list mode
                shorts = []
                for oi, e in exprs[:2]:
                    shorts.append(f"o{oi}={e}")
                cell_txt = f"[{c.op}:{'|'.join(shorts)}]"
                line_parts.append(cell_txt)
        print(' '.join(line_parts))


def main():
    ap = argparse.ArgumentParser(description="Dump BitGrid program cells as boolean expressions")
    ap.add_argument("path", help="Path to Program JSON (e.g., out/u8_add_aligned.json)")
    ap.add_argument("--grid", action="store_true", help="Print a compact grid view")
    ap.add_argument("--all", action="store_true", help="Include cells with no active outputs (default hides them in list mode)")
    ap.add_argument("--only-op", help="Filter by op type (e.g., ROUTE4, ADD_BIT)")
    args = ap.parse_args()

    prog = Program.load(args.path)
    if args.grid:
        dump_grid(prog, only_op=args.only_op)
    else:
        dump_list(prog, only_nonzero=(not args.all), only_op=args.only_op)


if __name__ == "__main__":
    main()
