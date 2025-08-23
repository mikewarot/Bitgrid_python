from __future__ import annotations

from typing import Dict, List, Tuple
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

    def run_vector(self, inputs: Dict[str, int]) -> Dict[str, int]:
        # Provide per-bit input function
        def src_value(src: Dict) -> int:
            t = src['type']
            if t == 'const':
                return int(src['value']) & 1
            if t == 'input':
                name = src['name']
                bit = int(src['bit'])
                val = int(inputs.get(name, 0))
                return (val >> bit) & 1
            if t == 'cell':
                key = (int(src['x']), int(src['y']))
                out_idx = int(src.get('out', 0))
                return self.cell_out.get(key, [0,0,0,0])[out_idx] & 1
            return 0

        # two-phase stepping for p.latency cycles
        for cyc in range(self.p.latency):
            phase = 'A' if (cyc % 2 == 0) else 'B'
            for c in self.p.cells:
                is_even = ((c.x + c.y) % 2 == 0)
                if (phase == 'A' and not is_even) or (phase == 'B' and is_even):
                    continue
                a = src_value(c.inputs[0])
                b = src_value(c.inputs[1])
                cin = src_value(c.inputs[2])
                # implement ops
                if c.op == 'BUF':
                    o0 = a
                    outs = [o0, 0, 0, 0]
                elif c.op == 'NOT':
                    outs = [1 - a, 0, 0, 0]
                elif c.op == 'AND':
                    outs = [a & b, 0, 0, 0]
                elif c.op == 'OR':
                    outs = [a | b, 0, 0, 0]
                elif c.op == 'XOR':
                    outs = [a ^ b, 0, 0, 0]
                elif c.op == 'ADD_BIT':
                    s = (a ^ b) ^ cin
                    cout = (a & b) | (a & cin) | (b & cin)
                    outs = [s & 1, cout & 1, 0, 0]
                elif c.op == 'ROUTE4':
                    # 4-input (N,E,S,W) -> 4 outputs (N,E,S,W) via 4 LUTs (16-bit each)
                    # Inputs mapping: inputs[0]=N, [1]=E, [2]=S, [3]=W
                    n = a
                    e = b
                    sbit = src_value(c.inputs[2])
                    w = src_value(c.inputs[3])
                    idx = (n & 1) | ((e & 1) << 1) | ((sbit & 1) << 2) | ((w & 1) << 3)
                    luts = c.params.get('luts', [0, 0, 0, 0])
                    on = (int(luts[0]) >> idx) & 1
                    oe = (int(luts[1]) >> idx) & 1
                    os = (int(luts[2]) >> idx) & 1
                    ow = (int(luts[3]) >> idx) & 1
                    outs = [on, oe, os, ow]
                else:
                    outs = [0, 0, 0, 0]
                self.cell_out[(c.x, c.y)] = outs

        # Sample outputs
        outputs: Dict[str, int] = {}
        for name, bits in self.p.output_bits.items():
            val = 0
            for i, src in enumerate(bits):
                val |= (src_value(src) & 1) << i
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
        def src_value(src: Dict, inputs: Dict[str,int]) -> int:
            t = src['type']
            if t == 'const':
                return int(src['value']) & 1
            if t == 'input':
                name = src['name']
                bit = int(src['bit'])
                val = int(inputs.get(name, 0))
                return (val >> bit) & 1
            if t == 'cell':
                key = (int(src['x']), int(src['y']))
                out_idx = int(src.get('out', 0))
                return self.cell_out.get(key, [0,0,0,0])[out_idx] & 1
            return 0

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
                    # reuse core evaluation but inline to pass dynamic inputs
                    def sv(src: Dict) -> int:
                        return src_value(src, step_inputs)
                    a = sv(c.inputs[0])
                    b = sv(c.inputs[1])
                    cin = sv(c.inputs[2])
                    if c.op == 'BUF':
                        outs = [a, 0, 0, 0]
                    elif c.op == 'NOT':
                        outs = [1 - a, 0, 0, 0]
                    elif c.op == 'AND':
                        outs = [a & b, 0, 0, 0]
                    elif c.op == 'OR':
                        outs = [a | b, 0, 0, 0]
                    elif c.op == 'XOR':
                        outs = [a ^ b, 0, 0, 0]
                    elif c.op == 'ADD_BIT':
                        s = (a ^ b) ^ cin
                        cout = (a & b) | (a & cin) | (b & cin)
                        outs = [s & 1, cout & 1, 0, 0]
                    elif c.op == 'ROUTE4':
                        n = a
                        e = b
                        sbit = sv(c.inputs[2])
                        w = sv(c.inputs[3])
                        idx = (n & 1) | ((e & 1) << 1) | ((sbit & 1) << 2) | ((w & 1) << 3)
                        luts = c.params.get('luts', [0, 0, 0, 0])
                        on = (int(luts[0]) >> idx) & 1
                        oe = (int(luts[1]) >> idx) & 1
                        os = (int(luts[2]) >> idx) & 1
                        ow = (int(luts[3]) >> idx) & 1
                        outs = [on, oe, os, ow]
                    else:
                        outs = [0, 0, 0, 0]
                    self.cell_out[(c.x, c.y)] = outs
                self._cycle += 1
            # sample outputs after advancing
            out_sample: Dict[str,int] = {}
            for name, bits in self.p.output_bits.items():
                val = 0
                for i, src in enumerate(bits):
                    # use current step inputs for input sources
                    t = src['type']
                    if t == 'const':
                        bitv = int(src['value']) & 1
                    elif t == 'input':
                        bitv = (int(step_inputs.get(src['name'], 0)) >> int(src['bit'])) & 1
                    elif t == 'cell':
                        key = (int(src['x']), int(src['y']))
                        out_idx = int(src.get('out', 0))
                        bitv = self.cell_out.get(key, [0,0,0,0])[out_idx] & 1
                    else:
                        bitv = 0
                    val |= (bitv & 1) << i
                out_sample[name] = val
            outputs_over_time.append(out_sample)
        return outputs_over_time
