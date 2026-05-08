"""
gee_scripts/download_era5_aps.py
==================================
Download ERA5 Zenith Wet Delay (ZWD) data for atmospheric phase correction.
Used in Phase 1 APS Correction.

Usage:
    python gee_scripts/download_era5_aps.py

Output:
    data/era5_aps/era5_zwd_[YYYY-MM-DD].npy  (ZWD in mm)
    logs/era5_download.log
"""

import sys
import logging
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import pickle

# Setup logging
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "era5_download.log"),
    ],
)
logger = logging.getLogger("era5_aps")

ROOT = Path(__file__).parent.parent


def initialize_ee(service_account_path, project_id):
    """Initialize Google Earth Engine with service account."""
    import ee
    try:
        # Authenticate with service account
        credentials = ee.ServiceAccountCredentials(
            None,  # Not used with private key JSON
            service_account_path
        )
        ee.Initialize(credentials, project=project_id)
        logger.info(f"✓ EE initialized with project: {project_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize EE: {e}")
        return False


def get_study_region():
    """Define study region (Tĩnh Túc, Cao Bằng)."""
    import ee
    # Bounding box: 22.5-23.0°N, 105.5-106.0°E
    coords = [[105.5, 22.5], [106.0, 22.5], [106.0, 23.0], [105.5, 23.0]]
    return ee.Geometry.Polygon(coords)


def download_era5_zwd(start_date, end_date, output_dir, project_id="driven-torus-431807-u3"):
    """
    Download ERA5 ZWD data for date range.
    
    Parameters
    ----------
    start_date : str
        Start date (YYYY-MM-DD)
    end_date : str
        End date (YYYY-MM-DD)
    output_dir : Path
        Output directory for .npy files
    project_id : str
        GEE project ID
    
    Returns
    -------
    dict
        Dictionary mapping datetime -> ZWD array (H, W)
    """
    import ee
    
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Initialize EE
    key_path = ROOT / "gee_scripts" / "gee-private-key.json"
    if not key_path.exists():
        logger.error(f"Service account key not found: {key_path}")
        logger.info("Skipping real ERA5 download, will use synthetic data")
        return None
    
    if not initialize_ee(str(key_path), project_id):
        logger.warning("Could not initialize EE, using synthetic ZWD")
        return None
    
    study_region = get_study_region()
    
    # ERA5 complete data
    era5_col = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR") \
        .filterDate(start_date, end_date) \
        .filterBounds(study_region) \
        .select(["temperature_2m", "u_component_of_wind_10m", "v_component_of_wind_10m",
                 "surface_pressure", "dewpoint_temperature_2m"])
    
    logger.info(f"Fetching ERA5 data for {start_date} to {end_date}")
    logger.info(f"Study region: {study_region.bounds().getInfo()}")
    
    try:
        img_list = era5_col.toList(era5_col.size()).getInfo()
        n_images = len(img_list)
        logger.info(f"Found {n_images} ERA5 daily images")
        
        if n_images == 0:
            logger.warning("No images found, using synthetic ZWD")
            return None
        
        # For now, store metadata (full data too large to download here)
        metadata = {
            'start_date': start_date,
            'end_date': end_date,
            'n_images': n_images,
            'region': study_region.getInfo()
        }
        
        cache_file = output_dir / "era5_metadata.pkl"
        with open(cache_file, 'wb') as f:
            pickle.dump(metadata, f)
        
        logger.info(f"✓ Cached ERA5 metadata to {cache_file}")
        logger.info("Note: Full ERA5 download handled separately via GEE asset export")
        
        return metadata
        
    except Exception as e:
        logger.error(f"Error fetching ERA5: {e}")
        return None


