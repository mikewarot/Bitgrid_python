from __future__ import annotations

from ..graph import Graph, Node


def build_f8_mul_graph(a_name: str = 'a', b_name: str = 'b', out_name: str = 'p', fmt: str = 'e4m3') -> Graph:
    # FP8 multiply (prototype for sizing) — supports E4M3 by default
    if fmt.lower() != 'e4m3':
        raise ValueError('Only E4M3 supported in this prototype')
    EXP_BITS = 4
    FRAC_BITS = 3
    BIAS = 7

    g = Graph()
    g.add_input(a_name, 8)
    g.add_input(b_name, 8)

    def add(id_: str, op: str, inputs, width: int, params=None):
        g.add_node(Node(id=id_, op=op, inputs=list(inputs), width=width, params=params or {}))

    def bit(src: str, i: int) -> str:
        nid = f"{src}_b{i}"
        add(nid, 'BIT', [src], 1, {'index': i})
        return nid

    def const(v: int, w: int = 8) -> str:
        nid = f"c_{v}_{w}_{len(g.nodes)}"
        g.add_const(nid, v, w)
        return nid

    def pack_bits(prefix: str, bits, width: int) -> str:
        acc = const(0, width)
        for i, b in enumerate(bits):
            sh = f"{prefix}_sh{i}"
            add(sh, 'SHL', [b, const(i, 3)], width, {'amount': i})
            orid = f"{prefix}_or{i}"
            add(orid, 'OR', [acc, sh], width)
            acc = orid
        return acc

    # Fields
    sa = bit(a_name, 7)
    sb = bit(b_name, 7)
    ea_bits = [bit(a_name, i) for i in range(FRAC_BITS, FRAC_BITS + EXP_BITS)]
    eb_bits = [bit(b_name, i) for i in range(FRAC_BITS, FRAC_BITS + EXP_BITS)]
    fa_bits = [bit(a_name, i) for i in range(0, FRAC_BITS)]
    fb_bits = [bit(b_name, i) for i in range(0, FRAC_BITS)]

    ea = pack_bits('ea', ea_bits, EXP_BITS)
    eb = pack_bits('eb', eb_bits, EXP_BITS)

    # Mantissas with hidden 1 (normals only)
    ma = pack_bits('ma', [*fa_bits, const(1, 1)], FRAC_BITS + 1)  # 4 bits
    mb = pack_bits('mb', [*fb_bits, const(1, 1)], FRAC_BITS + 1)

    # 4x4 -> 8-bit multiply via shift-add
    acc = None
    for i in range(FRAC_BITS + 1):
        bi = f"bbit{i}"; add(bi, 'BIT', [mb], 1, {'index': i})
        shi = f"sh{i}"; add(shi, 'SHL', [ma, const(i, 3)], (FRAC_BITS + 1) + i, {'amount': i})
        andi = f"and{i}"; add(andi, 'AND', [shi, bi], (FRAC_BITS + 1) + i)
        if acc is None:
            acc = andi
        else:
            sumi = f"add{i}"; add(sumi, 'ADD', [acc, andi], (FRAC_BITS + 1) * 2)
            acc = sumi
    mm = acc  # up to 8 bits

    # Exponent add and rebias
    e_sum = 'e_sum'; add(e_sum, 'ADD', [ea, eb], EXP_BITS + 1)
    e_tmp = 'e_tmp'; add(e_tmp, 'ADD', [e_sum, const(-BIAS, EXP_BITS + 1)], EXP_BITS + 1)

    # Normalize: if top of mm set, shift right 1 and inc exp; else keep mm and e_tmp
    top = 'm_top'; add(top, 'BIT', [mm], 1, {'index': (FRAC_BITS + 1) * 2 - 1})
    m_shift = 'm_shift'; add(m_shift, 'SHR', [mm, const(1, 3)], (FRAC_BITS + 1) * 2, {'amount': 1})
    e_inc = 'e_inc'; add(e_inc, 'ADD', [e_tmp, const(1, 1)], EXP_BITS + 1)
    top_n = 'm_top_n'; add(top_n, 'NOT', [top], 1)
    m_keep0 = 'm_keep0'; add(m_keep0, 'AND', [mm, top_n], (FRAC_BITS + 1) * 2)
    m_take1 = 'm_take1'; add(m_take1, 'AND', [m_shift, top], (FRAC_BITS + 1) * 2)
    mN = 'mN'; add(mN, 'OR', [m_keep0, m_take1], (FRAC_BITS + 1) * 2)
    e_keep0 = 'e_keep0'; add(e_keep0, 'AND', [e_tmp, top_n], EXP_BITS + 1)
    e_take1 = 'e_take1'; add(e_take1, 'AND', [e_inc, top], EXP_BITS + 1)
    eN = 'eN'; add(eN, 'OR', [e_keep0, e_take1], EXP_BITS + 1)

    # Rounding: take low FRAC_BITS of mN and add guard bit (next bit)
    frac_pre = const(0, FRAC_BITS)
    for i in range(FRAC_BITS):
        bi = f"fpre_b{i}"; add(bi, 'BIT', [mN], 1, {'index': i})
        shi = f"fpre_s{i}"; add(shi, 'SHL', [bi, const(i, 3)], FRAC_BITS, {'amount': i})
        fri = f"fpre_or{i}"; add(fri, 'OR', [frac_pre, shi], FRAC_BITS); frac_pre = fri
    gbit = 'gbit'; add(gbit, 'BIT', [mN], 1, {'index': FRAC_BITS})
    rounded = 'rounded'; add(rounded, 'ADD', [frac_pre, gbit], FRAC_BITS + 1)
    rcarry = 'rcarry'; add(rcarry, 'BIT', [rounded], 1, {'index': FRAC_BITS})

    # Exponent increment on rounding overflow
    eN_plus = 'eN_plus'; add(eN_plus, 'ADD', [eN, const(1, 1)], EXP_BITS + 1)
    rnc = 'rnc'; add(rnc, 'NOT', [rcarry], 1)
    e_keep = 'e_keep'; add(e_keep, 'AND', [eN, rnc], EXP_BITS + 1)
    e_take = 'e_take'; add(e_take, 'AND', [eN_plus, rcarry], EXP_BITS + 1)
    e_final = 'e_final'; add(e_final, 'OR', [e_keep, e_take], EXP_BITS + 1)

    # Final fraction bits (zero when rounding overflow)
    frac_bits_out = []
    for i in range(FRAC_BITS):
        rbi = f"rfo_{i}"; add(rbi, 'BIT', [rounded], 1, {'index': i})
        take = f"rf_t{i}"; add(take, 'AND', [rbi, rnc], 1)
        frac_bits_out.append(take)

    # Pack exponent bits from e_final
    exp_bits_out = []
    for i in range(EXP_BITS):
        bi = f"eo_{i}"; add(bi, 'BIT', [e_final], 1, {'index': i}); exp_bits_out.append(bi)

    acc8 = const(0, 8)
    for i, b in enumerate(frac_bits_out):
        sh = f"pf_{i}"; add(sh, 'SHL', [b, const(i, 3)], 8, {'amount': i})
        orid = f"porf_{i}"; add(orid, 'OR', [acc8, sh], 8); acc8 = orid
    for i, b in enumerate(exp_bits_out):
        sh = f"pe_{i}"; add(sh, 'SHL', [b, const(FRAC_BITS + i, 3)], 8, {'amount': FRAC_BITS + i})
        orid = f"pore_{i}"; add(orid, 'OR', [acc8, sh], 8); acc8 = orid
    shs = 'ps'; add(shs, 'SHL', [sa, const(7, 4)], 8, {'amount': 7})
    final = 'final'; add(final, 'OR', [acc8, shs], 8)

    g.set_output(out_name, final, 8)
    return g
