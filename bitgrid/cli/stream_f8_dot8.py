from __future__ import annotations

import argparse
import csv
import os
import random
from .run_f8_dot8 import build_dot8_prog
from ..emulator import Emulator
from ..float.f8_utils import encode_fp8_e4m3 as f8_enc, decode_fp8_e4m3 as f8_dec


def parse_csv(path: str):
    def parse_b(s: str) -> int:
        s = s.strip()
        if s.lower().startswith('0x'):
            return int(s, 16) & 0xFF
        return int(s, 10) & 0xFF
    out = []
    with open(path, 'r', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            vec = {}
            for i in range(8):
                vec[f"a{i}"] = parse_b(row[f"a{i}"])
                vec[f"b{i}"] = parse_b(row[f"b{i}"])
            out.append(vec)
    return out


def gen_random(n: int, seed: int | None = None):
    rng = random.Random(seed)
    vecs = []
    for _ in range(n):
        v = {}
        for i in range(8):
            v[f"a{i}"] = rng.randrange(0, 256)
            v[f"b{i}"] = rng.randrange(0, 256)
        vecs.append(v)
    return vecs


def main():
    ap = argparse.ArgumentParser(description='Stream FP8 (E4M3) dot-8: one vector per cycle, aligned outputs after pipeline fill')
    ap.add_argument('--inputs', help='Optional CSV with a0..a7,b0..b7; if omitted, generates random vectors')
    ap.add_argument('--count', type=int, default=256, help='Number of random vectors (used if --inputs omitted)')
    ap.add_argument('--seed', type=int, default=0, help='RNG seed')
    ap.add_argument('--outputs', required=True, help='Output CSV file')
    ap.add_argument('--grid-width', type=int, default=2048)
    ap.add_argument('--grid-height', type=int, default=256)
    ap.add_argument('--compare-host', action='store_true')
    ap.add_argument('--hold', type=int, default=0, help='Repeat each vector for this many cycles; 0 means use program latency')
    args = ap.parse_args()

    if args.grid_width % 2 or args.grid_height % 2:
        raise SystemExit('Grid width and height must be even.')

    prog = build_dot8_prog(args.grid_width, args.grid_height)
    emu = Emulator(prog)
    latency = prog.latency
    hold = args.hold if args.hold and args.hold > 0 else latency

    vectors = parse_csv(args.inputs) if args.inputs else gen_random(args.count, args.seed)

    # Stream with hold: repeat each vector 'hold' cycles, then drain pipeline with zeros
    steps = []
    for v in vectors:
        for _ in range(hold):
            steps.append(v)
    drain = {f"a{i}": 0 for i in range(8)}
    drain.update({f"b{i}": 0 for i in range(8)})
    steps.extend(drain for _ in range(latency))

    outs = emu.run_stream(steps, cycles_per_step=1, reset=True)

    os.makedirs(os.path.dirname(args.outputs) or '.', exist_ok=True)
    fieldnames = ['dot'] + (['host_dot', 'match'] if args.compare_host else [])
    with open(args.outputs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        # Align: with hold H, output for vector i appears at index i*H + latency - 1
        H = hold
        for i in range(len(vectors)):
            oidx = i*H + latency - 1
            if oidx >= len(outs):
                break
            val = outs[oidx].get('dot', 0) & 0xFF
            row = {'dot': f"0x{val:02X}"}
            if args.compare_host:
                acc = 0
                vec = vectors[i]
                for k in range(8):
                    a = vec[f"a{k}"] & 0xFF
                    b = vec[f"b{k}"] & 0xFF
                    prod = f8_enc(f8_dec(a) * f8_dec(b))
                    acc = f8_enc(f8_dec(acc) + f8_dec(prod))
                row['host_dot'] = f"0x{acc:02X}"
                row['match'] = '1' if acc == val else '0'
            w.writerow(row)


if __name__ == '__main__':
    main()
