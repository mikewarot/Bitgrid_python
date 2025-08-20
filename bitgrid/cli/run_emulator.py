from __future__ import annotations

import argparse
import csv
from typing import Dict, List, Set
from ..program import Program
from ..emulator import Emulator


def parse_int(s: str) -> int:
    s = s.strip()
    if not s:
        return 0
    sign = 1
    if s[0] in '+-':
        if s[0] == '-':
            sign = -1
        s_body = s[1:].strip()
    else:
        s_body = s
    lb = s_body.lower()
    if lb.startswith('0x'):
        return sign * int(s_body, 16)
    if lb.startswith('0b'):
        return sign * int(s_body, 2)
    return sign * int(s_body, 10)


def main():
    ap = argparse.ArgumentParser(description='Run BitGrid emulator')
    ap.add_argument('--program', required=True, help='Program JSON file')
    ap.add_argument('--inputs', required=True, help='Input CSV file (header matches var names)')
    ap.add_argument('--outputs', required=True, help='Output CSV file')
    ap.add_argument('--log', help='Optional debug log file')
    ap.add_argument('--format', choices=['hex','dec','bin'], default='hex', help='Output number format (default: hex)')
    ap.add_argument('--signed', help='Comma-separated list of output names to interpret as signed (two\'s complement) when using dec format')
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
    signed_names: Set[str] = set()
    if args.signed:
        signed_names = {n.strip() for n in args.signed.split(',') if n.strip()}
    with open(args.outputs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for res in results:
            row: Dict[str,str] = {}
            for k in out_fields:
                bits = len(prog.output_bits[k])
                val = res[k]
                if args.format == 'dec':
                    if k in signed_names and bits > 0:
                        sign_bit = 1 << (bits - 1)
                        mask = (1 << bits) - 1
                        sval = (val & mask)
                        if sval & sign_bit:
                            sval = sval - (1 << bits)
                        row[k] = str(sval)
                    else:
                        row[k] = str(val)
                elif args.format == 'hex':
                    # zero-padded to width
                    pad = (bits + 3) // 4
                    row[k] = f"0x{val & ((1<<bits)-1):0{pad}X}" if bits > 0 else f"0x{val:X}"
                else:  # bin
                    row[k] = f"0b{(val & ((1<<bits)-1)):0{bits}b}" if bits > 0 else f"0b{val:b}"
            w.writerow(row)

    if args.log:
        with open(args.log, 'w') as f:
            f.write(f"Program latency: {prog.latency}\n")
            f.write(f"Grid size: {prog.width}x{prog.height}\n")
            f.write(f"Ran {len(vectors)} vectors\n")

    print(f'Wrote outputs to {args.outputs}')


if __name__ == '__main__':
    main()
