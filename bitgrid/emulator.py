from __future__ import annotations

from typing import Dict, List, Tuple, Any
from .program import Program, Cell
from .bitstream import apply_bitstream_to_program


class Emulator:
    def __init__(self, program: Program):
        self.p = program
        # State per cell: outputs list of 4 bits
        self.cell_out: Dict[Tuple[int,int], List[int]] = {}
        for c in self.p.cells:
            self.cell_out[(c.x, c.y)] = [0, 0, 0, 0]
        # Persistent cycle counter for streaming mode
        self._cycle = 0

    def load_bitstream(self, data: bytes, order: str | None = None, width: int | None = None, height: int | None = None) -> Dict[str, Any]:
        """
        Update program LUTs by applying a bitstream (headered or raw). Resets internal state.
        Returns metadata from apply_bitstream_to_program.
        """
        meta = apply_bitstream_to_program(self.p, data, order=order, width=width, height=height)
        # Ensure state exists for all cells (new cells may have been added)
        for c in self.p.cells:
            if (c.x, c.y) not in self.cell_out:
                self.cell_out[(c.x, c.y)] = [0, 0, 0, 0]
        # Reset internal outputs and cycle counter
        for k in list(self.cell_out.keys()):
            self.cell_out[k] = [0, 0, 0, 0]
        self._cycle = 0
        return meta

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
        # LUT-only evaluation: 'luts' (list up to 4) or 'lut' (single on output 0)
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
            # Special-case ROUTE4 with missing LUTs: default zeros for safety
            if c.op == 'ROUTE4' and lparam is None:
                return [0, 0, 0, 0]
            return [(lut >> idx) & 1, 0, 0, 0]

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

    def sample_outputs(self, inputs: Dict[str, int]) -> Dict[str, int]:
        """Sample current outputs without advancing cycles, using provided input values."""
        outputs: Dict[str, int] = {}
        for name, bits in self.p.output_bits.items():
            val = 0
            for i, src in enumerate(bits):
                bitv = self._src_value(src, inputs)
                val |= (bitv & 1) << i
            outputs[name] = val
        return outputs
