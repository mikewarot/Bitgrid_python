from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict


def main():
    ap = argparse.ArgumentParser(description='Summarize BitGrid trace JSONL events')
    ap.add_argument('path', type=str, help='trace .jsonl file')
    ap.add_argument('--top', type=int, default=20, help='show top N event kinds')
    args = ap.parse_args()

    kind_counts = Counter()
    mismatches = Counter()
    by_epoch = defaultdict(Counter)

    with open(args.path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            k = ev.get('kind', 'unknown')
            kind_counts[k] += 1
            e = ev.get('epoch')
            if isinstance(e, int):
                by_epoch[e][k] += 1
            if k == 'barrier_neighbor_hdr':
                mismatches[ev.get('status', 'unknown')] += 1

    print('Event counts:')
    for k, n in kind_counts.most_common(args.top):
        print(f'  {k}: {n}')
    if mismatches:
        print('Barrier header statuses:')
        for k, n in mismatches.most_common():
            print(f'  {k}: {n}')
    print('By-epoch (non-zero):')
    for e in sorted(by_epoch.keys()):
        row = ', '.join(f'{k}:{n}' for k, n in by_epoch[e].most_common())
        print(f'  epoch {e}: {row}')


if __name__ == '__main__':
    main()
