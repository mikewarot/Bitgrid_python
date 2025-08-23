from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import heapq
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
        if width % 2 != 0 or height % 2 != 0:
            raise ValueError("Grid dimensions must be even (width and height)")
        self.W = width
        self.H = height
        self.occ = [[False for _ in range(self.H)] for _ in range(self.W)]

    def occupy(self, x: int, y: int):
        if 0 <= x < self.W and 0 <= y < self.H:
            self.occ[x][y] = True

    def is_free(self, x: int, y: int) -> bool:
        return (0 <= x < self.W and 0 <= y < self.H and not self.occ[x][y])

    def route(self, src: Tuple[int,int], dst: Tuple[int,int], turn_penalty: float = 0.0) -> List[Tuple[int,int]]:
        # A* Manhattan routing with 4-neighbor moves and simple occupancy.
        # Optional turn_penalty (>0) biases toward straighter paths (fewer corners).
        sx, sy = src
        tx, ty = dst
        def h(x: int, y: int) -> int:
            return abs(x - tx) + abs(y - ty)
        openh: List[Tuple[float, Tuple[int,int]]] = []
        heapq.heappush(openh, (float(h(sx, sy)), (sx, sy)))
        gscore: Dict[Tuple[int,int], float] = {(sx, sy): 0.0}
        came: Dict[Tuple[int,int], Tuple[int,int]] = {}
        came_dir: Dict[Tuple[int,int], Tuple[int,int]] = {}
        closed: set[Tuple[int,int]] = set()
        while openh:
            _, (x, y) = heapq.heappop(openh)
            if (x, y) in closed:
                continue
            if (x, y) == (tx, ty):
                # reconstruct excluding the start
                path: List[Tuple[int,int]] = []
                cur = (x, y)
                while cur != (sx, sy):
                    path.append(cur)
                    cur = came[cur]
                path.reverse()
                return path
            closed.add((x, y))
            for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nx, ny = x+dx, y+dy
                if not self.is_free(nx, ny) and (nx, ny) != (tx, ty):
                    continue
                # base cost is 1 per move
                cost = 1.0
                # apply small penalty for turns relative to arriving direction
                if turn_penalty > 0.0 and (x, y) in came_dir:
                    pdx, pdy = came_dir[(x, y)]
                    if (pdx, pdy) != (dx, dy):
                        cost += float(turn_penalty)
                ng = gscore[(x, y)] + cost
                if ng < gscore.get((nx, ny), float('inf')):
                    gscore[(nx, ny)] = ng
                    came[(nx, ny)] = (x, y)
                    came_dir[(nx, ny)] = (dx, dy)
                    heapq.heappush(openh, (ng + float(h(nx, ny)), (nx, ny)))
        raise RuntimeError("No route found")

    def wire_with_route4(self, src_cell: Tuple[int,int], dst_cell: Tuple[int,int]) -> Tuple[List[Cell], str]:
        # Insert ROUTE4 cells along path from src to dst, using pass-through in the travel direction
        path = self.route(src_cell, dst_cell)
        cells: List[Cell] = []
        prev_src = {"type": "cell", "x": src_cell[0], "y": src_cell[1], "out": 0}
        cur = (src_cell[0], src_cell[1])
        last_dir = 'E'
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
            last_dir = direction
            cur = nxt
        return cells, last_dir
