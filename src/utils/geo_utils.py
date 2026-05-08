"""
src/utils/geo_utils.py
======================
Tiện ích tính toán địa lý và véctơ SAR.
"""

import numpy as np
from typing import Tuple, Dict


# ─────────────────────────────────────────────────────────────
# 1. TÍNH TOÁN VÉCTƠ LOS
# ─────────────────────────────────────────────────────────────

def compute_los_vector(incidence_deg: float,
                       heading_deg: float) -> Dict[str, float]:
    """
    Tính véctơ đơn vị LOS từ tham số quỹ đạo vệ tinh.

    Parameters
    ----------
    incidence_deg : float — góc tới (degree), đo từ thẳng đứng
    heading_deg   : float — góc phương vị vệ tinh (degree, dương CW từ Bắc)

    Returns
    -------
    dict với keys 'east', 'north', 'vertical'

    Tham chiếu: Hanssen (2001); Hu et al. (2014)
    """
    inc = np.radians(incidence_deg)
    head = np.radians(heading_deg)

    # Quy ước: dương = về phía vệ tinh (range decrease = chuyển động lại gần vệ tinh)
    # E: âm vì orbit descending hướng đầu về phía Tây (bais hướng East)
    east = -np.cos(head) * np.sin(inc)
    # N: thành phần Bắc, nhỏ — Sentinel-1 gần cực’nên heading gần 0
    north = np.sin(head) * np.sin(inc)
    # V: lớn nhất (cosin góc tới) — SAR nhạy nhất với thành phần thẳng đứng
    vertical = np.cos(inc)

    return {"east": east, "north": north, "vertical": vertical}


