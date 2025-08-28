from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class Tech:
    # Technology/implementation assumptions (tunable)
    cell_area_um2: float = 10.0  # area of one BitGrid cell (4x LUT4 + latches) in square microns
    luts_per_cell: int = 4       # number of 4-input LUTs per BitGrid cell
    e_toggle_fJ: float = 1.0     # energy per cell output toggle (femtojoules)
    avg_toggles_per_cell: float = 0.15  # average fraction of cell outputs toggling each cycle
    cell_leakage_nW: float = 0.5  # leakage per cell (nanowatts)


def estimate_transformer_madds_per_token(layers: int, d_model: int, d_ff: int, seq_len: int) -> float:
    """Very rough per-token MAdds for a decoder-only transformer with KV cache.

    Formula (per layer, per token):
      - Projections (Q,K,V,Out): ~4 * d_model^2 multiplies
      - MLP: ~2 * d_model * d_ff multiplies
      - Attention with KV cache: ~2 * d_model * seq_len multiplies (scores + weighted sum)
    FLOPs per layer ~ 2x the above; MAdds = FLOPs / 2 ~ the above terms.
    """
    per_layer_madds = 4.0 * d_model * d_model + 2.0 * d_model * d_ff + 2.0 * d_model * seq_len
    return layers * per_layer_madds


def estimate_cells_from_madds(
    madds_per_token: float,
    luts_per_mac32: float = 64.0,
    luts_per_cell: int = 4,
    precision_bits: int = 8,
) -> Dict[str, float]:
    """Map MAdds to BitGrid LUT/cell counts.

    - Assumes a 32-bit MAC equivalent costs luts_per_mac32 LUT4s at target timing; scale by precision.
    - cells ~= (total LUTs) / luts_per_cell.
    Returns dict with luts and cells estimates.
    """
    # Scale by precision: crude linear scaling vs 32-bit
    scale = max(1.0, precision_bits / 32.0)
    total_luts = madds_per_token * luts_per_mac32 * scale
    cells = total_luts / max(1, luts_per_cell)
    return {"luts": total_luts, "cells": cells}


def estimate_area_power(
    cells: float,
    freq_ghz: float,
    tech: Tech,
) -> Dict[str, float]:
    """Compute area (mm^2) and power (W) from cell count and assumptions."""
    area_mm2 = cells * tech.cell_area_um2 * 1e-6  # um^2 to mm^2
    # Dynamic power: E = N_toggles * e_toggle; P = E * f
    # Assume avg toggles per cell per cycle across outputs is tech.avg_toggles_per_cell
    # Use e_toggle per cell-equivalent (approx)
    dyn_watts = cells * tech.avg_toggles_per_cell * tech.e_toggle_fJ * 1e-15 * (freq_ghz * 1e9)
    leak_watts = cells * tech.cell_leakage_nW * 1e-9
    total_watts = dyn_watts + leak_watts
    return {
        "area_mm2": area_mm2,
        "dyn_watts": dyn_watts,
        "leak_watts": leak_watts,
        "total_watts": total_watts,
    }
