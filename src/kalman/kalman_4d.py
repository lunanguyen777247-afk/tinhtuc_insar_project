"""
src/kalman/kalman_4d.py
========================
Spatiotemporal-constrained Kalman Filter để ước lượng chuyển động 4D hàng ngày.

Phương pháp: Zheng et al. (2026), Section 3.1
  - Ràng buộc không gian: Surface-Parallel Flow (SPF)
  - Ràng buộc thời gian: Time-dependent smooth process
  - Xử lý outlier: Huber weight function
"""

import numpy as np
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Tuple, List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class KalmanState:
    """
    Vector trạng thái của Kalman Filter tại một thời điểm.
    Lưu trữ lịch sử n bước để tính ràng buộc thời gian.
    """
    # Dịch chuyển tích lũy (mm): n_steps × 3 (East, North, Vertical)
    displacement: np.ndarray       # shape (n_steps, 3)
    # Ma trận phương sai-hiệp phương sai: (3×n_steps, 3×n_steps)
    var_cov: np.ndarray
    timestamps: List[datetime] = field(default_factory=list)
    n_steps: int = 5               # Số bước lịch sử giữ lại


class SpatiotemporalKalmanFilter:
    """
    Kalman Filter với ràng buộc không-thời gian cho giám sát 4D.

    Dùng cho MỘT điểm quan trắc (pixel). Gọi song song cho nhiều điểm.

    Tham chiếu: Zheng et al. (2026); Liu et al. (2022a)
    """

    def __init__(self,
                 n_steps: int = 5,
                 poly_order: int = 2,
                 huber_delta: float = 1.5,
                 use_spf: bool = True,
                 spf_coeffs: Optional[Dict] = None):
        """
        Parameters
        ----------
        n_steps      : số bước thời gian trước dùng trong STE (n=5 theo Zheng et al.)
        poly_order   : bậc đa thức nội suy (m=2 theo Zheng et al.)
        huber_delta  : ngưỡng hàm Huber để xử lý outlier
        use_spf      : có dùng ràng buộc SPF không
        spf_coeffs   : {'theta_e': float, 'theta_n': float, 'theta_asp': float}
                       từ DEM — BẮT BUỘC nếu use_spf=True
        """
        self.n = n_steps
        self.m = poly_order
        self.huber_delta = huber_delta
        self.use_spf = use_spf
        self.spf = spf_coeffs or {"theta_e": 0.1, "theta_n": 0.1, "theta_asp": 0.5}

        # Kích thước state vector = 3 hướng × n_steps
        self.state_dim = 3 * n_steps
        self.state: Optional[KalmanState] = None

    # ──────────────────────────────────────────────────────────
    # KHỞI TẠO
    # ──────────────────────────────────────────────────────────

    def initialize(self,
                   initial_velocity_3d: np.ndarray,
                   initial_var_cov: np.ndarray,
                   start_dates: List[datetime]) -> None:
        """
        Khởi tạo state vector từ kết quả SBAS.

        Args:
            initial_velocity_3d (np.ndarray): Vận tốc ban đầu (mm/năm), shape (3,) [East, North, Vertical].
            initial_var_cov (np.ndarray): Ma trận phương sai (3,3) cho mỗi hướng.
            start_dates (List[datetime]): Danh sách ngày khởi tạo state.

        Biến nội bộ:
            displ (np.ndarray): Dịch chuyển tích lũy từng bước, shape (n, 3).
            full_var (np.ndarray): Ma trận phương sai cho toàn bộ state vector, shape (3*n, 3*n).
        """
        n = self.n
        dt_years = np.array([
            (start_dates[i] - start_dates[0]).days / 365.25
            for i in range(min(n, len(start_dates)))
        ])

        # Dịch chuyển tích lũy = vận tốc × thời gian
        displ = np.zeros((n, 3))
        for i in range(min(n, len(dt_years))):
            displ[i] = initial_velocity_3d * dt_years[i]

        # Mở rộng ma trận phương sai cho n bước
        full_var = np.kron(np.eye(n), initial_var_cov)

        self.state = KalmanState(
            displacement=displ,
            var_cov=full_var,
            timestamps=list(start_dates[:n]),
            n_steps=n,
        )
        logger.debug(f"KF initialized: state dim={self.state_dim}, n_steps={n}")

    # ──────────────────────────────────────────────────────────
    # PHƯƠNG TRÌNH CHUYỂN TRẠNG THÁI (STE)
    # ──────────────────────────────────────────────────────────

    def _build_temporal_transition(self, dt_days: float) -> np.ndarray:
        """
        Xây dựng ma trận chuyển trạng thái thời gian Be.
        Time-dependent smooth process (Liu et al., 2022a; Zheng et al., 2026).

        x̂_{e,i} = [1, Δt, Δt², ..., Δtⁿ] · (BᵢᵀBᵢ)⁻¹ · Bᵢᵀ · X̂_{e,i-1}
        """
        n, m = self.n, self.m
        dt_i = dt_days / 365.25  # Convert to years

        # Ma trận Bi: lịch sử thời gian của n bước trước
        # Mỗi hàng: [1, Δt_{i-k}, Δt²_{i-k}, ...]
        B = np.zeros((n, m + 1))
        for k in range(n):
            dt_k = (k + 1) * 12 / 365.25  # Ước tính: 12 ngày/cảnh
            for p in range(m + 1):
                B[k, p] = dt_k ** p

        # Véctơ interpolation: [1, Δtᵢ, Δtᵢ², ...]
        interp = np.array([dt_i ** p for p in range(m + 1)])

        # ω = interp · (BᵀB)⁻¹ · Bᵀ
        try:
            BtB_inv = np.linalg.inv(B.T @ B + 1e-8 * np.eye(m + 1))
            omega = interp @ BtB_inv @ B.T   # shape (n,)
        except np.linalg.LinAlgError:
            omega = np.zeros(n)
            omega[0] = 1.0

        # Be matrix: chuyển từ n bước trước sang bước hiện tại
        Be = np.zeros((n, n))
        Be[0, :] = omega           # Hàng đầu: dự báo bước mới
        Be[1:, :-1] = np.eye(n - 1)  # Dịch chuyển bước cũ

        return Be

    def _build_spatial_transition(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Xây dựng hệ số ràng buộc SPF.
        Fe = [1, 0, 0]
        Fn = [cos(θasp)/sin(θasp), 0, 0]  (aspect constraint)
        Fv = [θe, θn, 0]                   (gradient constraint)
        """
        te, tn = self.spf["theta_e"], self.spf["theta_n"]
        asp = self.spf["theta_asp"]

        cos_asp = np.cos(asp)
        sin_asp = np.sin(asp) if abs(np.sin(asp)) > 1e-6 else 1e-6

        Fe = np.array([1.0, 0.0, 0.0])
        Fn = np.array([cos_asp / sin_asp, -1.0, 0.0])
        Fv = np.array([te, tn, -1.0])

        return Fe, Fn, Fv

    def predict(self, dt_days: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Bước dự báo (prediction step) của KF.

        X̂⁻ᵢ = F · X̂ᵢ₋₁
        D⁻_{X̂,i} = F · D_{X̂,i-1} · Fᵀ + Qᵢ

        Returns
        -------
        state_pred  : np.ndarray (state_dim,)
        var_pred    : np.ndarray (state_dim, state_dim)
        """
        if self.state is None:
            raise RuntimeError("Gọi initialize() trước predict()")

        n = self.n
        # Xây dựng ma trận chuyển trạng thái Be cho bước đầu tiên (STE)
        Be = self._build_temporal_transition(dt_days)

        if self.use_spf:
            Fe, Fn, Fv = self._build_spatial_transition()
            # Ma trận F block-diagonal: mỗi hướng (E, N, V) dùng cùng Be
            # Phân giải đơn giản hóa: bỏ qua coupling giữa hướng
            # F = diag(Be, Be, Be) với ràng buộc SPF được xử lý trong update()
            F = np.zeros((3 * n, 3 * n))
            F[0:n, 0:n] = Be         # Thành phần East
            F[n:2*n, n:2*n] = Be     # Thành phần North
            F[2*n:3*n, 2*n:3*n] = Be # Thành phần Vertical
        else:
            # Không SPF: 3 thành phần độc lập hoàn toàn
            F = np.zeros((3 * n, 3 * n))
            F[0:n, 0:n] = Be
            F[n:2*n, n:2*n] = Be
            F[2*n:3*n, 2*n:3*n] = Be

        # Flatten state vector: thứ tự [E_0..E_{n-1}, N_0..N_{n-1}, V_0..V_{n-1}]
        # .T.ravel() đảm bảo thứ tự đúng khi displacement có shape (n, 3)
        x_prev = self.state.displacement.T.ravel()  # (3n,)
        D_prev = self.state.var_cov

        # Ước lượng process noise Q thích nghi (adaptive)
        Q = self._estimate_process_noise(D_prev)

        # Bước dự báo:
        # X̂^-_i = F · X̂_{i-1}        (state prediction)
        # D^-_{X̂,i} = F · D_{X̂,i-1} · F^T + Q  (covariance prediction)
        x_pred = F @ x_prev
        D_pred = F @ D_prev @ F.T + Q

        return x_pred, D_pred

    def _estimate_process_noise(self, D_prev: np.ndarray) -> np.ndarray:
        """
        Ước tính process noise Q adaptively.
        Q_i được ước tính từ Q_{i-1} theo Liu et al. (2022a).
        Đơn giản hóa: Q = α × D_prev
        """
        alpha = 0.1  # Hệ số noise
        return alpha * np.diag(np.diag(D_prev))

    # ──────────────────────────────────────────────────────────
    # PHƯƠNG TRÌNH CẬP NHẬT TRẠNG THÁI (SUE)
    # ──────────────────────────────────────────────────────────

    def _build_observation_matrix(self,
                                   los_vectors: List[Dict[str, float]],
                                   n_ifg: int) -> np.ndarray:
        """
        Xây dựng ma trận quan sát H kết hợp ràng buộc không gian SPF.
        L = H · X̂⁻ᵢ = [obsLOS, 0, 0]ᵀ

        Tham chiếu: Zheng et al. (2026), Eq. (8), (9)
        """
        n = self.n
        n_obs = len(los_vectors) * n_ifg + (2 if self.use_spf else 0)
        H = np.zeros((n_obs, 3 * n))

        # Quan sát LOS
        for track_idx, los in enumerate(los_vectors):
            ea, na, va = los["east"], los["north"], los["vertical"]
            for ifg_idx in range(n_ifg):
                row = track_idx * n_ifg + ifg_idx
                H[row, ifg_idx] = ea          # East component
                H[row, n + ifg_idx] = na      # North component
                H[row, 2*n + ifg_idx] = va    # Vertical component

        # Ràng buộc SPF
        if self.use_spf:
            te, tn = self.spf["theta_e"], self.spf["theta_n"]
            asp = self.spf["theta_asp"]
            cos_asp = np.cos(asp)
            sin_asp = np.sin(asp) if abs(np.sin(asp)) > 1e-6 else 1e-6
            # Ràng buộc gradient: θe·xe + θn·xn - xv = 0
            H[-2, 0] = te; H[-2, n] = tn; H[-2, 2*n] = -1.0
            # Ràng buộc aspect: cos(asp)/sin(asp)·xe - xn = 0
            H[-1, 0] = cos_asp / sin_asp; H[-1, n] = -1.0

        return H

    def update(self,
               x_pred: np.ndarray,
               D_pred: np.ndarray,
               observations: np.ndarray,
               obs_var_cov: np.ndarray,
               los_vectors: List[Dict[str, float]],
               n_ifg: int = 1) -> Tuple[np.ndarray, np.ndarray]:
        """
        Bước cập nhật (update step) của KF.

        X̂ᵢ = X̂⁻ᵢ + KGM·(L - H·X̂⁻ᵢ)
        D_{X̂,i} = (E - KGM·H)·D⁻_{X̂,i}

        Parameters
        ----------
        x_pred, D_pred   : kết quả từ predict()
        observations     : np.ndarray — giá trị LOS đo được (mm)
        obs_var_cov      : ma trận phương sai quan sát
        los_vectors      : list véctơ LOS cho từng track
        n_ifg            : số interferogram mới

        Returns
        -------
        x_updated, D_updated
        """
        H = self._build_observation_matrix(los_vectors, n_ifg)
        n_state = H.shape[1]
        n_obs = len(observations)

        # Đệm đếm quan sát với ràng buộc SPF (pad bằng 0 tương ứng)
        if H.shape[0] > n_obs:
            observations_padded = np.zeros(H.shape[0])
            observations_padded[:n_obs] = observations  # Điền quan sát thực
            # Phương sai ràng buộc SPF rất nhỏ (1e-6) = cơng buộc mạnh
            padded_var = np.zeros((H.shape[0], H.shape[0]))
            padded_var[:n_obs, :n_obs] = obs_var_cov
            padded_var[n_obs:, n_obs:] = 1e-6 * np.eye(H.shape[0] - n_obs)
        else:
            observations_padded = observations
            padded_var = obs_var_cov

        # Kalman Gain: KGM = D^- · H^T · (H · D^- · H^T + D_L)^{-1}
        # S = H·D·H^T + R: sây biển đổi (innovation covariance)
        S = H @ D_pred @ H.T + padded_var
        try:
            KGM = D_pred @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            # Nếu S suy biến: KGM = 0 (không cập nhật)
            KGM = np.zeros((n_state, H.shape[0]))

        # Innovation = phần chủ (residual): độ lệch giữa quan sát và dự báo
        innovation = observations_padded - H @ x_pred
        # Huber weighting cho outlier
        innovation_w = self._huber_weights(innovation)

        # Update
        x_updated = x_pred + KGM @ (innovation * innovation_w)
        I = np.eye(n_state)
        D_updated = (I - KGM @ H) @ D_pred

        return x_updated, D_updated

    def _huber_weights(self, innovation: np.ndarray) -> np.ndarray:
        """
        Hàm trọng số Huber để giảm ảnh hưởng của outlier.
        w(r) = 1           nếu |r| ≤ δ
             = δ / |r|     nếu |r| > δ
        Tham chiếu: Liu et al. (2022a); Zheng et al. (2026)
        """
        delta = self.huber_delta
        abs_innov = np.abs(innovation)
        weights = np.where(abs_innov <= delta, 1.0, delta / (abs_innov + 1e-10))
        return weights

    def step(self,
             observation: np.ndarray,
             obs_var_cov: np.ndarray,
             los_vectors: List[Dict[str, float]],
             current_date: datetime,
             n_ifg: int = 1) -> Dict[str, float]:
        """
        Thực hiện một bước dự báo + cập nhật đầy đủ.
        Cập nhật self.state.

        Returns
        -------
        dict với 'east', 'north', 'vertical' (mm tích lũy từ t=0)
        """
        if self.state is None:
            raise RuntimeError("Gọi initialize() trước step()")

        # Tính dt từ bước trước
        if self.state.timestamps:
            dt_days = (current_date - self.state.timestamps[-1]).days
        else:
            dt_days = 12

        # Predict
        x_pred, D_pred = self.predict(dt_days)

        # Update nếu có quan sát
        if observation is not None and len(observation) > 0:
            x_updated, D_updated = self.update(
                x_pred, D_pred, observation, obs_var_cov,
                los_vectors, n_ifg
            )
        else:
            x_updated, D_updated = x_pred, D_pred

        # Cập nhật state
        n = self.n
        displ_new = x_updated.reshape(3, n).T  # (n, 3)
        self.state.displacement = displ_new
        self.state.var_cov = D_updated
        self.state.timestamps.append(current_date)
        if len(self.state.timestamps) > n:
            self.state.timestamps = self.state.timestamps[-n:]

        # Lấy dịch chuyển mới nhất (bước hiện tại)
        current_displ = displ_new[0]  # [E, N, V] mm
        return {
            "east": float(current_displ[0]),
            "north": float(current_displ[1]),
            "vertical": float(current_displ[2]),
            "date": current_date.strftime("%Y-%m-%d"),
        }


class DailyFusionFramework:
    """
    Khung kết hợp đầy đủ: KF + Transformer → dịch chuyển 4D hàng ngày.
    Điều phối luồng dữ liệu giữa các module.

    Tham chiếu: Zheng et al. (2026), Fig. 2(a)
    """

    def __init__(self,
                 kf: SpatiotemporalKalmanFilter,
                 transformer=None,   # HydrometTransformer instance
                 los_vectors: Optional[List[Dict]] = None):
        self.kf = kf
        self.transformer = transformer
        self.los_vectors = los_vectors or []
        self.results: List[Dict] = []

    def run(self,
            sar_observations: Dict[datetime, np.ndarray],
            sar_var_covs: Dict[datetime, np.ndarray],
            hydro_data: Dict[str, np.ndarray],
            hydro_dates: List[datetime],
            start_date: datetime,
            end_date: datetime) -> List[Dict]:
        """
        Chạy vòng lặp cập nhật hàng ngày.

        Parameters
        ----------
        sar_observations : {date: LOS array} — quan sát SAR thực
        sar_var_covs     : {date: var_cov}
        hydro_data       : dữ liệu khí tượng (rainfall, soil_moisture, ...)
        hydro_dates      : danh sách ngày tương ứng hydro_data
        start_date, end_date : khoảng thời gian chạy

        Returns
        -------
        List[Dict] — kết quả 4D theo ngày
        """
        from datetime import timedelta

        current = start_date
        daily_results = []

        logger.info(f"Running daily fusion framework: {start_date.date()} → {end_date.date()}")

        while current <= end_date:
            # Kiểm tra: có ảnh SAR hôm nay không?
            if current in sar_observations:
                obs = sar_observations[current]
                var_cov = sar_var_covs.get(current, np.eye(len(obs)) * 4.0)
                obs_type = "SAR"
            elif self.transformer is not None:
                # Dùng Transformer + hydro để sinh interferogram ảo
                hydro_today = self._get_hydro_at_date(
                    current, hydro_data, hydro_dates
                )
                obs = self.transformer.predict_los(hydro_today)
                var_cov = self._estimate_synthetic_var_cov(current, sar_observations)
                obs_type = "Transformer"
            else:
                # Không có quan sát → chỉ predict
                obs = np.array([])
                var_cov = np.eye(2) * 100.0
                obs_type = "predict_only"

            # KF step
            result = self.kf.step(
                observation=obs,
                obs_var_cov=var_cov,
                los_vectors=self.los_vectors,
                current_date=current,
            )
            result["obs_type"] = obs_type
            daily_results.append(result)

            current += timedelta(days=1)

        self.results = daily_results
        logger.info(f"Fusion framework done: {len(daily_results)} daily estimates")
        return daily_results

    def _get_hydro_at_date(self,
                            date: datetime,
                            hydro_data: Dict,
                            hydro_dates: List[datetime]) -> Dict:
        """Lấy dữ liệu khí tượng tại ngày cụ thể."""
        if not hydro_dates:
            return {"rainfall_mm": 0.0, "soil_moisture": 0.3}
        # Tìm ngày gần nhất
        diffs = [abs((d - date).days) for d in hydro_dates]
        idx = int(np.argmin(diffs))
        result = {}
        for key, vals in hydro_data.items():
            if key != "dates" and idx < len(vals):
                result[key] = float(vals[idx])
        return result

    def _estimate_synthetic_var_cov(self,
                                     current_date: datetime,
                                     sar_obs: Dict[datetime, np.ndarray]
                                     ) -> np.ndarray:
        """
        Ước tính phương sai cho interferogram tổng hợp từ Transformer.
        Dùng temporal decorrelation model (Zebker & Villasenor, 1992).
        """
        if not sar_obs:
            return np.eye(2) * 9.0  # 3mm std default

        # Tìm quan sát SAR gần nhất
        sar_dates = sorted(sar_obs.keys())
        past_sar = [d for d in sar_dates if d <= current_date]
        if not past_sar:
            return np.eye(2) * 9.0

        last_sar = past_sar[-1]
        dt_days = (current_date - last_sar).days

        # Exponential temporal decorrelation: σ² ∝ exp(dt/τ)
        tau_days = 30.0  # Time constant
        sigma2 = 4.0 * np.exp(dt_days / tau_days)  # 2mm → tăng dần
        return np.eye(2) * sigma2

    def compute_rmse(self,
                     reference: List[Dict],
                     component: str = "east") -> float:
        """Tính RMSE so với kết quả tham chiếu."""
        if not self.results or not reference:
            return float("nan")
        pred = [r.get(component, 0) for r in self.results]
        ref = [r.get(component, 0) for r in reference]
        n = min(len(pred), len(ref))
        rmse = np.sqrt(np.mean([(pred[i] - ref[i])**2 for i in range(n)]))
        return float(rmse)
