from __future__ import annotations

import math


def encode_fp8_e4m3(x: float) -> int:
    """Encode Python float to FP8 E4M3 (sign=1, exp=4, frac=3). Simplified:
    - normals and zero; subnormals flushed to zero; inf/NaN saturated to max finite.
    - round-to-nearest, ties to away from zero (approx via +0.5 then clamp).
    Returns 0..255.
    """
    if x == 0.0 or not math.isfinite(x):
        if not math.isfinite(x):
            # saturate to max finite with sign
            s = 1 if math.copysign(1.0, x) < 0 else 0
            return (s << 7) | (0xE << 3) | 0x7
        return 0
    s = 1 if x < 0 else 0
    v = abs(x)
    m, e = math.frexp(v)  # v = m * 2^e, m in [0.5,1)
    m *= 2.0
    e -= 1
    bias = 7
    E = e + bias
    if E <= 0:
        return 0  # flush subnormals for now
    if E >= 0xF:
        E = 0xE
        frac = 0x7
        return (s << 7) | (E << 3) | frac
    # quantize fractional part to 3 bits
    frac_f = max(0.0, min(1.0, m - 1.0))
    q = int(frac_f * (1 << 3) + 0.5)
    if q == (1 << 3):
        q = 0
        E += 1
        if E >= 0xF:
            E = 0xE
            q = 0x7
    return ((s & 1) << 7) | ((E & 0xF) << 3) | (q & 0x7)


def decode_fp8_e4m3(b: int) -> float:
    """Decode FP8 E4M3 byte (0..255) to Python float. Subnormals treated as zero; inf/NaN not represented."""
    b &= 0xFF
    s = (b >> 7) & 1
    E = (b >> 3) & 0xF
    F = b & 0x7
    if E == 0 and F == 0:
        return -0.0 if s else 0.0
    bias = 7
    # treat as normalized always (subnormals skipped)
    e = E - bias
    m = 1.0 + (F / (1 << 3))
    val = math.ldexp(m, e)
    return -val if s else val
