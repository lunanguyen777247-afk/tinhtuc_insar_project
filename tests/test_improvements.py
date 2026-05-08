"""
tests/test_improvements.py
==========================
Comprehensive test suite for accuracy improvement modules:
- Atmospheric Correction
- Adaptive Kalman Filter
- PyTorch Transformer
- GPS Validation
"""

import pytest
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

# Import new modules
from src.corrections.atmospheric_correction import (
    ERA5Corrector, AtmosphericConfig, correct_interferogram
)
from src.kalman.kalman_adaptive import (
    AdaptiveKalmanFilter, AdaptiveKalmanConfig
)
from src.transformer.hydro_transformer_torch import (
    HydrometTransformerTorch, TransformerConfig, TimeSeriesDataset
)
from src.validation.cross_validator import (
    CrossValidator, GPSPoint, TimeSeriesValidator
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def synthetic_data_256x256():
    """Generate synthetic 256x256 InSAR-like data."""
    H, W = 256, 256
    
    # Create synthetic interferogram with deformation pattern
    y, x = np.meshgrid(np.arange(W), np.arange(H))
    
    # Gaussian subsidence lobe
    cx, cy = W//3, H//3
    deformation = 10 * np.exp(-((x-cx)**2 + (y-cy)**2) / (50**2))
    
    # Add noise
    noise = np.random.randn(H, W) * 2
    interferogram = deformation + noise
    
    # Create coherence map (higher in deformation area)
    coherence = 0.3 + 0.5 * np.exp(-((x-cx)**2 + (y-cy)**2) / (100**2))
    coherence = np.clip(coherence, 0, 1)
    
    # DEM gradient
    dem = 200 + 5 * x + 3 * y + 100 * np.exp(-((x-cx)**2 + (y-cy)**2) / (80**2))
    
    # Velocity map
    velocity_map = np.zeros((H, W))
    velocity_map[max(0, cx-50):cx+50, max(0, cy-50):cy+50] = -5.0  # mm/year
    
    return {
        'interferogram': interferogram,
        'coherence': coherence,
        'dem': dem,
        'velocity_map': velocity_map,
        'H': H,
        'W': W
    }


@pytest.fixture
def timeseries_5years():
    """Generate 5-year synthetic time series."""
    n_days = 365 * 5
    H, W, F = 64, 64, 5  # (H, W, features=[d, P, SM, GWL, T])
    
    data = np.zeros((n_days, H, W, F))
    
    # Feature 0: displacement (mm)
    t = np.arange(n_days)
    displacement_trend = 0.01 * t  # Linear subsidence
    displacement_seasonal = 5 * np.sin(2*np.pi*t/365)  # Yearly cycle
    displacement_noise = np.random.randn(n_days) * 1
    
    for i in range(H):
        for j in range(W):
            data[t, i, j, 0] = displacement_trend + displacement_seasonal + displacement_noise
    
    # Feature 1: Precipitation (mm/day)
    for t_idx in range(n_days):
        month = (t_idx % 365) // 30
        # Monsoon: June-September rain
        if 5 <= month <= 8:
            rainfall = np.random.exponential(5, (H, W))
        else:
            rainfall = np.random.exponential(1, (H, W))
        data[t_idx, :, :, 1] = np.maximum(rainfall, 0)
    
    # Feature 2: Soil Moisture (m³/m³)
    data[:, :, :, 2] = 0.3 + 0.15 * np.sin(2*np.pi*t/365) + np.random.randn(n_days, H, W)*0.05
    data[:, :, :, 2] = np.clip(data[:, :, :, 2], 0.05, 0.60)
    
    # Feature 3: Groundwater Level (m below surface)
    data[:, :, :, 3] = 2.0 + np.random.randn(n_days, H, W)*0.3
    
    # Feature 4: Temperature (°C)
    data[:, :, :, 4] = 20 + 10*np.sin(2*np.pi*t/365) + np.random.randn(n_days, H, W)*1.5
    
    timestamps = np.arange(n_days)
    
    return data, timestamps


# ============================================================================
# TESTS: ATMOSPHERIC CORRECTION
# ============================================================================

class TestAtmosphericCorrection:
    """Test suite for APS removal."""
    
    def test_era5_corrector_reduces_variance(self, synthetic_data_256x256):
        """Verify APS correction reduces phase variance."""
        
        cfg = AtmosphericConfig(method="era5", coherence_threshold=0.4)
        corrector = ERA5Corrector(cfg)
        
        # Create APS-contaminated interferogram
        igram = synthetic_data_256x256['interferogram']
        aps_model = 15 * np.sin(2*np.pi*np.arange(256)/50)[:, np.newaxis]  # Atmospheric gradient
        igram_contaminated = igram + aps_model
        
        # Correct
        igram_corrected = corrector.correct(
            igram_contaminated,
            dem=synthetic_data_256x256['dem'],
            coherence=synthetic_data_256x256['coherence'],
            dates=(datetime(2020, 1, 1), datetime(2020, 2, 1)),
            era5_zwd1=np.ones((256, 256)) * 50,
            era5_zwd2=np.ones((256, 256)) * 45
        )
        
        # Phase variance should decrease
        var_before = np.var(igram_contaminated)
        var_after = np.var(igram_corrected)
        
        print(f"Variance: {var_before:.1f} → {var_after:.1f} mm²")
        assert var_after < var_before * 0.95, "APS correction should reduce variance"
    
    def test_correct_interferogram_wrapper(self, synthetic_data_256x256):
        """Test convenience function."""
        
        corrected = correct_interferogram(
            synthetic_data_256x256['interferogram'],
            synthetic_data_256x256['dem'],
            synthetic_data_256x256['coherence'],
            (datetime(2020, 1, 1), datetime(2020, 2, 1)),
            method="era5"
        )
        
        assert corrected.shape == synthetic_data_256x256['interferogram'].shape
        assert not np.all(np.isnan(corrected))


# ============================================================================
# TESTS: ADAPTIVE KALMAN FILTER
# ============================================================================

class TestAdaptiveKalman:
    """Test suite for Adaptive Kalman Filter."""
    
    def test_adaptive_kalman_initialization(self, synthetic_data_256x256):
        """Test Kalman filter initialization."""
        
        cfg = AdaptiveKalmanConfig()
        kalman = AdaptiveKalmanFilter(
            synthetic_data_256x256['velocity_map'],
            synthetic_data_256x256['coherence'],
            cfg
        )
        
        # Check noise maps exist
        assert kalman.R_map.shape == (256, 256)
        assert kalman.Q_disp_map.shape == (256, 256)
        assert kalman.Q_vel_map.shape == (256, 256)
        
        # Q should be higher in low-coherence regions
        low_coh_Q = np.mean(kalman.Q_disp_map[synthetic_data_256x256['coherence'] < 0.5])
        high_coh_Q = np.mean(kalman.Q_disp_map[synthetic_data_256x256['coherence'] > 0.7])
        
        assert low_coh_Q > high_coh_Q, "Q should adapt to coherence"
    
    def test_adaptive_kalman_filtering(self, synthetic_data_256x256):
        """Test Kalman filtering with time series."""
        
        # Create synthetic time series
        n_times = 10
        ts = np.tile(synthetic_data_256x256['interferogram'][np.newaxis, :, :], (n_times, 1, 1))
        ts = ts + np.random.randn(*ts.shape) * 0.5  # Add noise
        
        timestamps = np.arange(n_times)
        
        cfg = AdaptiveKalmanConfig()
        kalman = AdaptiveKalmanFilter(
            synthetic_data_256x256['velocity_map'],
            synthetic_data_256x256['coherence'],
            cfg
        )
        
        filtered, uncertainty = kalman.filter(ts, timestamps)
        
        assert filtered.shape == ts.shape
        assert uncertainty.shape == ts.shape
        assert np.all(uncertainty >= 0), "Uncertainty should be non-negative"
        
        print(f"Filtered time series: {filtered.shape}")
        print(f"Uncertainty range: [{uncertainty.min():.2f}, {uncertainty.max():.2f}] mm")


# ============================================================================
# TESTS: PYTORCH TRANSFORMER
# ============================================================================

class TestTransformer:
    """Test suite for PyTorch Transformer."""
    
    def test_transformer_initialization(self):
        """Test model initialization."""
        
        cfg = TransformerConfig(
            seq_length=30,
            n_features=5,
            d_model=16,
            n_heads=2,
            n_layers=1
        )
        
        model = HydrometTransformerTorch(cfg)
        assert model.model is not None
        assert model.optimizer is not None
        assert not model.is_trained
    
    def test_timeseries_dataset(self, timeseries_5years):
        """Test dataset creation."""
        
        data, timestamps = timeseries_5years
        seq_len = 30
        
        dataset = TimeSeriesDataset(data, seq_len, train=True, train_ratio=0.7)
        
        assert len(dataset) > 0
        assert dataset[0][0].shape == (seq_len, 64*64, 5)
        assert dataset[0][1].shape == (64*64,)
    
    def test_transformer_training(self, timeseries_5years):
        """Test training loop."""
        
        data, timestamps = timeseries_5years
        
        cfg = TransformerConfig(
            seq_length=30,
            n_epochs=3,  # Short for testing
            batch_size=8,
            early_stopping_patience=1000  # Disable early stopping
        )
        
        model = HydrometTransformerTorch(cfg)
        history = model.fit(data, verbose=False)
        
        assert 'train_loss' in history
        assert len(history['train_loss']) > 0
        assert history['train_loss'][0] > 0
        
        print(f"Training history: {history['train_loss']}")
    
    def test_transformer_prediction(self, timeseries_5years):
        """Test prediction."""
        
        data, timestamps = timeseries_5years
        
        cfg = TransformerConfig(seq_length=30, n_epochs=2)
        model = HydrometTransformerTorch(cfg)
        model.fit(data, verbose=False)
        
        predictions = model.predict(data)
        
        # Should predict for (T - seq_len) time steps
        assert predictions.shape[0] == data.shape[0] - cfg.seq_length
        assert predictions.shape[1:] == (64, 64)


# ============================================================================
# TESTS: GPS VALIDATION
# ============================================================================

class TestCrossValidator:
    """Test suite for GPS validation."""
    
    def test_add_gps_point(self):
        """Test adding GPS points."""
        
        validator = CrossValidator()
        
        point = GPSPoint(
            name="T1-MINE",
            lon=105.63,
            lat=22.73,
            displacement_mm=np.random.randn(100),
            timestamps=np.arange(100),
            velocity_mm_per_year=-2.5,
            uncertainty_mm=3.0
        )
        
        validator.add_gps_point(point)
        assert len(validator.gps_points) == 1
    
    def test_compare_timeseries(self):
        """Test InSAR vs GPS comparison."""
        
        # Create synthetic InSAR
        H, W = 64, 64
        T = 100
        insar_ts = np.random.randn(T, H, W) * 5 + np.linspace(0, 10, T)[:, np.newaxis, np.newaxis]
        
        # Create lat/lon grid
        lat_grid = np.linspace(22.70, 22.75, H)[:, np.newaxis] * np.ones((1, W))
        lon_grid = np.linspace(105.60, 105.65, W)[np.newaxis, :] * np.ones((H, 1))
        
        timestamps = np.arange(T)
        
        # GPS point in the middle
        gps_point = GPSPoint(
            name="T1",
            lon=105.625,
            lat=22.725,
            displacement_mm=np.linspace(0, 9, T),
            timestamps=np.arange(T),
            velocity_mm_per_year=1.0,
            uncertainty_mm=2.0
        )
        
        validator = CrossValidator()
        validator.add_gps_point(gps_point)
        
        metrics = validator.compare_timeseries(insar_ts, lat_grid, lon_grid, timestamps)
        
        assert metrics.rmse > 0
        assert 0 <= metrics.r2 <= 1
        print(f"Validation metrics: RMSE={metrics.rmse:.2f}, R²={metrics.r2:.3f}")
    
    def test_cross_validate_macs(self):
        """Test MAC classification validation."""
        
        validator = CrossValidator()
        
        truth = np.zeros((64, 64), dtype=int)
        truth[20:40, 20:40] = 1  # One MAC
        
        pred = np.zeros((64, 64), dtype=int)
        pred[20:40, 20:40] = 1
        pred[50:55, 50:55] = 1  # False positive
        
        results = validator.cross_validate_macs(truth, pred, truth)
        
        assert 'accuracy' in results
        assert 'precision' in results
        print(f"MAC validation: Accuracy={results['accuracy']:.2f}")


class TestTimeSeriesValidator:
    """Test suite for time series validation."""
    
    def test_forecast_metrics(self):
        """Test forecast accuracy metrics."""
        
        actual = np.linspace(0, 10, 100)
        forecast = actual + np.random.randn(100) * 0.5
        
        metrics = TimeSeriesValidator.compute_forecast_metrics(
            actual[np.newaxis, :, np.newaxis] * np.ones((1, 100, 64)),
            forecast[np.newaxis, :, np.newaxis] * np.ones((1, 100, 64))
        )
        
        assert metrics['rmse'] < 1.0  # Should be small error
        assert metrics['r2'] > 0.9    # Should have high R²
    
    def test_event_detection(self):
        """Test acceleration event detection."""
        
        time = np.arange(100)
        # Smooth trend + acceleration event
        actual = 0.1 * time + 5 * np.exp(-(time-50)**2/100)
        forecast = actual + np.random.randn(100) * 0.3
        
        results = TimeSeriesValidator.significant_events_detection(actual, forecast, threshold_mm=1.0)
        
        assert results['detection_rate'] >= 0
        print(f"Event detection rate: {results['detection_rate']:.2%}")


# ============================================================================
# INTEGRATION TEST
# ============================================================================

def test_full_pipeline_integration(synthetic_data_256x256, timeseries_5years):
    """Integration test: APS → Kalman → Transformer → Validation."""
    
    # Step 1: APS correction
    corrector = ERA5Corrector()
    igram_corrected = corrector.correct(
        synthetic_data_256x256['interferogram'],
        synthetic_data_256x256['dem'],
        synthetic_data_256x256['coherence'],
        (datetime(2020, 1, 1), datetime(2020, 2, 1))
    )
    
    # Step 2: Adaptive Kalman
    kalman = AdaptiveKalmanFilter(
        synthetic_data_256x256['velocity_map'],
        synthetic_data_256x256['coherence']
    )
    
    ts = timeseries_5years[0][:-1, :256, :256, 0]  # Get first 3D
    # Pad to 256x256
    ts_padded = np.zeros((ts.shape[0], 256, 256))
    ts_padded[:, :ts.shape[1], :ts.shape[2]] = ts
    
    filtered, unc = kalman.filter(ts_padded, np.arange(ts.shape[0]))
    
    # Step 3: Transformer training
    data_train = timeseries_5years[0]
    
    cfg = TransformerConfig(seq_length=30, n_epochs=2)
    model = HydrometTransformerTorch(cfg)
    model.fit(data_train, verbose=False)
    
    # Step 4: Validation
    validator = CrossValidator()
    gps_point = GPSPoint(
        name="T1",
        lon=105.63,
        lat=22.73,
        displacement_mm=np.random.randn(100),
        timestamps=np.arange(100),
        velocity_mm_per_year=-2.5,
        uncertainty_mm=3.0
    )
    validator.add_gps_point(gps_point)
    
    print("\n✓ Integration test passed!")


# ============================================================================
# PYTEST CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
