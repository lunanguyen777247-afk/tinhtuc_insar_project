"""
pipeline_architecture.md
========================
End-to-End Pipeline Architecture for Flood Detection Analysis
"""

from pathlib import Path
from datetime import datetime
from typing import Dict, List


def generate_pipeline_architecture():
    """Generate comprehensive pipeline architecture document."""
    
    equ = "=" * 100
    dash = "-" * 100
    
    doc = equ
SAR-BASED FLOOD RISK ASSESSMENT PIPELINE
End-to-End Architecture for Tĩnh Túc Mining Region
{'=' * 100}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

────────────────────────────────────────────────────────────────────────────────────────────────────
LEVEL 1: DATA FLOW OVERVIEW
────────────────────────────────────────────────────────────────────────────────────────────────────

┌─────────────────┐
│  GEE/Sentinel-1 │  ← Download S1 GRD (VV, VH)
└────────┬────────┘
         │
         ▼
   ┌──────────────────────────────────────┐
   │ LAYER 1: DATA INGESTION & AUDIT      │
   ├──────────────────────────────────────┤
   │ • Input Data Audit                   │
   │ • Metadata extraction                │
   │ • Dataset separation (ASC/DESC)      │
   │ • Quality assessment                 │
   └────────┬─────────────────────────────┘
         │
         ▼
   ┌──────────────────────────────────────┐
   │ LAYER 2: PREPROCESSING               │
   ├──────────────────────────────────────┤
   │ • Radiometric calibration (σ₀)       │
   │ • Speckle filtering (Lee/Gamma)      │
   │ • Terrain correction (DEM)           │
   │ • Coregistration (ASC/DESC if fusion)│
   └────────┬─────────────────────────────┘
         │
         ▼
   ┌──────────────────────────────────────────────────┐
   │ LAYER 3: FEATURE EXTRACTION & DETECTION          │
   ├──────────────────────────────────────────────────┤
   │ • Backscatter change index                       │
   │ • Water surface detection (threshold)            │
   │ • Time series filtering (Kalman/median)          │
   │ • Change point detection (CUSUM)                 │
   │ • Anomaly scoring (z-score / MAD)                │
   └────────┬─────────────────────────────────────────┘
         │
         ▼
   ┌──────────────────────────────────────────────────┐
   │ LAYER 4: DECISION & FUSION                       │
   ├──────────────────────────────────────────────────┤
   │ • Per-pixel classification (water/non-water)     │
   │ • Morphological filtering (remove noise)         │
   │ • Confidence scoring                             │
   │ • ASC/DESC fusion (if dual-track)                │
   └────────┬─────────────────────────────────────────┘
         │
         ▼
   ┌──────────────────────────────────────────────────┐
   │ LAYER 5: ANALYSIS & ASSESSMENT                   │
   ├──────────────────────────────────────────────────┤
   │ • Water extent mapping                           │
   │ • Trend analysis (temporal ramps)                │
   │ • Volume/area estimation                         │
   │ • Risk severity classification                   │
   │ • Early warning generation                       │
   └────────┬─────────────────────────────────────────┘
         │
         ▼
   ┌──────────────────────────────────────────────────┐
   │ LAYER 6: VALIDATION & QUALITY ASSURANCE          │
   ├──────────────────────────────────────────────────┤
   │ • Accuracy assessment (confusion matrix)         │
   │ • Cross-validation (ASC vs DESC)                 │
   │ • Ground truth comparison (if available)         │
   │ • Performance reporting                          │
   └────────┬─────────────────────────────────────────┘
         │
         ▼
   ┌──────────────────────────────────────────────────┐
   │ OUTPUT PRODUCTS                                  │
   ├──────────────────────────────────────────────────┤
   │ • Water extent maps (GeoTIFF)                    │
   │ • Time series datasets (NetCDF)                  │
   │ • Risk maps & alert bulletins (JSON/GeoJSON)    │
   │ • Analysis reports (PDF/HTML)                    │
   │ • Visualizations (PNG/SVG)                       │
   └──────────────────────────────────────────────────┘


