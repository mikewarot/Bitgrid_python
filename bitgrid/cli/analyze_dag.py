from __future__ import annotations

import argparse
import json
from typing import Optional

from ..expr_to_graph import ExprToGraph
from ..dag import analyze_dag, to_dot
from ..graph import Graph


def parse_var_widths(s: str):
    d = {}
    signed = {}
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
    ap = argparse.ArgumentParser(description='Analyze DAG of an expression or graph JSON')
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--expr', help='Assignment expression, e.g., out = (a & b) ^ c')
    src.add_argument('--graph', help='Path to graph JSON created by compile_expr or similar')
    ap.add_argument('--vars', help='For --expr, comma list: name:width,... e.g., a:16,b:16,c:16')
    ap.add_argument('--dot', help='Optional path to write Graphviz DOT')
    ap.add_argument('--out-json', help='Optional path to write analysis JSON')
    args = ap.parse_args()

    if args.expr:
        if not args.vars:
            ap.error('--vars is required when using --expr')
        var_widths, var_signed = parse_var_widths(args.vars)
        etg = ExprToGraph(var_widths, var_signed)
        g = etg.parse(args.expr)
    else:
        g = Graph.load(args.graph)

    analysis = analyze_dag(g)

    # Print concise summary
    print(f"nodes={len(g.nodes)} inputs={len(g.inputs)} outputs={len(g.outputs)}")
    print(f"levels={len(analysis.level_nodes)} critical_len={analysis.critical_path_len}")
    if analysis.critical_path:
        tail = analysis.critical_path[-5:]
        if len(analysis.critical_path) > 5:
            print('critical_path=...,' + '->'.join(tail))
        else:
            print('critical_path=' + '->'.join(analysis.critical_path))
    for name, depth in analysis.per_output_depth.items():
        print(f"output {name}: depth={depth}")

    if args.dot:
        with open(args.dot, 'w', encoding='utf-8') as f:
            f.write(to_dot(g, analysis.levels))
        print(f"Wrote DOT to {args.dot}")
    if args.out_json:
        payload = {
            'topo_order': analysis.topo_order,
            'levels': analysis.levels,
            'critical_path_len': analysis.critical_path_len,
            'critical_path': analysis.critical_path,
            'per_output_depth': analysis.per_output_depth,
        }
        with open(args.out_json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        print(f"Wrote analysis JSON to {args.out_json}")


if __name__ == '__main__':
    main()
