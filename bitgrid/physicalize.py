from __future__ import annotations

from typing import Dict, List, Tuple

from .program import Program, Cell
from .router import ManhattanRouter


def physicalize_to_edges(prog: Program, input_side: str = 'W', output_side: str = 'E', input_side_map: Dict[str, str] | None = None, output_side_map: Dict[str, str] | None = None, output_extra_hops: Dict[str, int] | None = None, align_parity: bool = True) -> Program:
    """Convert a logical Program into a neighbor-only, edge-driven Program.
    - All Program inputs are assumed to be driven from a single physical edge (input_side).
    - All Program outputs are assumed to be sampled at a single physical edge (output_side).
    - For each input bit source chain, route from the edge position to the sink cell adjacency and
      replace the sink input with the last ROUTE4 hop output.
    - For each output bit, route from its source cell out to the edge; this exposes it at the border.
    Returns a new Program with ROUTE4 cells appended. The cell LUTs remain as in the original, and
    the new ROUTE4 cells are added with appropriate params['luts'].
    Note: This assumes each logical input/output maps to a position index along the chosen edge.
    Index is taken from the bit index in the bus order.
    """
    # Determine per-bus side for inputs/outputs to size edges
    side_for_input: Dict[str, str] = {}
    for name in prog.input_bits.keys():
        side_for_input[name] = ((input_side_map.get(name) if input_side_map else None) or input_side).upper()
    side_for_output: Dict[str, str] = {}
    for name in prog.output_bits.keys():
        side_for_output[name] = ((output_side_map.get(name) if output_side_map else None) or output_side).upper()

    # Count required positions per side (sum across buses sharing a side)
    need_by_side = {'N': 0, 'E': 0, 'S': 0, 'W': 0}
    for name, bits in prog.input_bits.items():
        s = side_for_input[name]
        need_by_side[s] += len(bits)
    for name, bits in prog.output_bits.items():
        s = side_for_output[name]
        need_by_side[s] += len(bits)

    # Base dimensions, then grow to fit edge position counts
    baseW, baseH = prog.width, prog.height
    reqH = max(baseH, need_by_side['W'], need_by_side['E'])
    reqW = max(baseW, need_by_side['N'], need_by_side['S'])
    # Ensure even dimensions for routing; pad width/height if needed
    W = reqW if (reqW % 2 == 0) else (reqW + 1)
    H = reqH if (reqH % 2 == 0) else (reqH + 1)
    router = ManhattanRouter(W, H)
    for c in prog.cells:
        router.occupy(c.x, c.y)

    new_cells: List[Cell] = []
    pin_map = {'N':0,'E':1,'S':2,'W':3}

    # Pre-assign unique input positions per chosen side: (name, bit) -> (side, pos)
    in_pos: Dict[Tuple[str,int], Tuple[str,int]] = {}
    next_pos_by_side_in: Dict[str, int] = {'N': 0, 'E': 0, 'S': 0, 'W': 0}
    for name, bits in prog.input_bits.items():
        side_for_bus = side_for_input[name]
        side_for_bus = side_for_bus.upper()
        for b_idx, _ in enumerate(bits):
            pos = next_pos_by_side_in[side_for_bus]
            in_pos[(name, b_idx)] = (side_for_bus, pos)
            next_pos_by_side_in[side_for_bus] += 1

    # Drive inputs: for each sink cell input that references an input bit, route from its assigned edge/pos
    for sink in prog.cells:
        sx, sy = sink.x, sink.y
        for i, src in enumerate(sink.inputs):
            if src.get('type') != 'input':
                continue
            bit = int(src.get('bit', 0))
            name = src.get('name') or ''
            side_fallback = (input_side_map.get(name) if input_side_map else input_side)
            side, pos = in_pos.get((name, bit), (side_fallback, bit))
            side = (side or input_side).upper()
            # Only skip routing if the sink pin faces the same edge we're driving this input from
            # AND the sink cell sits at the matching edge position (so edge injection reaches that pin).
            pin_side = {0:'N',1:'E',2:'S',3:'W'}.get(i, 'N')
            on_edge = (pin_side == 'W' and sx == 0) or (pin_side == 'E' and sx == W - 1) \
                      or (pin_side == 'N' and sy == 0) or (pin_side == 'S' and sy == H - 1)
            desired_pos_matches = ((pin_side in ('W','E') and sy == pos) or (pin_side in ('N','S') and sx == pos))
            if on_edge and (pin_side == side) and desired_pos_matches:
                continue
            # Optional: parity alignment by adding extra hops if starting parity doesn't match sink-1 hop parity
            extra = 0
            if align_parity:
                # Starting at edge-adjacent cell has parity p0 = (start_x + start_y) % 2
                if side == 'W':
                    start = (0, pos)
                elif side == 'E':
                    start = (W - 1, pos)
                elif side == 'N':
                    start = (pos, 0)
                else:
                    start = (pos, H - 1)
                p0 = (start[0] + start[1]) & 1
                # We stop adjacent to sink: last_xy must have opposite parity to sink
                # If the path length from start to (sink neighbor) doesn't have right parity, add one detour hop
                psink = (sx + sy) & 1
                # For an even-length hop list, parity stays p0; for odd-length, flips
                # We want final neighbor cell parity != psink.
                # If p0 == psink, we need an odd number of hops; else even. We only control pre-hops minimally.
                needs_odd = (p0 == psink)
                extra = 1 if needs_odd else 0
            # Route from edge (input_side, pos) to a neighbor of sink (generic)
            cells, last_dir, last_xy, _hopc = router.wire_from_edge_to(side, pos, (sx, sy), extra_hops=extra)
            # Ensure we land on the specific neighbor that matches this pin index i (0:N,1:E,2:S,3:W)
            pin_to_delta = {0:(0,-1), 1:(1,0), 2:(0,1), 3:(-1,0)}
            dx, dy = pin_to_delta.get(i, (0,-1))
            desired = (sx + dx, sy + dy)
            # Only if inside grid and not already at desired
            if 0 <= desired[0] < W and 0 <= desired[1] < H and (last_xy != desired):
                add_cells, _last = router.wire_with_route4(last_xy, desired)
                cells.extend(add_cells)
                # Now the direction from desired neighbor to sink is opposite of pin side
                last_dir = {0:'S', 1:'W', 2:'N', 3:'E'}[i]
                last_xy = desired
            new_cells.extend(cells)
            sink.inputs[i] = {"type":"cell","x":last_xy[0],"y":last_xy[1],"out":pin_map[last_dir]}

    # Expose outputs: for each output bit mapping, route to the designated edge (per-bus or default).
    # Assign unique positions along each chosen edge across all output buses to avoid collisions.
    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
    # Flatten outputs to stable list with chosen side per bit
    flat_outputs: List[Tuple[str,int,dict,str]] = []
    for name, bits in prog.output_bits.items():
        for b_idx, bsrc in enumerate(bits):
            side_for_bit = side_for_output[name]
            flat_outputs.append((name, b_idx, bsrc, side_for_bit))
    # Assign positions per edge incrementally
    pos_by_key: Dict[Tuple[str,int], int] = {}
    next_pos_by_side: Dict[str, int] = {'N': 0, 'E': 0, 'S': 0, 'W': 0}
    for name, b_idx, _bsrc, side_for_bit in flat_outputs:
        pos_by_key[(name, b_idx)] = next_pos_by_side[side_for_bit]
        next_pos_by_side[side_for_bit] += 1
    # Now route each output to its assigned position and edge
    for name, b_idx, bsrc, side_for_bit in flat_outputs:
        if bsrc.get('type') != 'cell':
            # If it's a pass-through of an input or const, skip; edge will be driven by earlier routing
            continue
        sx, sy = int(bsrc['x']), int(bsrc['y'])
        sout = int(bsrc.get('out', 0))
        pos_out = pos_by_key[(name, b_idx)]
        # Determine if the source cell already sits on the chosen edge
        on_edge = (side_for_bit == 'W' and sx == 0) or (side_for_bit == 'E' and sx == W - 1) \
                  or (side_for_bit == 'N' and sy == 0) or (side_for_bit == 'S' and sy == H - 1)
        # If it's on the edge AND the output pin already faces that edge AND it's already at the desired position, skip routing
        desired_pos_matches = ((side_for_bit in ('W','E') and sy == pos_out) or (side_for_bit in ('N','S') and sx == pos_out))
        if on_edge and sout == dir_to_idx[side_for_bit] and desired_pos_matches:
            continue
        # Otherwise, route to expose this output bit at the correct edge and position
        extra = (output_extra_hops or {}).get(name, 0)
        cells = router.wire_to_edge_from((sx, sy), side_for_bit, pos_out, src_out=sout, extra_hops=int(extra))
        new_cells.extend(cells)

    return Program(width=W, height=H, cells=prog.cells + new_cells,
                   input_bits=prog.input_bits, output_bits=prog.output_bits, latency=prog.latency)
