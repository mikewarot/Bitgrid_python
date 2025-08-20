from __future__ import annotations

import argparse
from typing import Dict, Tuple
from ..expr_to_graph import ExprToGraph
from ..mapper import Mapper


def parse_var_widths(s: str) -> Tuple[Dict[str, int], Dict[str, bool]]:
    d: Dict[str,int] = {}
    signed: Dict[str,bool] = {}
    for part in s.split(','):
        part = part.strip()
        if not part:
            continue
        name, width = part.split(':')
        name = name.strip()
        wstr = width.strip().lower()
        is_signed = False
        if wstr.startswith('s'):
            is_signed = True
            wstr = wstr[1:]
        d[name] = int(wstr)
        signed[name] = is_signed
    return d, signed


def main():
    ap = argparse.ArgumentParser(description='Compile expression to BitGrid program')
    ap.add_argument('--expr', required=True, help='Assignment expression, e.g., out = (a & b) ^ c')
    ap.add_argument('--vars', required=True, help='Comma list: name:width,... e.g., a:16,b:16,c:16')
    ap.add_argument('--graph', required=True, help='Output graph JSON path')
    ap.add_argument('--program', required=True, help='Output program JSON path')
    args = ap.parse_args()

    var_widths, var_signed = parse_var_widths(args.vars)
    etg = ExprToGraph(var_widths, var_signed)
    g = etg.parse(args.expr)
    g.save(args.graph)

    mapper = Mapper()
    prog = mapper.map(g)
    prog.save(args.program)
    print(f'Wrote graph to {args.graph} and program to {args.program} (latency={prog.latency}, size={prog.width}x{prog.height})')


if __name__ == '__main__':
    main()
