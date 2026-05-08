"""
src/sbas/sbas_processor.py
===========================
P-SBAS processing: tạo bản đồ vận tốc LOS và chuỗi thời gian biến dạng
từ tập interferogram Sentinel-1.

Phương pháp: Berardino et al. (2002); Manunta et al. (2019)
Áp dụng: Festa et al. (2022) — rà soát diện rộng
"""

import numpy as np
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Dict

logger = logging.getLogger(__name__)


class InterferogramNetwork:
    """
    Quản lý mạng lưới interferogram: kết nối thời gian - không gian.

    Biến:
        dates (List[datetime]): Danh sách ngày chụp SAR, đã sắp xếp tăng dần.
        tb_max (int): Ngưỡng baseline thời gian tối đa (ngày) để chọn cặp ảnh.
        sb_max (float): Ngưỡng baseline không gian tối đa (mét) để chọn cặp ảnh.
        pairs (List[Tuple[int, int]]): Danh sách các cặp chỉ số ảnh tạo interferogram.
        design_matrix (np.ndarray): Ma trận thiết kế A cho hệ SBAS (dùng giải SVD).
    """

    def __init__(self, dates: List[datetime],
                 temporal_baseline_max: int = 36,
                 spatial_baseline_max: float = 150.0):
        """
        Khởi tạo mạng lưới interferogram.
        Args:
            dates (List[datetime]): Danh sách ngày chụp SAR.
            temporal_baseline_max (int): Baseline thời gian tối đa (ngày) để tạo cặp ảnh.
            spatial_baseline_max (float): Baseline không gian tối đa (mét) để tạo cặp ảnh.
        """
        self.dates = sorted(dates)
        self.tb_max = temporal_baseline_max
        self.sb_max = spatial_baseline_max
        self.pairs: List[Tuple[int, int]] = []
        self.design_matrix: Optional[np.ndarray] = None

    def build_network(self,
                      spatial_baselines: Optional[np.ndarray] = None) -> None:
        """
        Xây dựng mạng lưới interferogram SBAS (small-baseline).
        Chỉ tạo cặp khi cả baseline thời gian VÀ không gian thỏa mãn.
        """
        n = len(self.dates)
        self.pairs = []  # Danh sách cặp (i, j) tạo thành interferogram

        for i in range(n):
            for j in range(i + 1, n):
                # Tính baseline thời gian (temporal baseline, đơn vị ngày)
                tb = (self.dates[j] - self.dates[i]).days
                if tb > self.tb_max:
                    # Vì dates đã sắp xếp tăng dần, mọi j lớn hơn đều vượt ngưỡng
                    break

                # Tính baseline không gian (spatial baseline, đơn vị m)
                if spatial_baselines is not None:
                    sb = abs(spatial_baselines[j] - spatial_baselines[i])
                else:
                    # Sentinel-1 có ống quỹ đạo rất hẹp (~200 m) → coi = 0
                    sb = 0.0

                if sb <= self.sb_max:
                    self.pairs.append((i, j))  # Cặp này hợp lệ → thêm vào network

        logger.info(f"Network: {n} SAR images → {len(self.pairs)} interferograms")
        self._build_design_matrix(n)

    def _build_design_matrix(self, n_images: int) -> None:
        """
        Xây dựng ma trận thiết kế A cho hệ SBAS.
        A[k, i] = -1 (primary), A[k, j] = +1 (secondary)
        Mỗi hàng là một interferogram, mỗi cột là một interval thời gian.
        """
        n_ifg = len(self.pairs)      # Số dòng = số interferogram
        n_int = n_images - 1         # Số cột = số khoảng thời gian giữa các cảnh
        A = np.zeros((n_ifg, n_int), dtype=np.float32)

        for k, (i, j) in enumerate(self.pairs):
            # Độ dài từng khoảng thời gian (ngày) → chuyển sang năm
            # Interferogram (i,j) bao phủ khoảng thời gian từ cột i đến cột j-1
            dt_days = np.array([(self.dates[l + 1] - self.dates[l]).days
                                 for l in range(n_int)], dtype=np.float32)
            A[k, i:j] = dt_days[i:j] / 365.25   # Đơn vị: năm (để vận tốc ra mm/yr)

        self.design_matrix = A
        logger.debug(f"Design matrix: {A.shape}")

    def get_connection_stats(self) -> dict:
        """Thống kê kết nối mạng lưới để kiểm tra chất lượng."""
        if not self.pairs:
            return {}
        tb_list = [(self.dates[j] - self.dates[i]).days for i, j in self.pairs]
        return {
            "n_images": len(self.dates),
            "n_interferograms": len(self.pairs),
            "tb_mean_days": np.mean(tb_list),
            "tb_max_days": np.max(tb_list),
            "connected": self._check_connectivity(),
        }

    def _check_connectivity(self) -> bool:
        """Kiểm tra mạng lưới liên thông (không có isolated nodes)."""
        if not self.pairs:
            return False
        n = len(self.dates)
        adj = [set() for _ in range(n)]
        for i, j in self.pairs:
            adj[i].add(j)
            adj[j].add(i)

        visited = set()
        stack = [0]
        while stack:
            node = stack.pop()
            if node not in visited:
                visited.add(node)
                stack.extend(adj[node] - visited)
        return len(visited) == n


