"""
src/kinematics/kinematics_analyzer.py
=======================================
Phân tích kinematics trượt lở từ dữ liệu 4D hàng ngày:
  - Strain invariants (MSS, DIL)
  - Độ dày khối trượt (mass conservation)
  - Hình học bề mặt trượt
  - Tương quan với khí tượng (ICA + WTC)

Tham chiếu: Zheng et al. (2026), Section 5.4
"""

import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 1. STRAIN INVARIANTS
# ─────────────────────────────────────────────────────────────

class StrainAnalyzer:
    """
    Tính strain invariants từ trường vận tốc 3D.
    Dùng để hiểu tương tác giữa các khối trong sạt lở.

    Biến:
        window (int): Kích thước cửa sổ tính gradient (pixel).
        dx, dy (float): Kích thước pixel theo hai phương (mét).
    """

    def __init__(self, window_px: int = 3, pixel_size_m: float = 80.0):
        self.window = window_px
        self.dx = pixel_size_m
        self.dy = pixel_size_m

    def compute_strain_tensor(self,
                               ve: np.ndarray,
                               vn: np.ndarray,
                               vv: np.ndarray
                               ) -> Dict[str, np.ndarray]:
        """
        Tính tensor biến dạng từ trường vận tốc 3D.

        Parameters
        ----------
        ve, vn, vv : np.ndarray (H, W) — vận tốc E, N, Vertical (mm/yr)

        Returns
        -------
        dict với:
          'exx', 'eyy', 'exy' : thành phần strain 2D (× 10⁻³)
          'mss'               : Maximum Shear Strain
          'dil'               : Dilatation
        """
        H, W = ve.shape

        # Gradient vận tốc trên mặt phẳng nằm ngang
        # np.gradient dùng độ sẹ trung tâm (central difference) bên trong
        # và độ sẹ tiến/lùi (forward/backward) tại biên
        dve_dx = np.gradient(ve, self.dx, axis=1)  # ∂Ve/∂x (E)
        dve_dy = np.gradient(ve, self.dy, axis=0)  # ∂Ve/∂y (N)
        dvn_dx = np.gradient(vn, self.dx, axis=1)
        dvn_dy = np.gradient(vn, self.dy, axis=0)
        dvv_dx = np.gradient(vv, self.dx, axis=1)
        dvv_dy = np.gradient(vv, self.dy, axis=0)

        # Tensor strain (phần đối xứng của gradient vận tốc)
        exx = dve_dx                           # Normal strain E-W
        eyy = dvn_dy                           # Normal strain N-S
        exy = 0.5 * (dve_dy + dvn_dx)         # Shear strain (trung bình)

        # Strain invariants (Zheng et al., 2026, Fig. 11)
        # Dilatation: thể hiện sự chéch đạo / giãn nở vậtchất
        dilatation = exx + eyy

        # Maximum Shear Strain: mức độ biến dạng cắt tối đa
        # |ε_max| = √{[(exx-eyy)/2]² + exy²}
        mss = np.sqrt(((exx - eyy) / 2) ** 2 + exy ** 2)

        return {
            "exx": exx * 1e3,      # × 10⁻³ (thuyết: không đơn vị, nhưng scale có thể hiển thị)
            "eyy": eyy * 1e3,
            "exy": exy * 1e3,
            "mss": mss * 1e3,
            "dil": dilatation * 1e3,
        }

    def compute_timeseries_strain(self,
                                   movements_4d: Dict[str, np.ndarray],
                                   dates: List[datetime]
                                   ) -> Dict[str, np.ndarray]:
        """
        Tính chuỗi thời gian MSS và DIL từ 4D movements.
        Output: {date_str: {'mss': array, 'dil': array}}
        """
        results = {}
        east = movements_4d["east"]    # (n_dates, H, W)
        north = movements_4d["north"]
        vert = movements_4d["vertical"]

        n_dates = len(dates)
        if east.ndim == 2:
            # Single snapshot
            strain = self.compute_strain_tensor(east, north, vert)
            return {dates[0].strftime("%Y-%m-%d"): strain}

        for i, d in enumerate(dates):
            strain = self.compute_strain_tensor(east[i], north[i], vert[i])
            results[d.strftime("%Y-%m-%d")] = {
                "mss": strain["mss"],
                "dil": strain["dil"],
            }

        logger.info(f"Computed strain for {len(results)} time steps")
        return results

    def extract_profile(self,
                         strain_ts: Dict,
                         profile_pixels: List[Tuple[int,int]]
                         ) -> Dict[str, np.ndarray]:
        """
        Trích xuất chuỗi thời gian MSS, DIL dọc theo profile P-P'.
        Tham chiếu: Zheng et al. (2026), Fig. 11(b)(c)
        """
        dates = sorted(strain_ts.keys())
        rows = [p[0] for p in profile_pixels]
        cols = [p[1] for p in profile_pixels]
        n_profile = len(profile_pixels)
        n_dates = len(dates)

        mss_profile = np.zeros((n_dates, n_profile))
        dil_profile = np.zeros((n_dates, n_profile))

        for i, d in enumerate(dates):
            data = strain_ts[d]
            for j, (r, c) in enumerate(zip(rows, cols)):
                H, W = data["mss"].shape
                r_c = min(r, H - 1)
                c_c = min(c, W - 1)
                mss_profile[i, j] = data["mss"][r_c, c_c]
                dil_profile[i, j] = data["dil"][r_c, c_c]

        return {"dates": np.array(dates), "mss": mss_profile, "dil": dil_profile}


