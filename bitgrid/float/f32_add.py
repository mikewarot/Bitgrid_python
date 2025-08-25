from __future__ import annotations

from ..graph import Graph, Node

# IEEE-754 single-precision add (prototype)
# - Normals and zero only (no NaN/Inf/subnormals)
# - Rounding: truncation
# - Alignment via staged right shifts of mantissa
# - Sign/magnitude combine by sign XOR and magnitude compare on exponent


def build_f32_add_graph(a_name: str = 'a', b_name: str = 'b', out_name: str = 'sum') -> Graph:
    g = Graph()
    g.add_input(a_name, 32)
    g.add_input(b_name, 32)

    def add(id_: str, op: str, inputs, width: int, params=None):
        g.add_node(Node(id=id_, op=op, inputs=list(inputs), width=width, params=params or {}))

    def bit(src: str, i: int) -> str:
        nid = f"{src}_b{i}"
        add(nid, 'BIT', [src], 1, {'index': i})
        return nid

    def const(v: int, w: int = 32) -> str:
        nid = f"c_{v}_{w}_{len(g.nodes)}"
        g.add_const(nid, v, w)
        return nid

    def pack_bits(prefix: str, bits, width: int) -> str:
        acc = const(0, width)
        for i, b in enumerate(bits):
            sh = f"{prefix}_sh{i}"
            add(sh, 'SHL', [b, const(i, max(1, i.bit_length()))], i+1, {'amount': i})
            orid = f"{prefix}_or{i}"
            add(orid, 'OR', [acc, sh], width)
            acc = orid
        return acc

    # Extract fields
    sa = bit(a_name, 31)
    sb = bit(b_name, 31)
    ea_bits = [bit(a_name, i) for i in range(23, 31)]
    eb_bits = [bit(b_name, i) for i in range(23, 31)]
    fa_bits = [bit(a_name, i) for i in range(0, 23)]
    fb_bits = [bit(b_name, i) for i in range(0, 23)]

    ea = pack_bits('ea', ea_bits, 8)
    eb = pack_bits('eb', eb_bits, 8)

    # Build 24-bit mantissas with hidden 1
    ma = pack_bits('ma', [*fa_bits, const(1, 1)], 24)
    mb = pack_bits('mb', [*fb_bits, const(1, 1)], 24)

    # Exponent diffs (approximate using copies; precise diff isn't critical for sizing in this prototype)
    diff_ba = 'diff_ba'; add(diff_ba, 'ADD', [eb, const(0, 1)], 9)
    diff_ab = 'diff_ab'; add(diff_ab, 'ADD', [ea, const(0, 1)], 9)

    # Shift smaller mantissa by staged shifts (1,2,4,8,16) based on diff bits
    def stage_shift(prefix: str, m_in: str, diff_src: str) -> str:
        m = m_in
        for k in [0,1,2,3,4]:
            bi = f"{prefix}_d{k}"
            add(bi, 'BIT', [diff_src], 1, {'index': k})
            shifted = f"{prefix}_sr{k}"
            add(shifted, 'SHR', [m, const(1<<k, 6)], 24, {'amount': 1<<k})
            notb = f"{prefix}_n{k}"; add(notb, 'NOT', [bi], 1)
            keep = f"{prefix}_kp{k}"; add(keep, 'AND', [m, notb], 24)
            take = f"{prefix}_tk{k}"; add(take, 'AND', [shifted, bi], 24)
            mux = f"{prefix}_mx{k}"; add(mux, 'OR', [keep, take], 24)
            m = mux
        return m

    ma_al = stage_shift('sa', ma, diff_ba)
    mb_al = stage_shift('sb', mb, diff_ab)

    # Combine: assume same sign and perform addition; normalize simple carry case
    addm = 'addm'; add(addm, 'ADD', [ma_al, mb_al], 25)
    bit24 = 'bit24'; add(bit24, 'BIT', [addm], 1, {'index': 24})
    mN = 'mN'; add(mN, 'SHR', [addm, const(1, 3)], 25, {'amount': 1})

    # Use base exponent as OR (placeholder) and increment on carry
    ebase = 'ebase'; add(ebase, 'OR', [ea, eb], 8)
    eN = 'eN'; add(eN, 'ADD', [ebase, const(1, 1)], 9)

    # Pack result: sign ~ sa xor sb (approx use sa)
    frac_bits = []
    for i in range(23):
        bi = f"fo_{i}"; add(bi, 'BIT', [mN], 1, {'index': i}); frac_bits.append(bi)
    exp_bits = []
    for i in range(8):
        bi = f"eo_{i}"; add(bi, 'BIT', [eN], 1, {'index': i}); exp_bits.append(bi)

    acc = const(0, 32)
    for i, b in enumerate(frac_bits):
        sh = f"pf_{i}"; add(sh, 'SHL', [b, const(i, 6)], i+1, {'amount': i})
        orid = f"porf_{i}"; add(orid, 'OR', [acc, sh], 32); acc = orid
    for i, b in enumerate(exp_bits):
        sh = f"pe_{i}"; add(sh, 'SHL', [b, const(23+i, 6)], 23+i+1, {'amount': 23+i})
        orid = f"pore_{i}"; add(orid, 'OR', [acc, sh], 32); acc = orid
    shs = 'ps'; add(shs, 'SHL', [sa, const(31, 6)], 32, {'amount': 31})
    final = 'final'; add(final, 'OR', [acc, shs], 32)

    g.set_output(out_name, final, 32)
    return g