────────────────────────────────────────────────────────────────────────────────────────────────────
LEVEL 2: MODULAR PIPELINE STRUCTURE
────────────────────────────────────────────────────────────────────────────────────────────────────

python_pipeline/
├── src/
│   ├── data_audit/
│   │   ├── input_data_audit.py         ← Audit & metadata extraction
│   │   ├── dataset_separation.py       ← Split ASC/DESC
│   │   └── experiment_scenarios.py     ← Design analysis scenarios
│   │
│   ├── preprocessing/
│   │   ├── radiometric_calibration.py  ← Convert DN → σ₀
│   │   ├── speckle_filters.py          ← Lee/Gamma/NL-means filtering
│   │   ├── terrain_correction.py       ← Terrain geocoding (DEM-based)
│   │   └── coregistration.py           ← Align multi-temporal images
│   │
│   ├── feature_extraction/
│   │   ├── backscatter_indices.py      ← Change index, water index
│   │   ├── water_detection.py          ← Threshold-based classifier
│   │   ├── temporal_filtering.py       ← Kalman, median, outlier removal
│   │   └── changepoint_detection.py    ← CUSUM, Bayesian change point
│   │
│   ├── analysis/
│   │   ├── time_series_analysis.py     ← Trend fitting, forecasting
│   │   ├── anomaly_detection.py        ← Z-score, MAD, isolation forest
│   │   ├── area_volume_estimation.py   ← Water extent → area/volume
│   │   └── risk_assessment.py          ← Severity classification
│   │
│   ├── fusion/
│   │   ├── asc_desc_fusion.py          ← Combine ASC and DESC results
│   │   ├── confidence_scoring.py       ← Per-pixel confidence
│   │   └── ensemble_methods.py         ← Voting/weighted ensemble
│   │
│   ├── validation/
│   │   ├── accuracy_assessment.py      ← Confusion matrix, metrics
│   │   ├── cross_validation.py         ← K-fold, temporal CV
│   │   └── ground_truth_comparison.py  ← Compare vs field data
│   │
│   └── utils/
│       ├── io_utils.py                 ← Data I/O (GEE, files)
│       ├── geo_utils.py                ← Geospatial operations
│       ├── visualization.py            ← Maps, plots, dashboards
│       └── config.py                   ← Centralized parameters
│
├── notebooks/
│   ├── 01_scenario1_analysis.ipynb     ← Before-after comparison
│   ├── 02_scenario2_timeseries.ipynb   ← Full time series analysis
│   ├── 03_scenario3_asc_desc.ipynb     ← ASC vs DESC validation
│   └── 04_scenario4_anomaly.ipynb      ← Real-time alerting
│
├── config/
│   ├── settings.py                     ← Global parameters
│   ├── processing_params.yaml          ← Algorithm tuning
│   └── aoi_config.yaml                 ← Study region definitions
│
├── data/
│   ├── raw/
│   │   ├── sentinel1/ascending/
│   │   ├── sentinel1/descending/
│   │   ├── dem/
│   │   └── reference_data/
│   ├── processed/
│   │   ├── preprocessed/
│   │   ├── features/
│   │   └── results/
│   └── external/
│       ├── rainfall/
│       └── ground_truth/
│
├── outputs/
│   ├── data_audit/
│   ├── dataset_separation/
│   ├── scenario_1_results/
│   ├── scenario_2_results/
│   ├── scenario_3_results/
│   ├── scenario_4_results/
│   └── reports/
│
└── scripts/
    ├── run_full_pipeline.py            ← End-to-end orchestrator
    ├── run_single_scenario.py           ← Run one scenario
    └── deploy_operational_system.py     ← Deploy alerting system


