from __future__ import annotations

import argparse
import csv
import os
from ..int.u8_add import build_u8_add_graph
from ..mapper import Mapper
from ..cli.align_u8_add_inputs import align_u8_program
from ..emulator import Emulator


def main():
    ap = argparse.ArgumentParser(description='Exhaustive streaming check for 8-bit unsigned add (a+b mod 256)')
    ap.add_argument('--outputs', help='Optional CSV to write mismatches or all results')
    ap.add_argument('--write-all', action='store_true', help='When set, write all rows to CSV; otherwise write only mismatches')
    ap.add_argument('--grid-width', type=int, default=512)
    ap.add_argument('--grid-height', type=int, default=128)
    args = ap.parse_args()

    if args.grid_width % 2 or args.grid_height % 2:
        raise SystemExit('Grid width and height must be even.')

    # Build and map once
    g = build_u8_add_graph('a', 'b', 's')
    prog = Mapper(grid_width=args.grid_width, grid_height=args.grid_height).map(g)
    # Align inputs with delay ladders to enable cps=1 coherent streaming
    prog = align_u8_program(prog)
    # Optionally export the aligned program to JSON for external tracing/inspection
    try:
        prog.save('out/u8_add_aligned.json')
    except Exception:
        pass
    emu = Emulator(prog)
    latency = prog.latency
    print(f"Program: cells={len(prog.cells)}, latency={latency}")

    # Generate all pairs in streaming order
    steps = []
    for a in range(256):
        for b in range(256):
            steps.append({'a': a, 'b': b})
    # Drain pipeline
    for _ in range(latency):
        steps.append({'a': 0, 'b': 0})

    outs = emu.run_stream(steps, cycles_per_step=1, reset=True)

    total = 256 * 256
    mismatches = 0
    rows = []
    for i in range(total):
        a = i // 256
        b = i % 256
        oidx = i + latency - 1
        val = outs[oidx].get('s', 0) & 0xFF
        exp = (a + b) & 0xFF
        ok = (val == exp)
        if not ok:
            mismatches += 1
        if args.outputs and (args.write_all or not ok):
            rows.append({'a': f"0x{a:02X}", 'b': f"0x{b:02X}", 's': f"0x{val:02X}", 'expected': f"0x{exp:02X}", 'match': '1' if ok else '0'})

    print(f"Checked {total} pairs: {total - mismatches} match, {mismatches} mismatch")

    if args.outputs:
        os.makedirs(os.path.dirname(args.outputs) or '.', exist_ok=True)
        with open(args.outputs, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['a', 'b', 's', 'expected', 'match'])
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"Wrote {len(rows)} rows to {args.outputs}")


if __name__ == '__main__':
    main()
