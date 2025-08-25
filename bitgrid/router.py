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
        # Track ROUTE4 cells we create during a routing pass for per-output sharing
        self._route_cells = {}

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

    def wire_adjacent_to(self, src_cell: Tuple[int,int], dst_cell: Tuple[int,int], src_out: int = 0) -> Tuple[List[Cell], str, Tuple[int,int]]:
        # Route from src to a neighbor of dst (stop one hop before dst). Returns (cells, dir_to_dst, last_xy).
        path = self.route(src_cell, dst_cell)
        if not path:
            # already at dst; no routing and no adjacency
            return [], 'E', src_cell
        # stop before reaching dst
        hops = path[:-1]
        cells: List[Cell] = []
        prev_src = {"type": "cell", "x": src_cell[0], "y": src_cell[1], "out": int(src_out)}
        cur = src_cell
        last_dir = 'E'
        pin_map = {'N':0,'E':1,'S':2,'W':3}
        for nxt in hops:
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
            # Create or reuse a ROUTE4 cell here and add mapping for this hop
            opposite = {'E':'W','W':'E','N':'S','S':'N'}[direction]
            cell, created = self._add_or_merge_route4(x, y, out_dir=direction, in_pin=opposite, upstream=prev_src)
            if created:
                cells.append(cell)
            prev_src = {"type": "cell", "x": x, "y": y, "out": pin_map[direction]}
            last_dir = direction
            cur = nxt
        # At this point, cur is adjacent to dst, and last_dir points towards dst
        return cells, last_dir, cur

    def _add_or_merge_route4(self, x: int, y: int, out_dir: str, in_pin: str, upstream: Dict) -> Tuple[Cell, bool]:
        """Ensure there is a ROUTE4 cell at (x,y) with mapping out_dir <- in_pin.
        If a cell exists from this router pass, merge the mapping (per-output sharing).
        Otherwise create a new ROUTE4 cell. Returns (cell, created_new).
        Notes:
          - We do not merge into non-ROUTE4 compute cells; caller must avoid occupied compute cells.
          - We forbid double assignment of the same out_dir.
          - We require unique input pins per cell unless the same upstream source is used.
        """
        pin_map = {'N':0,'E':1,'S':2,'W':3}
        out_idx = pin_map[out_dir]
        in_idx = pin_map[in_pin]
        cell = self._route_cells.get((x, y))
        if cell is None:
            # Create fresh
            inputs = [ {"type":"const","value":0} for _ in range(4) ]
            inputs[in_idx] = upstream
            luts = [0,0,0,0]
            # set mapping for out_dir
            rl = route_luts(out_dir, in_pin)
            for i in range(4):
                luts[i] |= rl[i]
            cell = Cell(x=x, y=y, inputs=inputs, op='ROUTE4', params={'luts': luts})
            # Mark occupancy and remember for sharing
            self.occupy(x, y)
            self._route_cells[(x, y)] = cell
            return cell, True
        # Merge into existing route cell created in this pass
        if cell.op != 'ROUTE4':
            raise RuntimeError(f'Cannot merge routing into non-ROUTE4 cell at {(x,y)}')
        # Check output direction availability
        luts = [int(v) for v in cell.params.get('luts', [0,0,0,0])]
        if luts[out_idx] != 0:
            raise RuntimeError(f'ROUTE4 out {out_dir} already assigned at {(x,y)}')
        # Set/validate upstream on the input pin
        cur_in = cell.inputs[in_idx]
        if cur_in.get('type') == 'const' and int(cur_in.get('value',0)) == 0:
            cell.inputs[in_idx] = upstream
        else:
            # If it's not the same source, we disallow sharing that input pin
            if cur_in != upstream:
                raise RuntimeError(f'ROUTE4 input pin {in_pin} already used at {(x,y)}')
        rl = route_luts(out_dir, in_pin)
        for i in range(4):
            luts[i] |= rl[i]
        cell.params['luts'] = luts
        return cell, False


def route_program(prog: Program) -> Program:
    """
    Insert ROUTE4 cells for non-adjacent cell->cell inputs to enforce neighbor-only hops.
    For each cell input referencing another cell at distance > 1, route a path to a neighbor
    of the sink and reconnect the input to the last ROUTE4 cell's output in the direction
    facing the sink.
    """
    router = ManhattanRouter(prog.width, prog.height)
    # Occupy existing cells
    for c in prog.cells:
        router.occupy(c.x, c.y)

    new_cells: List[Cell] = []
    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}

    # Rewire inputs
    for sink in prog.cells:
        sx, sy = sink.x, sink.y
        for i, src in enumerate(sink.inputs):
            if src.get('type') != 'cell':
                continue
            if 'x' not in src or 'y' not in src:
                continue
            try:
                tx, ty = int(src['x']), int(src['y'])
                tout = int(src.get('out', 0))
            except Exception:
                continue
            # if already adjacent, leave as-is
            if abs(tx - sx) + abs(ty - sy) <= 1:
                continue
            # route to a neighbor of sink
            cells, last_dir, last_xy = router.wire_adjacent_to((tx, ty), (sx, sy), src_out=tout)
            new_cells.extend(cells)
            # Connect sink input to the last hop cell's output facing the sink
            sink.inputs[i] = {"type":"cell","x":last_xy[0],"y":last_xy[1],"out":dir_to_idx[last_dir]}

    # Return updated program with inserted route cells appended
    return Program(width=prog.width, height=prog.height, cells=prog.cells + new_cells,
                   input_bits=prog.input_bits, output_bits=prog.output_bits, latency=prog.latency)