────────────────────────────────────────────────────────────────────────────────────────────────────
LEVEL 3: DATA FLOW FOR EACH SCENARIO
────────────────────────────────────────────────────────────────────────────────────────────────────

SCENARIO 1: BEFORE-AFTER ANALYSIS
─────────────────────────────────
Input:  reference_image (dry season) + current_image (wet season) + DEM
        │
        ├→ Radiometric calibration
        │  ├→ reference_σ₀_vv.npy
        │  └→ current_σ₀_vv.npy
        │
        ├→ Speckle filtering (Lee 3×3)
        │  ├→ reference_filtered.npy
        │  └→ current_filtered.npy
        │
        ├→ Calculate change index
        │  └→ change_index = (I_wet - I_dry) / I_dry
        │
        ├→ Thresholding
        │  └→ water_mask = change_index < threshold (e.g., -0.1)
        │
        └→ Morphological operations
           └→ water_extent_map.tif (cleaned water pixels)

Output: water_extent_map.tif + change_magnitude.tif + accuracy_metrics.json
Duration: 2-3 hours (1 image pair)


SCENARIO 2: TIME SERIES ANALYSIS
──────────────────────────────────
Input:  [Image₁, Image₂, ..., Image_N] (ASCENDING, N~1300) + DEM
        │
        ├→ Batch preprocessing
        │  ├→ radiometric_calibration()
        │  ├→ speckle_filter()
        │  └→ terrain_correction()
        │  → preprocessed_series.npy [N, H, W]
        │
        ├→ Create time series
        │  └→ backscatter_ts.npy [N, H, W]
        │
        ├→ Temporal filtering (Kalman)
        │  └→ smooth_ts.npy [N, H, W]  (reduced speckle variance)
        │
        ├→ Change point detection (CUSUM)
        │  └→ changepoints.json
        │
        ├→ Water detection per time step
        │  └→ water_ts.npy [N, H, W] (binary)
        │
        ├→ Water extent time series
        │  └→ water_extent_ts.csv (area vs time)
        │
        ├→ Trend analysis (linear regression)
        │  └→ trend_map.tif (slope per pixel)
        │
        └→ Anomaly detection & alerting
           └→ alert_bulletin.json

Output: water_extent_timeseries.tif + trend_map.tif + alert_bulletin.json
Duration: 1-2 weeks (full processing)


SCENARIO 3: ASC vs DESC COMPARISON
───────────────────────────────────
Input:  ascending_series [1304 images] + descending_series [1253 images] + DEM
        │
        ├─────────────────────────────┬──────────────────────────────
        │                             │
        ▼                             ▼
    ASCENDING PROCESSING          DESCENDING PROCESSING
    (Parallel tracks)             (Parallel tracks)
        │                             │
    asc_water_ts.npy              desc_water_ts.npy
        │                             │
        └─────────────────┬───────────┘
                          ▼
            Co-registration to UTM48N grid
                          │
            ┌─────────────┴──────────────┐
            ▼                            ▼
        Intersection/Union        Confusion matrix
            │                            │
            ├→ agreement_map.tif        ├→ sensitivity.csv
            └→ iou_timeseries.csv       └→ specificity.csv

Output: asc_water_ts.tif + desc_water_ts.tif + agreement_map.tif + iou_curve.csv
Duration: 2-3 weeks (dual processing)


SCENARIO 4: REAL-TIME ANOMALY DETECTION
────────────────────────────────────────
Input:  baseline_ts (2019-2024) + current_image (2025) + threshold_config
        │
        ├→ Compute baseline statistics
        │  ├→ mean_water.tif
        │  ├→ std_water.tif
        │  ├→ min_water.tif
        │  └→ max_water.tif
        │
        ├→ Load current image → current_water.tif
        │
        ├→ Compute anomaly score
        │  └→ anomaly = (current - mean) / std  [z-score]
        │
        ├→ Apply severity thresholds
        │  ├→ Low: 1σ < anomaly < 2σ
        │  ├→ Medium: 2σ < anomaly < 3σ
        │  ├→ High: 3σ < anomaly
        │  └→ severity_map.tif
        │
        ├→ Generate alert bulletin
        │  ├→ flagged_pixels: count
        │  ├→ severity_level: classification
        │  ├→ affected_area: km²
        │  └→ alert_bulletin.json
        │
        └→ Output to operations center
           └→ auto_alert_email.txt