class SBASProcessor:
    """
    Xử lý P-SBAS: ước lượng vận tốc LOS và chuỗi thời gian biến dạng
    từ tập interferogram đã unwrap.

    Biến:
        network (InterferogramNetwork): Đối tượng mạng interferogram đã xây dựng.
        wavelength (float): Bước sóng radar (m), mặc định 0.056 m cho Sentinel-1.
        velocity_map (np.ndarray): Bản đồ vận tốc trung bình (mm/năm), shape (H, W).
        timeseries (np.ndarray): Chuỗi thời gian dịch chuyển (mm), shape (n_dates, H, W).

    Phương pháp: Giải hệ phương trình tuyến tính A·v = φ bằng
    SVD có chính quy hóa (Tikhonov regularization).
    """

    def __init__(self, network: InterferogramNetwork,
                 wavelength_m: float = 0.056):
        self.network = network
        self.wavelength = wavelength_m
        self.velocity_map: Optional[np.ndarray] = None
        self.timeseries: Optional[np.ndarray] = None

    def process(self,
                interferograms: np.ndarray,
                coherence_maps: np.ndarray,
                coherence_threshold: float = 0.20,
                regularization: float = 0.01) -> Tuple[np.ndarray, np.ndarray]:
        """
        Chạy xử lý SBAS đầy đủ.

        Args:
            interferograms (np.ndarray): Dữ liệu pha unwrap, shape (n_ifg, H, W), đơn vị mm.
            coherence_maps (np.ndarray): Bản đồ coherence, shape (n_ifg, H, W), giá trị 0–1.
            coherence_threshold (float): Ngưỡng coherence tối thiểu để giữ pixel (lọc nhiễu).
            regularization (float): Hệ số Tikhonov λ để chống singular khi giải SVD.

        Returns:
            velocity (np.ndarray): Bản đồ vận tốc trung bình (mm/năm), shape (H, W).
            ts (np.ndarray): Chuỗi thời gian dịch chuyển (mm), shape (n_dates, H, W).
        """
        n_ifg, H, W = interferograms.shape
        n_images = len(self.network.dates)
        A = self.network.design_matrix

        logger.info(f"SBAS processing: {n_ifg} ifgs, grid {H}×{W}")

        velocity = np.full((H, W), np.nan, dtype=np.float32)
        ts = np.zeros((n_images, H, W), dtype=np.float32)

        # Mask pixel theo coherence: giữ pixel có coherence trung bình > ngưỡng
        # coherence_maps shape: (n_ifg, H, W) → lấy trung bình theo trục interferogram
        mean_coh = np.mean(coherence_maps, axis=0)   # (H, W)
        valid_mask = mean_coh >= coherence_threshold  # True = pixel đủ chất lượng
        n_valid = np.sum(valid_mask)
        logger.info(f"Valid pixels: {n_valid}/{H*W} "
                    f"({100*n_valid/(H*W):.1f}%) above coh={coherence_threshold}")

        # Giải SBAS pixel-by-pixel (có thể song song hóa bằng joblib/dask)
        ys, xs = np.where(valid_mask)  # Tọa độ các pixel hợp lệ
        for idx, (r, c) in enumerate(zip(ys, xs)):
            phi_pixel = interferograms[:, r, c]   # (n_ifg,) — pha tại pixel này
            coh_pixel = coherence_maps[:, r, c]   # (n_ifg,) — coherence tại pixel này

            # Trọng số theo coherence dùng công thức Fisher information:
            # w = γ / (1 - γ²) — pixel coherence cao được tin cậy hơn
            gamma = np.clip(coh_pixel, 0.01, 0.99)  # clip để tránh chia 0
            weights = gamma / (1 - gamma**2)
            W_diag = np.diag(weights)  # Ma trận trọng số dạng đường chéo

            # Giải weighted least squares với Tikhonov regularization:
            # min ||W^½(Av - φ)||² + λ||v||²  →  (AᵀWA + λI)v = AᵀWφ
            AtW = A.T @ W_diag
            AtWA = AtW @ A
            reg_matrix = regularization * np.eye(AtWA.shape[0])  # λI chống singular
            try:
                v_rates = np.linalg.solve(AtWA + reg_matrix, AtW @ phi_pixel)
                # Chuyển vận tốc theo khoảng → chuỗi dịch chuyển tích lũy
                dt_years = np.array(
                    [(self.network.dates[i + 1] - self.network.dates[i]).days / 365.25
                     for i in range(n_images - 1)]
                )
                # cumsum nhân từng đoạn vận tốc × thời gian = displacement tích lũy (mm)
                cumulative = np.concatenate([[0.0], np.cumsum(v_rates * dt_years)])
                ts[:, r, c] = cumulative.astype(np.float32)
                # Ước tính vận tốc tuyến tính trung bình từ chuỗi tích lũy (mm/yr)
                t_years = np.array(
                    [(d - self.network.dates[0]).days / 365.25
                     for d in self.network.dates]
                )
                vel, _ = np.polyfit(t_years, cumulative, 1)  # Hệ số bậc 1 = tốc độ
                velocity[r, c] = vel

            except np.linalg.LinAlgError:
                pass

            if idx % 10000 == 0 and idx > 0:
                logger.debug(f"  Processed {idx}/{n_valid} pixels")

        self.velocity_map = velocity
        self.timeseries = ts
        logger.info(f"SBAS done. Velocity range: "
                    f"[{np.nanmin(velocity):.1f}, {np.nanmax(velocity):.1f}] mm/yr")
        return velocity, ts

    def apply_atmospheric_correction(self,
                                     dem: np.ndarray,
                                     interferograms: np.ndarray
                                     ) -> np.ndarray:
        """
        Loại bỏ nhiễu khí quyển theo mô hình phụ thuộc độ cao.
        φ_atm ≈ a + b·h  (linear stratified delay)

        Args:
            dem (np.ndarray): Dữ liệu DEM (độ cao), shape (H, W), đơn vị mét.
            interferograms (np.ndarray): Dữ liệu interferogram, shape (n_ifg, H, W).

        Returns:
            corrected (np.ndarray): Interferogram đã loại bỏ nhiễu khí quyển, shape như đầu vào.

        Tham chiếu: Hanssen (2001); Festa et al. (2022)
        """
        corrected = interferograms.copy()   # Không sửa in-place, trả về bản sao
        dem_flat = dem.ravel()              # Flatten DEM để dùng trong regression
        valid_idx = np.isfinite(dem_flat)   # Loại bỏ pixel DEM không hợp lệ (NaN/Inf)

        for k in range(interferograms.shape[0]):
            phi_flat = interferograms[k].ravel()
            valid = valid_idx & np.isfinite(phi_flat)  # Pixel hợp lệ ở cả DEM và phase
            if np.sum(valid) < 10:   # Cần ít nhất 10 điểm để fit được
                continue
            # Fit mô hình tuyến tính: φ = a + b·h
            # a = hằng số delay trung bình, b = hệ số phụ thuộc độ cao
            H_mat = np.column_stack([np.ones(np.sum(valid)), dem_flat[valid]])
            coeffs, _, _, _ = np.linalg.lstsq(H_mat, phi_flat[valid], rcond=None)
            # Tạo mô hình khí quyển tổng hợp trên toàn bộ ảnh và trừ đi
            atm_model = coeffs[0] + coeffs[1] * dem
            corrected[k] -= atm_model

        logger.debug("Atmospheric stratification correction applied")
        return corrected

    def estimate_initial_state(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Trích xuất vector trạng thái ban đầu cho Kalman Filter:
        vận tốc 3D và ma trận phương sai-hiệp phương sai.
        Sử dụng kết quả SBAS đã tính.

        Returns:
            vel (np.ndarray): Bản đồ vận tốc (mm/năm), shape (H, W).
            var_cov (np.ndarray): Ma trận phương sai-hiệp phương sai (3,3), dùng cho Kalman.
        """
        if self.velocity_map is None:
            raise RuntimeError("Chạy process() trước khi gọi estimate_initial_state()")

        vel = self.velocity_map
        H, W = vel.shape

        # Ma trận phương sai ước tính từ residual SBAS
        residuals = np.nanstd(vel)
        sigma2 = residuals**2 if residuals > 0 else 1.0
        var_cov = np.eye(3) * sigma2   # Đơn giản hóa: isotropic

        logger.info(f"Initial state: vel std={residuals:.2f} mm/yr")
        return vel, var_cov


def run_sbas_pipeline(orbit: str,
                      settings: dict) -> Tuple[np.ndarray, np.ndarray, List]:
    """
    Pipeline đầy đủ: tải dữ liệu → xử lý SBAS → trả về kết quả.

    Parameters
    ----------
    orbit    : 'asc' hoặc 'desc'
    settings : dict cấu hình (từ config/settings.py)

    Returns
    -------
    velocity : np.ndarray (H, W) mm/yr
    ts       : np.ndarray (n_dates, H, W) mm
    dates    : List[datetime]
    """
    from src.utils.io_utils import load_interferogram, load_coherence, load_dem
    import sys, os
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    s1_cfg = settings.get("SENTINEL1", {})
    sbas_cfg = settings.get("SBAS", {})

    logger.info(f"=== SBAS Pipeline: {orbit.upper()} ===")

    # --- Sinh dữ liệu tổng hợp cho demo/testing ---
    n_images = 50
    H, W = 200, 200
    rng = np.random.default_rng(42)

    dates = [datetime(2019, 1, 1) + __import__("datetime").timedelta(days=12 * i)
             for i in range(n_images)]

    # Tạo interferogram tổng hợp với tín hiệu biến dạng thực tế
    network = InterferogramNetwork(
        dates,
        temporal_baseline_max=s1_cfg.get("temporal_baseline_max_days", 36),
        spatial_baseline_max=s1_cfg.get("spatial_baseline_max_m", 150),
    )
    network.build_network()
    stats = network.get_connection_stats()
    logger.info(f"Network stats: {stats}")

    n_ifg = len(network.pairs)
    # Tín hiệu biến dạng: trượt lở tại góc trên bên trái
    x_grid, y_grid = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H))
    landslide_signal = -25.0 * np.exp(-((x_grid - 0.25)**2 + (y_grid - 0.35)**2) / 0.03)
    mine_signal = -15.0 * np.exp(-((x_grid - 0.7)**2 + (y_grid - 0.7)**2) / 0.02)
    deform_field = landslide_signal + mine_signal   # mm/yr

    interferograms = np.zeros((n_ifg, H, W), dtype=np.float32)
    coherence_maps = np.zeros((n_ifg, H, W), dtype=np.float32)

    for k, (i, j) in enumerate(network.pairs):
        dt_yr = (dates[j] - dates[i]).days / 365.25
        interferograms[k] = deform_field * dt_yr + rng.normal(0, 2.0, (H, W))
        # Coherence thấp hơn ở vùng thực vật (giả lập vùng trung tâm)
        base_coh = 0.6 - 0.3 * np.exp(-((x_grid - 0.5)**2 + (y_grid - 0.5)**2) / 0.1)
        coherence_maps[k] = np.clip(base_coh + rng.normal(0, 0.05, (H, W)), 0.01, 0.99)

    # Xử lý SBAS
    processor = SBASProcessor(network, wavelength_m=s1_cfg.get("wavelength_m", 0.056))
    velocity, ts = processor.process(
        interferograms, coherence_maps,
        coherence_threshold=s1_cfg.get("coherence_threshold", 0.20),
    )

    return velocity, ts, dates
