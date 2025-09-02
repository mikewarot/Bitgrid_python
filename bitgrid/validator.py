from __future__ import annotations

from typing import List, Tuple, Dict, Optional
from .program import Program, Cell
from .lut_only import LUTGrid


def _dir_from_delta(dx: int, dy: int) -> str:
    if dx == 1:
        return 'E'
    if dx == -1:
        return 'W'
    if dy == 1:
        return 'S'
    if dy == -1:
        return 'N'
    raise ValueError('Non-adjacent delta')


def validate_program_connectivity(prog: Program) -> List[str]:
    """
    Validate structural connectivity for cell->cell links:
      - Every cell-referenced input must be geometrically adjacent to the sink.
      - The referenced source out index must match the direction from source to sink.
      - If the source is a ROUTE4 cell, it must actually drive that out pin (non-zero LUT).
    Returns a list of human-readable issue strings; empty means pass.
    """
    issues: List[str] = []
    cells_by_xy: Dict[Tuple[int, int], Cell] = {(c.x, c.y): c for c in prog.cells}
    dir_to_idx = {'N': 0, 'E': 1, 'S': 2, 'W': 3}

    for sink in prog.cells:
        sx, sy = sink.x, sink.y
        for i, src in enumerate(sink.inputs):
            if src.get('type') != 'cell':
                continue
            if 'x' not in src or 'y' not in src:
                issues.append(f"Cell({sx},{sy}) input[{i}] references cell without coordinates: {src}")
                continue
            try:
                tx, ty = int(src['x']), int(src['y'])
                tout = int(src.get('out', 0))
            except Exception:
                issues.append(f"Cell({sx},{sy}) input[{i}] has invalid source format: {src}")
                continue

            dx, dy = sx - tx, sy - ty
            manh = abs(dx) + abs(dy)
            if manh != 1:
                issues.append(f"Cell({sx},{sy}) input[{i}] source Cell({tx},{ty}) is not adjacent (|dx|+|dy|={manh})")
                continue
            try:
                dname = _dir_from_delta(dx, dy)  # direction from source to sink
            except ValueError:
                issues.append(f"Cell({sx},{sy}) input[{i}] source Cell({tx},{ty}) has non-adjacent delta ({dx},{dy})")
                continue
            expected_out = dir_to_idx[dname]
            if tout != expected_out:
                issues.append(
                    f"Cell({sx},{sy}) input[{i}] expects source out={expected_out} ({dname}) but found out={tout}"
                )

            scell = cells_by_xy.get((tx, ty))
            if scell is None:
                issues.append(f"Cell({sx},{sy}) input[{i}] references missing Cell({tx},{ty})")
                continue
            if scell.op == 'ROUTE4':
                luts = [int(v) for v in scell.params.get('luts', [0, 0, 0, 0])]
                if tout < 0 or tout > 3 or luts[tout] == 0:
                    issues.append(
                        f"Cell({sx},{sy}) input[{i}] expects ROUTE4 at ({tx},{ty}) to drive out[{tout}] but LUT is empty"
                    )

    return issues


# ---- LUTGrid connectivity checks (edge-to-edge) ----

_VAR_MASKS = {
    # idx = N | (E<<1) | (S<<2) | (W<<3)
    # Bit patterns by variable:
    #  N: 0xAAAA (0101 repeating from LSB)
    #  E: 0xCCCC (0011 repeating from LSB)
    #  S: 0xF0F0 (00001111 repeating)
    #  W: 0xFF00 (lower 8 zeros, upper 8 ones)
    'N': 0xAAAA,
    'E': 0xCCCC,
    'S': 0xF0F0,
    'W': 0xFF00,
}

_IDX_TO_DIR = {0: 'N', 1: 'E', 2: 'S', 3: 'W'}
_DIR_TO_IDX = {'N': 0, 'E': 1, 'S': 2, 'W': 3}
_OPPOSITE = {'N': 'S', 'E': 'W', 'S': 'N', 'W': 'E'}
_DELTA = {'N': (0, -1), 'E': (1, 0), 'S': (0, 1), 'W': (-1, 0)}