def compute_spf_coefficients(dem: np.ndarray,
                              dx: float, dy: float
                              ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Tính hệ số ràng buộc Surface-Parallel Flow (SPF) từ DEM.

    SPF giả định chuyển động dọc theo sườn dốc:
        0 = θe·xe + θn·xn - xv
        0 = cos(θasp)/sin(θasp)·xe - xn

    Parameters
    ----------
    dem : np.ndarray(H, W)  — elevation (m)
    dx, dy : float          — độ phân giải pixel (m)

    Returns
    -------
    theta_e, theta_n : gradient địa hình theo E, N
    theta_asp        : góc aspect

    Tham chiếu: Joughin et al. (1998); Zheng et al. (2026)
    """
    # Gradient địa hình (chính xác: central difference bên trong, forward/backward tại biên)
    grad_e = np.gradient(dem, dx, axis=1)   # ∂z/∂x (hướng East)
    grad_n = np.gradient(dem, dy, axis=0)   # ∂z/∂y (hướng North)

    # Aspect: góc của mặt dốc trong mặt phẳng nằm ngang
    # arctan2 trả về góc tính từ East, ngược chiều kim
    theta_asp = np.arctan2(grad_n, grad_e)

    return grad_e, grad_n, theta_asp


def los_to_3d(los_asc: np.ndarray, los_desc: np.ndarray,
              los_vec_asc: Dict[str, float],
              los_vec_desc: Dict[str, float],
              grad_e: np.ndarray = None,
              grad_n: np.ndarray = None,
              theta_asp: np.ndarray = None) -> Dict[str, np.ndarray]:
    """
    Phân tách dịch chuyển LOS thành 3 thành phần (East, North, Vertical).
    Sử dụng ràng buộc SPF khi có DEM.

    Parameters
    ----------
    los_asc, los_desc : np.ndarray — vận tốc LOS (mm/yr)
    los_vec_asc/desc  : dict       — véctơ đơn vị LOS
    grad_e, grad_n, theta_asp     — hệ số SPF (tùy chọn)

    Returns
    -------
    dict với keys 'east', 'north', 'vertical' (np.ndarray, mm/yr)
    """
    H, W = los_asc.shape

    ea, na, va = los_vec_asc["east"], los_vec_asc["north"], los_vec_asc["vertical"]
    ed, nd, vd = los_vec_desc["east"], los_vec_desc["north"], los_vec_desc["vertical"]

    east = np.full((H, W), np.nan, dtype=np.float64)
    north = np.full((H, W), np.nan, dtype=np.float64)
    vert = np.full((H, W), np.nan, dtype=np.float64)

    if grad_e is not None:
        # Dùng SPF: 3 phương trình (2 LOS + 1 SPF), 3 ẩn (xe, xn, xv)
        for i in range(H):
            for j in range(W):
                A = np.array([
                    [ea, na, va],
                    [ed, nd, vd],
                    [grad_e[i, j], grad_n[i, j], -1.0],
                ])
                b = np.array([los_asc[i, j], los_desc[i, j], 0.0])
                try:
                    sol = np.linalg.lstsq(A, b, rcond=None)[0]
                    east[i, j], north[i, j], vert[i, j] = sol
                except np.linalg.LinAlgError:
                    pass
    else:
        # 2 quan sát, bỏ qua N-S (xấp xỉ phổ biến)
        # [ea, va; ed, vd] · [xe, xv]ᵀ = [los_asc, los_desc]ᵀ
        A = np.array([[ea, va], [ed, vd]])
        try:
            inv_A = np.linalg.inv(A)
            stack = np.stack([los_asc.ravel(), los_desc.ravel()])
            sol = inv_A @ stack
            east = sol[0].reshape(H, W)
            vert = sol[1].reshape(H, W)
            north = np.zeros((H, W))
        except np.linalg.LinAlgError:
            pass

    return {"east": east, "north": north, "vertical": vert}


# ─────────────────────────────────────────────────────────────
# 2. PHÂN TÁCH THÀNH PHẦN 2D (Festa et al., 2022)
# ─────────────────────────────────────────────────────────────

def decompose_2d(v_asc: np.ndarray, v_desc: np.ndarray,
                 inc_asc: float, head_asc: float,
                 inc_desc: float, head_desc: float
                 ) -> Tuple[np.ndarray, np.ndarray]:
    """
    Phân tách LOS ascending + descending thành thành phần
    Thẳng đứng (VV) và Nằm ngang E-W (VH).

    Công thức: Notti et al. (2014); Festa et al. (2022)
    """
    inc_a, hd_a = np.radians(inc_asc), np.radians(head_asc)
    inc_d, hd_d = np.radians(inc_desc), np.radians(head_desc)

    # Hệ số nhạy cảm LOS: hếy chiếu của các thành phần V và H
    # Theo quy ước hu hếy địa lý của Notti et al. (2014)
    hlos_a = np.cos(hd_a)          # Họ số thành phần ngang đượng thiết gián
    elos_a = np.cos(np.pi / 2 - hd_a) * np.cos(3 * np.pi / 2 - inc_a)  # thành phần đứng
    hlos_d = np.cos(hd_d)
    elos_d = np.cos(np.pi / 2 - hd_d) * np.cos(3 * np.pi / 2 - inc_d)

    # Mẫu số phân tích: khác 0 khi 2 quỹ đạo có góc tới khác nhau
    denom_v = (hlos_d / elos_d - hlos_a / elos_a)
    denom_h = (elos_d / hlos_d - elos_a / hlos_a)

    eps = 1e-10  # Tránh chia cho 0 khi các góc quá gần nhau
    vv = (v_desc / elos_d - v_asc / elos_a) / (denom_v + eps)   # Thẳng đứng (mm/yr)
    vh = (v_desc / hlos_d - v_asc / hlos_a) / (denom_h + eps)   # Nằm ngang E-W (mm/yr)

    return vv, vh


def compute_kvh(vv: np.ndarray, vh: np.ndarray) -> np.ndarray:
    """
    Tính tỷ số KVH = |VV| / |VH|.
    KVH > 1 → lún / trồi; KVH < 1 → trượt ngang.
    """
    eps = 1e-6
    return np.abs(vv) / (np.abs(vh) + eps)


# ─────────────────────────────────────────────────────────────
# 3. TÍNH TOÁN ĐỊA HÌNH
# ─────────────────────────────────────────────────────────────

def compute_slope(dem: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Tính độ dốc địa hình (degree)."""
    gy, gx = np.gradient(dem, dy, dx)
    slope_rad = np.arctan(np.sqrt(gx**2 + gy**2))
    return np.degrees(slope_rad)


def compute_aspect(dem: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Tính aspect (degree, 0°=Bắc, tăng CW)."""
    gy, gx = np.gradient(dem, dy, dx)
    aspect = np.degrees(np.arctan2(-gx, gy))
    return (aspect + 360) % 360


def cramer_rao_bound(coherence: np.ndarray,
                     wavelength_m: float,
                     n_looks: int = 4) -> np.ndarray:
    """
    Tính Cramer-Rao Bound cho độ lệch chuẩn pha.
    σ_φ ≈ (1/√(2·Nlook)) · √(1-γ²)/γ
    Chuyển sang mm: σ_d = σ_φ · λ / (4π)

    Tham chiếu: Zheng et al. (2026) — dùng đánh giá tiền giám sát
    """
    gamma = np.clip(np.abs(coherence), 1e-6, 1.0 - 1e-6)  # Tránh chia 0 và log(0)
    # Công thức CRB cho ước toán phase từ interferogram N look
    # sigma_phi: độ lệch chuẩn pha (radian)
    sigma_phi = (1.0 / np.sqrt(2 * n_looks)) * np.sqrt(1 - gamma**2) / gamma
    # Chuyển pha (radian) sang dichês chuyển (mm): d = phi * lambda / (4*pi)
    sigma_mm = sigma_phi * wavelength_m * 1000 / (4 * np.pi)
    return sigma_mm
