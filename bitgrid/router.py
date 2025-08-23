from __future__ import annotations

from typing import Dict, List, Tuple, Optional
from .program import Cell, Program


def route_luts(out_dir: str, in_pin: str) -> List[int]:
    # Build 4 LUTs (16-bit) such that output 'out_dir' equals the chosen 'in_pin' input.
    # Inputs order: N,E,S,W; idx = N | (E<<1) | (S<<2) | (W<<3)
    lutN = lutE = lutS = lutW = 0
    out_map = {'N': 'lutN', 'E': 'lutE', 'S': 'lutS', 'W': 'lutW'}
    for idx in range(16):
        n = (idx >> 0) & 1
        e = (idx >> 1) & 1
        s = (idx >> 2) & 1
        w = (idx >> 3) & 1
        val = {'N': n, 'E': e, 'S': s, 'W': w}[in_pin]
        if out_dir == 'N':
            lutN |= (val << idx)
        elif out_dir == 'E':
            lutE |= (val << idx)
        elif out_dir == 'S':
            lutS |= (val << idx)
        elif out_dir == 'W':
            lutW |= (val << idx)
    return [lutN, lutE, lutS, lutW]


class ManhattanRouter:
    def __init__(self, width: int, height: int):
        self.W = width
        self.H = height
        self.occ = [[False for _ in range(self.H)] for _ in range(self.W)]

    def occupy(self, x: int, y: int):
        if 0 <= x < self.W and 0 <= y < self.H:
            self.occ[x][y] = True

    def is_free(self, x: int, y: int) -> bool:
        return (0 <= x < self.W and 0 <= y < self.H and not self.occ[x][y])

    def route(self, src: Tuple[int,int], dst: Tuple[int,int]) -> List[Tuple[int,int]]:
        # simple L-shaped path: horizontal then vertical
        x0, y0 = src
        x1, y1 = dst
        path: List[Tuple[int,int]] = []
        x = x0
        step = 1 if x1 >= x0 else -1
        while x != x1:
            x += step
            if not self.is_free(x, y0):
                raise RuntimeError(f"Blocked at {(x,y0)}")
            path.append((x, y0))
        y = y0
        step = 1 if y1 >= y0 else -1
        while y != y1:
            y += step
            if not self.is_free(x1, y):
                raise RuntimeError(f"Blocked at {(x1,y)}")
            path.append((x1, y))
        return path

    def wire_with_route4(self, src_cell: Tuple[int,int], dst_cell: Tuple[int,int]) -> List[Cell]:
        # Insert ROUTE4 cells along path from src to dst, using pass-through in the travel direction
        path = self.route(src_cell, dst_cell)
        cells: List[Cell] = []
        prev_src = {"type": "cell", "x": src_cell[0], "y": src_cell[1], "out": 0}
        cur = (src_cell[0], src_cell[1])
        for nxt in path:
            dx = nxt[0] - cur[0]
            dy = nxt[1] - cur[1]
            if dx == 1:
                direction = 'E'
            elif dx == -1:
                direction = 'W'
            elif dy == 1:
                direction = 'S'
            elif dy == -1:
                direction = 'N'
            else:
                raise RuntimeError('Non-adjacent hop encountered')
            x, y = nxt
            self.occupy(x, y)
            inputs = [ {"type":"const","value":0} for _ in range(4) ]
            # Map previous source onto the opposite side input and configure LUT to copy that pin to 'direction'
            pin_map = {'N':0,'E':1,'S':2,'W':3}
            opposite = {'E':'W','W':'E','N':'S','S':'N'}[direction]
            inputs[pin_map[opposite]] = prev_src
            luts = route_luts(direction, opposite)
            cell = Cell(x=x, y=y, inputs=inputs, op='ROUTE4', params={'luts': luts})
            cells.append(cell)
            prev_src = {"type": "cell", "x": x, "y": y, "out": pin_map[direction]}
            cur = nxt
        return cells
