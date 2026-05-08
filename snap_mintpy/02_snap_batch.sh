#!/bin/bash
# =============================================================================
# snap_mintpy/02_snap_batch.sh
# Script xử lý InSAR tự động với SNAP cho Tĩnh Túc, Cao Bằng
# Tạo interferograms từ Sentinel-1 SLC data
#
# Yêu cầu: SNAP 9.0+ với S1TBX plugin
# Tải SNAP: https://step.esa.int/main/download/snap-download/
# Tải SLC: https://search.asf.alaska.edu (ASF Vertex, miễn phí)
# =============================================================================

set -e  # Dừng nếu có lỗi

# ─── CẤU HÌNH ─────────────────────────────────────────────────────────────
SNAP_DIR="/usr/local/snap/bin"      # Thay bằng đường dẫn SNAP của bạn
GPT="${SNAP_DIR}/gpt"
DATA_DIR="./data/raw/slc"           # Thư mục chứa file SLC .zip
ORBIT_DIR="./data/raw/orbits"       # Thư mục orbit files
DEM_DIR="./data/raw/dem"            # Copernicus DEM 30m
OUTPUT_DIR="./data/processed/snap"
LOG_DIR="./logs"

# Thông số khu vực Tĩnh Túc
SUBSET="105.85,22.55,106.10,22.80"  # lon_min,lat_min,lon_max,lat_max
PIXEL_SPACING=15                    # m

mkdir -p ${OUTPUT_DIR}/{coreg,ifg,unwrapped} ${LOG_DIR}

echo "=============================================="
echo "  SNAP InSAR Pipeline — Tĩnh Túc, Cao Bằng"
echo "=============================================="
echo "Data dir: ${DATA_DIR}"
echo "Output:   ${OUTPUT_DIR}"

# ─── BƯỚC 1: KIỂM TRA SNAP ────────────────────────────────────────────────
echo ""
echo ">>> BƯỚC 1: Kiểm tra SNAP..."
if [ ! -f "${GPT}" ]; then
  echo "❌ SNAP không tìm thấy tại: ${GPT}"
  echo "   Vui lòng cài đặt SNAP 9.0 từ: https://step.esa.int/"
  echo "   Sau đó cập nhật biến SNAP_DIR trong script này."
  exit 1
fi
${GPT} --version
echo "✅ SNAP OK"

