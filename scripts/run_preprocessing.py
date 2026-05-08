#!/usr/bin/env python
"""
Preprocessing Runner Script

Orchestrates SAR preprocessing for all input images:
- Radiometric calibration
- Speckle filtering
- Terrain correction (optional)
- AOI clipping
- Output: Preprocessed ready-to-analyze dataset
"""

import logging
import argparse
from pathlib import Path
from datetime import datetime

from src.preprocessing import SARPreprocessor
from src.utils.config_manager import get_config, setup_logging


def main():
    """Run SAR preprocessing pipeline."""
    
    # Configuration
    config = get_config()
    logger = setup_logging(config)
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="SAR Preprocessing Pipeline Runner"
    )
    parser.add_argument(
        "--input-dir",
        default=config.get("preprocessing.input_dir", "data/raw/sentinel1"),
        help="Input directory with raw SAR images"
    )
    parser.add_argument(
        "--output-dir",
        default=config.get("preprocessing.output.output_dir", "data/processed"),
        help="Output directory for preprocessed images"
    )
    parser.add_argument(
        "--orbit",
        choices=["ascending", "descending", "both"],
        default="ascending",
        help="Which orbital pass to process"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=config.get("preprocessing.batch_processing.parallel_jobs", 4),
        help="Number of parallel workers"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files to process (for testing)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Print configuration
    logger.info("="*70)
    logger.info("SAR PREPROCESSING PIPELINE")
    logger.info("="*70)
    logger.info(f"Configuration loaded from: config/")
    logger.info(f"Input directory: {args.input_dir}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Orbital pass: {args.orbit}")
    logger.info(f"Parallel workers: {args.workers}")
    logger.info("")
    
    # Configuration summary
    logger.info("Preprocessing Configuration:")
    logger.info(f"  Radiometric calibration: {config.get('preprocessing.radiometric_calibration.enabled')}")
    logger.info(f"  Speckle filtering: {config.get('preprocessing.speckle_filtering.enabled')}")
    logger.info(f"    - Algorithm: {config.get('preprocessing.speckle_filtering.algorithm')}")
    logger.info(f"    - Window size: {config.get('preprocessing.speckle_filtering.window_size')}")
    logger.info(f"  Terrain correction: {config.get('preprocessing.terrain_correction.enabled')}")
    logger.info(f"  AOI clipping: {config.get('preprocessing.aoi_clipping.enabled')}")
    logger.info("")
    
    # Create preprocessor
    preprocessor = SARPreprocessor(config)
    
    # Find input files
    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        logger.error(f"Input directory not found: {input_dir}")
        return 1
    
    # Get files based on orbit
    input_files = []
    if args.orbit in ["ascending", "both"]:
        input_files.extend(sorted(input_dir.glob("ascending/*.tif")))
    if args.orbit in ["descending", "both"]:
        input_files.extend(sorted(input_dir.glob("descending/*.tif")))
    
    if not input_files:
        logger.warning(f"No input files found in {input_dir}")
        logger.info("Create test data with: python -m src.data_audit.input_data_audit")
        return 0
    
    # Limit files for testing
    if args.limit:
        input_files = input_files[:args.limit]
    
    logger.info(f"Found {len(input_files)} input files")
    logger.info("")
    
    # Process files
    start_time = datetime.now()
    
    logger.info("Starting preprocessing...")
    output_files = preprocessor.preprocess_batch(
        [str(f) for f in input_files],
        n_workers=args.workers
    )
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Print report
    print("\n" + "="*70)
    print("PREPROCESSING REPORT")
    print("="*70)
    preprocessor.print_report()
    print(f"Elapsed time: {elapsed:.2f}s")
    print(f"Throughput: {len(input_files)/elapsed:.2f} images/sec")
    print(f"Output directory: {preprocessor.output_dir}")
    print("="*70)
    
    # Summary
    logger.info("")
    logger.info("="*70)
    logger.info("PREPROCESSING COMPLETE")
    logger.info("="*70)
    logger.info(f"Processed: {len(input_files)} files")
    logger.info(f"Successful: {preprocessor.stats['successful']}")
    logger.info(f"Failed: {preprocessor.stats['failed']}")
    logger.info(f"Output: {preprocessor.output_dir}")
    logger.info("")
    
    return 0 if preprocessor.stats['failed'] == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
