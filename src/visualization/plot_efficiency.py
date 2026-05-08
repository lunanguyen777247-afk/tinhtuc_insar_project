"""
src/visualization/plot_efficiency.py
======================================
Vẽ biểu đồ so sánh hiệu quả KF vs Tikhonov (Fig. 8 của Zheng et al. 2026).
Chạy độc lập: python src/visualization/plot_efficiency.py
"""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
from pathlib import Path
from src.visualization.plotter import plot_efficiency_comparison

def simulate_efficiency_comparison(n_updates: int = 200):
    """
    Mô phỏng thời gian xử lý và RMSE của hai phương pháp.
    Theo kết quả định tính từ Zheng et al. (2026), Fig. 8:
      - Tikhonov: thời gian tăng bậc hai theo số SLC
      - KF Fusion: thời gian gần như hằng số (~2s)
    """
    rng = np.random.default_rng(42)
    n = n_updates

    # Tikhonov: O(n²) thời gian, RMSE tăng dần
    tikho_times = [(0.5 + i * 0.07 + rng.uniform(0, 0.3)) for i in range(n)]
    tikho_rmse_e = [8.0 + i * 0.06 + rng.normal(0, 1.0) for i in range(n)]
    tikho_rmse_e = np.clip(tikho_rmse_e, 5, 50).tolist()

    # KF Fusion: O(1) thời gian sau bước đầu, RMSE ổn định
    kf_times = [93.0 if i == 0 else 1.5 + rng.uniform(0, 0.5) for i in range(n)]
    kf_rmse_e = [9.5 + rng.normal(0, 0.8) for _ in range(n)]
    kf_rmse_e = np.clip(kf_rmse_e, 3, 15).tolist()

    return kf_times, tikho_times, kf_rmse_e, tikho_rmse_e

if __name__ == "__main__":
    kf_t, tk_t, kf_r, tk_r = simulate_efficiency_comparison(200)
    out = Path(__file__).parent.parent.parent / "outputs" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    plot_efficiency_comparison(kf_t, tk_t, kf_r, tk_r,
                                out / "efficiency_comparison.png")
    print(f"Saved: {out / 'efficiency_comparison.png'}")
