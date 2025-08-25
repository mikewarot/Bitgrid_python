from __future__ import annotations

import argparse
from ..float.f32_mul import build_f32_mul_graph
from ..float.f32_add import build_f32_add_graph
from ..sizer import size_graph


def main():
    ap = argparse.ArgumentParser(description='Estimate FP32 dot-8 and 8x8 matmul sizes without full graph build')
    args = ap.parse_args()

    g_mul = build_f32_mul_graph('a0', 'b0', 'p')
    mul_est = size_graph(g_mul)
    g_add = build_f32_add_graph('x', 'y', 's')
    add_est = size_graph(g_add)

    # dot-8: 8 multiplies + 7 adds
    dot_cols = 8 * mul_est['cols'] + 7 * add_est['cols']
    dot_cells = 8 * mul_est['cells'] + 7 * add_est['cells']
    dot_h = max(mul_est['height_bits'], add_est['height_bits'])

    # matmul 8x8: 64 outputs, each dot-8: 64*8 muls, 64*7 adds
    mm_mul = 64 * 8
    mm_add = 64 * 7
    mm_cols = mm_mul * mul_est['cols'] + mm_add * add_est['cols']
    mm_cells = mm_mul * mul_est['cells'] + mm_add * add_est['cells']
    mm_h = dot_h

    print('Single f32 MUL: ', mul_est)
    print('Single f32 ADD: ', add_est)
    print(f"Dot-8 estimate: cols~{dot_cols}, height_bits~{dot_h}, cells~{dot_cells}")
    # Linear 8->8 (batch=1): 8 dot-8 + 8 bias adds
    lin_cols = 8 * dot_cols + 8 * add_est['cols']
    lin_cells = 8 * dot_cells + 8 * add_est['cells']
    print(f"Linear 8->8 estimate (incl. 8 biases): cols~{lin_cols}, height_bits~{dot_h}, cells~{lin_cells}")
    print(f"Matmul 8x8 estimate: cols~{mm_cols}, height_bits~{mm_h}, cells~{mm_cells}")


if __name__ == '__main__':
    main()
