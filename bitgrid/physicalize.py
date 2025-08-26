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
    router = ManhattanRouter(prog.width, prog.height)
    for c in prog.cells:
        router.occupy(c.x, c.y)

    new_cells: List[Cell] = []
    pin_map = {'N':0,'E':1,'S':2,'W':3}

    # Drive inputs: for each sink cell input that references an input bit, route from edge
    for sink in prog.cells:
        sx, sy = sink.x, sink.y
        for i, src in enumerate(sink.inputs):
            if src.get('type') != 'input':
                continue
            bit = int(src.get('bit', 0))
            name = src.get('name') or ''
            side = (input_side_map.get(name) if input_side_map else None) or input_side
            # If this input pin faces a physical edge and the sink is on that edge, skip routing and rely on edge injection
            pin_side = {0:'N',1:'E',2:'S',3:'W'}.get(i, 'N')
            if (pin_side == 'W' and sx == 0) or (pin_side == 'E' and sx == prog.width - 1) \
               or (pin_side == 'N' and sy == 0) or (pin_side == 'S' and sy == prog.height - 1):
                continue
            # Optional: parity alignment by adding extra hops if starting parity doesn't match sink-1 hop parity
            extra = 0
            if align_parity:
                # Starting at edge-adjacent cell has parity p0 = (start_x + start_y) % 2
                if side == 'W':
                    start = (0, bit)
                elif side == 'E':
                    start = (prog.width - 1, bit)
                elif side == 'N':
                    start = (bit, 0)
                else:
                    start = (bit, prog.height - 1)
                p0 = (start[0] + start[1]) & 1
                # We stop adjacent to sink: last_xy must have opposite parity to sink
                # If the path length from start to (sink neighbor) doesn't have right parity, add one detour hop
                psink = (sx + sy) & 1
                # For an even-length hop list, parity stays p0; for odd-length, flips
                # We want final neighbor cell parity != psink.
                # If p0 == psink, we need an odd number of hops; else even. We only control pre-hops minimally.
                needs_odd = (p0 == psink)
                extra = 1 if needs_odd else 0
            # Route from edge (input_side, pos=bit) to neighbor of sink
            cells, last_dir, last_xy, _hopc = router.wire_from_edge_to(side, bit, (sx, sy), extra_hops=extra)
            new_cells.extend(cells)
            sink.inputs[i] = {"type":"cell","x":last_xy[0],"y":last_xy[1],"out":pin_map[last_dir]}

    # Expose outputs: for each output bit mapping, route to the designated edge (per-bus or default).
    # Assign unique positions along each chosen edge across all output buses to avoid collisions.
    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
    # Flatten outputs to stable list with chosen side per bit
    flat_outputs: List[Tuple[str,int,dict,str]] = []
    for name, bits in prog.output_bits.items():
        for b_idx, bsrc in enumerate(bits):
            side_for_bit = (output_side_map.get(name) if output_side_map else None) or output_side
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
        on_edge = (side_for_bit == 'W' and sx == 0) or (side_for_bit == 'E' and sx == prog.width - 1) \
                  or (side_for_bit == 'N' and sy == 0) or (side_for_bit == 'S' and sy == prog.height - 1)
        # If it's on the edge AND the output pin already faces that edge AND it's already at the desired position, skip routing
        desired_pos_matches = ((side_for_bit in ('W','E') and sy == pos_out) or (side_for_bit in ('N','S') and sx == pos_out))
        if on_edge and sout == dir_to_idx[side_for_bit] and desired_pos_matches:
            continue
    # Otherwise, route to expose this output bit at the correct edge and position
    extra = (output_extra_hops or {}).get(name, 0)
    cells = router.wire_to_edge_from((sx, sy), side_for_bit, pos_out, src_out=sout, extra_hops=int(extra))
    new_cells.extend(cells)

    return Program(width=prog.width, height=prog.height, cells=prog.cells + new_cells,
                   input_bits=prog.input_bits, output_bits=prog.output_bits, latency=prog.latency)
