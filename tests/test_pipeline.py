"""
tests/test_pipeline.py
========================
Unit tests cho các module chính.
Chạy: python -m pytest tests/ -v
"""

import sys
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────
# GEO UTILS
# ─────────────────────────────────────────────────────────────

class TestGeoUtils:
    def test_los_vector_ascending(self):
        from src.utils.geo_utils import compute_los_vector
        los = compute_los_vector(38.0, -12.0)
        assert set(los.keys()) == {"east", "north", "vertical"}
        # Magnitude phải gần = 1
        mag = np.sqrt(los["east"]**2 + los["north"]**2 + los["vertical"]**2)
        assert abs(mag - 1.0) < 0.01

    def test_los_vector_descending(self):
        from src.utils.geo_utils import compute_los_vector
        los_asc = compute_los_vector(38.0, -12.0)
        los_desc = compute_los_vector(38.0, -168.0)
        # East component phải có dấu ngược nhau cho asc vs desc
        assert los_asc["east"] * los_desc["east"] < 0

    def test_slope_computation(self):
        from src.utils.geo_utils import compute_slope
        # DEM phẳng → slope = 0
        flat_dem = np.ones((20, 20)) * 500.0
        slope = compute_slope(flat_dem, 30.0, 30.0)
        assert np.allclose(slope, 0.0, atol=0.01)

    def test_decompose_2d(self):
        from src.utils.geo_utils import decompose_2d, compute_kvh
        H, W = 30, 30
        rng = np.random.default_rng(42)
        v_asc = -15.0 * np.ones((H, W)) + rng.normal(0, 0.5, (H, W))
        v_desc = -13.0 * np.ones((H, W)) + rng.normal(0, 0.5, (H, W))
        vv, vh = decompose_2d(v_asc, v_desc, 38.0, -12.0, 38.5, -168.0)
        # Kiểm tra shape và tính hữu hạn
        assert vv.shape == (H, W)
        assert vh.shape == (H, W)
        assert np.sum(np.isfinite(vv)) > H * W * 0.8
        # VV phải âm (lún) khi cả hai LOS đều âm
        assert np.nanmean(vv) < 0

    def test_cramer_rao_bound(self):
        from src.utils.geo_utils import cramer_rao_bound
        coh_high = np.ones((10, 10)) * 0.9
        coh_low = np.ones((10, 10)) * 0.3
        crb_high = cramer_rao_bound(coh_high, 0.056, n_looks=4)
        crb_low = cramer_rao_bound(coh_low, 0.056, n_looks=4)
        # CRB phải lớn hơn khi coherence thấp
        assert np.mean(crb_low) > np.mean(crb_high)

    def test_spf_coefficients(self):
        from src.utils.geo_utils import compute_spf_coefficients
        dem = np.tile(np.linspace(100, 500, 20), (20, 1))
        grad_e, grad_n, asp = compute_spf_coefficients(dem, dx=80.0, dy=80.0)
        assert grad_e.shape == (20, 20)
        # DEM tăng theo hướng E → gradient_e dương
        assert np.mean(grad_e[:, 5:-5]) > 0


# ─────────────────────────────────────────────────────────────
# SBAS
# ─────────────────────────────────────────────────────────────

