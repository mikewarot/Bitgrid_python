from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import time
from .run_f8_dot8 import build_dot8_prog
from ..emulator import Emulator
from ..float.f8_utils import encode_fp8_e4m3 as f8_enc, decode_fp8_e4m3 as f8_dec


def gen_vector(rng: random.Random) -> dict[str, int]:
    return {**{f"a{i}": rng.randrange(0, 256) for i in range(8)},
            **{f"b{i}": rng.randrange(0, 256) for i in range(8)}}


def write_header_if_needed(path: str):
    exists = os.path.exists(path)
    if not exists or os.path.getsize(path) == 0:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['dot', 'host_dot', 'match'])
            w.writeheader()


def main():
    ap = argparse.ArgumentParser(description='Soak test FP8 (E4M3) dot-8: long-running random compare with periodic progress')
    ap.add_argument('--total', type=int, default=5000, help='Total number of random vectors to run')
    ap.add_argument('--chunk-size', type=int, default=50, help='Progress/report and flush interval')
    ap.add_argument('--seed', type=int, default=0, help='RNG seed for reproducibility')
    ap.add_argument('--outputs', default='out/f8_dot8_soak.csv', help='CSV to append results')
    ap.add_argument('--grid-width', type=int, default=2048)
    ap.add_argument('--grid-height', type=int, default=256)
    args = ap.parse_args()

    if args.grid_width % 2 or args.grid_height % 2:
        raise SystemExit('Grid width and height must be even.')

    print(f"Mapping dot-8 once (grid {args.grid_width}x{args.grid_height})...")
    prog = build_dot8_prog(args.grid_width, args.grid_height)
    emu = Emulator(prog)
    print(f"Program: cells={len(prog.cells)}, latency={prog.latency}")

    rng = random.Random(args.seed)
    write_header_if_needed(args.outputs)

    matches = 0
    start = time.time()
    last_print = start
    done = 0
    # Open in append mode and write rows incrementally
    with open(args.outputs, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['dot', 'host_dot', 'match'])
        while done < args.total:
            # Run one vector
            vec = gen_vector(rng)
            res = emu.run([vec])[0]
            # host reference
            acc = 0
            for k in range(8):
                a = vec[f"a{k}"] & 0xFF
                b = vec[f"b{k}"] & 0xFF
                prod = f8_enc(f8_dec(a) * f8_dec(b))
                acc = f8_enc(f8_dec(acc) + f8_dec(prod))
            ok = (acc == (res['dot'] & 0xFF))
            if ok:
                matches += 1
            w.writerow({'dot': f"0x{(res['dot'] & 0xFF):02X}", 'host_dot': f"0x{acc:02X}", 'match': '1' if ok else '0'})
            done += 1

            # Periodic flush and progress
            if done % args.chunk_size == 0 or done == args.total:
                f.flush()
                os.fsync(f.fileno())
                now = time.time()
                elapsed = now - start
                rate = done / elapsed if elapsed > 0 else 0.0
                eta = (args.total - done) / rate if rate > 0 else float('inf')
                print(f"{done}/{args.total} done | matches={matches} ({(matches/done*100.0):.1f}%) | {rate:.2f} vec/s | ETA {eta/60:.1f} min")
                sys.stdout.flush()

    total = args.total
    rate = (matches / total * 100.0) if total else 0.0
    print(f"Completed {total}: {matches} match ({rate:.1f}%) -> {args.outputs}")


if __name__ == '__main__':
    main()
