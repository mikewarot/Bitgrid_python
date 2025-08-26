from __future__ import annotations

from typing import Dict, List, Tuple

from .program import Program, Cell
from .router import ManhattanRouter


def physicalize_to_edges(prog: Program, input_side: str = 'W', output_side: str = 'E', input_side_map: Dict[str, str] | None = None) -> Program:
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
            # Route from edge (input_side, pos=bit) to neighbor of sink
            cells, last_dir, last_xy = router.wire_from_edge_to(side, bit, (sx, sy))
            new_cells.extend(cells)
            sink.inputs[i] = {"type":"cell","x":last_xy[0],"y":last_xy[1],"out":pin_map[last_dir]}

    # Expose outputs: for each output bit mapping, route to edge
    # Assumes each output bit ultimately references a cell output.
    for name, bits in prog.output_bits.items():
        for b_idx, bsrc in enumerate(bits):
            if bsrc.get('type') != 'cell':
                # If it's a pass-through of an input or const, skip; edge will be driven by earlier routing
                continue
            sx, sy = int(bsrc['x']), int(bsrc['y'])
            sout = int(bsrc.get('out', 0))
            cells = router.wire_to_edge_from((sx, sy), output_side, b_idx, src_out=sout)
            new_cells.extend(cells)

    return Program(width=prog.width, height=prog.height, cells=prog.cells + new_cells,
                   input_bits=prog.input_bits, output_bits=prog.output_bits, latency=prog.latency)