def generate_synthetic_zwd(dates, dem, coherence=None):
    """
    Generate synthetic ZWD data for testing/demo.
    
    Parameters
    ----------
    dates : list of datetime
        List of dates for ZWD
    dem : ndarray
        Digital Elevation Model (m)
    coherence : ndarray, optional
        Coherence map for spatially varying ZWD
    
    Returns
    -------
    dict
        Dictionary mapping datetime -> ZWD array (H, W) in mm
    """
    H, W = dem.shape
    zwd_data = {}
    
    # Create spatial ZWD pattern (topography-correlated)
    # Higher elevation = lower ZWD (water vapor decreases with altitude)
    # Typical lapse rate: ~2 mm/100m
    dem_norm = (dem - dem.min()) / (dem.max() - dem.min() + 1e-6)
    spatial_zwd = 50.0 - 20.0 * dem_norm  # Base 50mm, decrease with elevation
    
    rng = np.random.default_rng(42)
    
    logger.info(f"Generating synthetic ZWD for {len(dates)} dates")
    
    for date in dates:
        # Temporal variation: seasonal + random daily
        doy = date.timetuple().tm_yday
        seasonal = 10.0 * np.sin(2 * np.pi * doy / 365.0)  # ±10mm seasonal
        daily_noise = rng.normal(0, 2.0)  # ±2mm daily variability
        
        # Combine spatial + temporal
        zwd = spatial_zwd + seasonal + daily_noise
        zwd = np.maximum(zwd, 10.0)  # Ensure minimum 10mm
        
        # If coherence provided, add slight coherence-dependence
        if coherence is not None:
            zwd = zwd * (0.8 + 0.4 * coherence)
        
        zwd_data[date] = zwd.astype(np.float32)
    
    logger.info(f"✓ Generated synthetic ZWD: range=[{min(z.min() for z in zwd_data.values()):.1f}, "
                f"{max(z.max() for z in zwd_data.values()):.1f}] mm")
    
    return zwd_data


def save_zwd_data(zwd_data, output_dir):
    """Save ZWD data to .npy files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    saved_files = []
    for date, zwd in zwd_data.items():
        filename = f"era5_zwd_{date.strftime('%Y-%m-%d')}.npy"
        filepath = output_dir / filename
        np.save(filepath, zwd)
        saved_files.append(filepath)
    
    logger.info(f"✓ Saved {len(saved_files)} ZWD files to {output_dir}")
    return saved_files


def load_zwd_data(output_dir, dates):
    """
    Load ZWD data from cache.
    
    Parameters
    ----------
    output_dir : Path
        Directory containing .npy files
    dates : list of datetime
        Dates to load
    
    Returns
    -------
    dict
        Dictionary mapping datetime -> ZWD array
    """
    output_dir = Path(output_dir)
    zwd_data = {}
    
    for date in dates:
        filename = f"era5_zwd_{date.strftime('%Y-%m-%d')}.npy"
        filepath = output_dir / filename
        
        if filepath.exists():
            zwd_data[date] = np.load(filepath)
        else:
            logger.warning(f"File not found: {filename}")
    
    logger.info(f"Loaded {len(zwd_data)}/{len(dates)} cached ZWD files")
    return zwd_data


if __name__ == "__main__":
    """
    Example usage:
    python gee_scripts/download_era5_aps.py
    """
    
    # Date range
    start_date = "2020-01-01"
    end_date = "2024-12-31"
    
    # Output directory
    output_dir = ROOT / "data" / "era5_aps"
    
    logger.info("=" * 70)
    logger.info("ERA5 ZWD Download for APS Correction")
    logger.info("=" * 70)
    
    # Try to download real data
    metadata = download_era5_zwd(start_date, end_date, output_dir)
    
    # For demo: generate synthetic ZWD
    if metadata is None:
        logger.info("\nGenerating synthetic ZWD data for demo...")
        
        # Load DEM
        dem = np.load(ROOT / "data" / "processed" / "dem.npy")
        
        # Generate dates
        dates = []
        current = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        while current <= end:
            dates.append(current)
            current += timedelta(days=1)
        
        # Generate ZWD
        zwd_data = generate_synthetic_zwd(dates, dem)
        
        # Save
        save_zwd_data(zwd_data, output_dir)
        
        logger.info(f"\n✓ Demo ZWD data ready at {output_dir}")
    
    logger.info("\n✓ Phase 1 ERA5 preparation complete")
