from __future__ import annotations

import argparse
import json
from typing import Dict, List, Tuple, Optional, Set

from ..lut_only import LUTGrid


PIN_IDX = {'N': 0, 'E': 1, 'S': 2, 'W': 3}
IDX_PIN = {0: 'N', 1: 'E', 2: 'S', 3: 'W'}


def lut_uses_inputs(lut_bits: int) -> List[bool]:
    """Return a 4-length list indicating whether each variable (N,E,S,W) influences the LUT output.
    LUT index encoding: idx = N | (E<<1) | (S<<2) | (W<<3)
    """
    uses = [False, False, False, False]
    for var in range(4):
        delta = 1 << var
        for idx in range(16):
            b0 = (lut_bits >> idx) & 1
            b1 = (lut_bits >> (idx ^ delta)) & 1
            if b0 != b1:
                uses[var] = True
                break
    return uses


def lut_is_const(lut_bits: int) -> Optional[int]:
    """Return 0 or 1 if LUT is a constant, else None."""
    any1 = (lut_bits & 0xFFFF) != 0
    all1 = (lut_bits & 0xFFFF) == 0xFFFF
    if not any1:
        return 0
    if all1:
        return 1
    return None


def upstream_of(g: LUTGrid, x: int, y: int, pin: str) -> Tuple[str, int, int, Optional[int]]:
    """Return upstream source for a given input pin at cell (x,y).
    Returns a tuple (src_type, ux, uy, edge_index) where src_type in {'cell','edge'}.
    If src_type=='cell', (ux,uy) is the neighbor cell coordinate providing the opposite output.
    If src_type=='edge', (ux,uy) are -1 and edge_index gives the edge position.
    """
    W, H = g.W, g.H
    if pin == 'N':
        if y == 0:
            return 'edge', -1, -1, x
        return 'cell', x, y - 1, None
    if pin == 'E':
        if x == W - 1:
            return 'edge', -1, -1, y
        return 'cell', x + 1, y, None
    if pin == 'S':
        if y == H - 1:
            return 'edge', -1, -1, x
        return 'cell', x, y + 1, None
    if pin == 'W':
        if x == 0:
            return 'edge', -1, -1, y
        return 'cell', x - 1, y, None
    raise ValueError('invalid pin')


def build_graph_for_output(g: LUTGrid, x: int, y: int, out_dir: str, visited: Set[Tuple[int,int,str]]) -> Dict:
    """Recursively build a dependency graph for cell (x,y) output out_dir in {'N','E','S','W'}."""
    key = (x, y, out_dir)
    if key in visited:
        return {"type": "cycle", "x": x, "y": y, "dir": out_dir}
    visited.add(key)

    cell = g.cells[y][x]
    lut_bits = int(cell.luts[PIN_IDX[out_dir]]) & 0xFFFF
    const = lut_is_const(lut_bits)
    if const is not None:
        return {
            "type": "cell_output",
            "x": x,
            "y": y,
            "dir": out_dir,
            "const": const,
            "depends_on": [],
            "depth": 0,
        }

    used = lut_uses_inputs(lut_bits)
    deps: List[Dict] = []
    max_depth = 0
    for i, uses in enumerate(used):
        if not uses:
            continue
        pin = IDX_PIN[i]
        src_type, ux, uy, eidx = upstream_of(g, x, y, pin)
        if src_type == 'edge':
            dep = {"type": "edge_input", "side": pin, "index": eidx, "depth": 0}
            deps.append(dep)
        else:
            # neighbor cell output is the opposite dir of this pin
            opposite = {'N': 'S', 'E': 'W', 'S': 'N', 'W': 'E'}[pin]
            sub = build_graph_for_output(g, ux, uy, opposite, visited)
            deps.append(sub)
            max_depth = max(max_depth, int(sub.get("depth", 0)))

    return {
        "type": "cell_output",
        "x": x,
        "y": y,
        "dir": out_dir,
        "const": None,
        "depends_on": deps,
        "depth": (0 if not deps else (1 + max_depth)),
    }


def main():
    ap = argparse.ArgumentParser(description='Reverse-engineer dependency graphs for non-zero edge outputs from a LUTGrid.')
    ap.add_argument('--in', dest='inp', required=True, help='Input LUTGrid JSON')
    ap.add_argument('--out', dest='out', help='Output JSON for graphs; omit to print to stdout')
    ap.add_argument('--include-internal', action='store_true', help='Also include graphs for non-zero internal cell outputs')
    args = ap.parse_args()

    g = LUTGrid.load(args.inp)

    graphs: Dict[str, List[Optional[Dict]]] = {
        'N': [None for _ in range(g.W)],
        'E': [None for _ in range(g.H)],
        'S': [None for _ in range(g.W)],
        'W': [None for _ in range(g.H)],
    }

    # Edge outputs map to specific border cells and directions
    # For each, if the LUT for that output is non-zero, build graph
    # N edge: cell (x,0), out_dir 'N'
    for x in range(g.W):
        cell = g.cells[0][x]
        lut_bits = int(cell.luts[PIN_IDX['N']]) & 0xFFFF
        if lut_bits != 0:
            graphs['N'][x] = build_graph_for_output(g, x, 0, 'N', set())

    # E edge: cell (W-1,y), out 'E'
    for y in range(g.H):
        cell = g.cells[y][g.W - 1]
        lut_bits = int(cell.luts[PIN_IDX['E']]) & 0xFFFF
        if lut_bits != 0:
            graphs['E'][y] = build_graph_for_output(g, g.W - 1, y, 'E', set())

    # S edge: cell (x,H-1), out 'S'
    for x in range(g.W):
        cell = g.cells[g.H - 1][x]
        lut_bits = int(cell.luts[PIN_IDX['S']]) & 0xFFFF
        if lut_bits != 0:
            graphs['S'][x] = build_graph_for_output(g, x, g.H - 1, 'S', set())

    # W edge: cell (0,y), out 'W'
    for y in range(g.H):
        cell = g.cells[y][0]
        lut_bits = int(cell.luts[PIN_IDX['W']]) & 0xFFFF
        if lut_bits != 0:
            graphs['W'][y] = build_graph_for_output(g, 0, y, 'W', set())

    out_obj: Dict = {
        'width': g.W,
        'height': g.H,
        'graphs': graphs,
    }

    if args.include_internal:
        internal: List[Dict] = []
        for y in range(g.H):
            for x in range(g.W):
                cell = g.cells[y][x]
                for d, dir_name in enumerate(('N','E','S','W')):
                    if int(cell.luts[d]) & 0xFFFF:
                        internal.append({'x': x, 'y': y, 'dir': dir_name, 'graph': build_graph_for_output(g, x, y, dir_name, set())})
        out_obj['internal'] = internal

    txt = json.dumps(out_obj, indent=2)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(txt)
        print(f"Wrote graphs to {args.out}")
    else:
        print(txt)


if __name__ == '__main__':
    main()
