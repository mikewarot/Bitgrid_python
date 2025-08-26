from __future__ import annotations

import argparse
from typing import List, Tuple, Optional

from ..lut_only import LUTGrid


PIN_IDX = {'N': 0, 'E': 1, 'S': 2, 'W': 3}
IDX_PIN = {0: 'N', 1: 'E', 2: 'S', 3: 'W'}


def lut_uses_inputs(lut_bits: int) -> List[bool]:
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


def upstream_of(g: LUTGrid, x: int, y: int, pin: str) -> Tuple[str, int, int, Optional[int]]:
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


def trace_all_paths(g: LUTGrid, x: int, y: int, out_dir: str, visited: Optional[set] = None) -> List[List[Tuple[str, object]]]:
    """Trace all dependency paths for a LUT output, branching when multiple inputs are used.
    Returns a list of paths. Each element in a path is either ('cell', (x,y)) or ('edge', (side, index)).
    Paths are ordered from the first upstream hop toward the border.
    """
    if visited is None:
        visited = set()
    key = (x, y, out_dir)
    if key in visited:
        return []  # avoid cycles
    visited.add(key)

    lut_bits = int(g.cells[y][x].luts[PIN_IDX[out_dir]]) & 0xFFFF
    if lut_bits == 0:
        return []
    used = lut_uses_inputs(lut_bits)
    paths: List[List[Tuple[str, object]]] = []
    any_used = False
    for i, u in enumerate(used):
        if not u:
            continue
        any_used = True
        pin = IDX_PIN[i]
        src_type, ux, uy, eidx = upstream_of(g, x, y, pin)
        if src_type == 'edge':
            # Edge input; include annotation and terminate this branch
            paths.append([('edge', (pin, eidx))])
        else:
            opposite = {'N': 'S', 'E': 'W', 'S': 'N', 'W': 'E'}[pin]
            subpaths = trace_all_paths(g, ux, uy, opposite, visited.copy())
            if not subpaths:
                # Leaf upstream cell; include it as single step
                paths.append([('cell', (ux, uy))])
            else:
                for sp in subpaths:
                    paths.append([('cell', (ux, uy))] + sp)
    if not any_used:
        # Constant LUT; no dependencies
        return []
    return paths


def main():
    ap = argparse.ArgumentParser(description='List linear dependency chains for non-zero edge outputs of a LUTGrid.')
    ap.add_argument('--in', dest='inp', required=True, help='Input LUTGrid JSON')
    ap.add_argument('--side', choices=['N','E','S','W'], help='Limit to one edge side')
    args = ap.parse_args()

    g = LUTGrid.load(args.inp)

    def print_side(side: str):
        if side in ('N','S'):
            count = g.W
        else:
            count = g.H
        for pos in range(count):
            if side == 'N':
                x, y, out_dir = pos, 0, 'N'
            elif side == 'E':
                x, y, out_dir = g.W - 1, pos, 'E'
            elif side == 'S':
                x, y, out_dir = pos, g.H - 1, 'S'
            else:  # 'W'
                x, y, out_dir = 0, pos, 'W'
            lut_bits = int(g.cells[y][x].luts[PIN_IDX[out_dir]]) & 0xFFFF
            if lut_bits == 0:
                continue
            paths = trace_all_paths(g, x, y, out_dir)
            if not paths:
                print(f"{side}@{pos}:")
                continue
            for p in paths:
                rendered: List[str] = []
                for kind, data in p:
                    if kind == 'cell':
                        cx, cy = data  # type: ignore
                        rendered.append(f"({cx},{cy})")
                    else:
                        eside, eidx = data  # type: ignore
                        rendered.append(f"edge {eside}@{eidx}")
                print(f"{side}@{pos}: " + ' -> '.join(rendered))

    if args.side:
        print_side(args.side)
    else:
        for s in ('N','E','S','W'):
            print_side(s)


if __name__ == '__main__':
    main()
