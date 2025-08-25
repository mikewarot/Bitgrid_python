from __future__ import annotations

from ..float.f8_add import build_f8_add_graph
from ..mapper import Mapper
from ..emulator import Emulator


def main():
    g = build_f8_add_graph('a', 'b', 's')
    # expose internal nodes if present
    for nid in ['ea', 'eb', 'ma', 'mb', 'addm', 'mN', 'eN', 'e_same_x', 'e_inc']:
        if nid in g.nodes:
            g.set_output(f"dbg_{nid}", nid, g.nodes[nid].width)
    prog = Mapper(grid_width=512, grid_height=128).map(g)
    emu = Emulator(prog)
    res = emu.run([{'a': 0x38, 'b': 0x38}])[0]
    print({k: hex(v) if isinstance(v, int) else v for k, v in res.items()})


if __name__ == '__main__':
    main()
