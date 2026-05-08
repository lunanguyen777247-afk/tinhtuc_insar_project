"""
src/visualization/plotter.py
==============================
Vẽ bản đồ, biểu đồ chuỗi thời gian và strain invariants.
Tương đương Fig. 3-12 trong Zheng et al. (2026) và Festa et al. (2022).
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")   # Non-interactive backend cho server
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.gridspec import GridSpec
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Màu sắc chuẩn cho phân loại MAC
CLASS_COLORS = {
    "landslide":              "#E74C3C",
    "potential_landslide":    "#F39C12",
    "mine_subsidence":        "#2C3E50",
    "mixed_deformation":      "#9B59B6",
    "earthquake_deformation": "#8E44AD",
    "potential_subsidence":   "#3498DB",
    "potential_uplift":       "#27AE60",
    "dump_site":              "#795548",
    "construction_site":      "#607D8B",
    "unclassified":           "#95A5A6",
}


def plot_velocity_map(velocity: np.ndarray,
                       orbit: str,
                       output_path: Path,
                       vmin: float = -30,
                       vmax: float = 30,
                       title: str = "") -> None:
    """
    Vẽ bản đồ vận tốc LOS (mm/yr).
    Tương đương Fig. 3 trong Festa et al. (2022).
    """
    fig, ax = plt.subplots(figsize=(10, 8))

    # RdYlGn_r: đỏ = lún (tiêu cực), xanh = trồi/ổn định
    im = ax.imshow(velocity, cmap="RdYlGn_r", vmin=vmin, vmax=vmax,
                   aspect="auto", origin="upper")
    cbar = plt.colorbar(im, ax=ax, shrink=0.7, label="LOS velocity (mm/yr)")

    ax.set_title(f"P-SBAS Velocity Map — {orbit.upper()} orbit\n{title}",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Column (E→W)")
    ax.set_ylabel("Row (N→S)")

    # Hiển thị dải giá trị toàn bức ảnh (chỉ pixel hợp lệ)
    valid = velocity[np.isfinite(velocity)]
    if len(valid) > 0:
        ax.text(0.02, 0.02,
                f"Range: [{np.nanmin(valid):.1f}, {np.nanmax(valid):.1f}] mm/yr",
                transform=ax.transAxes, fontsize=9, color="white",
                bbox=dict(boxstyle="round", facecolor="black", alpha=0.5))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()  # Giải phóng bộ nhớ: quan trọng khi vẽ nhiều hình trong pipeline
    logger.info(f"Saved velocity map: {output_path}")


def plot_mac_classification(velocity: np.ndarray,
                              macs: List[Dict],
                              output_path: Path) -> None:
    """
    Vẽ bản đồ MACs phân loại chồng lên bản đồ vận tốc.
    Tương đương Fig. 8 trong Festa et al. (2022).
    """
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Bản đồ vận tốc làm nền (grayscale thẩm mĩ); alpha=0.6 cho thấy MAC bên trên
    for ax in axes:
        ax.imshow(velocity, cmap="gray", alpha=0.6, aspect="auto", origin="upper")

    # Vẽ MACs theo phân loại
    ax_map, ax_pie = axes[0], axes[1]

    class_counts = {}
    for mac in macs:
        cls = mac.get("classification", "unclassified")
        color = CLASS_COLORS.get(cls, "#95A5A6")
        class_counts[cls] = class_counts.get(cls, 0) + 1

        pixels = mac.get("pixel_indices", [])
        if pixels and isinstance(pixels[0], (list, tuple)):
            # scatter từng pixel: chính xác hơn imshow nhưng chận hơn với MAC lớn
            rows = [p[0] for p in pixels]
            cols = [p[1] for p in pixels]
            ax_map.scatter(cols, rows, c=color, s=1, alpha=0.7)

    ax_map.set_title("Moving Area Clusters (MACs)\nTĩnh Túc, Cao Bằng",
                      fontsize=11, fontweight="bold")
    ax_map.set_xlabel("Column"); ax_map.set_ylabel("Row")

    # Legend: tạo một Patch cho mỗi loại MAC xuất hiện
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=CLASS_COLORS.get(cls, "#95A5A6"), label=cls)
                       for cls in class_counts.keys()]
    ax_map.legend(handles=legend_elements, loc="upper right",
                  fontsize=7, framealpha=0.8)

    # Pie chart: tỉ lệ các loại MAC
    if class_counts:
        labels = list(class_counts.keys())
        sizes = list(class_counts.values())
        colors = [CLASS_COLORS.get(l, "#95A5A6") for l in labels]
        ax_pie.pie(sizes, labels=labels, colors=colors, autopct="%1.1f%%",
                   startangle=90, textprops={"fontsize": 8})
        ax_pie.set_title(f"Classification Distribution\n(n={sum(sizes)} MACs)",
                         fontsize=11, fontweight="bold")
    else:
        ax_pie.text(0.5, 0.5, "No MACs classified", ha="center", va="center")
        ax_pie.axis("off")

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved MAC classification map: {output_path}")


def plot_4d_movements(movements_4d: Dict[str, np.ndarray],
                       selected_dates: List[str],
                       output_path: Path) -> None:
    """
    Vẽ bản đồ 4D movements cho các ngày được chọn.
    Tương đương Fig. 4 trong Zheng et al. (2026).
    """
    # Cãu hình: colormap RdBu_r (nhọ = chào sang đỏ = dương)
    # vlims: giới hạn hiển thị khác nhau cho từng thành phần
    components = ["east", "north", "vertical"]
    cmaps = {"east": "RdBu_r", "north": "RdBu_r", "vertical": "RdBu_r"}
    vlims = {"east": (-100, 100), "north": (-50, 50), "vertical": (-100, 50)}
    units = "mm"

    n_dates = len(selected_dates)
    n_comp = len(components)
    # Lưới các ảnh: hàng = thành phần (E/N/V), cột = ngày
    fig, axes = plt.subplots(n_comp, n_dates,
                              figsize=(3.5 * n_dates, 3.5 * n_comp))
    # Đảm bảo axes luôn là 2D ngay cả khi chỉ có 1 ngày hoặc 1 component
    if n_dates == 1:
        axes = axes.reshape(-1, 1)
    if n_comp == 1:
        axes = axes.reshape(1, -1)

    for ci, comp in enumerate(components):
        data = movements_4d.get(comp)
        if data is None:
            continue
        vmin, vmax = vlims[comp]

        for di, date_str in enumerate(selected_dates):
            ax = axes[ci][di]
            # Lấy frame ứng với ngày dị (theo index, không phải tìm kiếm chính xác)
            if data.ndim == 3 and di < data.shape[0]:
                frame = data[di]   # (H, W) cho ngày di
            elif data.ndim == 2:
                frame = data       # Snapshot đơn
            else:
                frame = np.zeros((50, 50))  # Placeholder rỗng

            im = ax.imshow(frame, cmap=cmaps[comp], vmin=vmin, vmax=vmax,
                           aspect="auto", origin="upper")
            if di == 0:  # Chỉ label hàng ở cột đầu
                ax.set_ylabel(comp.capitalize(), fontsize=10, fontweight="bold")
            if ci == 0:  # Chỉ title ở hàng đầu
                ax.set_title(date_str, fontsize=9, rotation=30)
            ax.set_xticks([]); ax.set_yticks([])  # Không cần tick (pixel index)

            # Chỉ hiển thị colorbar ở cột cuối
            plt.colorbar(im, ax=ax, shrink=0.7,
                         label=f"{units}" if di == n_dates - 1 else "")

    fig.suptitle("Daily 4D Movements — Tĩnh Túc Hotspot\n(East | North | Vertical)",
                 fontsize=13, fontweight="bold", y=1.01)
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved 4D movements plot: {output_path}")


def plot_timeseries_with_hydromet(timeseries_points: Dict[str, Dict],
                                   hydro_data: Dict[str, np.ndarray],
                                   dates: List,
                                   output_path: Path) -> None:
    """
    Vẽ chuỗi thời gian dịch chuyển cùng với dữ liệu khí tượng.
    Tương đương Fig. 5 trong Zheng et al. (2026).
    """
    components = ["east", "north", "vertical"]
    comp_colors = {"P1": "#2196F3", "P2": "#F44336", "P3": "#4CAF50"}  # Màu theo hotspot
    n_comp = len(components)

    # GridSpec: n_comp hàng displacement + 1 hàng khí tượng
    fig = plt.figure(figsize=(16, 12))
    gs = GridSpec(n_comp + 1, 1, hspace=0.05, figure=fig)

    # Hàng cuối: khí tượng thủy văn (mưa và độ ẩm đất)
    ax_hydro = fig.add_subplot(gs[n_comp])
    rain = hydro_data.get("rainfall_mm", np.zeros(len(dates)))
    sm = hydro_data.get("soil_moisture", np.full(len(dates), 0.3))

    date_nums = np.arange(len(dates))  # Trục x: số ngày từ bắt đầu
    # Bar chart mưa: dễ nhìn thấy đỉnh mưa theo ngày
    ax_hydro.bar(date_nums, rain, color="#64B5F6", alpha=0.7, label="Rainfall (mm/day)")
    # Đường độ ẩm đất: trục phụ (twin axis) vì đơn vị khác
    ax_hydro2 = ax_hydro.twinx()
    ax_hydro2.plot(date_nums, sm, "g-", linewidth=1.5, label="Soil moisture")
    ax_hydro.set_ylabel("Rainfall (mm)", color="#1565C0")
    ax_hydro2.set_ylabel("Soil moisture (m³/m³)", color="green")
    ax_hydro.set_xlabel("Time steps (days)")
    ax_hydro.grid(True, alpha=0.3)

    # Các hàng trên: chuỗi thời gian dịch chuyển E, N, V của từng hotspot
    for ci, comp in enumerate(components):
        ax = fig.add_subplot(gs[ci], sharex=ax_hydro)  # Chia sẻ trục x với khí tượng
        ax.set_ylabel(f"{comp.capitalize()} (mm)", fontsize=10)
        ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")  # Đường tham chiếu = 0
        ax.grid(True, alpha=0.3)

        for pt_name, pt_data in timeseries_points.items():
            ts = pt_data.get(comp, np.zeros(len(dates)))
            color = comp_colors.get(pt_name, "#9E9E9E")
            ax.plot(date_nums[:len(ts)], ts[:len(date_nums)],
                    "-o", markersize=3, color=color, linewidth=1.5,
                    label=pt_name, alpha=0.85)

        if ci == 0:
            ax.legend(loc="upper left", fontsize=9)
        plt.setp(ax.get_xticklabels(), visible=(ci == n_comp - 1))

    fig.suptitle("4D Movements & Hydrometeorological Data — Tĩnh Túc",
                 fontsize=13, fontweight="bold")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved timeseries plot: {output_path}")


def plot_strain_invariants(mss: np.ndarray,
                            dil: np.ndarray,
                            dem: np.ndarray,
                            output_path: Path) -> None:
    """
    Vẽ bản đồ Maximum Shear Strain và Dilatation.
    Tương đương Fig. 11 trong Zheng et al. (2026).
    """
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # MSS
    vmax_mss = np.nanpercentile(mss, 98)
    im1 = axes[0].imshow(mss, cmap="hot_r", vmin=0, vmax=vmax_mss,
                          aspect="auto", origin="upper")
    plt.colorbar(im1, ax=axes[0], label="MSS (×10⁻³)")
    axes[0].set_title("Maximum Shear Strain", fontweight="bold")

    # Dilatation
    dil_abs = np.nanpercentile(np.abs(dil), 98)
    im2 = axes[1].imshow(dil, cmap="RdBu_r", vmin=-dil_abs, vmax=dil_abs,
                          aspect="auto", origin="upper")
    plt.colorbar(im2, ax=axes[1], label="DIL (×10⁻³)")
    axes[1].set_title("Dilatation", fontweight="bold")
    axes[1].text(0.02, 0.98, "Blue=Compression\nRed=Extension",
                 transform=axes[1].transAxes, fontsize=8, va="top",
                 bbox=dict(boxstyle="round", facecolor="white", alpha=0.7))

    # DEM + contours
    im3 = axes[2].imshow(dem, cmap="terrain", aspect="auto", origin="upper")
    plt.colorbar(im3, ax=axes[2], label="Elevation (m)")
    axes[2].contour(mss, levels=5, colors="red", linewidths=0.5, alpha=0.6)
    axes[2].set_title("DEM + MSS contours", fontweight="bold")

    for ax in axes:
        ax.set_xlabel("Column"); ax.set_ylabel("Row")

    plt.suptitle("Strain Invariants — Tĩnh Túc Landslide",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved strain invariants plot: {output_path}")


def plot_efficiency_comparison(kf_times: List[float],
                                tikho_times: List[float],
                                kf_rmse: List[float],
                                tikho_rmse: List[float],
                                output_path: Path) -> None:
    """
    So sánh hiệu quả cập nhật KF vs Tikhonov.
    Tương đương Fig. 8 trong Zheng et al. (2026).
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

    n = range(len(kf_times))

    # Thời gian xử lý
    ax1.plot(n, tikho_times, "r-o", markersize=4, label="Tikhonov (traditional)",
             linewidth=2)
    ax1.plot(n, kf_times, "g-o", markersize=4, label="KF Fusion (proposed)",
             linewidth=2)
    ax1.set_ylabel("Processing Time (s)", fontsize=11)
    ax1.set_title("Computational Efficiency Comparison", fontsize=12, fontweight="bold")
    ax1.legend(fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_yscale("log")

    # RMSE so sánh
    ax2.plot(n, tikho_rmse, "r-s", markersize=4, label="Tikhonov RMSE",
             linewidth=2)
    ax2.plot(n, kf_rmse, "g-s", markersize=4, label="KF Fusion RMSE",
             linewidth=2)
    ax2.axhline(10.0, color="orange", linestyle="--", label="Target: 10mm")
    ax2.set_xlabel("Number of updating SLCs", fontsize=11)
    ax2.set_ylabel("RMSE (mm)", fontsize=11)
    ax2.set_title("Monitoring Accuracy (RMSE)", fontsize=12, fontweight="bold")
    ax2.legend(fontsize=10)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved efficiency comparison: {output_path}")
