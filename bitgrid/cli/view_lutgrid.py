from __future__ import annotations

import argparse
import re

from ..lut_only import LUTGrid
from ..lut_logic import decompile_lut_to_expr


def main():
    ap = argparse.ArgumentParser(description='View LUTGrid cells as per-output expressions (NESW).')
    ap.add_argument('--in', dest='inp', required=True, help='input LUTGrid JSON')
    ap.add_argument('--grid', action='store_true', help='Render as a grid summary (per cell)')
    ap.add_argument('--dirs', default='NESW', help='Filter which directions to show (subset of NESW), default NESW')
    ap.add_argument('--truncate', type=int, default=0, help='Truncate each cell string to N chars (0 = no truncation)')
    ap.add_argument('--cell-width', type=int, default=0, help='Fixed cell width (0 = auto per column)')
    ap.add_argument('--raw', action='store_true', help='Show raw LUT integers per selected direction (e.g., E=43690)')
    ap.add_argument('--truth', action='store_true', help='Show LUTs as 4-hex per selected direction (e.g., E=AAAA)')
    ap.add_argument('--headers', action='store_true', help='Show column/row headers and do not skip empty rows')
    ap.add_argument('--color', action='store_true', help='ANSI colorize direction letters (N/E/S/W)')
    args = ap.parse_args()

    g = LUTGrid.load(args.inp)
    if args.grid:
        dirs = ''.join([d for d in args.dirs.upper() if d in 'NESW']) or 'NESW'
        dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
        # Build cell strings matrix
        cells: list[list[str]] = [["" for _ in range(g.W)] for _ in range(g.H)]
        for y in range(g.H):
            for x in range(g.W):
                c = g.cells[y][x]
                parts = []
                for d in dirs:
                    i = dir_to_idx[d]
                    v = c.luts[i]
                    if v:
                        if args.raw:
                            parts.append(f"{d}={v}")
                        elif args.truth:
                            parts.append(f"{d}={v:04X}")
                        else:
                            parts.append(f"{d}={decompile_lut_to_expr(v)}")
                s = ','.join(parts)
                if args.truncate and len(s) > args.truncate:
                    s = s[:max(1, args.truncate-1)] + '…'
                # Coordinates: include only if not using headers and there is content
                if s and not args.headers:
                    s = f"({x},{y}):" + s
                cells[y][x] = s
        # Determine column widths
        widths = [0]*g.W
        for x in range(g.W):
            if args.cell_width > 0:
                widths[x] = args.cell_width
            else:
                widths[x] = max((len(cells[y][x]) for y in range(g.H)), default=0)
        # If headers, ensure header numbers fit
        if args.headers:
            for x in range(g.W):
                widths[x] = max(widths[x], len(str(x)))
        # Optional colorization helper (apply at print time)
        color_map = {'N':'36', 'E':'33', 'S':'32', 'W':'35'}  # cyan, yellow, green, magenta
        dir_eq_re = re.compile(r'([NESW])=([^,]+)')
        def colorize_cell(s: str) -> str:
            if not args.color or not s:
                return s
            # Color the entire D=expr segment for each comma-separated part
            def repl(m):
                d = m.group(1)
                expr = m.group(2)
                code = color_map.get(d, '0')
                return f"\x1b[{code}m{d}={expr}\x1b[0m"
            return dir_eq_re.sub(repl, s)
        # Print header row if requested
        left_w = len(str(g.H - 1)) if args.headers else 0
        if args.headers:
            header_cells = [(str(x).center(widths[x]) if widths[x] > 0 else str(x)) for x in range(g.W)]
            left_pad = ' ' * (left_w + 1) if left_w > 0 else ''
            print(left_pad + ' :: '.join(header_cells))
        # Print rows with padding; center each cell; include row labels when headers
        for y in range(g.H):
            row_strs = []
            for x in range(g.W):
                w = widths[x]
                s = cells[y][x]
                if w > 0:
                    s = s.center(w)
                row_strs.append(colorize_cell(s))
            line = ' :: '.join(row_strs).rstrip()
            if args.headers:
                label = str(y).rjust(left_w) + ' ' if left_w > 0 else ''
                print(label + line)
            else:
                if any(cells[y]):
                    print(line)
    else:
        for y in range(g.H):
            for x in range(g.W):
                c = g.cells[y][x]
                exprs = [decompile_lut_to_expr(c.luts[i]) if c.luts[i] else '0' for i in range(4)]
                if any(v != '0' for v in exprs):
                    print(f"Cell ({x},{y})")
                    for d, e in zip('NESW', exprs):
                        if e != '0':
                            print(f"  {d}: {e}")


if __name__ == '__main__':
    main()