# ─── BƯỚC 2: LIỆT KÊ FILE SLC ────────────────────────────────────────────
echo ""
echo ">>> BƯỚC 2: Liệt kê file Sentinel-1 SLC..."
SLC_FILES=(${DATA_DIR}/S1*IW*SLC*.zip)
N_FILES=${#SLC_FILES[@]}
echo "  Tìm thấy ${N_FILES} file SLC"

if [ ${N_FILES} -lt 2 ]; then
  echo "⚠️  Cần ít nhất 2 ảnh SLC để tạo interferogram"
  echo ""
  echo "  Hướng dẫn tải dữ liệu:"
  echo "  1. Truy cập https://search.asf.alaska.edu"
  echo "  2. Chọn Dataset: Sentinel-1 > SLC"
  echo "  3. Vẽ vùng: Tĩnh Túc (105.85–106.10°E, 22.55–22.80°N)"
  echo "  4. Chọn Platform: Sentinel-1A hoặc 1B"
  echo "  5. Path: 18 (Ascending) HOẶC 127 (Descending)"
  echo "  6. Lọc: 2017–2024, tải ít nhất 20 ảnh"
  echo "  7. Đặt file vào: ${DATA_DIR}/"
  echo ""
  echo "  Tên file mẫu:"
  echo "  S1A_IW_SLC__1SDV_20230101T230045_20230101T230112_046589_0596B1_1234.zip"
  exit 0
fi

for f in "${SLC_FILES[@]}"; do
  echo "  📁 $(basename ${f})"
done

# ─── BƯỚC 3: APPLY ORBIT FILES ───────────────────────────────────────────
echo ""
echo ">>> BƯỚC 3: Áp dụng precise orbit files..."
# SNAP tự tải orbit nếu có internet, hoặc dùng offline orbit

COREG_FILES=()
for i in "${!SLC_FILES[@]}"; do
  INPUT="${SLC_FILES[$i]}"
  BASENAME=$(basename ${INPUT} .zip)
  OUTPUT_ORBIT="${OUTPUT_DIR}/coreg/${BASENAME}_orb.dim"

  if [ ! -f "${OUTPUT_ORBIT}" ]; then
    echo "  Processing: $(basename ${INPUT})"
    ${GPT} Apply-Orbit-File \
      -Pinput="${INPUT}" \
      -Pfile="${OUTPUT_ORBIT}" \
      -PorbitType='Sentinel Precise (Auto Download)' \
      -PpolyDegree=3 \
      2>&1 | tee "${LOG_DIR}/orbit_${BASENAME}.log"
    echo "  ✅ Orbit applied: ${BASENAME}"
  else
    echo "  ⏭️  Skip (exists): ${BASENAME}"
  fi
  COREG_FILES+=("${OUTPUT_ORBIT}")
done

# ─── BƯỚC 4: TẠO INTERFEROGRAMS (SMALL-BASELINE) ────────────────────────
echo ""
echo ">>> BƯỚC 4: Tạo interferograms Small-Baseline..."
echo "  Chiến lược: kết hợp các cặp trong 36 ngày (3 revisit cycles)"

N_COREG=${#COREG_FILES[@]}
MAX_TEMP_BASELINE=36    # ngày
IFG_COUNT=0

for ((i=0; i<N_COREG; i++)); do
  for ((j=i+1; j<N_COREG; j++)); do
    # Kiểm tra temporal baseline
    # (Đơn giản hóa: cần parse date từ filename thực tế)
    DIFF=$((j - i))
    if [ ${DIFF} -le 3 ]; then  # Tối đa 3 acquisitions apart
      MASTER="${COREG_FILES[$i]}"
      SLAVE="${COREG_FILES[$j]}"
      IFG_NAME="ifg_${i}_${j}"
      OUTPUT_IFG="${OUTPUT_DIR}/ifg/${IFG_NAME}.dim"

      if [ ! -f "${OUTPUT_IFG}" ]; then
        echo "  Tạo interferogram: $i → $j"

        # Graph: Coregistration + Interferogram formation
        ${GPT} ${SNAP_DIR}/../graphs/InSAR/InSAR_Sentinel1_Graph.xml \
          -Pmaster="${MASTER}" \
          -Pslave="${SLAVE}" \
          -Pdem="${DEM_DIR}/copernicus_dem_tinhtuc.tif" \
          -PoutputFile="${OUTPUT_IFG}" \
          -Psubset="${SUBSET}" \
          2>&1 | tee "${LOG_DIR}/${IFG_NAME}.log" \
          || echo "  ⚠️  Lỗi: ${IFG_NAME} (xem log)"

        IFG_COUNT=$((IFG_COUNT + 1))
      fi
    fi
  done
done

echo "  ✅ Tổng interferograms tạo: ${IFG_COUNT}"

# ─── BƯỚC 5: GRAPH-BASED PROCESSING (từng interferogram) ────────────────
# Script SNAP Graph XML cho một interferogram đầy đủ:
echo ""
echo ">>> BƯỚC 5: Tạo SNAP Graph XML cho processing đầy đủ..."

cat > ${OUTPUT_DIR}/snap_insar_graph.xml << 'SNAP_XML'
<graph id="InSAR_TinhTuc_Graph">
  <version>1.0</version>

  <!-- Node 1: Đọc ảnh Master -->
  <node id="Read-Master">
    <operator>Read</operator>
    <sources/>
    <parameters>
      <file>$masterFile</file>
    </parameters>
  </node>

  <!-- Node 2: Đọc ảnh Slave -->
  <node id="Read-Slave">
    <operator>Read</operator>
    <sources/>
    <parameters>
      <file>$slaveFile</file>
    </parameters>
  </node>

  <!-- Node 3: Apply Orbit (Master) -->
  <node id="Apply-Orbit-Master">
    <operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="Read-Master"/></sources>
    <parameters>
      <orbitType>Sentinel Precise (Auto Download)</orbitType>
      <polyDegree>3</polyDegree>
    </parameters>
  </node>

  <!-- Node 4: Apply Orbit (Slave) -->
  <node id="Apply-Orbit-Slave">
    <operator>Apply-Orbit-File</operator>
    <sources><sourceProduct refid="Read-Slave"/></sources>
    <parameters>
      <orbitType>Sentinel Precise (Auto Download)</orbitType>
    </parameters>
  </node>

  <!-- Node 5: Back-Geocoding (coregistration với DEM) -->
  <!-- QUAN TRỌNG: dùng Copernicus DEM 30m cho vùng núi -->
  <node id="Back-Geocoding">
    <operator>Back-Geocoding</operator>
    <sources>
      <sourceProduct refid="Apply-Orbit-Master"/>
      <sourceProduct refid="Apply-Orbit-Slave"/>
    </sources>
    <parameters>
      <demName>Copernicus 30m Global DEM</demName>
      <demResamplingMethod>BILINEAR_INTERPOLATION</demResamplingMethod>
      <resamplingType>BISINC_5_POINT_INTERPOLATION</resamplingType>
      <maskOutAreaWithoutElevation>true</maskOutAreaWithoutElevation>
      <outputRangeAzimuthOffset>true</outputRangeAzimuthOffset>
    </parameters>
  </node>

  <!-- Node 6: Enhanced Spectral Diversity (ESD) — cải thiện azimuth coregistration -->
  <node id="Enhanced-Spectral-Diversity">
    <operator>Enhanced-Spectral-Diversity</operator>
    <sources><sourceProduct refid="Back-Geocoding"/></sources>
    <parameters>
      <fineWinWidthStr>512</fineWinWidthStr>
      <fineWinHeightStr>512</fineWinHeightStr>
    </parameters>
  </node>

  <!-- Node 7: Interferogram Formation -->
  <node id="Interferogram">
    <operator>Interferogram</operator>
    <sources><sourceProduct refid="Enhanced-Spectral-Diversity"/></sources>
    <parameters>
      <subtractFlatEarthPhase>true</subtractFlatEarthPhase>
      <srpPolynomialDegree>5</srpPolynomialDegree>
      <srpNumberPoints>501</srpNumberPoints>
      <orbitDegree>3</orbitDegree>
      <includeCoherence>true</includeCoherence>
      <cohWinAz>10</cohWinAz>
      <cohWinRg>10</cohWinRg>
    </parameters>
  </node>

  <!-- Node 8: TOPS Deburst -->
  <node id="TOPSAR-Deburst">
    <operator>TOPSAR-Deburst</operator>
    <sources><sourceProduct refid="Interferogram"/></sources>
    <parameters>
      <selectedPolarisations>VV</selectedPolarisations>
    </parameters>
  </node>

  <!-- Node 9: TopoPhaseRemoval (loại bỏ pha địa hình) -->
  <node id="TopoPhaseRemoval">
    <operator>TopoPhaseRemoval</operator>
    <sources><sourceProduct refid="TOPSAR-Deburst"/></sources>
    <parameters>
      <demName>Copernicus 30m Global DEM</demName>
      <tileExtensionPercent>100</tileExtensionPercent>
      <outputTopoBand>true</outputTopoBand>
    </parameters>
  </node>

  <!-- Node 10: Goldstein Phase Filtering -->
  <node id="GoldsteinPhaseFiltering">
    <operator>GoldsteinPhaseFiltering</operator>
    <sources><sourceProduct refid="TopoPhaseRemoval"/></sources>
    <parameters>
      <alpha>0.6</alpha>           <!-- Tăng lên 0.8 nếu coherence thấp -->
      <numBlockRows>4</numBlockRows>
      <numBlockCols>4</numBlockCols>
      <numOverlapPixels>3</numOverlapPixels>
      <useCoherenceMask>true</useCoherenceMask>
      <coherenceThreshold>0.2</coherenceThreshold>
    </parameters>
  </node>

  <!-- Node 11: Subset (cắt vùng Tĩnh Túc) -->
  <node id="Subset">
    <operator>Subset</operator>
    <sources><sourceProduct refid="GoldsteinPhaseFiltering"/></sources>
    <parameters>
      <geoRegion>POLYGON ((105.85 22.55, 106.10 22.55, 106.10 22.80, 105.85 22.80, 105.85 22.55))</geoRegion>
      <copyMetadata>true</copyMetadata>
    </parameters>
  </node>

  <!-- Node 12: Geocoding (Range-Doppler Terrain Correction) -->
  <node id="Terrain-Correction">
    <operator>Terrain-Correction</operator>
    <sources><sourceProduct refid="Subset"/></sources>
    <parameters>
      <demName>Copernicus 30m Global DEM</demName>
      <demResamplingMethod>BILINEAR_INTERPOLATION</demResamplingMethod>
      <imgResamplingMethod>BILINEAR_INTERPOLATION</imgResamplingMethod>
      <pixelSpacingInMeter>15.0</pixelSpacingInMeter>
      <mapProjection>AUTO:42001</mapProjection>
      <nodataValueAtSea>false</nodataValueAtSea>
      <saveDEM>false</saveDEM>
      <saveLatLon>false</saveLatLon>
      <saveIncidenceAngleFromEllipsoid>true</saveIncidenceAngleFromEllipsoid>
    </parameters>
  </node>

  <!-- Node 13: Ghi kết quả -->
  <node id="Write">
    <operator>Write</operator>
    <sources><sourceProduct refid="Terrain-Correction"/></sources>
    <parameters>
      <file>$outputFile</file>
      <formatName>GeoTIFF</formatName>
    </parameters>
  </node>
</graph>
SNAP_XML

echo "  ✅ SNAP Graph XML đã tạo: ${OUTPUT_DIR}/snap_insar_graph.xml"

# ─── BƯỚC 6: PHASE UNWRAPPING (SNAPHU) ───────────────────────────────────
echo ""
echo ">>> BƯỚC 6: Phase Unwrapping với SNAPHU..."
echo "  (Cần cài SNAPHU: https://web.stanford.edu/group/radar/softwareandlinks/sw/snaphu/)"
echo ""
echo "  Lệnh export từ SNAP:"
echo "  ${GPT} SnaphuExport -Ssource=<interferogram.dim> -PtargetFolder=${OUTPUT_DIR}/unwrapped"
echo ""
echo "  Lệnh chạy SNAPHU:"
echo "  snaphu -s <phase.snaphu.hdr> <phase.snaphu>"
echo "  (Xem hướng dẫn chi tiết trong file snaphu_config.cfg)"

# ─── BƯỚC 7: HƯỚNG DẪN TIẾP THEO ─────────────────────────────────────────
echo ""
echo "=============================================="
echo "  BƯỚC TIẾP THEO: Chạy MintPy"
echo "=============================================="
echo ""
echo "  Sau khi có đủ interferograms từ SNAP:"
echo "  1. Đặt tất cả GeoTIFF vào: ${OUTPUT_DIR}/"
echo "  2. Chỉnh sửa: snap_mintpy/03_mintpy_config.cfg"
echo "  3. Chạy: bash snap_mintpy/04_mintpy_run.sh"
echo ""
echo "=============================================="