Output: anomaly_map.tif + alert_level_map.tif + alert_bulletin.json
Duration: 5-15 minutes (real-time after each acquisition)


────────────────────────────────────────────────────────────────────────────────────────────────────
LEVEL 4: KEY ALGORITHM COMPONENTS
────────────────────────────────────────────────────────────────────────────────────────────────────

1. PREPROCESSING CHAIN
   ├─ Radiometric Calibration
   │  └─ σ₀ [dB] = 10 * log₁₀(intensity) + 10 * log₁₀(sin θ) - calibration_constant
   │
   ├─ Speckle Filtering
   │  ├─ Lee filter (adaptive, preserve edges)
   │  │  └─ Output: smoothed image, variance reduced
   │  ├─ Gamma MAP filter (for GRD products)
   │  └─ NL-means (non-local means, computationally expensive)
   │
   ├─ Terrain Correction
   │  ├─ Use DEM to remove topographic phase
   │  └─ Geocode to UTM grid
   │
   └─ Coregistration (if ASC/DESC fusion)
      ├─ Compute image offsets via cross-correlation
      └─ Reproject to common grid

2. WATER DETECTION
   ├─ Backscatter-based thresholding
   │  ├─ Water has low VV backscatter (specular reflection)
   │  ├─ Threshold: σ₀_vv < -12 dB → water pixel
   │  └─ Refinement with VV/VH ratio
   │
   ├─ Change detection method
   │  ├─ Change_index = (I_wet - I_dry) / I_dry
   │  ├─ Threshold: Change_index < -0.1 → new water
   │  └─ Morphological filtering: remove salt-and-pepper noise
   │
   └─ ML-based classification (optional future)
      ├─ Train classifier on labeled samples
      ├─ Random Forest / SVM / CNN
      └─ Per-pixel water probability

3. TIME SERIES FILTERING
   ├─ Kalman Filter
   │  ├─ State: [position, velocity, acceleration]
   │  ├─ Measurement: observed backscatter
   │  └─ Output: smoothed time series + uncertainty estimates
   │
   ├─ Median filtering
   │  ├─ Simple but effective for speckle reduction
   │  └─ Kernel size: 3×3 or 5×5 over time window
   │
   └─ Outlier detection
      ├─ Z-score method: |x - μ| > 3σ → outlier
      └─ Median Absolute Deviation (MAD)

4. CHANGE POINT DETECTION (CUSUM)
   ├─ Cumulative Sum Control Chart
   ├─ Detect shifts in mean
   ├─ Sensitive to gradual ramps + sudden jumps
   └─ Per-pixel detection → timestamps of changes

5. ANOMALY DETECTION
   ├─ Z-score: z = (x - μ) / σ
   ├─ Threshold: |z| > 2 or 3 (configurable)
   ├─ Median Absolute Deviation (robust to outliers)
   │  └─ MAD = median(|x - median(x)|)
   └─ Isolation Forest (if using ML)

6. ACCURACY METRICS
   ├─ Confusion Matrix: TP, TN, FP, FN
   ├─ Sensitivity (recall): TP / (TP + FN)
   ├─ Specificity: TN / (TN + FP)
   ├─ Precision: TP / (TP + FP)
   ├─ F1-score: 2 * (precision * recall) / (precision + recall)
   ├─ IoU (Jaccard): Intersection / Union
   └─ Kappa coefficient: inter-rater agreement


