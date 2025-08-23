from __future__ import annotations

from typing import Dict, List, Tuple, Any
from .program import Program, Cell


class Emulator:
    def __init__(self, program: Program):
        self.p = program
        # State per cell: outputs list of 4 bits
        self.cell_out: Dict[Tuple[int,int], List[int]] = {}
        for c in self.p.cells:
            self.cell_out[(c.x, c.y)] = [0, 0, 0, 0]
        # Persistent cycle counter for streaming mode
        self._cycle = 0

    def _src_value(self, src: Dict[str, Any], inputs: Dict[str, int]) -> int:
        t = src.get('type')
        if t == 'const':
            return int(src.get('value', 0)) & 1
        if t == 'input':
            name = str(src.get('name'))
            bit = int(src.get('bit', 0))
            val = int(inputs.get(name, 0))
            return (val >> bit) & 1
        if t == 'cell':
            key = (int(src.get('x', 0)), int(src.get('y', 0)))
            out_idx = int(src.get('out', 0))
            return self.cell_out.get(key, [0,0,0,0])[out_idx] & 1
        return 0

    def _eval_cell(self, c: Cell, cur_inputs: Dict[str, int]) -> List[int]:
        # Gather up to 4 input bits (pad to 4 with zeros)
        in_bits = [self._src_value(c.inputs[i], cur_inputs) if i < len(c.inputs) else 0 for i in range(4)]
        idx = (in_bits[0] & 1) | ((in_bits[1] & 1) << 1) | ((in_bits[2] & 1) << 2) | ((in_bits[3] & 1) << 3)
        params = c.params or {}
        # Prefer LUT-based evaluation when provided: 'luts' (list of up to 4) or 'lut' (single)
        if 'luts' in params or 'lut' in params:
            lparam = params.get('luts', params.get('lut'))
            if isinstance(lparam, (list, tuple)):
                l0 = int(lparam[0]) if len(lparam) > 0 else 0
                l1 = int(lparam[1]) if len(lparam) > 1 else 0
                l2 = int(lparam[2]) if len(lparam) > 2 else 0
                l3 = int(lparam[3]) if len(lparam) > 3 else 0
                return [(l0 >> idx) & 1, (l1 >> idx) & 1, (l2 >> idx) & 1, (l3 >> idx) & 1]
            else:
                try:
                    lut = int(lparam) if lparam is not None else 0
                except Exception:
                    lut = 0
                return [(lut >> idx) & 1, 0, 0, 0]

        # Fallback to op-based logic for legacy cells without LUT params
        a, b, cin = in_bits[0], in_bits[1], in_bits[2]
        if c.op == 'BUF':
            return [a, 0, 0, 0]
        if c.op == 'NOT':
            return [1 - a, 0, 0, 0]
        if c.op == 'AND':
            return [a & b, 0, 0, 0]
        if c.op == 'OR':
            return [a | b, 0, 0, 0]
        if c.op == 'XOR':
            return [a ^ b, 0, 0, 0]
        if c.op == 'ADD_BIT':
            s = (a ^ b) ^ cin
            cout = (a & b) | (a & cin) | (b & cin)
            return [s & 1, cout & 1, 0, 0]
        if c.op == 'ROUTE4':
            # No LUTs provided: default zeros
            return [0, 0, 0, 0]
        return [0, 0, 0, 0]

    def run_vector(self, inputs: Dict[str, int]) -> Dict[str, int]:
        # two-phase stepping for p.latency cycles
        for cyc in range(self.p.latency):
            phase = 'A' if (cyc % 2 == 0) else 'B'
            for c in self.p.cells:
                is_even = ((c.x + c.y) % 2 == 0)
                if (phase == 'A' and not is_even) or (phase == 'B' and is_even):
                    continue
                outs = self._eval_cell(c, inputs)
                self.cell_out[(c.x, c.y)] = outs

        # Sample outputs
        outputs: Dict[str, int] = {}
        for name, bits in self.p.output_bits.items():
            val = 0
            for i, src in enumerate(bits):
                val |= (self._src_value(src, inputs) & 1) << i
            outputs[name] = val
        return outputs

    def run(self, vectors: List[Dict[str, int]]) -> List[Dict[str, int]]:
        results = []
        for vec in vectors:
            # clear state between vectors
            for k in self.cell_out.keys():
                self.cell_out[k] = [0,0,0,0]
            results.append(self.run_vector(vec))
        return results

    def run_stream(self, steps: List[Dict[str, int]], cycles_per_step: int = 1, reset: bool = True) -> List[Dict[str, int]]:
    # Stream mode: do not clear state between steps; apply inputs and advance cycles_per_step cycles each step

        if reset:
            for k in self.cell_out.keys():
                self.cell_out[k] = [0,0,0,0]
            self._cycle = 0

        outputs_over_time: List[Dict[str,int]] = []
        for step_inputs in steps:
            # advance cycles_per_step cycles with current inputs
            for _ in range(cycles_per_step):
                phase = 'A' if (self._cycle % 2 == 0) else 'B'
                for c in self.p.cells:
                    is_even = ((c.x + c.y) % 2 == 0)
                    if (phase == 'A' and not is_even) or (phase == 'B' and is_even):
                        continue
                    outs = self._eval_cell(c, step_inputs)
                    self.cell_out[(c.x, c.y)] = outs
                self._cycle += 1
            # sample outputs after advancing
            out_sample: Dict[str,int] = {}
            for name, bits in self.p.output_bits.items():
                val = 0
                for i, src in enumerate(bits):
                    bitv = self._src_value(src, step_inputs)
                    val |= (bitv & 1) << i
                out_sample[name] = val
            outputs_over_time.append(out_sample)
        return outputs_over_time
