"""
scripts/apply_aps_correction.py
================================
Apply atmospheric phase correction to InSAR displacement data.
Phase 1: Main execution script.

Usage:
    python scripts/apply_aps_correction.py --method era5 --output-dir outputs/

Outputs:
    outputs/displacement_aps_corrected.npy
    outputs/aps_phase_screen.npy
    outputs/aps_correction_report.txt
"""

import argparse
import logging
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.corrections.atmospheric_correction import (
    ERA5Corrector, GACOSCorrector, AtmosphericConfig, correct_interferogram
)
from gee_scripts.download_era5_aps import (
    load_zwd_data, generate_synthetic_zwd, save_zwd_data
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(ROOT / "logs" / "aps_correction.log"),
    ],
)
logger = logging.getLogger("aps_correction")


def main(method="era5", use_synthetic=True):
    """
    Apply APS correction to displacement timeseries.
    
    Parameters
    ----------
    method : str
        Correction method: "era5" or "gacos"
    use_synthetic : bool
        Use synthetic ZWD if real data unavailable
    
    Returns
    -------
    displacement_corrected : ndarray
        APS-corrected displacement (n_time, H, W)
    report : dict
        Correction statistics
    """
    
    logger.info("=" * 70)
    logger.info(f"PHASE 1: APS CORRECTION (Method: {method.upper()})")
    logger.info("=" * 70)
    
    # Load processed data
    processed_dir = ROOT / "data" / "processed"
    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    
    logger.info("Loading InSAR data...")
    displacement = np.load(processed_dir / "displacement.npy")  # (n_time, H, W)
    dem = np.load(processed_dir / "dem.npy")  # (H, W)
    lat_grid = np.load(processed_dir / "lat_grid.npy")
    lon_grid = np.load(processed_dir / "lon_grid.npy")
    time_days = np.load(processed_dir / "time_days.npy")
    
    H, W = dem.shape
    n_time = len(time_days)
    
    logger.info(f"  Displacement: {displacement.shape}, range=[{np.nanmin(displacement):.1f}, "
                f"{np.nanmax(displacement):.1f}] mm")
    logger.info(f"  DEM: {dem.shape}, range=[{dem.min():.1f}, {dem.max():.1f}] m")
    logger.info(f"  Time points: {n_time}, days range=[{time_days.min():.0f}, {time_days.max():.0f}]")
    
    # Create dates from time_days
    start_date = datetime(2020, 1, 1)
    dates = np.array([start_date + timedelta(days=int(d)) for d in time_days])
    
    # Create synthetic coherence map (higher in deformation areas)
    logger.info("Creating coherence map...")
    x, y = np.meshgrid(np.linspace(0, 1, W), np.linspace(0, 1, H))
    cx, cy = 0.4, 0.4
    coherence = 0.5 + 0.4 * np.exp(-((x-cx)**2 + (y-cy)**2) / 0.1)  # High in center
    coherence = np.clip(coherence, 0.2, 0.95)
    
    logger.info(f"  Coherence: range=[{coherence.min():.2f}, {coherence.max():.2f}]")
    
    # ─── Prepare ZWD data ───
    logger.info(f"Preparing ZWD data (method={method})...")
    
    era5_dir = ROOT / "data" / "era5_aps"
    era5_dir.mkdir(exist_ok=True, parents=True)
    
    # Try to load from cache
    zwd_data = load_zwd_data(era5_dir, dates)
    
    if len(zwd_data) < len(dates):
        logger.info(f"  Only {len(zwd_data)}/{len(dates)} ZWD files in cache")
        
        if use_synthetic or method == "synthetic":
            logger.info("  Generating synthetic ZWD data...")
            zwd_data = generate_synthetic_zwd(dates, dem, coherence)
            save_zwd_data(zwd_data, era5_dir)
        else:
            logger.warning("  No ZWD data available. Use synthetic mode.")
            return None, None
    
    logger.info(f"  ZWD ready: {len(zwd_data)} dates")
    
    # ─── Initialize corrector ───
    cfg = AtmosphericConfig(
        method=method,
        coherence_threshold=0.4,
        max_iterations=3
    )
    
    if method == "era5":
        corrector = ERA5Corrector(cfg)
        logger.info("Using ERA5Corrector (11 km resolution, 3 iterations)")
    elif method == "gacos":
        corrector = GACOSCorrector(cfg)
        logger.info("Using GACOSCorrector (2 km resolution)")
    else:
        logger.error(f"Unknown method: {method}")
        return None, None
    
    # ─── Apply correction ───
    logger.info("Applying APS correction to displacement...")
    
    displacement_corrected = np.zeros_like(displacement)
    aps_screens = np.zeros_like(displacement)  # Store APS phase screens
    
    # Variance reduction tracking
    variance_before = []
    variance_after = []
    
    for t in range(n_time):
        if t > 0:  # Need pairs for interferogram
            # Get two consecutive ZWD maps
            date1 = dates[t-1]
            date2 = dates[t]
            
            zwd1 = zwd_data.get(date1, np.ones((H, W)) * 40.0)
            zwd2 = zwd_data.get(date2, np.ones((H, W)) * 40.0)
            
            # Apply correction to displacement
            disp_before = displacement[t]
            
            # Simulate APS phase in mm
            aps_phase = ERA5Corrector._zwd_to_phase_mm(zwd1, zwd2)  # mm
            
            # Remove APS from displacement
            disp_corrected = correct_interferogram(
                disp_before,
                dem=dem,
                coherence=coherence,
                dates=(date1, date2),
                method=method,
                era5_zwd1=zwd1,
                era5_zwd2=zwd2
            )
            
            displacement_corrected[t] = disp_corrected
            aps_screens[t] = aps_phase
            
            # Track variance
            var_before = np.nanvar(disp_before)
            var_after = np.nanvar(disp_corrected)
            variance_before.append(var_before)
            variance_after.append(var_after)
            
            if (t + 1) % 5 == 0:
                logger.info(f"  Time step {t+1}/{n_time}: "
                           f"var {var_before:.1f}→{var_after:.1f} mm², "
                           f"APS range=[{aps_phase.min():.1f}, {aps_phase.max():.1f}] mm")
        else:
            # First frame: no pair
            displacement_corrected[t] = displacement[t]
            aps_screens[t] = 0.0
    
    # ─── Compute statistics ───
    variance_before = np.array(variance_before)
    variance_after = np.array(variance_after)
    variance_reduction = 100 * (1 - variance_after.mean() / variance_before.mean())
    
    aps_mean = np.nanmean(aps_screens)
    aps_std = np.nanstd(aps_screens)
    aps_range = (np.nanmin(aps_screens), np.nanmax(aps_screens))
    
    report = {
        'method': method,
        'n_time': n_time,
        'shape': (H, W),
        'variance_before': variance_before.mean(),
        'variance_after': variance_after.mean(),
        'variance_reduction_pct': variance_reduction,
        'aps_mean': aps_mean,
        'aps_std': aps_std,
        'aps_range': aps_range,
        'coherence_mean': coherence.mean(),
        'coherence_range': (coherence.min(), coherence.max()),
    }
    
    logger.info("✓ APS correction complete")
    logger.info(f"  Variance reduction: {variance_before.mean():.1f} → {variance_after.mean():.1f} mm² "
                f"({variance_reduction:+.1f}%)")
    logger.info(f"  APS phase screen: mean={aps_mean:.1f} mm, std={aps_std:.1f} mm, "
                f"range=[{aps_range[0]:.1f}, {aps_range[1]:.1f}] mm")
    
    # ─── Save outputs ───
    logger.info("Saving outputs...")
    np.save(output_dir / "displacement_aps_corrected.npy", displacement_corrected.astype(np.float32))
    np.save(output_dir / "aps_phase_screens.npy", aps_screens.astype(np.float32))
    np.save(output_dir / "coherence_map.npy", coherence.astype(np.float32))
    
    # Save report
    report_text = f"""
APS CORRECTION REPORT
{'='*60}
Date: {datetime.now().isoformat()}
Method: {report['method'].upper()}
Study Region: Tĩnh Túc, Cao Bằng
Grid Size: {report['shape'][0]} x {report['shape'][1]} pixels
Time Points: {report['n_time']}

VARIANCE REDUCTION (mm²)
  Before: {report['variance_before']:.2f}
  After:  {report['variance_after']:.2f}
  Reduction: {report['variance_reduction_pct']:.1f}%

ATMOSPHERIC PHASE SCREEN (mm)
  Mean: {report['aps_mean']:.2f}
  Std:  {report['aps_std']:.2f}
  Range: [{report['aps_range'][0]:.2f}, {report['aps_range'][1]:.2f}]

COHERENCE STATISTICS
  Mean: {report['coherence_mean']:.3f}
  Range: [{report['coherence_range'][0]:.3f}, {report['coherence_range'][1]:.3f}]

INTERPRETATION
  - Variance reduction > 10%: APS correction effective
  - APS std < 5mm: Strong atmospheric signal detected
  - Next step: Feed to P-SBAS with Adaptive Kalman filtering

FILES SAVED
  ✓ displacement_aps_corrected.npy
  ✓ aps_phase_screens.npy
  ✓ coherence_map.npy
"""
    
    report_file = output_dir / "aps_correction_report.txt"
    with open(report_file, 'w') as f:
        f.write(report_text)
    
    logger.info(f"  Saved to: {output_dir}/")
    logger.info(f"  Report: {report_file}")
    
    return displacement_corrected, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply APS correction to InSAR data")
    parser.add_argument("--method", default="era5", choices=["era5", "gacos", "synthetic"],
                       help="Correction method")
    parser.add_argument("--synthetic", action="store_true",
                       help="Force synthetic ZWD data")
    args = parser.parse_args()
    
    displacement_corrected, report = main(
        method=args.method,
        use_synthetic=args.synthetic
    )
    
    if report:
        print("\n" + "="*70)
        print("APS CORRECTION SUMMARY")
        print("="*70)
        print(f"Method: {report['method']}")
        print(f"Variance reduction: {report['variance_reduction_pct']:.1f}%")
        print(f"APS range: [{report['aps_range'][0]:.1f}, {report['aps_range'][1]:.1f}] mm")
        print("✓ Ready for Phase 2 (Adaptive Kalman)")
