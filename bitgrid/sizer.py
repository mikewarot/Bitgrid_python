from __future__ import annotations

from typing import Dict
from .graph import Graph


def size_graph(g: Graph) -> Dict[str, int]:
    """Estimate grid requirements from Graph without routing/mapping.

    Returns dict with:
      - nodes: count of mapped nodes (excludes INPUT/CONST/OUTPUT)
      - cols: columns required (one per mapped node)
      - height_bits: max bit-width across mapped nodes (proxy for grid height)
      - cells: total LUT cells ~= sum of bit-widths across mapped nodes
    """
    mapped_ops = {'AND','OR','XOR','NOT','SHL','SHR','SAR','ADD','BIT'}
    cols = 0
    cells = 0
    height = 0
    for nid, n in g.nodes.items():
        if n.op in ('INPUT','CONST','OUTPUT'):
            continue
        if n.op not in mapped_ops:
            # Treat unknowns as mapped once with n.width bits
            pass
        cols += 1
        w = max(1, int(n.width))
        cells += w
        if w > height:
            height = w
    return {
        'nodes': cols,
        'cols': cols,
        'height_bits': height,
        'cells': cells,
    }
