from __future__ import annotations

import argparse

from ..lut_only import LUTGrid


def main():
    ap = argparse.ArgumentParser(description='Validate a LUTGrid JSON file for common issues.')
    ap.add_argument('--in', dest='inp', required=True, help='input LUTGrid JSON')
    args = ap.parse_args()

    g = LUTGrid.load(args.inp)
    errors = []
    for y in range(g.H):
        for x in range(g.W):
            c = g.cells[y][x]
            if not isinstance(c.luts, list) or len(c.luts) != 4:
                errors.append(f"Cell ({x},{y}) has invalid luts list")
                continue
            for i, v in enumerate(c.luts):
                if not isinstance(v, int):
                    errors.append(f"Cell ({x},{y}) luts[{i}] not an int: {v}")
                    continue
                if v < 0 or v > 0xFFFF:
                    errors.append(f"Cell ({x},{y}) luts[{i}] out of 16-bit range: {v}")
    if errors:
        print('Validation FAILED:')
        for e in errors[:200]:
            print(' -', e)
        raise SystemExit(1)
    print(f"Validation OK: {g.W}x{g.H} grid")


if __name__ == '__main__':
    main()
