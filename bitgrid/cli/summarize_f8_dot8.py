from __future__ import annotations

import argparse
import csv
import os
from typing import List


def summarize_file(path: str, show_mismatches: int = 0) -> dict:
    total = 0
    matches = 0
    mismatches: List[dict] = []
    # Accept files with columns: dot, host_dot, match (stream/soak) or just dot (no host)
    with open(path, 'r', newline='') as f:
        r = csv.DictReader(f)
        has_host = 'host_dot' in r.fieldnames if r.fieldnames else False
        has_match = 'match' in r.fieldnames if r.fieldnames else False
        for row in r:
            total += 1
            if has_match:
                ok = (str(row.get('match', '')).strip() == '1')
            elif has_host:
                ok = str(row.get('dot','')).strip().lower() == str(row.get('host_dot','')).strip().lower()
            else:
                ok = True  # no host info; treat as trivially ok
            matches += 1 if ok else 0
            if not ok and len(mismatches) < show_mismatches:
                mismatches.append({'dot': row.get('dot'), 'host_dot': row.get('host_dot')})
    rate = (matches / total * 100.0) if total else 0.0
    return {'file': path, 'total': total, 'matches': matches, 'rate': rate, 'mismatches': mismatches}


def main():
    ap = argparse.ArgumentParser(description='Summarize FP8 dot-8 result CSVs (match rate, counts, sample mismatches)')
    ap.add_argument('inputs', nargs='+', help='One or more CSV files (e.g., out/stream_dot8.csv out/f8_dot8_soak.csv)')
    ap.add_argument('--show-mismatches', type=int, default=0, help='Show up to N mismatches per file')
    args = ap.parse_args()

    agg_total = 0
    agg_matches = 0
    for p in args.inputs:
        if not os.path.exists(p):
            print(f"Skip missing: {p}")
            continue
        s = summarize_file(p, args.show_mismatches)
        agg_total += s['total']
        agg_matches += s['matches']
        print(f"{os.path.basename(s['file'])}: {s['matches']}/{s['total']} match ({s['rate']:.1f}%)")
        if args.show_mismatches and s['mismatches']:
            for m in s['mismatches']:
                print(f"  dot={m['dot']} host_dot={m['host_dot']}")
    if agg_total:
        agg_rate = agg_matches / agg_total * 100.0
        print(f"TOTAL: {agg_matches}/{agg_total} match ({agg_rate:.1f}%)")


if __name__ == '__main__':
    main()