# ─────────────────────────────────────────────────────────────
# 2. ĐỘ DÀY VÀ HÌNH HỌC BỀ MẶT TRƯỢT
# ─────────────────────────────────────────────────────────────

class SlipSurfaceInverter:
    """
    Nghịch đảo độ dày khối trượt và hình học bề mặt trượt
    từ trường vận tốc 3D.

    Phương pháp: Luật bảo toàn khối lượng (mass conservation).
    Tham chiếu: Zheng et al. (2026), Section 5.4; Zheng et al. (2023)
    """

    def estimate_thickness(self,
                            ve: np.ndarray,
                            vn: np.ndarray,
                            vv: np.ndarray,
                            surface_dem: np.ndarray,
                            dx: float = 80.0) -> np.ndarray:
        """
        Ước tính độ dày khối trượt từ bảo toàn khối lượng.

        div(v·h) + ∂h/∂t = 0  →  h = -∂h/∂t / div(v)

        Đơn giản hóa cho trượt lở ổn định:
        h ≈ |v_surface| / |∂v/∂z|

        Parameters
        ----------
        ve, vn, vv     : trường vận tốc (mm/yr)
        surface_dem    : DEM (m)
        dx             : kích thước pixel (m)

        Returns
        -------
        thickness      : np.ndarray (H, W) — độ dày ước tính (m)
        """
        # Vận tốc bề mặt tổng (vector magnitude)
        v_surface = np.sqrt(ve**2 + vn**2 + vv**2)  # mm/yr

        # Divergence của trường vận tốc nằm ngang
        # div(v) = ∂Ve/∂x + ∂Vn/∂y
        grad_ve = np.gradient(ve, dx, axis=1)
        grad_vn = np.gradient(vn, dx, axis=0)
        divergence = grad_ve + grad_vn + 1e-6  # Tránh chia 0

        # Ước tính độ dày: tỷ lệ nghịch với gradient vận tốc
        # Những vùng gradient lớn = vận tốc biến đổi nhanh → khối mỏng
        thickness = v_surface / (np.abs(divergence) + 1e-8)

        # Chuẩn hóa: đặt trung vị tại vùng chuyển động mạnh nhất = 50m
        # (giá trị tham khảo từ các khối trượt lở điển hình)
        finite_vals = v_surface[np.isfinite(v_surface)]
        if len(finite_vals) > 10:
            moving_mask = v_surface > np.percentile(finite_vals, 75)  # Top 25% pixel
        else:
            moving_mask = v_surface > 0
        if np.sum(moving_mask) > 0:
            scale = 50.0 / (np.nanmedian(thickness[moving_mask]) + 1e-8)
            thickness = thickness * scale

        # Giới hạn vật lý hợp lý: 0–200m
        # Trượt lở tại Tĩnh Túc: ước tính 20–80m theo địa hình
        thickness = np.clip(thickness, 0, 200)
        thickness[~np.isfinite(thickness)] = 0.0

        logger.info(f"Thickness: max={np.nanmax(thickness):.1f}m, "
                    f"mean={np.nanmean(thickness[thickness>0]):.1f}m")
        return thickness.astype(np.float32)

    def get_subsurface_geometry(self,
                                 surface_dem: np.ndarray,
                                 thickness: np.ndarray
                                 ) -> np.ndarray:
        """
        Tính hình học bề mặt trượt = DEM - thickness.
        Tham chiếu: Zheng et al. (2026), Fig. 11(d)
        """
        subsurface = surface_dem - thickness
        logger.debug("Subsurface geometry computed")
        return subsurface


# ─────────────────────────────────────────────────────────────
# 3. PHÂN TÍCH ICA VÀ WAVELET
# ─────────────────────────────────────────────────────────────