────────────────────────────────────────────────────────────────────────────────────────────────────
LEVEL 5: IMPLEMENTATION TECHNOLOGIES & TOOLS
────────────────────────────────────────────────────────────────────────────────────────────────────

Language & Ecosystem:
  • Python 3.10+
  • Conda/virtualenv (environment management)
  • Git (version control)

Core Libraries:
  • NumPy: numerical arrays
  • SciPy: scientific computing, signal processing
  • Pandas: data frames, time series
  • Scikit-learn: ML classifiers, metrics, preprocessing

Geospatial:
  • Rasterio: read/write GeoTIFF, NetCDF
  • GDAL: geospatial data translation
  • Shapely: geometric operations
  • GeoPandas: vector data manipulation
  • Pyproj: coordinate transformations
  • Fiona: vector I/O

Remote Sensing:
  • Google Earth Engine (Python API): data access
  • SNAP (via subprocess): SAR processing (optional)
  • Astropy: astronomical/scientific computing

Visualization:
  • Matplotlib: basic plotting
  • Folium: interactive web maps
  • Plotly: interactive dashboards
  • Basemap/Cartopy: map projections

ML/Advanced:
  • TensorFlow/PyTorch: neural networks (if upgrading to CNN-based water detection)
  • Scikit-optimize: hyperparameter tuning

DevOps:
  • Docker: containerization
  • GitHub Actions: CI/CD
  • Jupyter: interactive notebooks

Cloud/Storage:
  • Google Cloud Storage (for GEE integration)
  • AWS S3 (optional for data backup)


────────────────────────────────────────────────────────────────────────────────────────────────────
LEVEL 6: DEPLOYMENT & OPERATIONAL PIPELINE
────────────────────────────────────────────────────────────────────────────────────────────────────

Development Phase:
  1. Design & prototyping (notebooks)
  2. Algorithm development (modular scripts)
  3. Unit testing
  4. Integration testing

Testing Phase:
  1. Scenario 1 validation (2-3 days)
  2. Scenario 2 validation (1-2 weeks)
  3. Scenario 3 cross-validation (2-3 weeks)
  4. Ground truth comparison (if available)

Operational Deployment:
  1. Schedule GEE data downloads (automated, daily)
  2. Run preprocessing pipeline (overnight batch)
  3. Compute water detection (Scenario 1)
  4. Update time series & trend analysis (Scenario 2)
  5. Anomaly detection & alert generation (Scenario 4)
  6. Generate bulletin & notify stakeholders (real-time)

Monitoring & Maintenance:
  • Log all pipeline runs
  • Track processing times
  • Monitor disk usage
  • Validate output products
  • Collect user feedback


────────────────────────────────────────────────────────────────────────────────────────────────────
LEVEL 7: OUTPUT PRODUCTS SPECIFICATION
────────────────────────────────────────────────────────────────────────────────────────────────────

Primary Outputs:
  1. water_extent_map.tif
     ├─ Format: GeoTIFF (UTM48N projection)
     ├─ Data type: uint8 (0=non-water, 1=water, 255=nodata)
     ├─ Metadata: timestamp, processing date, parameters used
     └─ Usage: visualization, area calculation, change detection

  2. trend_map.tif
     ├─ Format: GeoTIFF
     ├─ Data type: float32 (slope in pixels/month or mm/year)
     ├─ Interpretation: positive = subsidence/water rise, negative = uplift
     └─ Usage: long-term trend analysis, projection

  3. alert_bulletin.json
     - Structure: {
         "timestamp": "2025-05-15T10:30:00Z",
         "severity": "HIGH",
         "affected_area_km2": 2.35,
         "water_extent_change_pct": "+45.2",
         "recommendation": "Increase water pumping capacity",
         "next_image_expected": "2025-05-27T10:30:00Z"
       }
     - Usage: automated alerts to operators, dashboards

  4. accuracy_metrics.json
     - Structure: {
         "confusion_matrix": "...",
         "sensitivity": 0.92,
         "specificity": 0.88,
         "f1_score": 0.90,
         "iou": 0.82
       }
     - Usage: quality assessment, method validation

