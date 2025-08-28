from __future__ import annotations

import argparse
from ..estimator import Tech, estimate_transformer_madds_per_token, estimate_cells_from_madds, estimate_area_power


def main():
    ap = argparse.ArgumentParser(description='Estimate BitGrid size/area/power for a transformer LLM')
    ap.add_argument('--layers', type=int, required=True, help='Number of transformer layers (decoder-only)')
    ap.add_argument('--d-model', type=int, required=True, help='Model width (hidden size)')
    ap.add_argument('--d-ff', type=int, required=True, help='Feed-forward expansion size')
    ap.add_argument('--seq-len', type=int, required=True, help='Context length for attention work per token')
    ap.add_argument('--precision', type=int, default=8, help='Effective precision in bits (affects MAC LUT cost)')
    ap.add_argument('--luts-per-mac32', type=float, default=64.0, help='LUT4s per 32-bit MAC equivalent')
    ap.add_argument('--luts-per-cell', type=int, default=4, help='LUT4s per BitGrid cell')
    ap.add_argument('--freq-ghz', type=float, default=1.0, help='Operating frequency in GHz')
    # Tech params
    ap.add_argument('--cell-area-um2', type=float, default=10.0, help='Area of one BitGrid cell (um^2)')
    ap.add_argument('--e-toggle-fj', type=float, default=1.0, help='Energy per cell toggle (fJ)')
    ap.add_argument('--avg-toggles', type=float, default=0.15, help='Average toggles per cell per cycle')
    ap.add_argument('--leak-nw', type=float, default=0.5, help='Leakage per cell (nW)')
    args = ap.parse_args()

    madds = estimate_transformer_madds_per_token(args.layers, args.d_model, args.d_ff, args.seq_len)
    mac = estimate_cells_from_madds(madds, luts_per_mac32=args.luts_per_mac32, luts_per_cell=args.luts_per_cell, precision_bits=args.precision)
    tech = Tech(cell_area_um2=args.cell_area_um2, luts_per_cell=args.luts_per_cell, e_toggle_fJ=args.e_toggle_fj, avg_toggles_per_cell=args.avg_toggles, cell_leakage_nW=args.leak_nw)
    apwr = estimate_area_power(mac['cells'], args.freq_ghz, tech)

    print(f"Per-token MAdds: {madds:,.0f}")
    print(f"Estimated LUT4s: {mac['luts']:,.0f}")
    print(f"Estimated cells: {mac['cells']:,.0f}")
    print(f"Area (mm^2): {apwr['area_mm2']:,.2f}")
    print(f"Power: dyn={apwr['dyn_watts']:.1f} W, leak={apwr['leak_watts']:.1f} W, total={apwr['total_watts']:.1f} W")


if __name__ == '__main__':
    main()
