from __future__ import annotations

from ..cli.run_f8_dot8 import build_dot8_prog
from ..mapper import Mapper
from ..emulator import Emulator
from ..graph import Graph
from ..float.f8_mul import build_f8_mul_graph
from ..float.f8_add import build_f8_add_graph


def build_graph_only() -> Graph:
    g = Graph()
    for i in range(8):
        g.add_input(f"a{i}", 8)
        g.add_input(f"b{i}", 8)

    def merge_with_prefix(dst: Graph, src: Graph, prefix: str, passthrough: set[str]):
        from ..graph import Node
        id_map = {}
        for nid, n in src.nodes.items():
            if n.op == 'INPUT':
                id_map[nid] = nid
                continue
            new_id = nid if nid in passthrough else f"{prefix}{nid}"
            id_map[nid] = new_id
        for nid, n in src.nodes.items():
            if n.op in ('INPUT','OUTPUT'):
                continue
            new_id = id_map[nid]
            new_inputs = [id_map.get(inp, inp) for inp in n.inputs]
            dst.add_node(Node(id=new_id, op=n.op, inputs=new_inputs, width=n.width, params=dict(n.params)))
        for nid, n in src.nodes.items():
            if n.op != 'OUTPUT':
                continue
            if not n.inputs:
                continue
            src_in = n.inputs[0]
            prod_id = id_map.get(src_in, src_in)
            c0 = f"{prefix}c0_3"
            if c0 not in dst.nodes:
                dst.add_const(c0, 0, 3)
            dst.add_node(Node(id=nid, op='SHL', inputs=[prod_id, c0], width=n.width, params={'amount': 0}))

    mul_out = []
    for i in range(8):
        gi = build_f8_mul_graph(f"a{i}", f"b{i}", f"p{i}")
        merge_with_prefix(g, gi, prefix=f"mul{i}_", passthrough={f"a{i}", f"b{i}", f"p{i}"})
        mul_out.append(f"p{i}")
    # Balanced tree of adds
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
    # output dot
    g.set_output('dot', current[0], 8)
    # debug outputs
    for i in range(8):
        if f"p{i}" in g.nodes:
            g.set_output(f"d_p{i}", f"p{i}", 8)
    # expose intermediate sums
    for nid, n in list(g.nodes.items()):
        if nid.startswith('s') and n.op == 'OUTPUT':
            g.set_output(f"d_{nid}", nid, 8)
    return g


def main():
    g = build_graph_only()
    prog = Mapper(grid_width=2048, grid_height=256).map(g)
    emu = Emulator(prog)
    vec = {f"a{i}": 0x38 for i in range(8)}
    vec.update({f"b{i}": 0x38 for i in range(8)})
    out = emu.run([vec])[0]
    keys = ['dot'] + [f"d_p{i}" for i in range(8)] + [f"d_s{i}" for i in range(1,8)]
    data = {}
    for k in keys:
        v = out.get(k)
        data[k] = (v & 0xFF) if isinstance(v, int) else None
    import os, json
    os.makedirs('out', exist_ok=True)
    with open('out/f8_dot8_debug.json', 'w') as f:
        json.dump(data, f, indent=2)
    print('wrote out/f8_dot8_debug.json')


if __name__ == '__main__':
    main()