Secondary Outputs:
  5. time_series_data.nc (NetCDF format)
     ├─ Dimensions: time (1300), y (512), x (512)
     ├─ Variables: backscatter, water_extent, confidence
     └─ Usage: detailed analysis, archival

  6. Analysis reports (HTML/PDF)
     ├─ Executive summary
     ├─ Method description
     ├─ Results & interpretation
     ├─ Limitations & uncertainties
     └─ Recommendations


────────────────────────────────────────────────────────────────────────────────────────────────────
LEVEL 8: QUALITY ASSURANCE & ERROR HANDLING
────────────────────────────────────────────────────────────────────────────────────────────────────

Data Quality Checks:
  ✓ Input image validity (metadata, no corruption)
  ✓ Coverage verification (AOI fully covered)
  ✓ Radiometric calibration validation
  ✓ Temporal consistency (timestamps, gaps)

Algorithm Quality:
  ✓ Parameter validation (thresholds in valid ranges)
  ✓ Intermediate output sanity checks
  ✓ Numerical stability (NaN/Inf checks)
  ✓ Statistical tests (distribution checks)

Output Validation:
  ✓ Geospatial correctness (CRS, bounds)
  ✓ Value range validation (pixels 0-1 for binary, etc.)
  ✓ File integrity (checksums, metadata)
  ✓ Performance benchmarks (processing time within SLA)

Error Handling:
  • Graceful degradation (skip bad images, continue pipeline)
  • Logging all warnings & errors
  • Alert on critical failures
  • Automatic retry (with backoff) for transient failures


────────────────────────────────────────────────────────────────────────────────────────────────────
EXECUTION TIMELINE
────────────────────────────────────────────────────────────────────────────────────────────────────

Week 1: Data Preparation
  ✓ Input Data Audit (DONE)
  ✓ Dataset Separation (DONE)
  ✓ Experiment Scenarios Design (DONE)
  ✓ Set up preprocessing module

Week 2: Scenario 1 Implementation
  - Load reference + current images
  - Implement radiometric calibration
  - Implement speckle filtering
  - Implement water detection threshold
  - Manual validation with Google Earth
  - Generate before-after maps

Week 3-4: Scenario 2 Implementation
  - Batch preprocessing all 1300 ASCENDING images
  - Build time series data structures
  - Implement Kalman filter
  - Implement CUSUM change point detection
  - Generate trend maps
  - Compare with rainfall records

Week 5: Scenario 3 Implementation
  - Parallel: Process 1250 DESCENDING images
  - Co-register ASC & DESC outputs
  - Compute agreement maps
  - Calculate IoU time series
  - Assess viewing-angle sensitivity

Week 6+: Scenario 4 Deployment
  - Train anomaly detection model
  - Tune severity thresholds
  - Implement automated bulletin generation
  - Deploy to operations center
  - Set up monitoring & alerting


{'=' * 100}
END OF ARCHITECTURE DOCUMENT
{'=' * 100}
"""
    
    return doc


def main():
    import logging
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Generate document
    doc = generate_pipeline_architecture()
    
    # Save to file
    output_dir = Path("outputs/pipeline_architecture")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    doc_path = output_dir / "pipeline_architecture.txt"
    with open(doc_path, "w") as f:
        f.write(doc)
    
    # Also save a markdown version
    md_path = output_dir / "pipeline_architecture.md"
    with open(md_path, "w") as f:
        f.write(doc)
    
    # Print to console
    print(doc)
    
    logger.info(f"Pipeline architecture saved to:")
    logger.info(f"  • {doc_path}")
    logger.info(f"  • {md_path}")


if __name__ == "__main__":
    main()