class TestSBAS:
    def _make_network(self, n=20):
        from src.sbas.sbas_processor import InterferogramNetwork
        dates = [datetime(2020, 1, 1) + timedelta(days=12*i) for i in range(n)]
        net = InterferogramNetwork(dates, 36, 150)
        net.build_network()
        return net

    def test_network_connectivity(self):
        net = self._make_network(20)
        stats = net.get_connection_stats()
        assert stats["connected"] is True
        assert stats["n_interferograms"] > 0

    def test_network_min_pairs(self):
        net = self._make_network(10)
        # Mỗi ảnh phải có ít nhất 1 cặp với ảnh lân cận
        assert len(net.pairs) >= 9

    def test_sbas_velocity_shape(self):
        from src.sbas.sbas_processor import SBASProcessor, InterferogramNetwork
        H, W, n = 30, 30, 15
        dates = [datetime(2020, 1, 1) + timedelta(days=12*i) for i in range(n)]
        net = InterferogramNetwork(dates, 36, 150)
        net.build_network()

        rng = np.random.default_rng(0)
        n_ifg = len(net.pairs)
        ifgrams = rng.normal(0, 5.0, (n_ifg, H, W)).astype(np.float32)
        coh = np.ones((n_ifg, H, W), dtype=np.float32) * 0.7

        processor = SBASProcessor(net, 0.056)
        vel, ts = processor.process(ifgrams, coh, coherence_threshold=0.3)
        assert vel.shape == (H, W)
        assert ts.shape == (n, H, W)

    def test_sbas_velocity_range(self):
        from src.sbas.sbas_processor import run_sbas_pipeline
        vel, ts, dates = run_sbas_pipeline("asc", {
            "SENTINEL1": {"temporal_baseline_max_days": 36,
                           "spatial_baseline_max_m": 150,
                           "coherence_threshold": 0.20,
                           "wavelength_m": 0.056}
        })
        assert not np.all(np.isnan(vel))
        assert np.nanmin(vel) < 0   # Phải có dịch chuyển âm (lún/trượt)


# ─────────────────────────────────────────────────────────────
# SPATIAL CLUSTERING
# ─────────────────────────────────────────────────────────────

class TestClustering:
    def test_cluster_detects_active_areas(self):
        from src.clustering.spatial_clustering import SpatialClusterer
        H, W = 60, 60
        velocity = np.zeros((H, W), dtype=np.float32)
        # Thêm vùng biến dạng mạnh
        velocity[10:25, 10:25] = -20.0   # Sạt lở
        velocity[40:55, 40:55] = -15.0   # Lún mỏ

        clusterer = SpatialClusterer(1.0, 2, 3, 80.0)
        macs = clusterer.cluster(velocity)
        assert len(macs) >= 2

    def test_cluster_minimum_size(self):
        from src.clustering.spatial_clustering import SpatialClusterer
        H, W = 30, 30
        velocity = np.zeros((H, W), dtype=np.float32)
        # Chỉ 2 pixel hoạt động (tách biệt hoàn toàn) → không đủ min_size=3
        velocity[5, 5] = -20.0
        velocity[5, 6] = -18.0
        # buffer=0: không giãn nở → cluster chỉ có 2 pixel < min_size=3
        clusterer = SpatialClusterer(1.0, 0, 3, 80.0)
        macs = clusterer.cluster(velocity)
        assert len(macs) == 0

    def test_cluster_area_calculation(self):
        from src.clustering.spatial_clustering import SpatialClusterer
        H, W = 50, 50
        velocity = np.zeros((H, W), dtype=np.float32)
        velocity[10:20, 10:20] = -25.0   # 10×10 = 100 pixels

        clusterer = SpatialClusterer(1.0, 1, 3, 80.0)
        macs = clusterer.cluster(velocity)
        if macs:
            # 80m pixel → 80×80m = 0.0064 km² per pixel
            # 100 pixels ≈ 0.64 km² (±buffer)
            assert macs[0].area_km2 > 0.01


# ─────────────────────────────────────────────────────────────
# CLASSIFICATION
# ─────────────────────────────────────────────────────────────

