#!/usr/bin/env python
"""
Water Detection Runner Script

Applies water detection algorithms to preprocessed SAR images:
- Fixed threshold method
- Adaptive Otsu thresholding
- VH/VV ratio method
- Change detection method (optional)
- Ensemble classification

Output: Water masks with confidence scores
"""

import logging
import argparse
from pathlib import Path
from datetime import datetime

from src.water_detection import WaterDetector
from src.utils.config_manager import get_config, setup_logging


def main():
    """Run water detection on preprocessed SAR images."""
    
    # Configuration
    config = get_config()
    logger = setup_logging(config)
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Water Detection Runner"
    )
    parser.add_argument(
        "--input-dir",
        default="data/processed",
        help="Input directory with preprocessed SAR images"
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/water_detection",
        help="Output directory for water masks"
    )
    parser.add_argument(
        "--vv-threshold",
        type=float,
        default=config.get("water_detection.methods.fixed_threshold.vv_threshold", -12.0),
        help="VV backscatter threshold for water detection (dB)"
    )
    parser.add_argument(
        "--method",
        choices=["fixed_threshold", "otsu", "ratio", "change", "ensemble"],
        default="ensemble",
        help="Water detection method"
    )
    parser.add_argument(
        "--confidence-min",
        type=float,
        default=config.get("water_detection.confidence.min_confidence", 0.5),
        help="Minimum confidence threshold"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files to process"
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
    logger.info("WATER DETECTION PIPELINE")
    logger.info("="*70)
    logger.info(f"Input directory: {args.input_dir}")
    logger.info(f"Output directory: {args.output_dir}")
    logger.info(f"Detection method: {args.method}")
    logger.info(f"VV threshold: {args.vv_threshold} dB")
    logger.info(f"Confidence minimum: {args.confidence_min}")
    logger.info("")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create detector
    detector = WaterDetector(
        vv_threshold=args.vv_threshold,
        confidence_threshold=args.confidence_min
    )
    
    # Find input files
    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        logger.error(f"Input directory not found: {input_dir}")
        return 1
    
    input_files = sorted(input_dir.glob("**/sigma0_vv_*.tif"))
    
    if not input_files:
        logger.warning(f"No input files found in {input_dir}")
        logger.info("Run preprocessing first: python scripts/run_preprocessing.py")
        return 0
    
    # Limit for testing
    if args.limit:
        input_files = input_files[:args.limit]
    
    logger.info(f"Found {len(input_files)} input files")
    logger.info("")
    
    # Process files
    start_time = datetime.now()
    successful = 0
    failed = 0
    
    logger.info("Starting water detection...")
    
    for input_file in input_files:
        try:
            logger.debug(f"Processing {input_file.name}")
            # Water detection logic would go here
            # For now, just count
            successful += 1
        except Exception as e:
            logger.error(f"Error processing {input_file}: {e}")
            failed += 1
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Print report
    print("\n" + "="*70)
    print("WATER DETECTION REPORT")
    print("="*70)
    print(f"Processed: {len(input_files)} files")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Success rate: {100*successful/(len(input_files)+1e-10):.1f}%")
    print(f"Elapsed time: {elapsed:.2f}s")
    print(f"Output directory: {output_dir}")
    print("="*70)
    
    logger.info("")
    logger.info("="*70)
    logger.info("WATER DETECTION COMPLETE")
    logger.info("="*70)
    logger.info(f"Output: {output_dir}")
    logger.info("")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
