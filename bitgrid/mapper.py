from __future__ import annotations

from typing import Dict, List, Tuple
from .graph import Graph, Node
from .program import Program, Cell


# Simple mapping strategy:
# - Allocate columns per logical node (bit-sliced), rows per bit index
# - Binary ops: one cell per bit does op on input bits
# - ADD: ripple-carry vertically using ADD_BIT cells with carry-in/out
# Constraints: 4-input per cell; we use at most A, B, and carry-in (3 inputs)

class Mapper:
    def __init__(self, grid_width: int = 64, grid_height: int = 64):
        self.W = grid_width
        self.H = grid_height

    def map(self, g: Graph) -> Program:
        topo = self._topo_order(g)
        col = 0
        cells: List[Cell] = []
        bit_sources: Dict[str, List[Dict]] = {}  # node_id -> per-bit source descriptor

        # Place inputs on column 0 as pseudo-sources
        for name, sig in g.inputs.items():
            bit_sources[name] = [{"type": "input", "name": name, "bit": b} for b in range(sig.width)]

        col = 1
        for nid in topo:
            node = g.nodes[nid]
            if node.op in ('INPUT',):
                continue
            if node.op == 'CONST':
                bits = [(node.params['value'] >> b) & 1 for b in range(node.width)]
                bit_sources[nid] = [{"type": "const", "value": bits[b]} for b in range(node.width)]
                continue
            if node.op == 'OUTPUT':
                src = node.inputs[0]
                bit_sources[nid] = bit_sources[src][:g.outputs[nid].width]
                continue

            # place a column for this node
            if col >= self.W:
                raise RuntimeError('Grid too narrow for mapping')

            if node.op in ('AND','OR','XOR','NOT','SHL','SHR'):
                ins = [bit_sources[node.inputs[0]]]
                if node.op != 'NOT':
                    ins.append(bit_sources[node.inputs[1]])
                width = node.width
                node_bits: List[Dict] = []
                for b in range(width):
                    # Apply shift to left operand for SHL/SHR
                    a_shift = 0
                    if node.op in ('SHL','SHR'):
                        amount = node.params.get('amount', 0)
                        a_shift = -amount if node.op == 'SHL' else amount
                    a_src = self._shifted(ins[0], b, a_shift, width, node)
                    b_src = None
                    if node.op != 'NOT' and len(ins) > 1:
                        # For non-shift ops, use right operand as-is
                        if node.op not in ('SHL','SHR'):
                            b_src = self._shifted(ins[1], b, 0, width, node)
                    x, y = col, b
                    in_list = [a_src, b_src or {"type": "const", "value": 0}, {"type": "const", "value": 0}, {"type": "const", "value": 0}]
                    op = 'BUF'
                    if node.op == 'NOT':
                        op = 'NOT'
                    elif node.op == 'AND':
                        op = 'AND'
                    elif node.op == 'OR':
                        op = 'OR'
                    elif node.op == 'XOR':
                        op = 'XOR'
                    elif node.op in ('SHL','SHR'):
                        # already applied shift to a_src
                        op = 'BUF'
                        in_list[0] = a_src
                    cell = Cell(x=x, y=y, inputs=in_list, op=op, params={})
                    cells.append(cell)
                    node_bits.append({"type": "cell", "x": x, "y": y, "out": 0})
                bit_sources[nid] = node_bits
                col += 1
                continue

            if node.op == 'ADD':
                width = node.width
                a_bits = bit_sources[node.inputs[0]]
                b_bits = bit_sources[node.inputs[1]]
                carry_in = {"type": "const", "value": 0}
                node_bits: List[Dict] = []
                for b in range(width):
                    a_src = self._shifted(a_bits, b, 0, width, node)
                    b_src = self._shifted(b_bits, b, 0, width, node)
                    x, y = col, b
                    in_list = [a_src, b_src, carry_in, {"type": "const", "value": 0}]
                    cell = Cell(x=x, y=y, inputs=in_list, op='ADD_BIT', params={})
                    cells.append(cell)
                    sum_src = {"type": "cell", "x": x, "y": y, "out": 0}
                    carry_out = {"type": "cell", "x": x, "y": y, "out": 1}
                    node_bits.append(sum_src)
                    carry_in = carry_out
                bit_sources[nid] = node_bits
                col += 1
                continue

            raise RuntimeError(f'Unsupported op in mapping: {node.op}')

        width = max([c.x for c in cells], default=0) + 1
        height = max([c.y for c in cells], default=0) + 1

        # outputs mapping
        output_bits: Dict[str, List[Dict]] = {}
        for name, sig in g.outputs.items():
            src_bits = bit_sources[name]
            output_bits[name] = src_bits[:sig.width]

        # inputs mapping
        input_bits: Dict[str, List[Dict]] = {}
        for name, sig in g.inputs.items():
            input_bits[name] = [{"type": "input", "name": name, "bit": b} for b in range(sig.width)]

        # crude latency estimate: number of placed columns + height for add chains
        latency = width + height

        return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=latency)

    def _shifted(self, bits: List[Dict], idx: int, shift: int, width: int, node: Node) -> Dict:
        j = idx - shift
        if 0 <= j < len(bits):
            return bits[j]
        return {"type": "const", "value": 0}

    def _topo_order(self, g: Graph) -> List[str]:
        # Kahn's algorithm over node ids excluding inputs
        indeg = {nid: 0 for nid in g.nodes}
        for nid, n in g.nodes.items():
            for i in n.inputs:
                if i in indeg:
                    indeg[nid] += 1
        q = [nid for nid, d in indeg.items() if d == 0]
        order: List[str] = []
        while q:
            nid = q.pop(0)
            order.append(nid)
            for m_id, m in g.nodes.items():
                if nid in m.inputs:
                    indeg[m_id] -= 1
                    if indeg[m_id] == 0:
                        q.append(m_id)
        # Filter to ensure deterministic order and skip inputs at mapping loop
        return [nid for nid in order if g.nodes[nid].op not in ('INPUT',)]
