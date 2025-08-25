from __future__ import annotations

from ..graph import Graph, Node


def build_u8_add_graph(a_name: str = 'a', b_name: str = 'b', out_name: str = 's') -> Graph:
    g = Graph()
    g.add_input(a_name, 8)
    g.add_input(b_name, 8)
    # Single 8-bit add (mod 256): drop carry beyond 8 bits by using width=8
    g.add_node(Node(id='sum8', op='ADD', inputs=[a_name, b_name], width=8, params={}))
    g.set_output(out_name, 'sum8', 8)
    return g
