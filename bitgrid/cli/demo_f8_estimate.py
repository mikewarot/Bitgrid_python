from __future__ import annotations

import argparse
from ..float.f8_mul import build_f8_mul_graph
from ..float.f8_add import build_f8_add_graph
from ..sizer import size_graph


def main():
    ap = argparse.ArgumentParser(description='Estimate FP8 (E4M3) dot-8 and 8->8 linear sizes')
    args = ap.parse_args()

    g_mul = build_f8_mul_graph('a0', 'b0', 'p')
    mul_est = size_graph(g_mul)
    g_add = build_f8_add_graph('x', 'y', 's')
    add_est = size_graph(g_add)

    # dot-8: 8 mul + 7 add
    dot_cols = 8 * mul_est['cols'] + 7 * add_est['cols']
    dot_cells = 8 * mul_est['cells'] + 7 * add_est['cells']
    dot_h = max(mul_est['height_bits'], add_est['height_bits'])

    # linear 8->8: 8 dot-8 + 8 bias adds
    lin_cols = 8 * dot_cols + 8 * add_est['cols']
    lin_cells = 8 * dot_cells + 8 * add_est['cells']

    print('FP8 E4M3 Single MUL: ', mul_est)
    print('FP8 E4M3 Single ADD: ', add_est)
    print(f"FP8 dot-8 estimate: cols~{dot_cols}, height_bits~{dot_h}, cells~{dot_cells}")
    print(f"FP8 Linear 8->8 estimate: cols~{lin_cols}, height_bits~{dot_h}, cells~{lin_cells}")


if __name__ == '__main__':
    main()
