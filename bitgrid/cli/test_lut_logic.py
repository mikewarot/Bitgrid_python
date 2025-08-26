from __future__ import annotations

from ..lut_logic import compile_expr_to_lut, decompile_lut_to_expr


def expect(expr: str, expected_hex: str):
    got = compile_expr_to_lut(expr)
    got_hex = f"0x{got:04X}"
    assert got_hex == expected_hex, f"{expr}: expected {expected_hex}, got {got_hex}"


def run():
    # Single variables (indexing: idx = N | (E<<1) | (S<<2) | (W<<3))
    # That yields a bit set wherever the variable is 1 across 16 combinations -> repeated 8/4/2/1 patterns
    expect("N", "0xAAAA")  # 1010 repeating every 1 bit
    expect("E", "0xCCCC")  # 1100 repeating every 2 bits
    expect("S", "0xF0F0")  # 11110000 ...
    expect("W", "0xFF00")  # high half

    # Basic ops
    expect("N & E", "0x8888")
    expect("N | E", "0xEEEE")
    expect("N ^ E", "0x6666")
    expect("!N", "0x5555")
    expect("~E", "0x3333")
    expect("(N & S) | (E & W)", "0xECA0")

    print("OK")

    # Round-trip: expr -> lut -> expr' -> lut
    for expr in [
        "N", "E", "S", "W",
        "N & E", "N | E", "N ^ E",
        "!N", "(~E)", "(N & S) | (E & W)",
        "(N & !E) | (!N & E)",
    ]:
        lut = compile_expr_to_lut(expr)
        expr2 = decompile_lut_to_expr(lut)
        lut2 = compile_expr_to_lut(expr2)
        assert lut == lut2, f"Round-trip failed for {expr}: {hex(lut)} vs {hex(lut2)} via {expr2}"


if __name__ == "__main__":
    run()
