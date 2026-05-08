# InSAR Ground Deformation Monitoring — Tĩnh Túc, Cao Bằng, Vietnam

## Project Overview

This is an advanced remote sensing and geophysics pipeline for monitoring ground deformation and flood risks in the Tĩnh Túc mining region using InSAR (Interferometric Synthetic Aperture Radar).

### Key Features
- **P-SBAS**: Pixel-based Small BAseline Subset processing for displacement time series
- **4D Kalman Filter**: Spatiotemporal state estimation for smoothing deformation signals
- **Hydromet Transformer**: Deep learning model linking ground deformation to rainfall and soil moisture
- **MAC Classification**: 11-class Moving Area Coherent Subsets classifier
- **Kinematics Analysis**: Strain tensor analysis, ICA, and Wavelet Transform Coherence

### Pipeline Phases
1. **Phase 1**: Data acquisition and preprocessing (Sentinel-1, ALOS-2, DEM, hydro data)
2. **Phase 2**: P-SBAS processing, spatial clustering, MAC classification
3. **Phase 3**: Transformer training and 4D Kalman monitoring
4. **Phase 4**: Kinematics analysis (strain, slip surface inversion, alerts)
5. **Phase 5**: Report generation and visualization

## Project Structure

```
run_pipeline.py         # Main entry point — runs all 5 phases
run_input_data_audit.py # Data audit utility
config/
  settings.py           # Central configuration (AOI, parameters)
  gee_config.yaml       # Google Earth Engine config
src/
  sbas/                 # P-SBAS processing
  kalman/               # 4D Kalman filter
  transformer/          # Hydromet Transformer (PyTorch + NumPy fallback)
  classification/       # MAC classifier
  clustering/           # Spatial clustering
  kinematics/           # Strain analysis
  corrections/          # Atmospheric correction
  visualization/        # Plotting utilities
gee_scripts/            # Google Earth Engine JavaScript/Python scripts
data/                   # Input data (ERA5, SAR, DEM)
outputs/                # Results: maps, figures, reports
logs/                   # Pipeline logs
```

## Running

```bash
python3 run_pipeline.py
```

## Dependencies

- Python 3.12
- NumPy, SciPy, Pandas, Matplotlib, Scikit-learn
- PyTorch (with NumPy fallback if unavailable)
- PyWavelets, GeoPandas, Shapely, Rasterio, PyProj
- H5py, NetCDF4, PyYAML

Install: `pip install -r requirements.txt`

## Configuration

- Study area and processing parameters: `config/settings.py`
- GEE integration: `config/gee_config.yaml` and `gee_scripts/`
- Environment variables: copy `.env.example` to `.env`

## User Preferences

- Vietnamese language comments and logging are used throughout the codebase — maintain this convention.
- The pipeline supports a synthetic/demo mode when real SAR data is unavailable.