class TemporalAnalyzer:
    """
    Phân tích thành phần độc lập (ICA) và tương quan wavelet (WTC).
    Xác định đóng góp của rainfall và soil_moisture vào chuyển động.

    Tham chiếu: Zheng et al. (2026), Section 5.3; Grinsted et al. (2004)
    """

    def ica_decompose(self,
                       movements: np.ndarray,
                       n_components: int = 3
                       ) -> Tuple[np.ndarray, np.ndarray]:
        """
        ICA decomposition của chuỗi thời gian biến dạng.
        Input: (n_pixels, n_dates) — dùng spatial ICA

        Returns
        -------
        components    : (n_components, n_dates) — temporal patterns
        score_maps    : (n_components, n_pixels) — spatial scores
        """
        try:
            from sklearn.decomposition import FastICA
            ica = FastICA(n_components=n_components, random_state=42, max_iter=500)
            # ICA trên ma trận (n_dates, n_pixels)
            # (khác temporal ICA: tìm các pattern không gian độc lập)
            if movements.ndim == 3:
                H, W = movements.shape[1], movements.shape[2]
                # Reshape thành (n_px, n_t): mỗi hàng là chuỗi thời gian của 1 pixel
                M = movements.reshape(movements.shape[0], -1).T  # (n_px, n_t)
            else:
                M = movements

            # score_maps: (n_px, n_comp) — đóng góp không gian của mỗi thành phần
            # components: (n_comp, n_t) — dạng sóng thời gian tương ứng
            score_maps = ica.fit_transform(M)     # (n_px, n_comp)
            components = ica.components_           # (n_comp, n_t)

            logger.info(f"ICA: {n_components} components extracted")
            return components, score_maps.T   # (n_comp, n_t), (n_comp, n_px)

        except ImportError:
            logger.warning("scikit-learn not available. Using PCA fallback for ICA.")
            return self._pca_fallback(movements, n_components)

    def _pca_fallback(self,
                      movements: np.ndarray,
                      n_components: int) -> Tuple[np.ndarray, np.ndarray]:
        """PCA fallback khi không có sklearn."""
        if movements.ndim == 3:
            M = movements.reshape(movements.shape[0], -1).T
        else:
            M = movements

        M_centered = M - np.mean(M, axis=0)
        U, S, Vt = np.linalg.svd(M_centered, full_matrices=False)
        n = min(n_components, Vt.shape[0])
        components = Vt[:n]       # (n_comp, n_t)
        score_maps = U[:, :n]     # (n_px, n_comp)
        return components, score_maps.T

    def wavelet_coherence(self,
                           ts1: np.ndarray,
                           ts2: np.ndarray,
                           dt: float = 1.0,
                           periods: Optional[np.ndarray] = None
                           ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Wavelet Transform Coherence (WTC) giữa hai chuỗi thời gian.
        Đơn giản hóa: dùng sliding-window cross-correlation nếu pywt không có.

        Tham chiếu: Grinsted et al. (2004)

        Returns
        -------
        wtc      : np.ndarray (n_periods, n_time) — coherence (0–1)
        periods  : np.ndarray — khoảng chu kỳ (ngày)
        """
        try:
            import pywt
            return self._wtc_pywt(ts1, ts2, dt, periods)
        except ImportError:
            return self._wtc_sliding_window(ts1, ts2, dt)

    def _wtc_pywt(self, ts1, ts2, dt, periods):
        """WTC dùng PyWavelets (nếu có)."""
        import pywt
        wavelet = "cmor1.5-1.0"
        n = len(ts1)
        if periods is None:
            periods = np.geomspace(4, n // 4, 20) * dt
        scales = periods / (pywt.scale2frequency(wavelet, 1) * dt)

        cwt1, _ = pywt.cwt(ts1, scales, wavelet, sampling_period=dt)
        cwt2, _ = pywt.cwt(ts2, scales, wavelet, sampling_period=dt)

        # Coherence: |<W1·W2*>|² / (|W1|² · |W2|²)
        sigma = max(len(ts1) // 10, 5)
        from scipy.ndimage import uniform_filter1d
        cross = cwt1 * np.conj(cwt2)
        num = np.abs(uniform_filter1d(cross, sigma, axis=1))**2
        den1 = uniform_filter1d(np.abs(cwt1)**2, sigma, axis=1)
        den2 = uniform_filter1d(np.abs(cwt2)**2, sigma, axis=1)
        wtc = np.clip(num / (den1 * den2 + 1e-10), 0, 1)
        return wtc, periods

    def _wtc_sliding_window(self,
                             ts1: np.ndarray,
                             ts2: np.ndarray,
                             dt: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Fallback WTC bằng sliding-window cross-correlation.
        Kém chính xác hơn wavelet nhưng không cần dependency.
        """
        n = len(ts1)
        periods = np.array([7, 14, 30, 60, 91, 182, 365]) * dt
        wtc = np.zeros((len(periods), n))

        for i, period in enumerate(periods):
            window = max(int(period), 5)
            for t in range(n):
                start = max(0, t - window // 2)
                end = min(n, t + window // 2 + 1)
                if end - start < 3:
                    continue
                seg1 = ts1[start:end]
                seg2 = ts2[start:end]
                corr = np.corrcoef(seg1, seg2)[0, 1]
                wtc[i, t] = np.clip(abs(corr), 0, 1)

        logger.debug("WTC computed via sliding-window (fallback)")
        return wtc, periods

    def quantify_hydromet_influence(self,
                                     ic_timeseries: np.ndarray,
                                     rainfall: np.ndarray,
                                     soil_moisture: np.ndarray,
                                     dt: float = 1.0) -> Dict:
        """
        Định lượng ảnh hưởng của rainfall và soil_moisture lên từng IC.
        Tính WTC tại chu kỳ 1 năm (period = 365 ngày).
        Tham chiếu: Zheng et al. (2026), Fig. 10
        """
        results = {}
        for i, ic in enumerate(ic_timeseries):
            wtc_rain, periods = self.wavelet_coherence(ic, rainfall, dt)
            wtc_sm, _ = self.wavelet_coherence(ic, soil_moisture, dt)

            # Lấy giá trị WTC tại period ≈ 365 ngày
            annual_idx = np.argmin(np.abs(periods - 365 * dt))
            wtc_rain_annual = float(np.nanmean(wtc_rain[annual_idx]))
            wtc_sm_annual = float(np.nanmean(wtc_sm[annual_idx]))

            results[f"IC{i+1}"] = {
                "wtc_rainfall_annual": wtc_rain_annual,
                "wtc_soil_moisture_annual": wtc_sm_annual,
                "dominant_driver": "rainfall" if wtc_rain_annual > wtc_sm_annual
                                   else "soil_moisture",
                "wtc_rainfall_full": wtc_rain,
                "wtc_sm_full": wtc_sm,
                "periods": periods,
            }
            logger.info(f"IC{i+1}: WTC(rainfall)={wtc_rain_annual:.2f}, "
                        f"WTC(soil_moisture)={wtc_sm_annual:.2f}")

        return results


# ─────────────────────────────────────────────────────────────
# 4. CẢNH BÁO SỚM
# ─────────────────────────────────────────────────────────────

class EarlyWarningDetector:
    """
    Phát hiện tín hiệu gia tốc bất thường để cảnh báo sớm.
    Tham chiếu: Zheng et al. (2026), Section 5.4 (Hooskanaden case)
    """

    def __init__(self, accel_threshold_mm_day2: float = 0.5):
        self.threshold = accel_threshold_mm_day2

    def detect_acceleration(self,
                              daily_movements: List[Dict],
                              component: str = "east",
                              window_days: int = 7) -> List[Dict]:
        """
        Tính gia tốc và phát hiện bất thường.

        Returns
        -------
        List[Dict] với field 'acceleration' và 'alert_level' (0-3)
        """
        if len(daily_movements) < window_days + 1:
            return daily_movements

        displ = np.array([m.get(component, 0) for m in daily_movements])
        vel = np.gradient(displ)
        accel = np.gradient(vel)

        results = []
        for i, m in enumerate(daily_movements):
            m = m.copy()
            m["velocity_mm_day"] = float(vel[i])
            m["acceleration_mm_day2"] = float(accel[i])

            # Rolling mean để giảm nhiễu
            start = max(0, i - window_days)
            rolling_accel = float(np.mean(np.abs(accel[start:i+1])))
            m["rolling_accel"] = rolling_accel

            # Alert level
            if rolling_accel > self.threshold * 3:
                alert = 3   # Nguy hiểm cao
            elif rolling_accel > self.threshold * 2:
                alert = 2   # Cảnh báo
            elif rolling_accel > self.threshold:
                alert = 1   # Chú ý
            else:
                alert = 0   # Bình thường

            m["alert_level"] = alert
            results.append(m)

        n_alerts = sum(1 for m in results if m["alert_level"] >= 2)
        if n_alerts > 0:
            logger.warning(f"⚠ {n_alerts} alert events detected in {component} component")

        return results
