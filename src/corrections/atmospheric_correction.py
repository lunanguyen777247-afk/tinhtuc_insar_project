"""
src/corrections/atmospheric_correction.py
==========================================
Atmospheric Phase Screen (APS) correction for InSAR interferograms.

References:
- Yu, C., Li, Z., Penna, N. T. (2018). GACOS: Generic Atmospheric Correction Online Service.
  Available at: http://cryosat.mssl.ucl.ac.uk/gacos/
- Bevis, M., Businger, S., Herring, T. A., et al. (1992). GPS meteorology: Remote sensing of 
  atmospheric water vapor using the Global Positioning System. J. Geophys. Res.
"""

import numpy as np
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Tuple, Dict
from datetime import datetime, timedelta
from scipy import interpolate
from scipy.ndimage import gaussian_filter

logger = logging.getLogger(__name__)


@dataclass
class AtmosphericConfig:
    """Configuration for APS correction."""
    method: str = "era5"  # "era5" or "gacos"
    window_size: int = 5  # Smoothing window (pixels)
    dem_ref_height: float = 500.0  # Reference DEM height (m)
    scale_factor: float = -0.0000225  # dPhase/dHeight (rad/m) for C-band
    max_iterations: int = 3  # For iterative correction
    coherence_threshold: float = 0.4  # Min coherence for valid correction


