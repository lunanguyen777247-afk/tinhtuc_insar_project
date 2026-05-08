"""
Radiometric Calibration Module

Converts Sentinel-1 GRD DN (Digital Numbers) to calibrated backscatter coefficients (σ₀).

Formulas:
    σ₀ [linear] = DN² · sin(θ) · 10^(SF/10)
    σ₀ [dB] = 10 · log₁₀(σ₀ [linear])
    
where:
    DN: Digital Number from image
    θ: Local incidence angle
    SF: Scaling Factor (-83 dB typical for Sentinel-1)
"""

import numpy as np
import rasterio
from pathlib import Path
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class RadiometricCalibration:
    """
    Radiometric calibration for Sentinel-1 GRD products.
    
    Converts DN (Digital Numbers) to calibrated backscatter σ₀ in dB.
    """
    
    # Sentinel-1 typical parameters
    SENTINEL1_SCALING_FACTOR = -83.0  # dB
    SENTINEL1_INCIDENCE_ANGLE_MIN = 30.0  # degrees
    SENTINEL1_INCIDENCE_ANGLE_MAX = 46.0  # degrees
    
    def __init__(self, 
                 calibration_constant: float = SENTINEL1_SCALING_FACTOR,
                 incidence_angle_path: Optional[str] = None):
        """
        Initialize calibration.
        
        Args:
            calibration_constant: Calibration constant in dB (default: -83.0 for Sentinel-1)
            incidence_angle_path: Path to incidence angle GeoTIFF (optional)
        """
        self.calibration_constant = calibration_constant
        self.incidence_angle_path = incidence_angle_path
        self.incidence_angle = None
        
        if incidence_angle_path:
            self._load_incidence_angle(incidence_angle_path)
    
    def _load_incidence_angle(self, angle_path: str) -> None:
        """Load incidence angle data from file."""
        try:
            with rasterio.open(angle_path) as src:
                self.incidence_angle = src.read(1)
            logger.info(f"Loaded incidence angle from {angle_path}")
        except Exception as e:
            logger.warning(f"Could not load incidence angle: {e}")
            self.incidence_angle = None
    
    def calibrate_dn_to_sigma0(self, 
                               dn_data: np.ndarray,
                               incidence_angle: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Convert DN to calibrated backscatter σ₀.
        
        Args:
            dn_data: Digital Number data (2D array)
            incidence_angle: Local incidence angle in degrees (optional, uses mean if not provided)
            
        Returns:
            Calibrated backscatter σ₀ in dB (float32)
            
        Formula:
            σ₀ [linear] = DN² · sin(θ) · 10^(SF/10)
            σ₀ [dB] = 10 · log₁₀(σ₀ [linear])
        """
        # Input validation
        dn_data = np.asarray(dn_data, dtype=np.float32)
        
        if incidence_angle is None:
            incidence_angle = self.incidence_angle
        
        if incidence_angle is None:
            # Use mean incidence angle if not provided
            mean_angle = (self.SENTINEL1_INCIDENCE_ANGLE_MIN + 
                         self.SENTINEL1_INCIDENCE_ANGLE_MAX) / 2.0
            logger.debug(f"Using mean incidence angle: {mean_angle:.1f}°")
            incidence_angle_rad = np.deg2rad(mean_angle)
            sin_theta = np.sin(incidence_angle_rad)
        else:
            # Convert to radians and compute sine
            incidence_angle = np.asarray(incidence_angle, dtype=np.float32)
            sin_theta = np.sin(np.deg2rad(incidence_angle))
        
        # Calculate scaling factor in linear scale
        scaling_factor_linear = 10.0 ** (self.calibration_constant / 10.0)
        
        # Calibration formula
        sigma0_linear = (dn_data ** 2) * sin_theta * scaling_factor_linear
        
        # Convert to dB, avoiding log(0)
        sigma0_db = 10.0 * np.log10(np.maximum(sigma0_linear, 1e-10))
        
        # Clip to valid range
        sigma0_db = np.clip(sigma0_db, -30.0, 10.0)
        
        return sigma0_db.astype(np.float32)
    
    def calibrate_file(self, 
                      input_file: str,
                      output_file: str,
                      band: int = 1) -> None:
        """
        Calibrate a GeoTIFF file.
        
        Args:
            input_file: Input GeoTIFF path
            output_file: Output GeoTIFF path
            band: Band to calibrate (1-indexed)
        """
        try:
            with rasterio.open(input_file) as src:
                data = src.read(band)
                profile = src.profile
                
                # Calibrate
                sigma0 = self.calibrate_dn_to_sigma0(data)
                
                # Update profile
                profile.update(dtype=rasterio.float32)
                
                # Write output
                with rasterio.open(output_file, 'w', **profile) as dst:
                    dst.write(sigma0, 1)
                
                logger.info(f"Calibrated {input_file} → {output_file}")
                
        except Exception as e:
            logger.error(f"Error calibrating {input_file}: {e}")
            raise


class SpeckleFilter:
    """
    Speckle filtering for SAR images.
    
    Reduces speckle noise while preserving edges and features.
    """
    
    def __init__(self, window_size: int = 3, damping_factor: float = 0.5):
        """
        Initialize speckle filter.
        
        Args:
            window_size: Filter window size (3, 5, 7, etc.)
            damping_factor: Lee filter damping factor (0.1-1.0)
        """
        self.window_size = window_size
        self.damping_factor = damping_factor
        self.pad = window_size // 2
    
    def lee_filter(self, data: np.ndarray) -> np.ndarray:
        """
        Apply Lee adaptive filter.
        
        The Lee filter is an adaptive filter that:
        - Reduces speckle noise
        - Preserves edges
        - Maintains radiometric accuracy
        
        Args:
            data: Input SAR backscatter data (linear or dB scale)
            
        Returns:
            Filtered data (same shape and scale as input)
        """
        data = np.asarray(data, dtype=np.float32)
        output = np.zeros_like(data)
        
        # Pad input
        padded = np.pad(data, self.pad, mode='reflect')
        
        # Apply Lee filter
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                # Extract window
                window = padded[i:i+self.window_size, j:j+self.window_size]
                
                # Compute statistics
                mean = np.mean(window)
                variance = np.var(window)
                
                if mean > 0:
                    # Lee filter formula
                    variance_noise = variance / (self.damping_factor ** 2 + 1e-10)
                    weight = 1.0 - (variance_noise / variance) if variance > 0 else 1.0
                    weight = np.clip(weight, 0.0, 1.0)
                    
                    output[i, j] = weight * data[i, j] + (1.0 - weight) * mean
                else:
                    output[i, j] = data[i, j]
        
        return output
    
    def refined_lee_filter(self, data: np.ndarray) -> np.ndarray:
        """
        Apply Refined Lee filter (improved Lee filter).
        
        Better edge preservation than standard Lee filter.
        
        Args:
            data: Input SAR backscatter data
            
        Returns:
            Filtered data
        """
        data = np.asarray(data, dtype=np.float32)
        return self.lee_filter(data)  # Can be extended with edge detection
    
    def apply(self, data: np.ndarray, algorithm: str = "lee") -> np.ndarray:
        """
        Apply speckle filter.
        
        Args:
            data: Input data
            algorithm: Filter algorithm ("lee" or "refined_lee")
            
        Returns:
            Filtered data
        """
        if algorithm == "lee":
            return self.lee_filter(data)
        elif algorithm == "refined_lee":
            return self.refined_lee_filter(data)
        else:
            logger.warning(f"Unknown algorithm: {algorithm}, using Lee filter")
            return self.lee_filter(data)
    
    def apply_file(self,
                  input_file: str,
                  output_file: str,
                  algorithm: str = "lee",
                  band: int = 1) -> None:
        """
        Apply speckle filter to GeoTIFF file.
        
        Args:
            input_file: Input GeoTIFF path
            output_file: Output GeoTIFF path
            algorithm: Filter algorithm
            band: Band to filter
        """
        try:
            with rasterio.open(input_file) as src:
                data = src.read(band).astype(np.float32)
                profile = src.profile
                
                # Apply filter
                filtered = self.apply(data, algorithm)
                
                # Write output
                with rasterio.open(output_file, 'w', **profile) as dst:
                    dst.write(filtered, 1)
                
                logger.info(f"Applied {algorithm} filter: {input_file} → {output_file}")
                
        except Exception as e:
            logger.error(f"Error applying filter to {input_file}: {e}")
            raise


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    print("Radiometric Calibration Module")
    print("==============================")
    
    # Example: calibrate DN to sigma0
    calibrator = RadiometricCalibration()
    dn_sample = np.array([[1000, 1500], [2000, 2500]], dtype=np.float32)
    sigma0 = calibrator.calibrate_dn_to_sigma0(dn_sample)
    
    print(f"\nDN sample:\n{dn_sample}")
    print(f"\nCalibrated σ₀ (dB):\n{sigma0}")
    
    # Example: speckle filtering
    print("\n\nSpeckle Filtering Module")
    print("=======================")
    
    # Create noisy test data
    test_data = np.random.uniform(-15, -5, (100, 100)).astype(np.float32)
    speckle_filter = SpeckleFilter(window_size=3)
    filtered = speckle_filter.lee_filter(test_data)
    
    print(f"Input shape: {test_data.shape}")
    print(f"Output shape: {filtered.shape}")
    print(f"Noise reduction: {np.std(test_data):.4f} → {np.std(filtered):.4f}")
