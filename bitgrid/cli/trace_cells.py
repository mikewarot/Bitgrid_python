from __future__ import annotations

import argparse
import json
from typing import Dict, List
from ..program import Program
from ..emulator import Emulator


def parse_name_u64_map(s: str) -> Dict[str, int]:
    m: Dict[str, int] = {}
    if not s:
        return m
    parts = [p for p in s.replace(';', ',').split(',') if p]
    for p in parts:
        if '=' not in p:
            continue
        k, v = p.split('=', 1)
        k = k.strip()
        v = v.strip()
        if v.lower().startswith('0x'):
            m[k] = int(v, 16)
        else:
            m[k] = int(v)
    return m


def main():
    ap = argparse.ArgumentParser(description='Trace per-subcycle cell outputs for a Program for visualization/debugging (JSONL).')
    ap.add_argument('--program', required=True, help='Program JSON path')
    ap.add_argument('--steps', type=int, default=8, help='Number of subcycles to run (A/B subcycles).')
    ap.add_argument('--inputs', type=str, default='', help='Constant inputs as name=val pairs (comma/semicolon-separated). Hex like 0x123 ok.')
    ap.add_argument('--out', type=str, default='out/cell_trace.jsonl', help='Trace JSONL output path')
    args = ap.parse_args()

    prog = Program.load(args.program)
    emu = Emulator(prog)

    const_inputs: Dict[str, int] = parse_name_u64_map(args.inputs)
    # Seed defaults for any declared inputs
    for name in prog.input_bits.keys():
        const_inputs.setdefault(name, 0)

    # Ensure output dir exists
    import os
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)

    # Reset emulator, then step one subcycle at a time and record after each
    emu.run_stream([const_inputs], cycles_per_step=0, reset=True)  # ensure reset without advancing

    with open(args.out, 'w', encoding='utf-8') as f:
        for i in range(int(args.steps)):
            # advance one subcycle
            emu.run_stream([const_inputs], cycles_per_step=1, reset=False)
            phase = 'A' if (i % 2 == 0) else 'B'
            # snapshot
            cell_dump = { f"{x},{y}": outs for (x,y), outs in emu.cell_out.items() }
            outputs = emu.sample_outputs(const_inputs)
            rec = {
                'step': i+1,
                'phase': phase,
                'cells': cell_dump,
                'outputs': outputs,
                'inputs': const_inputs,
            }
            f.write(json.dumps(rec) + '\n')
    print(f"Wrote {args.out} ({args.steps} subcycles)")


if __name__ == '__main__':
    main()