class TestClassification:
    def _make_mac(self, kvh, slope, vel):
        return {
            "mac_id": 1,
            "pixel_indices": [(i, j) for i in range(5) for j in range(5)],
            "kvh": kvh,
            "slope_deg": slope,
            "mean_slope_deg": slope,
            "mean_vv_mm_yr": -vel * kvh / (kvh + 1),
            "mean_vh_mm_yr": vel / (kvh + 1),
            "mean_velocity_mm_yr": -vel,
            "area_km2": 0.1,
            "has_both_orbits": True,
        }

    def test_classify_landslide_from_inventory(self):
        from src.classification.mac_classifier import MACClassifier
        clf = MACClassifier()
        mac = self._make_mac(kvh=0.5, slope=20.0, vel=15.0)
        pixels = {(i, j) for i in range(5) for j in range(5)}
        result = clf._classify_single(mac, {"landslide_inventory": pixels})
        assert result["classification"] == "landslide"
        assert result["confidence"] == 2

    def test_classify_mine_from_map(self):
        from src.classification.mac_classifier import MACClassifier
        clf = MACClassifier()
        mac = self._make_mac(kvh=2.0, slope=2.0, vel=12.0)
        pixels = {(i, j) for i in range(5) for j in range(5)}
        result = clf._classify_single(mac, {"mine_areas": pixels})
        assert result["classification"] in ["mine_subsidence", "mixed_deformation"]

    def test_classify_potential_landslide_by_kvh(self):
        from src.classification.mac_classifier import MACClassifier
        clf = MACClassifier(slope_threshold_deg=5.0)
        # KVH < 1, slope > 5°, không có lớp phụ trợ
        mac = self._make_mac(kvh=0.4, slope=15.0, vel=12.0)
        result = clf._classify_single(mac, {})
        assert result["classification"] == "potential_landslide"

    def test_classify_potential_subsidence(self):
        from src.classification.mac_classifier import MACClassifier
        clf = MACClassifier()
        # KVH > 1, slope < 5°, VV < 0
        mac = self._make_mac(kvh=3.0, slope=1.5, vel=10.0)
        result = clf._classify_single(mac, {})
        assert result["classification"] == "potential_subsidence"


# ─────────────────────────────────────────────────────────────
# KALMAN FILTER
# ─────────────────────────────────────────────────────────────

class TestKalmanFilter:
    def _make_kf(self, use_spf=False):
        from src.kalman.kalman_4d import SpatiotemporalKalmanFilter
        return SpatiotemporalKalmanFilter(
            n_steps=5, poly_order=2, huber_delta=1.5,
            use_spf=use_spf,
            spf_coeffs={"theta_e": 0.1, "theta_n": 0.1, "theta_asp": 0.5}
        )

    def _init_kf(self, kf):
        dates = [datetime(2020, 1, 1) + timedelta(days=12*i) for i in range(5)]
        kf.initialize(
            np.array([-15.0, -5.0, -10.0]),
            np.eye(3) * 25.0,
            dates
        )
        return dates

    def test_initialize(self):
        kf = self._make_kf()
        dates = self._init_kf(kf)
        assert kf.state is not None
        assert kf.state.displacement.shape == (5, 3)

    def test_predict_returns_correct_shape(self):
        kf = self._make_kf()
        self._init_kf(kf)
        x_pred, D_pred = kf.predict(dt_days=12)
        assert x_pred.shape == (15,)   # 3 × n_steps = 3 × 5
        assert D_pred.shape == (15, 15)

    def test_huber_weights(self):
        kf = self._make_kf()
        # Giá trị nhỏ → weight = 1
        small = np.array([0.5, 0.5])
        w_small = kf._huber_weights(small)
        assert np.all(w_small == 1.0)
        # Giá trị lớn → weight < 1
        large = np.array([10.0, -10.0])
        w_large = kf._huber_weights(large)
        assert np.all(w_large < 1.0)

    def test_step_output_keys(self):
        kf = self._make_kf()
        dates = self._init_kf(kf)
        los_vecs = [{"east": -0.3, "north": 0.09, "vertical": 0.94}]
        obs = np.array([-12.0])
        var = np.eye(1) * 4.0
        result = kf.step(obs, var, los_vecs,
                          current_date=datetime(2020, 3, 1))
        assert "east" in result
        assert "north" in result
        assert "vertical" in result

    def test_step_state_update(self):
        """State phải thay đổi sau khi update."""
        kf = self._make_kf()
        dates = self._init_kf(kf)
        initial_disp = kf.state.displacement.copy()
        los_vecs = [{"east": -0.3, "north": 0.09, "vertical": 0.94}]
        obs = np.array([-20.0])
        var = np.eye(1) * 4.0
        kf.step(obs, var, los_vecs, current_date=datetime(2020, 3, 15))
        # Displacement phải thay đổi
        assert not np.allclose(kf.state.displacement, initial_disp)


