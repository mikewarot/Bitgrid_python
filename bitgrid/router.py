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
        # Track edge fanout branches per lane
        self._edge_fanout_index = {}

    def occupy(self, x: int, y: int):
        if 0 <= x < self.W and 0 <= y < self.H:
            self.occ[x][y] = True

    def is_free(self, x: int, y: int) -> bool:
        return (0 <= x < self.W and 0 <= y < self.H and not self.occ[x][y])

    def route(self, src: Tuple[int,int], dst: Tuple[int,int], turn_penalty: float = 0.0, avoid_moves: Optional[set] = None) -> List[Tuple[int,int]]:
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
                # Respect explicit avoid list of moves (from (x,y) in direction (dx,dy))
                if avoid_moves is not None:
                    if dx == 1:
                        dname = 'E'
                    elif dx == -1:
                        dname = 'W'
                    elif dy == 1:
                        dname = 'S'
                    elif dy == -1:
                        dname = 'N'
                    else:
                        dname = None
                    if dname is not None and (x, y, dname) in avoid_moves:
                        continue
                if not self.is_free(nx, ny) and (nx, ny) != (tx, ty):
                    # Allow stepping onto ROUTE4 cells created in this routing pass for sharing/merging
                    if (nx, ny) not in self._route_cells:
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
            # If already assigned, allow reuse if mapping is identical and input pin upstream matches
            expected = route_luts(out_dir, in_pin)[out_idx]
            if luts[out_idx] == expected:
                cur_in = cell.inputs[in_idx]
                if cur_in == upstream:
                    # Safe to reuse existing mapping
                    return cell, False
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

    def wire_from_edge_to(self, side: str, pos: int, dst_cell: Tuple[int,int], extra_hops: int = 0) -> Tuple[List[Cell], str, Tuple[int,int], int]:
        """Route from a physical edge location into the grid, stopping adjacent to dst.
        side in {'N','E','S','W'}; pos is along that edge (x for N/S, y for E/W).
        extra_hops adds intentional detours before reaching dst to increase path length for alignment.
        Returns (cells, last_dir, last_xy, hop_count) where last_dir is the direction of the last hop taken.
        hop_count counts the number of inter-cell hops taken (excluding the final neighbor step into dst).
        """
        # Determine start and primary outward direction
        if side == 'W':
            start = (0, pos)
            primary = 'E'
        elif side == 'E':
            start = (self.W - 1, pos)
            primary = 'W'
        elif side == 'N':
            start = (pos, 0)
            primary = 'S'
        elif side == 'S':
            start = (pos, self.H - 1)
            primary = 'N'
        else:
            raise ValueError('Invalid side; expected one of N,E,S,W')

        # If start is compute-occupied, step one inward along primary
        if not self.is_free(start[0], start[1]):
            dd = {'N':(0,-1),'E':(1,0),'S':(0,1),'W':(-1,0)}[primary]
            alt = (start[0] + dd[0], start[1] + dd[1])
            if self.is_free(alt[0], alt[1]):
                start = alt

        def dir_from_delta(dx: int, dy: int) -> str:
            if dx == 1: return 'E'
            if dx == -1: return 'W'
            if dy == 1: return 'S'
            if dy == -1: return 'N'
            raise RuntimeError('Non-adjacent hop encountered')

        # Avoid retrograde moves back to boundary
        avoid_moves: set = set()
        if side == 'W':
            for y in range(self.H):
                avoid_moves.add((1, y, 'W'))
        elif side == 'E':
            for y in range(self.H):
                avoid_moves.add((self.W-2, y, 'E'))
        elif side == 'N':
            for x in range(self.W):
                avoid_moves.add((x, 1, 'N'))
        elif side == 'S':
            for x in range(self.W):
                avoid_moves.add((x, self.H-2, 'S'))

        # Also avoid using already-occupied out directions on existing route cells
        for (rx, ry), rcell in list(self._route_cells.items()):
            if rcell.op != 'ROUTE4':
                continue
            luts_used = [int(v) for v in rcell.params.get('luts', [0,0,0,0])]
            for dname, idx in (('N',0),('E',1),('S',2),('W',3)):
                if luts_used[idx] != 0:
                    avoid_moves.add((rx, ry, dname))

        cells: List[Cell] = []
        cur = start
        last_dir = primary
        pin_map = {'N':0,'E':1,'S':2,'W':3}
        edge_upstream = {"type":"edge","side":side,"index":int(pos)}

        # Try to reuse start mapping if compatible
        reused = False
        existing = self._route_cells.get(cur)
        if existing is not None and existing.op == 'ROUTE4':
            luts = [int(v) for v in existing.params.get('luts', [0,0,0,0])]
            if existing.inputs[pin_map[side]] == edge_upstream and luts[pin_map[primary]] != 0:
                prev_src = {"type":"cell","x":cur[0],"y":cur[1],"out":pin_map[primary]}
                reused = True

        if not reused:
            # Create mapping at start; if collision, try alternates
            try:
                start_cell, created = self._add_or_merge_route4(cur[0], cur[1], out_dir=primary, in_pin=side, upstream=edge_upstream)
                if created:
                    cells.append(start_cell)
                prev_src = {"type":"cell","x":cur[0],"y":cur[1],"out":pin_map[primary]}
                chosen_dir = primary
            except RuntimeError as e:
                if 'already' not in str(e):
                    raise
                chosen = None
                for d in (['E','W','N','S'] if side in ('W','E') else ['N','S','E','W']):
                    if d == primary:
                        continue
                    try:
                        start_cell, created = self._add_or_merge_route4(cur[0], cur[1], out_dir=d, in_pin=side, upstream=edge_upstream)
                        if created:
                            cells.append(start_cell)
                        prev_src = {"type":"cell","x":cur[0],"y":cur[1],"out":pin_map[d]}
                        chosen = d
                        break
                    except RuntimeError:
                        continue
                if chosen is None:
                    raise
                last_dir = chosen
                chosen_dir = chosen

        # Compute first step one hop into grid along chosen_dir
        if 'chosen_dir' not in locals():
            chosen_dir = primary
        dd_first = {'N':(0,-1),'E':(1,0),'S':(0,1),'W':(-1,0)}[chosen_dir]
        first_step: Optional[Tuple[int,int]] = None
        nx0, ny0 = start[0] + dd_first[0], start[1] + dd_first[1]
        if 0 <= nx0 < self.W and 0 <= ny0 < self.H and (nx0, ny0) != dst_cell:
            first_step = (nx0, ny0)

        # Build detours starting from first_step (or start if not valid)
        detours: List[Tuple[int,int]] = []
        base = first_step if first_step is not None else start
        cur_det = base
        if extra_hops > 0:
            perp = [(0,-1),(0,1)] if side in ('W','E') else [(1,0),(-1,0)]
            added = 0
            while added < int(extra_hops):
                placed = False
                for dxp, dyp in perp:
                    nxp, nyp = cur_det[0] + dxp, cur_det[1] + dyp
                    if 0 <= nxp < self.W and 0 <= nyp < self.H and self.is_free(nxp, nyp) and (nxp, nyp) != dst_cell:
                        detours.append((nxp, nyp))
                        cur_det = (nxp, nyp)
                        placed = True
                        added += 1
                        break
                if not placed:
                    break

        # Per-edge fanout stride along chosen_dir from end of detours
        k = int(self._edge_fanout_index.get((side, int(pos)), 0))
        if k > 0:
            dd = {'N':(0,-1),'E':(1,0),'S':(0,1),'W':(-1,0)}[chosen_dir]
            cx, cy = cur_det
            for _ in range(k):
                nx, ny = cx + dd[0], cy + dd[1]
                if 0 <= nx < self.W and 0 <= ny < self.H and (nx, ny) != dst_cell:
                    detours.append((nx, ny))
                    cx, cy = nx, ny
                else:
                    break
            cur_det = (cx, cy)

        # Route from last detour (or first_step/base) to dst
        start_for_core = cur_det
        try:
            core = self.route(start_for_core, dst_cell, avoid_moves=avoid_moves)
        except RuntimeError:
            # Retry without avoid rules
            try:
                core = self.route(start_for_core, dst_cell, avoid_moves=None)
            except RuntimeError:
                # Try from first_step directly if available
                alt_start = first_step if first_step is not None else start_for_core
                try:
                    core = self.route(alt_start, dst_cell, avoid_moves=None)
                except RuntimeError:
                    # Last resort: try from start with no detours
                    core = self.route(start, dst_cell, avoid_moves=None)

        # Build hop list excluding final step into dst
        hops: List[Tuple[int,int]] = []
        if first_step is not None:
            hops.append(first_step)
        hops.extend(detours)
        if core:
            hops.extend(core[:-1])
        hop_count = len(hops)

        # Determine the direction from the last hop cell into the destination
        if core and len(core) >= 1:
            last_cell_for_core = hops[-1] if hops else start
            # dir from last route cell to dst (core[-1] is dst)
            ddx = core[-1][0] - last_cell_for_core[0]
            ddy = core[-1][1] - last_cell_for_core[1]
            dir_to_dst = dir_from_delta(ddx, ddy) if (ddx != 0 or ddy != 0) else last_dir
        else:
            dir_to_dst = last_dir

        hop_count = 0
        idx = 0
        while idx < len(hops):
            hop = hops[idx]
            # incoming direction: from cur to hop
            dx_in = hop[0] - cur[0]
            dy_in = hop[1] - cur[1]
            in_dir = dir_from_delta(dx_in, dy_in)
            # outgoing direction: to next hop or toward dst
            if idx + 1 < len(hops):
                nx, ny = hops[idx+1]
                dx_out = nx - hop[0]
                dy_out = ny - hop[1]
                out_dir = dir_from_delta(dx_out, dy_out)
            else:
                # Final hop points towards the destination
                if core and len(core) >= 1:
                    last_cell_for_core = hop if hop is not None else cur
                    ddx = core[-1][0] - last_cell_for_core[0]
                    ddy = core[-1][1] - last_cell_for_core[1]
                    out_dir = dir_from_delta(ddx, ddy) if (ddx != 0 or ddy != 0) else last_dir
                else:
                    out_dir = last_dir
            x, y = hop
            opposite = {'E':'W','W':'E','N':'S','S':'N'}[in_dir]
            try:
                cell, created = self._add_or_merge_route4(x, y, out_dir=out_dir, in_pin=opposite, upstream=prev_src)
                if created:
                    cells.append(cell)
                prev_src = {"type":"cell","x":x,"y":y,"out":pin_map[out_dir]}
                last_dir = out_dir
                cur = hop
                hop_count += 1
                idx += 1
            except RuntimeError as e:
                if 'already' not in str(e):
                    raise
                # Avoid using this out direction at this cell and recompute the remainder route
                avoid_moves.add((x, y, out_dir))
                try:
                    new_core = self.route(cur, dst_cell, avoid_moves=avoid_moves)
                except RuntimeError:
                    try:
                        new_core = self.route(cur, dst_cell, avoid_moves=None)
                    except RuntimeError:
                        # Give up
                        raise
                # Rebuild hops from current position
                hops = new_core[:-1] if new_core else []
                idx = 0

        # Success; bump fanout index for this edge lane
        self._edge_fanout_index[(side, int(pos))] = k + 1
        return cells, last_dir, cur, hop_count

    def wire_to_edge_from(self, src_cell: Tuple[int,int], side: str, pos: int, src_out: int = 0, extra_hops: int = 0) -> List[Cell]:
        """Route from a source cell to a physical edge location. Returns created/merged ROUTE4 cells.
        The final cell at the edge drives its out_dir equal to the edge side from the opposite pin.
        Optional extra_hops adds detours before reaching the edge to increase path length for alignment.
        """
        if side == 'W':
            target = (0, pos)
        elif side == 'E':
            target = (self.W - 1, pos)
        elif side == 'N':
            target = (pos, 0)
        elif side == 'S':
            target = (pos, self.H - 1)
        else:
            raise ValueError('Invalid side; expected one of N,E,S,W')

        # Optional pre-hops detours perpendicular to the edge direction to lengthen the path
        pre_hops: List[Tuple[int,int]] = []
        if extra_hops > 0:
            # Choose detour directions perpendicular to the main heading towards the edge
            if side in ('W','E'):
                candidates = [(0,-1), (0,1)]  # N, S
            else:
                candidates = [(1,0), (-1,0)]  # E, W
            cur_det = src_cell
            added = 0
            while added < int(extra_hops):
                placed = False
                for dx, dy in candidates:
                    nx, ny = cur_det[0] + dx, cur_det[1] + dy
                    if 0 <= nx < self.W and 0 <= ny < self.H and self.is_free(nx, ny):
                        pre_hops.append((nx, ny))
                        cur_det = (nx, ny)
                        placed = True
                        added += 1
                        break
                if not placed:
                    break

        # Route from the last detour (or src) to the target edge cell
        start_for_route = pre_hops[-1] if pre_hops else src_cell
        core_path = self.route(start_for_route, target)
        path: List[Tuple[int,int]] = (pre_hops + core_path) if pre_hops else core_path

        cells: List[Cell] = []
        cur = src_cell
        pin_map = {'N':0,'E':1,'S':2,'W':3}
        prev_src = {"type":"cell","x":src_cell[0],"y":src_cell[1],"out":int(src_out)}
        for i, nxt in enumerate(path):
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
            # For intermediate hops, pass-through toward next cell.
            # For the last hop (edge cell), set out_dir to the edge side to expose on boundary.
            if i == len(path) - 1:
                out_dir = side
                in_pin = {'E':'W','W':'E','N':'S','S':'N'}[side]
            else:
                out_dir = direction
                in_pin = {'E':'W','W':'E','N':'S','S':'N'}[direction]
            cell, created = self._add_or_merge_route4(x, y, out_dir=out_dir, in_pin=in_pin, upstream=prev_src)
            if created:
                cells.append(cell)
            prev_src = {"type":"cell","x":x,"y":y,"out":pin_map[out_dir]}
            cur = nxt
        return cells

    def wire_edge_to_edge(self, side_src: str, pos_src: int, side_dst: str, pos_dst: int, extra_hops: int = 0) -> Tuple[List[Cell], int]:
        """Route directly from one physical edge location to another.
        Returns (created/merged ROUTE4 cells, hop_count). hop_count is number of inter-cell hops.
        """
        # Determine starting in-grid coordinate adjacent to source edge and initial out direction
        if side_src == 'W':
            start = (0, pos_src)
            out_dir_first = 'E'
        elif side_src == 'E':
            start = (self.W - 1, pos_src)
            out_dir_first = 'W'
        elif side_src == 'N':
            start = (pos_src, 0)
            out_dir_first = 'S'
        elif side_src == 'S':
            start = (pos_src, self.H - 1)
            out_dir_first = 'N'
        else:
            raise ValueError('Invalid side_src')

        # Determine destination edge target cell
        if side_dst == 'W':
            target = (0, pos_dst)
        elif side_dst == 'E':
            target = (self.W - 1, pos_dst)
        elif side_dst == 'N':
            target = (pos_dst, 0)
        elif side_dst == 'S':
            target = (pos_dst, self.H - 1)
        else:
            raise ValueError('Invalid side_dst')

        # Optional detours to lengthen path
        pre_hops: List[Tuple[int,int]] = []
        if extra_hops > 0:
            if side_src in ('W','E'):
                candidates = [(0,-1), (0,1)]
            else:
                candidates = [(1,0), (-1,0)]
            cur_det = start
            added = 0
            while added < int(extra_hops):
                placed = False
                for dx, dy in candidates:
                    nx, ny = cur_det[0] + dx, cur_det[1] + dy
                    if 0 <= nx < self.W and 0 <= ny < self.H and self.is_free(nx, ny) and (nx, ny) != target:
                        pre_hops.append((nx, ny))
                        cur_det = (nx, ny)
                        placed = True
                        added += 1
                        break
                if not placed:
                    break

        # Compute core route
        start_for_route = pre_hops[-1] if pre_hops else start
        core_path = self.route(start_for_route, target)
        path: List[Tuple[int,int]] = (pre_hops + core_path) if pre_hops else core_path

        cells: List[Cell] = []
        cur = start
        pin_map = {'N':0,'E':1,'S':2,'W':3}
        edge_upstream = {"type":"edge","side":side_src,"index":int(pos_src)}

        # Create or reuse initial mapping at start cell from the edge pin to first direction
        start_cell, created = self._add_or_merge_route4(cur[0], cur[1], out_dir=out_dir_first, in_pin=side_src, upstream=edge_upstream)
        if created:
            cells.append(start_cell)
        prev_src = {"type":"cell","x":cur[0],"y":cur[1],"out":pin_map[out_dir_first]}

        # Walk the path; final hop exposes to destination edge
        for i, nxt in enumerate(path):
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
            if i == len(path) - 1:
                out_dir = side_dst
                in_pin = {'E':'W','W':'E','N':'S','S':'N'}[side_dst]
            else:
                out_dir = direction
                in_pin = {'E':'W','W':'E','N':'S','S':'N'}[direction]
            cell, created = self._add_or_merge_route4(x, y, out_dir=out_dir, in_pin=in_pin, upstream=prev_src)
            if created:
                cells.append(cell)
            prev_src = {"type":"cell","x":x,"y":y,"out":pin_map[out_dir]}
            cur = nxt

        return cells, len(path)


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