class AtmosphericCorrector:
    """
    Base class for atmospheric phase screen correction.
    
    The atmospheric phase is dominated by water vapor in the troposphere:
        φ_atm = φ_hydro + φ_hydrostatic
    
    where:
    - φ_hydro: phase due to water vapor (dominates)
    - φ_hydrostatic: phase due to dry air (usually negligible)
    
    Reduction factor for C-band:
        φ_atm ≈ -5.16e-7 * ZWD  (radians)
        where ZWD = Zenith Wet Delay (mm)
    """
    
    def __init__(self, cfg: Optional[AtmosphericConfig] = None):
        """
        Initialize atmospheric corrector.
        
        Args:
            cfg: Configuration object, default uses ERA5 method
        """
        self.cfg = cfg or AtmosphericConfig()
        logger.info(f"Initialized AtmosphericCorrector with method: {self.cfg.method}")
    
    def correct(self, 
                interferogram: np.ndarray,
                dem: np.ndarray,
                coherence: np.ndarray,
                dates: Tuple[datetime, datetime],
                dem_error: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Apply atmospheric correction to interferogram.
        
        Args:
            interferogram: Wrapped or unwrapped phase (radians), shape (H, W)
            dem: Digital Elevation Model (m), shape (H, W)
            coherence: Coherence map [0,1], shape (H, W)
            dates: (date1, date2) tuple for interferogram time span
            dem_error: DEM error map (m), shape (H, W), optional
        
        Returns:
            Corrected interferogram, same shape as input
        """
        raise NotImplementedError("Subclass must implement correct()")
    
    def _estimate_dem_error(self, 
                            interferogram: np.ndarray,
                            dem: np.ndarray,
                            coherence: np.ndarray) -> np.ndarray:
        """
        Estimate DEM error from interferogram-topography correlation.
        
        DEM error introduces spurious topographic phase:
            φ_dem_err = (4π / λ) * (B_perp / r * sin(θ)) * ΔH_err
        
        where B_perp = perpendicular baseline, ΔH_err = DEM error
        
        Returns:
            Estimated DEM error map (m)
        """
        # High-pass filter to remove DEM effect and isolate atmospheric/deformation
        dem_smooth = gaussian_filter(dem, sigma=5)  # Low-pass
        dem_residual = dem - dem_smooth  # High-pass
        
        # Compute dem error from coherence-weighted correlation
        valid_mask = (coherence > self.cfg.coherence_threshold)
        
        if np.sum(valid_mask) < 10:
            logger.warning("Too few valid pixels for DEM error estimation")
            return np.zeros_like(dem)
        
        # Linear regression: interferogram ~ dem_residual
        X = dem_residual[valid_mask].flatten()
        y = interferogram[valid_mask].flatten()
        
        # Fit: y = a*X + b
        A = np.vstack([X, np.ones(len(X))]).T
        coeffs = np.linalg.lstsq(A, y, rcond=None)[0]
        dem_error_slope = coeffs[0]
        
        # Scale back to DEM error (assuming C-band, ~0.056 m wavelength)
        wavelength = 0.056  # Sentinel-1 C-band
        dem_error = dem_residual * dem_error_slope / (4 * np.pi / wavelength)
        
        logger.info(f"Estimated DEM error slope: {dem_error_slope:.6f} rad/m")
        return dem_error
    
    def _apply_topographic_filtering(self, 
                                     phase: np.ndarray,
                                     dem: np.ndarray) -> np.ndarray:
        """
        Apply high-pass filter to remove long-wavelength DEM-correlated phase.
        Uses Butterworth filter in wavenumber domain.
        """
        from scipy import fft
        
        H, W = phase.shape
        
        # FFT
        phase_fft = fft.fft2(phase)
        phase_fft = fft.fftshift(phase_fft)
        
        # Create wavenumber grid
        ky = fft.fftfreq(H)
        kx = fft.fftfreq(W)
        Kx, Ky = np.meshgrid(kx, ky)
        K = np.sqrt(Kx**2 + Ky**2)
        
        # Butterworth high-pass filter (cutoff ~2 km)
        cutoff_wavenumber = 1 / 2000  # 1/(2km) in 1/m
        order = 2
        butterworth = 1 / (1 + (cutoff_wavenumber / (K + 1e-10))**(2*order))
        
        # Apply filter
        phase_fft_filtered = phase_fft * butterworth
        phase_fft = fft.ifftshift(phase_fft_filtered)
        phase_filtered = np.real(fft.ifft2(phase_fft))
        
        return phase_filtered


class ERA5Corrector(AtmosphericCorrector):
    """
    ERA5-based atmospheric correction using ZWD (Zenith Wet Delay) from 
    ECMWF ERA5 reanalysis data.
    
    Advantage: Free, global, continuous coverage
    Limitation: ~11 km spatial resolution
    """
    
    def correct(self,
                interferogram: np.ndarray,
                dem: np.ndarray,
                coherence: np.ndarray,
                dates: Tuple[datetime, datetime],
                era5_zwd1: Optional[np.ndarray] = None,
                era5_zwd2: Optional[np.ndarray] = None,
                dem_error: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Correct atmospheric phase using ERA5 ZWD.
        
        Args:
            interferogram: Phase (rad)
            dem: DEM (m)
            coherence: Coherence map
            dates: (date1, date2) for interferogram
            era5_zwd1: ZWD at date1 (mm), shape (H, W)
            era5_zwd2: ZWD at date2 (mm), shape (H, W)
            dem_error: Known DEM error (m), optional
        
        Returns:
            Corrected interferogram
        """
        logger.info("Applying ERA5-based atmospheric correction...")
        
        corrected = interferogram.copy()
        
        # Remove topographic phase first (high-pass filter)
        if dem_error is not None:
            corrected = self._remove_dem_phase(corrected, dem, dem_error)
        
        # ERA5 phase difference
        if era5_zwd1 is not None and era5_zwd2 is not None:
            # ZWD → phase conversion (C-band)
            # φ = -5.16e-7 * ZWD (rad, where ZWD in mm)
            zwd_conversion = -5.16e-7
            era5_phase_diff = (zwd_conversion * (era5_zwd2 - era5_zwd1))
            
            # Remove ERA5 estimate
            corrected = corrected - era5_phase_diff
            logger.info(f"ERA5 APS range: [{era5_phase_diff.min():.4f}, "
                       f"{era5_phase_diff.max():.4f}] rad")
        
        # Iterative refinement: estimate residual APS from low-coherence pixels
        corrected = self._iterative_refinement(corrected, coherence)
        
        return corrected
    
    def _remove_dem_phase(self,
                         phase: np.ndarray,
                         dem: np.ndarray,
                         dem_error: np.ndarray) -> np.ndarray:
        """Remove phase induced by DEM error."""
        # φ_dem = (4π/λ) * B_perp/r * sin(θ) * ΔH
        # Assuming small DEM error contribution, approximate as linear
        wavelength = 0.056
        B_perp = 100  # Typical perpendicular baseline (m)
        r = 830000  # Slant range (m)
        theta = np.radians(34)  # Incident angle
        
        dem_phase = (4 * np.pi / wavelength) * (B_perp / r * np.sin(theta)) * dem_error
        return phase - dem_phase
    
    def _iterative_refinement(self,
                              phase: np.ndarray,
                              coherence: np.ndarray,
                              n_iter: int = 2) -> np.ndarray:
        """
        Iteratively refine residual APS estimation.
        Uses pixels with high coherence to constrain low-coherence regions.
        """
        refined = phase.copy()
        
        for it in range(n_iter):
            # Fit polynomial to high-coherence pixels
            mask = coherence > 0.6
            
            if np.sum(mask) < 100:
                logger.warning(f"Iteration {it}: Too few high-coherence pixels")
                break
            
            # Fit 2D polynomial
            y_idx, x_idx = np.meshgrid(np.arange(phase.shape[1]), 
                                       np.arange(phase.shape[0]))
            
            X = np.column_stack([
                x_idx[mask],
                y_idx[mask],
                x_idx[mask]**2,
                y_idx[mask]**2,
                x_idx[mask]*y_idx[mask],
                np.ones(np.sum(mask))
            ])
            
            y = refined[mask]
            try:
                coeffs = np.linalg.lstsq(X, y, rcond=None)[0]
                
                # Construct residual APS map
                X_full = np.column_stack([
                    x_idx.flatten(),
                    y_idx.flatten(),
                    x_idx.flatten()**2,
                    y_idx.flatten()**2,
                    x_idx.flatten()*y_idx.flatten(),
                    np.ones(x_idx.size)
                ])
                
                aps_model = (X_full @ coeffs).reshape(phase.shape)
                refined = refined - aps_model
                
                logger.info(f"Iteration {it+1}: Residual APS removed, "
                           f"std = {np.std(aps_model):.4f} rad")
            except np.linalg.LinAlgError:
                logger.warning(f"Iteration {it}: Linear algebra error, skipping")
        
        return refined


class GACOSCorrector(AtmosphericCorrector):
    """
    GACOS-based atmospheric correction.
    Requires GACOS data download from: http://cryosat.mssl.ucl.ac.uk/gacos/
    
    Advantage: Higher spatial resolution (~2 km)
    Limitation: Requires external data download
    """
    
    def __init__(self, gacos_dir: Optional[Path] = None, 
                 cfg: Optional[AtmosphericConfig] = None):
        """
        Initialize GACOS corrector.
        
        Args:
            gacos_dir: Directory containing GACOS .ztd files
            cfg: Configuration
        """
        super().__init__(cfg)
        self.gacos_dir = Path(gacos_dir) if gacos_dir else Path("data/gacos")
    
    def correct(self,
                interferogram: np.ndarray,
                dem: np.ndarray,
                coherence: np.ndarray,
                dates: Tuple[datetime, datetime],
                gacos_file1: Optional[Path] = None,
                gacos_file2: Optional[Path] = None,
                dem_error: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Correct using GACOS ZTD data.
        
        Args:
            interferogram: Phase (rad)
            dem: DEM (m)
            coherence: Coherence
            dates: (date1, date2)
            gacos_file1: Path to GACOS .ztd file for date1
            gacos_file2: Path to GACOS .ztd file for date2
            dem_error: DEM error, optional
        
        Returns:
            Corrected interferogram
        """
        logger.info("Applying GACOS-based atmospheric correction...")
        
        if gacos_file1 is None or gacos_file2 is None:
            logger.warning("GACOS files not provided, using time-averaged correction")
            return self._apply_time_averaged_correction(interferogram, coherence)
        
        try:
            ztd1 = self._load_gacos_ztd(gacos_file1)
            ztd2 = self._load_gacos_ztd(gacos_file2)
        except Exception as e:
            logger.error(f"Failed to load GACOS files: {e}")
            return interferogram
        
        # ZTD → phase conversion
        ztd_to_phase = -2.3e-6  # rad/mm for C-band
        aps_gacos = ztd_to_phase * (ztd2 - ztd1)
        
        corrected = interferogram - aps_gacos
        logger.info(f"GACOS APS range: [{aps_gacos.min():.4f}, "
                   f"{aps_gacos.max():.4f}] rad")
        
        # With high-coherence refinement
        corrected = self._refine_with_coherence(corrected, coherence, dem)
        
        return corrected
    
    def _load_gacos_ztd(self, gacos_file: Path) -> np.ndarray:
        """
        Load GACOS .ztd file (binary format).
        Format: 4-byte float, row-major (Western hemisphere convention)
        """
        with open(gacos_file, 'rb') as f:
            data = np.fromfile(f, dtype=np.float32)
        
        # Reshape to 2D (assuming 3601x3601 for 30-arc-second ZTD)
        ztd = data.reshape(3601, 3601)
        return ztd
    
    def _refine_with_coherence(self,
                               phase: np.ndarray,
                               coherence: np.ndarray,
                               dem: np.ndarray) -> np.ndarray:
        """Refine correction using high-coherence pixels."""
        # Use only high-coherence regions to estimate residual APS
        mask = coherence > 0.7
        
        if np.sum(mask) < 50:
            return phase
        
        # Estimate residual APS from high-coherence pixels
        residual = np.median(phase[mask])
        return phase - residual
    
    def _apply_time_averaged_correction(self,
                                       interferogram: np.ndarray,
                                       coherence: np.ndarray) -> np.ndarray:
        """Apply simple time-averaged correction when GACOS data unavailable."""
        # Estimate APS as spatial average of high-coherence pixels
        mask = coherence > 0.7
        if np.sum(mask) > 100:
            avg_aps = np.mean(interferogram[mask])
            return interferogram - avg_aps
        return interferogram


# Utility function for end-user
def correct_interferogram(
    interferogram: np.ndarray,
    dem: np.ndarray,
    coherence: np.ndarray,
    dates: Tuple[datetime, datetime],
    method: str = "era5",
    era5_zwd1: Optional[np.ndarray] = None,
    era5_zwd2: Optional[np.ndarray] = None,
    gacos_dir: Optional[Path] = None,
) -> np.ndarray:
    """
    Convenience function for atmospheric correction.
    
    Example:
        corrected_igram = correct_interferogram(
            igram, dem, coh, (date1, date2),
            method="era5",
            era5_zwd1=zwd1, era5_zwd2=zwd2
        )
    """
    if method == "era5":
        corrector = ERA5Corrector()
        return corrector.correct(
            interferogram, dem, coherence, dates,
            era5_zwd1=era5_zwd1, era5_zwd2=era5_zwd2
        )
    elif method == "gacos":
        corrector = GACOSCorrector(gacos_dir=gacos_dir)
        return corrector.correct(
            interferogram, dem, coherence, dates
        )
    else:
        raise ValueError(f"Unknown correction method: {method}")


# Static helper functions

def _zwd_to_phase_mm(zwd1_mm: np.ndarray, zwd2_mm: np.ndarray) -> np.ndarray:
    """
    Convert ZWD difference to atmospheric phase for C-band.
    
    Parameters
    ----------
    zwd1_mm : ndarray
        Zenith Wet Delay at date 1 (mm)
    zwd2_mm : ndarray
        Zenith Wet Delay at date 2 (mm)
    
    Returns
    -------
    phase_mm : ndarray
        Atmospheric phase difference (mm)
        
    Notes:
        C-band conversion factor: φ = -5.16e-7 * ZWD (rad/mm)
        To convert to mm: phase_mm = phase_rad * wavelength / (4π)
        For Sentinel-1: λ = 5.6 cm
    """
    wavelength = 0.056  # m, Sentinel-1 C-band
    zwd_conversion = -5.16e-7  # rad/mm
    
    # Phase difference in radians
    phase_diff_rad = zwd_conversion * (zwd2_mm - zwd1_mm)
    
    # Convert to mm
    phase_mm = phase_diff_rad * wavelength / (4 * np.pi)
    
    return phase_mm


# Add as staticmethod to ERA5Corrector for convenience
ERA5Corrector._zwd_to_phase_mm = staticmethod(_zwd_to_phase_mm)
