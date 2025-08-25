from __future__ import annotations

import argparse
import csv
import os
from ..float.f8_mul import build_f8_mul_graph
from ..float.f8_add import build_f8_add_graph
from ..graph import Graph, Node
from ..program import Program
from ..mapper import Mapper
from ..emulator import Emulator
from ..float.f8_utils import encode_fp8_e4m3 as f8_enc, decode_fp8_e4m3 as f8_dec


def build_dot8_prog(width: int, height: int) -> 'Program':
    # Compose 8 multiplies + 7 adds into one graph and map to a program
    # Inputs: a0..a7, b0..b7 (8-bit each); Output: dot (8-bit)
    g = Graph()
    for i in range(8):
        g.add_input(f"a{i}", 8)
        g.add_input(f"b{i}", 8)
    
    # Helper: merge a subgraph with a unique prefix to avoid id collisions.
    # Passthrough IDs (like a0..b7, intermediate pN/sN) are not prefixed and INPUT nodes are skipped.
    def merge_with_prefix(dst: Graph, src: Graph, prefix: str, passthrough: set[str]):
        id_map: dict[str, str] = {}
        # First, map ids for all non-INPUT nodes (we'll skip adding OUTPUTs and alias them later)
        for nid, n in src.nodes.items():
            if n.op == 'INPUT':
                # Do not import INPUT nodes; map to same id if passthrough
                id_map[nid] = nid
                continue
            new_id = nid if nid in passthrough else f"{prefix}{nid}"
            id_map[nid] = new_id
        # Add all non-INPUT and non-OUTPUT nodes with remapped inputs
        for nid, n in src.nodes.items():
            if n.op == 'INPUT':
                continue
            if n.op == 'OUTPUT':
                continue
            new_id = id_map[nid]
            new_inputs = [id_map.get(inp, inp) for inp in n.inputs]
            dst.add_node(type(n)(id=new_id, op=n.op, inputs=new_inputs, width=n.width, params=dict(n.params)))
        # For each OUTPUT in src, create an alias node in dst so the output id resolves to the internal producer
        # We implement alias as SHL amount 0 (identity). Provide a dummy const input as second operand.
        for nid, n in src.nodes.items():
            if n.op != 'OUTPUT':
                continue
            # The OUTPUT's input refers to the producer inside src
            if not n.inputs:
                continue
            src_in = n.inputs[0]
            prod_id = id_map.get(src_in, src_in)
            # alias id should remain passthrough id (e.g., p0, s1)
            alias_id = nid
            # ensure a zero const exists for shift input
            c0_id = f"{prefix}c0_3"
            if c0_id not in dst.nodes:
                dst.add_const(c0_id, 0, 3)
            dst.add_node(Node(id=alias_id, op='SHL', inputs=[prod_id, c0_id], width=n.width, params={'amount': 0}))

    # mults
    mul_out = []
    for i in range(8):
        gi = build_f8_mul_graph(f"a{i}", f"b{i}", f"p{i}")
        # merge nodes with unique prefix; keep a{i}, b{i}, p{i} as passthrough ids
        merge_with_prefix(g, gi, prefix=f"mul{i}_", passthrough={f"a{i}", f"b{i}", f"p{i}"})
        mul_out.append(f"p{i}")
    # adds via balanced reduction tree: (p0+p1),(p2+p3),(p4+p5),(p6+p7) -> then pairwise -> final
    level = 0
    current = mul_out[:]
    while len(current) > 1:
        next_level = []
        for i in range(0, len(current), 2):
            a_id = current[i]
            b_id = current[i+1]
            out_id = f"s{level}_{i//2}"
            gi = build_f8_add_graph(a_id, b_id, out_id)
            merge_with_prefix(g, gi, prefix=f"add{level}_{i//2}_", passthrough={a_id, b_id, out_id})
            next_level.append(out_id)
        current = next_level
        level += 1
    g.set_output('dot', current[0], 8)
    return Mapper(grid_width=width, grid_height=height).map(g)


def main():
    ap = argparse.ArgumentParser(description='Run FP8 (E4M3) dot-8 on BitGrid')
    ap.add_argument('--inputs', required=True, help='CSV with columns a0..a7,b0..b7 as 8-bit hex (0x..) or 0..255')
    ap.add_argument('--outputs', required=True, help='Output CSV file')
    ap.add_argument('--grid-width', type=int, default=2048)
    ap.add_argument('--grid-height', type=int, default=256)
    ap.add_argument('--compare-host', action='store_true', help='Also compute host FP8 reference and include in output')
    args = ap.parse_args()

    if args.grid_width % 2 or args.grid_height % 2:
        raise SystemExit('Grid width and height must be even.')
    prog = build_dot8_prog(args.grid_width, args.grid_height)
    emu = Emulator(prog)

    def parse_b(s: str) -> int:
        s = s.strip()
        if s.lower().startswith('0x'):
            return int(s, 16) & 0xFF
        return int(s, 10) & 0xFF

    vectors = []
    with open(args.inputs, 'r', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            vec = {}
            for i in range(8):
                vec[f"a{i}"] = parse_b(row[f"a{i}"])
                vec[f"b{i}"] = parse_b(row[f"b{i}"])
            vectors.append(vec)

    results = emu.run(vectors)
    os.makedirs(os.path.dirname(args.outputs), exist_ok=True)
    fieldnames = ['dot']
    if args.compare_host:
        fieldnames += ['host_dot', 'match']
    with open(args.outputs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i, res in enumerate(results):
            row = {'dot': f"0x{res['dot'] & 0xFF:02X}"}
            if args.compare_host:
                vec = vectors[i]
                acc = 0
                for k in range(8):
                    a = vec[f"a{k}"] & 0xFF
                    b = vec[f"b{k}"] & 0xFF
                    prod = f8_enc(f8_dec(a) * f8_dec(b))
                    acc = f8_enc(f8_dec(acc) + f8_dec(prod))
                row['host_dot'] = f"0x{acc:02X}"
                row['match'] = '1' if (acc == (res['dot'] & 0xFF)) else '0'
            w.writerow(row)


if __name__ == '__main__':
    main()