def _decode_var(lut_val: int) -> Optional[str]:
    for k, v in _VAR_MASKS.items():
        if int(lut_val) == int(v):
            return k
    return None


def _edge_of(x: int, y: int, W: int, H: int) -> Optional[str]:
    if x == 0:
        return 'W'
    if x == W - 1:
        return 'E'
    if y == 0:
        return 'N'
    if y == H - 1:
        return 'S'
    return None


def validate_lutgrid_connectivity(grid: LUTGrid) -> List[str]:
    """
    Validate that edge-ingress mappings form continuous paths that eventually reach an edge egress.
    Heuristic rules (for routing-only grids):
      - For each edge cell where an output maps from the edge-facing input pin, treat it as a path start.
      - From a cell and its inbound pin, find an output whose LUT equals that inbound pin variable; move to neighbor in that out direction.
      - Succeed if we reach a cell where an output maps to the boundary side (egress) using the current inbound pin.
      - Report broken if no matching out is found or we step out of bounds; guard against cycles with a visited set.
    Returns list of issues; empty means all detected ingress lanes reach an edge egress.
    """
    W, H = grid.W, grid.H
    # Precompute per-cell out mappings: list of (out_dir, in_pin) pairs
    mappings: Dict[Tuple[int, int], List[Tuple[str, str]]] = {}
    for y in range(H):
        for x in range(W):
            c = grid.cells[y][x]
            mm: List[Tuple[str, str]] = []
            for oi in range(4):
                out_dir = _IDX_TO_DIR[oi]
                inv = _decode_var(int(c.luts[oi]))
                if inv is not None:
                    mm.append((out_dir, inv))
            if mm:
                mappings[(x, y)] = mm

    issues: List[str] = []

    # Find ingress starts at edges
    starts: List[Tuple[int, int, str]] = []  # (x, y, inbound_pin)
    for (x, y), mm in mappings.items():
        edge = _edge_of(x, y, W, H)
        if not edge:
            continue
        # If any mapping consumes the edge-facing pin, it's an ingress
        for out_dir, in_pin in mm:
            if in_pin == edge:
                starts.append((x, y, edge))
                break

    # Trace each ingress
    for sx, sy, inbound in starts:
        # Step until we find an egress or error
        x, y = sx, sy
        current_in = inbound
        visited: set[Tuple[int, int, str]] = set()
        step_count = 0
        ok = False
        while True:
            state = (x, y, current_in)
            if state in visited:
                issues.append(f"Cycle detected starting at edge {inbound}@({sx},{sy}) around cell ({x},{y}) inbound {current_in}")
                break
            visited.add(state)
            mm = mappings.get((x, y), [])
            # Find an out that maps from current_in
            next_out: Optional[str] = None
            for od, ip in mm:
                if ip == current_in:
                    next_out = od
                    break
            if next_out is None:
                issues.append(f"Broken path from edge {inbound}@({sx},{sy}): cell ({x},{y}) has no out driven by inbound {current_in}")
                break
            # If next_out points to boundary side and we're at boundary, success (egress)
            edge_here = _edge_of(x, y, W, H)
            if edge_here and next_out == edge_here:
                ok = True
                break
            # Step to neighbor
            dx, dy = _DELTA[next_out]
            nx, ny = x + dx, y + dy
            if not (0 <= nx < W and 0 <= ny < H):
                issues.append(f"Broken path from edge {inbound}@({sx},{sy}): stepping out of bounds from ({x},{y}) via {next_out}")
                break
            x, y = nx, ny
            current_in = _OPPOSITE[next_out]
            step_count += 1
            if step_count > (W * H * 2):
                issues.append(f"Path from edge {inbound}@({sx},{sy}) exceeded step budget; possible loop or very long path")
                break

        if not ok:
            # Issue already recorded; continue
            continue

    return issues

