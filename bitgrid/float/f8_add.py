from __future__ import annotations

from ..graph import Graph, Node


def build_f8_add_graph(a_name: str = 'a', b_name: str = 'b', out_name: str = 's', fmt: str = 'e4m3') -> Graph:
    # FP8 add (E4M3) — equal-exponent add with normalization and simple half-up rounding on discarded bit
    if fmt.lower() != 'e4m3':
        raise ValueError('Only E4M3 supported in this prototype')
    EXP_BITS = 4
    FRAC_BITS = 3

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

    sa = bit(a_name, 7)
    sb = bit(b_name, 7)
    ea_bits = [bit(a_name, i) for i in range(FRAC_BITS, FRAC_BITS + EXP_BITS)]
    eb_bits = [bit(b_name, i) for i in range(FRAC_BITS, FRAC_BITS + EXP_BITS)]
    fa_bits = [bit(a_name, i) for i in range(0, FRAC_BITS)]
    fb_bits = [bit(b_name, i) for i in range(0, FRAC_BITS)]

    ea = pack_bits('ea', ea_bits, EXP_BITS)
    eb = pack_bits('eb', eb_bits, EXP_BITS)
    ma = pack_bits('ma', [*fa_bits, const(1, 1)], FRAC_BITS + 1)
    mb = pack_bits('mb', [*fb_bits, const(1, 1)], FRAC_BITS + 1)

    # Equal-exponent add path
    addm = 'addm'; add(addm, 'ADD', [ma, mb], FRAC_BITS + 2)  # width 5
    carry = 'carry'; add(carry, 'BIT', [addm], 1, {'index': FRAC_BITS + 1})

    # Normalized mantissa candidate (mN) by optional right shift when carry=1
    m_shift = 'm_shift'; add(m_shift, 'SHR', [addm, const(1, 3)], FRAC_BITS + 2, {'amount': 1})
    notc = 'notc'; add(notc, 'NOT', [carry], 1)
    m_keep0 = 'm_keep0'; add(m_keep0, 'AND', [addm, notc], FRAC_BITS + 2)
    m_take1 = 'm_take1'; add(m_take1, 'AND', [m_shift, carry], FRAC_BITS + 2)
    mN = 'mN'; add(mN, 'OR', [m_keep0, m_take1], FRAC_BITS + 2)

    # Exponent: base equals ea; increment by carry
    ea_x = 'ea_x'; add(ea_x, 'ADD', [ea, const(0, 1)], EXP_BITS + 1)
    e_inc = 'e_inc'; add(e_inc, 'ADD', [ea_x, const(1, 1)], EXP_BITS + 1)
    e_keep0 = 'e_keep0'; add(e_keep0, 'AND', [ea_x, notc], EXP_BITS + 1)
    e_take1 = 'e_take1'; add(e_take1, 'AND', [e_inc, carry], EXP_BITS + 1)
    eN = 'eN'; add(eN, 'OR', [e_keep0, e_take1], EXP_BITS + 1)

    # Select fraction bits to keep (low FRAC_BITS of mN) and compute guard based on discarded LSB when carry=1
    # frac_pre = mN[0..FRAC_BITS-1]
    frac_pre = const(0, FRAC_BITS)
    for i in range(FRAC_BITS):
        bi = f"fpre_b{i}"; add(bi, 'BIT', [mN], 1, {'index': i})
        shi = f"fpre_s{i}"; add(shi, 'SHL', [bi, const(i, 3)], FRAC_BITS, {'amount': i})
        fri = f"fpre_or{i}"; add(fri, 'OR', [frac_pre, shi], FRAC_BITS); frac_pre = fri
    # guard = carry ? addm bit0 : 0
    addm_b0 = 'addm_b0'; add(addm_b0, 'BIT', [addm], 1, {'index': 0})
    g_take = 'g_take'; add(g_take, 'AND', [addm_b0, carry], 1)
    gbit = 'gbit'; add(gbit, 'OR', [g_take, const(0, 1)], 1)

    # Round half-up on guard
    rounded = 'rounded'; add(rounded, 'ADD', [frac_pre, gbit], FRAC_BITS + 1)
    rcarry = 'rcarry'; add(rcarry, 'BIT', [rounded], 1, {'index': FRAC_BITS})

    # Exponent after rounding overflow
    eN_plus = 'eN_plus'; add(eN_plus, 'ADD', [eN, const(1, 1)], EXP_BITS + 1)
    rnc = 'rnc'; add(rnc, 'NOT', [rcarry], 1)
    e_keep = 'e_keep'; add(e_keep, 'AND', [eN, rnc], EXP_BITS + 1)
    e_take = 'e_take'; add(e_take, 'AND', [eN_plus, rcarry], EXP_BITS + 1)
    e_final = 'e_final'; add(e_final, 'OR', [e_keep, e_take], EXP_BITS + 1)

    # Final fraction: when rounding overflow, zero; else take rounded[0..FRAC_BITS-1]
    frac_bits_out = []
    for i in range(FRAC_BITS):
        rbi = f"rfo_{i}"; add(rbi, 'BIT', [rounded], 1, {'index': i})
        take = f"rf_t{i}"; add(take, 'AND', [rbi, rnc], 1)
        frac_bits_out.append(take)

    # Pack exponent bits from e_final
    exp_bits_out = []
    for i in range(EXP_BITS):
        bi = f"eo_{i}"; add(bi, 'BIT', [e_final], 1, {'index': i}); exp_bits_out.append(bi)

    # Pack into 8 bits: frac (0..2), exp (3..6), sign (7)
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
