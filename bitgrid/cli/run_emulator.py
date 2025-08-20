from __future__ import annotations

import argparse
import csv
from typing import Dict, List
from ..program import Program
from ..emulator import Emulator


def parse_int(s: str) -> int:
    s = s.strip()
    if s.lower().startswith('0x'):
        return int(s, 16)
    if s.lower().startswith('0b'):
        return int(s, 2)
    return int(s, 10)


def main():
    ap = argparse.ArgumentParser(description='Run BitGrid emulator')
    ap.add_argument('--program', required=True, help='Program JSON file')
    ap.add_argument('--inputs', required=True, help='Input CSV file (header matches var names)')
    ap.add_argument('--outputs', required=True, help='Output CSV file')
    ap.add_argument('--log', help='Optional debug log file')
    args = ap.parse_args()

    prog = Program.load(args.program)
    emu = Emulator(prog)

    # Read inputs
    vectors: List[Dict[str,int]] = []
    with open(args.inputs, 'r', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            vec = {k: parse_int(v) for k, v in row.items()}
            vectors.append(vec)

    results = emu.run(vectors)

    # Write outputs
    out_fields = list(prog.output_bits.keys())
    with open(args.outputs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for res in results:
            w.writerow({k: f"0x{res[k]:X}" for k in out_fields})

    if args.log:
        with open(args.log, 'w') as f:
            f.write(f"Program latency: {prog.latency}\n")
            f.write(f"Grid size: {prog.width}x{prog.height}\n")
            f.write(f"Ran {len(vectors)} vectors\n")

    print(f'Wrote outputs to {args.outputs}')


if __name__ == '__main__':
    main()
