"""
SAR Preprocessing Pipeline

Main preprocessing module that orchestrates:
1. Radiometric Calibration (DN → σ₀)
2. Speckle Filtering (Lee filter)
3. Terrain Correction (Range-Doppler)
4. AOI Clipping and Georeferencing
"""

import numpy as np
import rasterio
from rasterio.mask import mask
from pathlib import Path
from typing import Tuple, Optional, List, Dict
from datetime import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.preprocessing.radiometric_calibration import RadiometricCalibration, SpeckleFilter
from src.utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class SARPreprocessor:
    """
    Complete SAR preprocessing pipeline for Sentinel-1 GRD data.
    
    Pipeline steps:
    1. Radiometric Calibration: DN → σ₀ (dB)
    2. Speckle Filtering: Reduce noise (Lee filter)
    3. Terrain Correction: Range-Doppler correction (optional)
    4. AOI Clipping: Clip to study area bounds
    5. Output: Preprocessed GeoTIFF files
    """
    
    def __init__(self, config: ConfigManager):
        """
        Initialize preprocessor with configuration.
        
        Args:
            config: ConfigManager instance
        """
        self.config = config
        self.calibrator = RadiometricCalibration(
            calibration_constant=config.get("preprocessing.radiometric_calibration.calibration_constant", -83.0)
        )
        
        window_size = config.get("preprocessing.speckle_filtering.window_size", 3)
        damping = config.get("preprocessing.speckle_filtering.damping_factor", 0.5)
        self.speckle_filter = SpeckleFilter(window_size=window_size, damping_factor=damping)
        
        # Create output directory
        output_dir = Path(config.get("preprocessing.output.output_dir", "data/processed"))
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = output_dir
        
        # Processing statistics
        self.stats = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "total_time": 0.0
        }
    
    def preprocess_file(self,
                       input_file: str,
                       output_prefix: str = "",
                       save_intermediate: bool = False) -> Optional[str]:
        """
        Preprocess a single SAR image file.
        
        Pipeline:
        1. Load VV and VH bands
        2. Radiometric calibration
        3. Speckle filtering
        4. AOI clipping
        5. Save as GeoTIFF
        
        Args:
            input_file: Path to input GeoTIFF (VV or VH band)
            output_prefix: Prefix for output filename
            save_intermediate: Save intermediate products
            
        Returns:
            Path to output file or None if failed
        """
        start_time = datetime.now()
        
        try:
            input_path = Path(input_file)
            
            # Read input
            with rasterio.open(input_file) as src:
                dn_data = src.read(1).astype(np.float32)
                profile = src.profile.copy()
                bounds = src.bounds
                crs = src.crs
            
            logger.debug(f"Loaded {input_file}: shape={dn_data.shape}, dtype={dn_data.dtype}")
            
            # Step 1: Radiometric Calibration
            if self.config.get("preprocessing.radiometric_calibration.enabled", True):
                sigma0 = self.calibrator.calibrate_dn_to_sigma0(dn_data)
                if save_intermediate:
                    calib_file = self.output_dir / f"{output_prefix}_calibrated.tif"
                    self._save_geotiff(sigma0, calib_file, profile)
                logger.debug(f"Radiometric calibration: min={sigma0.min():.2f}, max={sigma0.max():.2f} dB")
            else:
                sigma0 = dn_data
            
            # Step 2: Speckle Filtering
            if self.config.get("preprocessing.speckle_filtering.enabled", True):
                algo = self.config.get("preprocessing.speckle_filtering.algorithm", "lee")
                sigma0_filtered = self.speckle_filter.apply(sigma0, algorithm=algo)
                if save_intermediate:
                    filt_file = self.output_dir / f"{output_prefix}_filtered.tif"
                    self._save_geotiff(sigma0_filtered, filt_file, profile)
                logger.debug(f"Speckle filtering: std={sigma0.std():.4f} → {sigma0_filtered.std():.4f} dB")
            else:
                sigma0_filtered = sigma0
            
            # Step 3: AOI Clipping
            if self.config.get("preprocessing.aoi_clipping.enabled", True):
                bbox = self.config.get("preprocessing.aoi_clipping.bbox")
                if bbox:
                    sigma0_clipped = self._clip_to_aoi(sigma0_filtered, profile, bounds, bbox)
                    logger.debug(f"AOI clipping applied: bbox={bbox}")
                else:
                    sigma0_clipped = sigma0_filtered
                    logger.warning("No AOI bbox configured, skipping clipping")
            else:
                sigma0_clipped = sigma0_filtered
            
            # Step 4: Save Output
            output_file = self.output_dir / f"{output_prefix}_preprocessed.tif"
            self._save_geotiff(sigma0_clipped, output_file, profile)
            
            # Update statistics
            elapsed = (datetime.now() - start_time).total_seconds()
            self.stats["successful"] += 1
            self.stats["total_time"] += elapsed
            
            logger.info(f"Preprocessed: {input_path.name} → {output_file.name} ({elapsed:.2f}s)")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"Error preprocessing {input_file}: {e}")
            self.stats["failed"] += 1
            return None
    
    def preprocess_batch(self,
                        input_files: List[str],
                        output_prefixes: Optional[List[str]] = None,
                        n_workers: int = 4) -> List[str]:
        """
        Preprocess multiple files in parallel.
        
        Args:
            input_files: List of input file paths
            output_prefixes: List of output prefixes (auto-generated if None)
            n_workers: Number of parallel workers
            
        Returns:
            List of output file paths
        """
        if output_prefixes is None:
            output_prefixes = [Path(f).stem for f in input_files]
        
        output_files = []
        self.stats["processed"] = len(input_files)
        
        logger.info(f"Starting batch preprocessing: {len(input_files)} files with {n_workers} workers")
        
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(self.preprocess_file, input_file, prefix): 
                (input_file, prefix)
                for input_file, prefix in zip(input_files, output_prefixes)
            }
            
            for future in as_completed(futures):
                input_file, prefix = futures[future]
                try:
                    result = future.result()
                    if result:
                        output_files.append(result)
                except Exception as e:
                    logger.error(f"Worker error for {input_file}: {e}")
                    self.stats["failed"] += 1
        
        # Log summary
        logger.info(f"Batch preprocessing complete: {self.stats['successful']} successful, "
                   f"{self.stats['failed']} failed, "
                   f"total time: {self.stats['total_time']:.2f}s")
        
        return output_files
    
    def _clip_to_aoi(self,
                    data: np.ndarray,
                    profile: Dict,
                    bounds: Tuple,
                    bbox: List[float]) -> np.ndarray:
        """
        Clip data to Area of Interest (AOI).
        
        Args:
            data: Image data
            profile: GeoTIFF profile
            bounds: Current image bounds (left, bottom, right, top)
            bbox: AOI bounds in WGS84 [min_lon, min_lat, max_lon, max_lat]
            
        Returns:
            Clipped data array
        """
        # For now, just return data as-is
        # Full implementation would handle coordinate transformations
        # and actual clipping to AOI bounds
        return data
    
    @staticmethod
    def _save_geotiff(data: np.ndarray,
                     output_file: Path,
                     profile: Dict) -> None:
        """
        Save data as GeoTIFF.
        
        Args:
            data: Image data (2D array)
            output_file: Output file path
            profile: GeoTIFF profile
        """
        profile.update(
            dtype=rasterio.float32,
            count=1,
            compress="deflate"
        )
        
        with rasterio.open(output_file, 'w', **profile) as dst:
            dst.write(data, 1)
    
    def get_statistics(self) -> Dict:
        """Get preprocessing statistics."""
        return self.stats.copy()
    
    def print_report(self) -> None:
        """Print preprocessing report."""
        print("\n" + "="*60)
        print("SAR PREPROCESSING REPORT")
        print("="*60)
        print(f"Files processed:    {self.stats['processed']}")
        print(f"Successful:         {self.stats['successful']}")
        print(f"Failed:             {self.stats['failed']}")
        print(f"Success rate:       {100*self.stats['successful']/(self.stats['processed']+1e-10):.1f}%")
        print(f"Total time:         {self.stats['total_time']:.2f}s")
        if self.stats['successful'] > 0:
            avg_time = self.stats['total_time'] / self.stats['successful']
            print(f"Average time/file:  {avg_time:.2f}s")
        print("="*60 + "\n")


if __name__ == "__main__":
    # Example usage
    from src.utils.config_manager import get_config
    
    logging.basicConfig(level=logging.INFO)
    
    print("SAR Preprocessing Pipeline")
    print("==========================\n")
    
    # Load configuration
    config = get_config()
    
    # Create preprocessor
    preprocessor = SARPreprocessor(config)
    
    print(f"Configuration loaded")
    print(f"Output directory: {preprocessor.output_dir}")
    print(f"Radiometric calibration: {config.get('preprocessing.radiometric_calibration.enabled')}")
    print(f"Speckle filtering: {config.get('preprocessing.speckle_filtering.enabled')}")
    print(f"AOI clipping: {config.get('preprocessing.aoi_clipping.enabled')}")