# ─────────────────────────────────────────────────────────────
# KINEMATICS
# ─────────────────────────────────────────────────────────────

class TestKinematics:
    def test_strain_tensor_shape(self):
        from src.kinematics.kinematics_analyzer import StrainAnalyzer
        H, W = 40, 40
        rng = np.random.default_rng(0)
        ve = rng.normal(-15, 3, (H, W)).astype(np.float32)
        vn = rng.normal(-5, 1, (H, W)).astype(np.float32)
        vv = rng.normal(-10, 2, (H, W)).astype(np.float32)
        sa = StrainAnalyzer()
        strain = sa.compute_strain_tensor(ve, vn, vv)
        for key in ["mss", "dil", "exx", "eyy", "exy"]:
            assert key in strain
            assert strain[key].shape == (H, W)

    def test_mss_nonnegative(self):
        from src.kinematics.kinematics_analyzer import StrainAnalyzer
        H, W = 20, 20
        rng = np.random.default_rng(1)
        ve = rng.normal(0, 5, (H, W)).astype(np.float32)
        vn = rng.normal(0, 2, (H, W)).astype(np.float32)
        vv = rng.normal(0, 3, (H, W)).astype(np.float32)
        strain = StrainAnalyzer().compute_strain_tensor(ve, vn, vv)
        # MSS phải không âm
        assert np.all(strain["mss"][np.isfinite(strain["mss"])] >= 0)

    def test_thickness_positive(self):
        from src.kinematics.kinematics_analyzer import SlipSurfaceInverter
        H, W = 30, 30
        rng = np.random.default_rng(2)
        dem = 400 + rng.normal(0, 20, (H, W)).astype(np.float32)
        ve = -20.0 * np.ones((H, W), dtype=np.float32)
        vn = -7.0 * np.ones((H, W), dtype=np.float32)
        vv = -15.0 * np.ones((H, W), dtype=np.float32)
        inv = SlipSurfaceInverter()
        thickness = inv.estimate_thickness(ve, vn, vv, dem, dx=80.0)
        assert thickness.shape == (H, W)
        assert np.all(thickness >= 0)

    def test_early_warning_alert_levels(self):
        from src.kinematics.kinematics_analyzer import EarlyWarningDetector
        # Tạo chuỗi gia tốc cao đột ngột
        results = [{"east": float(i**2 * 0.5), "date": f"2022-{i:03d}"}
                   for i in range(30)]
        detector = EarlyWarningDetector(accel_threshold_mm_day2=0.2)
        alerts = detector.detect_acceleration(results, component="east")
        assert len(alerts) == len(results)
        assert all("alert_level" in a for a in alerts)


if __name__ == "__main__":
    # Chạy nhanh không cần pytest
    import traceback
    test_classes = [TestGeoUtils, TestSBAS, TestClustering,
                    TestClassification, TestKalmanFilter, TestKinematics]
    total = passed = failed = 0
    for cls in test_classes:
        obj = cls()
        methods = [m for m in dir(obj) if m.startswith("test_")]
        for method in methods:
            total += 1
            try:
                getattr(obj, method)()
                print(f"  ✓ {cls.__name__}.{method}")
                passed += 1
            except Exception as e:
                print(f"  ✗ {cls.__name__}.{method}: {e}")
                traceback.print_exc()
                failed += 1
    print(f"\n{'='*50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
