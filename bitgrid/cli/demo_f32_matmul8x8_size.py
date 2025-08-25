from __future__ import annotations

import argparse
from ..float.f32_mul import build_f32_mul_graph
from ..float.f32_add import build_f32_add_graph
from ..graph import Graph
from ..sizer import size_graph


def build_matmul8x8_graph() -> Graph:
    # C = A(8x8) * B(8x8), f32
    g = Graph()
    # Inputs: Aij, Bij as 32-bit
    for i in range(8):
        for j in range(8):
            g.add_input(f"A{i}{j}", 32)
            g.add_input(f"B{i}{j}", 32)
    # Compute Cik = sum_j Aij * Bjk for each i,k
    for i in range(8):
        for k in range(8):
            # dot over j
            mul_ids = []
            for j in range(8):
                gi = build_f32_mul_graph(a_name=f"A{i}{j}", b_name=f"B{j}{k}", out_name=f"P{i}{j}{k}")
                for nid, n in gi.nodes.items():
                    if n.op == 'INPUT':
                        continue
                    g.nodes[nid] = n
                mul_ids.append(f"P{i}{j}{k}")
            acc = mul_ids[0]
            for j in range(1, 8):
                ai = build_f32_add_graph(a_name=acc, b_name=mul_ids[j], out_name=f"S{i}{j}{k}")
                for nid, n in ai.nodes.items():
                    if n.op == 'INPUT':
                        continue
                    g.nodes[nid] = n
                acc = f"S{i}{j}{k}"
            g.set_output(f"C{i}{k}", acc, 32)
    return g


def main():
    ap = argparse.ArgumentParser(description='Build/map an f32 matmul 8x8 and report program size')
    ap.add_argument('--grid', type=str, default='256x256', help='grid size WxH for mapper limit (even dims)')
    args = ap.parse_args()
    W, H = map(int, args.grid.lower().split('x'))

    g = build_matmul8x8_graph()
    est = size_graph(g)
    print(f"Estimate: cols~{est['cols']}, height_bits~{est['height_bits']}, cells~{est['cells']}")


if __name__ == '__main__':
    main()
