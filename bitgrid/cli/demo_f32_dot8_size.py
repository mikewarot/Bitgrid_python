from __future__ import annotations

import argparse
from ..float.f32_mul import build_f32_mul_graph
from ..float.f32_add import build_f32_add_graph
from ..graph import Graph, Node
from ..sizer import size_graph


def _merge_with_prefix(dst: Graph, src: Graph, prefix: str, bind_inputs: dict[str, str], out_name: str) -> str:
    """Merge src into dst with id prefixing; bind specified INPUT ids to existing dst ids.
    Returns the mapped compute id for src's output out_name (the source of the OUTPUT node).
    """
    # Build id map
    id_map: dict[str, str] = {}
    for nid, n in src.nodes.items():
        if n.op == 'INPUT':
            # Bind to provided id or keep as-is (assuming already present in dst)
            target = bind_inputs.get(nid, nid)
            id_map[nid] = target
            continue
        if n.op == 'OUTPUT':
            # Do not import OUTPUT nodes; we'll use their input as the compute id
            continue
        # Prefix internal nodes (including CONST and intermediates)
        new_id = f"{prefix}:{nid}"
        id_map[nid] = new_id

    # Emit nodes (skip INPUT, rewrite inputs)
    for nid, n in src.nodes.items():
        if n.op in ('INPUT','OUTPUT'):
            continue
        new_inputs = [id_map.get(i, i) for i in n.inputs]
        new_id = id_map[nid]
        dst.nodes[new_id] = Node(id=new_id, op=n.op, inputs=new_inputs, params=dict(n.params), width=n.width)

    # Resolve compute id behind OUTPUT
    out_node = src.nodes.get(out_name)
    if not out_node or out_node.op != 'OUTPUT' or not out_node.inputs:
        raise RuntimeError(f"Source graph missing OUTPUT '{out_name}'")
    src_compute = out_node.inputs[0]
    mapped_compute = id_map.get(src_compute, src_compute)
    return mapped_compute


def build_dot8_graph() -> Graph:
    # Build sum_{i=0..7} a[i]*b[i]
    g = Graph()
    # inputs: a0..a7, b0..b7
    for i in range(8):
        g.add_input(f"a{i}", 32)
        g.add_input(f"b{i}", 32)
    # generate partial products
    mul_ids: list[str] = []
    for i in range(8):
        gi = build_f32_mul_graph(a_name=f"a{i}", b_name=f"b{i}", out_name=f"p{i}")
        pid = _merge_with_prefix(
            g, gi, prefix=f"mul{i}",
            bind_inputs={f"a{i}": f"a{i}", f"b{i}": f"b{i}"},
            out_name=f"p{i}"
        )
        mul_ids.append(pid)
    # accumulate via adds
    acc_id = mul_ids[0]
    for i in range(1, 8):
        ai = build_f32_add_graph(a_name=f"acc{i-1}", b_name=f"p{i}", out_name=f"s{i}")
        acc_id = _merge_with_prefix(
            g, ai, prefix=f"add{i}",
            bind_inputs={
                f"acc{i-1}": acc_id,  # bind previous compute id
                f"p{i}": mul_ids[i],  # bind product compute id
            },
            out_name=f"s{i}"
        )
    g.set_output('dot', acc_id, 32)
    return g


def main():
    ap = argparse.ArgumentParser(description='Build/map an f32 dot-8 and report program size')
    ap.add_argument('--grid', type=str, default='64x64', help='grid size WxH for mapper limit (even dims)')
    args = ap.parse_args()
    W, H = map(int, args.grid.lower().split('x'))

    g = build_dot8_graph()
    est = size_graph(g)
    print(f"Estimate: cols~{est['cols']}, height_bits~{est['height_bits']}, cells~{est['cells']}")


if __name__ == '__main__':
    main()
