#!/bin/bash
# =============================================================================
# snap_mintpy/04_mintpy_run.sh
# Chạy đầy đủ MintPy time-series analysis cho Tĩnh Túc
#
# Cài đặt MintPy:
#   conda create -n mintpy -c conda-forge mintpy
#   conda activate mintpy
#   pip install pyaps3
# =============================================================================

set -e
conda activate mintpy 2>/dev/null || true

CFG="./snap_mintpy/03_mintpy_config.cfg"
WORK_DIR="./data/processed/mintpy"
mkdir -p ${WORK_DIR}
cd ${WORK_DIR}

echo "=============================================="
echo "  MintPy Time-Series — Tĩnh Túc, Cao Bằng"
echo "=============================================="

# ─── BƯỚC 1: Load data ────────────────────────────────────────────────────
echo ""
echo ">>> [1/9] Load interferogram stack..."
smallbaselineApp.py ${CFG} --start load_data --end load_data
# Kiểm tra: mintpy.load.coherenceFile phải > 0.4 cho đủ pixels

# ─── BƯỚC 2: Network modification ────────────────────────────────────────
echo ""
echo ">>> [2/9] Modify network (loại bỏ IFG chất lượng thấp)..."
smallbaselineApp.py ${CFG} --start modify_network --end modify_network
# Xem network: view.py inputs/ifgramStack.h5 --nodisplay

# ─── BƯỚC 3: Reference point ──────────────────────────────────────────────
echo ""
echo ">>> [3/9] Select reference point..."
smallbaselineApp.py ${CFG} --start reference_point --end reference_point

# ─── BƯỚC 4: Network inversion ────────────────────────────────────────────
echo ""
echo ">>> [4/9] Network inversion (giải bài toán time-series)..."
echo "  ⚠️  Bước này tốn thời gian nhất (~1-3 giờ)"
smallbaselineApp.py ${CFG} --start invert_network --end invert_network

# ─── BƯỚC 5: Temporal coherence mask ─────────────────────────────────────
echo ""
echo ">>> [5/9] Temporal coherence..."
smallbaselineApp.py ${CFG} --start correct_LOD --end correct_LOD

# ─── BƯỚC 6: Tropospheric correction ─────────────────────────────────────
echo ""
echo ">>> [6/9] Tropospheric correction (ERA5)..."
echo "  ℹ️  Cần kết nối internet lần đầu để tải ERA5"
smallbaselineApp.py ${CFG} --start correct_troposphere --end correct_troposphere

# ─── BƯỚC 7: DEM error ────────────────────────────────────────────────────
echo ""
echo ">>> [7/9] DEM error correction..."
smallbaselineApp.py ${CFG} --start correct_topography --end correct_topography

# ─── BƯỚC 8: Velocity estimation ──────────────────────────────────────────
echo ""
echo ">>> [8/9] Velocity estimation..."
smallbaselineApp.py ${CFG} --start velocity --end velocity

# ─── BƯỚC 9: Geocode & Export ─────────────────────────────────────────────
echo ""
echo ">>> [9/9] Geocode và xuất kết quả..."
smallbaselineApp.py ${CFG} --start geocode --end geocode

# ─── XUẤT KẾT QUẢ CHO PYTHON ─────────────────────────────────────────────
echo ""
echo ">>> Xuất kết quả GeoTIFF cho Python analysis..."

# Velocity map
save_gdal.py geo/geo_velocity.h5 velocity \
  -o ../../python_analysis/data/processed/velocity_mintpy.tif

# Time-series
save_gdal.py geo/geo_timeseries_ERA5.h5 timeseries \
  -o ../../python_analysis/data/processed/timeseries_mintpy.tif

# Temporal coherence
save_gdal.py geo/geo_temporalCoherence.h5 temporalCoherence \
  -o ../../python_analysis/data/processed/temporal_coherence.tif

# Displacement tích lũy
save_gdal.py geo/geo_timeseries_ERA5.h5 timeseries \
  --date-list first,last \
  -o ../../python_analysis/data/processed/cumulative_displacement.tif

echo ""
echo "=============================================="
echo "  ✅ MintPy hoàn thành!"
echo "  Kết quả tại: ${WORK_DIR}/"
echo ""
echo "  Bước tiếp theo:"
echo "  cd python_analysis"
echo "  python analysis/03_mining_deformation.py"
echo "=============================================="

# ─── LỆNH HỮU ÍCH ────────────────────────────────────────────────────────
echo ""
echo "  Lệnh kiểm tra nhanh:"
echo "  view.py geo/geo_velocity.h5  # Bản đồ velocity"
echo "  tsview.py geo/geo_timeseries_ERA5.h5  # Time-series viewer"
echo "  plot_network.py inputs/ifgramStack.h5  # Network plot"
