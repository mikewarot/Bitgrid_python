from __future__ import annotations

import os
from ..int.u8_add import build_u8_add_graph
from ..mapper import Mapper


def main():
    g = build_u8_add_graph('a', 'b', 's')
    os.makedirs('out', exist_ok=True)
    g.save('out/u8_add_graph.json')
    prog = Mapper(grid_width=512, grid_height=128).map(g)
    with open('out/u8_add_program.json', 'w', encoding='utf-8') as f:
        f.write(prog.to_json())
    print('Wrote out/u8_add_graph.json and out/u8_add_program.json')


if __name__ == '__main__':
    main()
