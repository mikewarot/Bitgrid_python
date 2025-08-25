from __future__ import annotations

import argparse
import csv
import os
import random
from .run_f8_dot8 import build_dot8_prog
from ..emulator import Emulator
from ..float.f8_utils import encode_fp8_e4m3 as f8_enc, decode_fp8_e4m3 as f8_dec


def gen_random_vectors(n: int, seed: int | None = None):
    rng = random.Random(seed)
    vecs = []
    for _ in range(n):
        v = {}
        for i in range(8):
            v[f"a{i}"] = rng.randrange(0, 256)
            v[f"b{i}"] = rng.randrange(0, 256)
        vecs.append(v)
    return vecs


def load_csv(path: str):
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


def main():
    ap = argparse.ArgumentParser(description='Compare FP8 (E4M3) dot-8 emulator vs host reference on random or CSV vectors')
    ap.add_argument('--count', type=int, default=64, help='Number of random vectors to generate (ignored if --inputs provided)')
    ap.add_argument('--seed', type=int, default=0, help='PRNG seed for reproducibility')
    ap.add_argument('--inputs', help='Optional CSV with a0..a7,b0..b7; if provided, overrides --count/--seed')
    ap.add_argument('--outputs', default='out/f8_dot8_compare.csv', help='Output CSV with columns dot,host_dot,match')
    ap.add_argument('--grid-width', type=int, default=2048)
    ap.add_argument('--grid-height', type=int, default=256)
    args = ap.parse_args()

    if args.grid_width % 2 or args.grid_height % 2:
        raise SystemExit('Grid width and height must be even.')

    prog = build_dot8_prog(args.grid_width, args.grid_height)
    emu = Emulator(prog)
    print(f"Program: cells={len(prog.cells)}, latency={prog.latency}")

    vectors = load_csv(args.inputs) if args.inputs else gen_random_vectors(args.count, args.seed)
    # Run and show lightweight progress
    results = []
    total = len(vectors)
    for i in range(total):
        results.extend(emu.run([vectors[i]]))
        if (i+1) % max(1, total // 8) == 0 or (i+1) == total:
            print(f"Ran {i+1}/{total} vectors...")

    os.makedirs(os.path.dirname(args.outputs), exist_ok=True)
    with open(args.outputs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['dot', 'host_dot', 'match'])
        w.writeheader()
        matches = 0
        for i, res in enumerate(results):
            row = {'dot': f"0x{(res['dot'] & 0xFF):02X}"}
            vec = vectors[i]
            acc = 0
            for k in range(8):
                a = vec[f"a{k}"] & 0xFF
                b = vec[f"b{k}"] & 0xFF
                prod = f8_enc(f8_dec(a) * f8_dec(b))
                acc = f8_enc(f8_dec(acc) + f8_dec(prod))
            row['host_dot'] = f"0x{acc:02X}"
            ok = (acc == (res['dot'] & 0xFF))
            row['match'] = '1' if ok else '0'
            if ok:
                matches += 1
            w.writerow(row)
    total = len(vectors)
    rate = (matches / total * 100.0) if total else 0.0
    print(f"Compared {total} vectors: {matches} match ({rate:.1f}%) -> {args.outputs}")


if __name__ == '__main__':
    main()
