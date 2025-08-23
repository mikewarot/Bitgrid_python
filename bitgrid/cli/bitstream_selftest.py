from __future__ import annotations

from ..program import Program, Cell
from ..bitstream import pack_program_bitstream, unpack_bitstream_to_luts, apply_luts_to_program


def main():
    # Tiny 2x2 with characteristic LUT patterns per direction
    p = Program(width=2, height=2, cells=[
        Cell(x=0, y=0, inputs=[], op='LUT', params={'luts': [0xAAAA, 0, 0, 0]}),  # N: toggles every 1
        Cell(x=1, y=0, inputs=[], op='LUT', params={'luts': [0, 0xCCCC, 0, 0]}),  # E: toggles every 2
        Cell(x=0, y=1, inputs=[], op='LUT', params={'luts': [0, 0, 0xF0F0, 0]}),  # S: toggles every 4
        Cell(x=1, y=1, inputs=[], op='LUT', params={'luts': [0, 0, 0, 0xFF00]}),  # W: toggles every 8
    ], input_bits={}, output_bits={}, latency=0)

    for order in ('row-major', 'col-major', 'snake'):
        bs = pack_program_bitstream(p, order=order)
        luts = unpack_bitstream_to_luts(bs, p.width, p.height, order=order)
        q = apply_luts_to_program(Program(width=p.width, height=p.height, cells=[], input_bits={}, output_bits={}, latency=0), luts)
        mp = {(c.x, c.y): c for c in p.cells}
        ok = True
        for c in q.cells:
            expect = mp[(c.x, c.y)].params['luts']
            got = c.params['luts']
            if got != expect:
                print(f'[{order}] mismatch at {(c.x, c.y)}: {got} != {expect}')
                ok = False
        print(f'[{order}] roundtrip ok: {ok}; bytes={len(bs)}')


if __name__ == '__main__':
    main()
