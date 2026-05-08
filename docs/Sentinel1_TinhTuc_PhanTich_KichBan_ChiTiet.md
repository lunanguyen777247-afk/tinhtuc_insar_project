# Phân tích dữ liệu SAR — Google Earth Engine

© 2025 Sentinel-1 Processing Report

---

## BÁO CÁO KỸ THUẬT

### Phân tích Sentinel-1 SAR

### Giám sát Ngập lụt, Sạt lở & Sụt lún bề mặt

### Tĩnh Túc, Cao Bằng — Mùa mưa lũ 2025 – 2026

| Mục | Chi tiết |
|------|----------|
| **Dữ liệu** | 67 cảnh Sentinel-1 GRD S1A + S1C (2025) + 1.130 cảnh (2015–2026) |
| **Thời gian** | 01/06/2025 – 27/12/2025 (ngập lụt); 20/02/2015 – 26/04/2026 (sụt lún) |
| **Phân cực** | VV + VH (Dual-Pol) |
| **Quỹ đạo** | Orbit 55 (ASC) · Orbit 91 (DESC) · Orbit 128 (ASC) |
| **Nền tảng** | Google Earth Engine JavaScript API + SNAP + MintPy |
| **Phương pháp** | Change Detection (dB) + InSAR Time-Series (SBAS/PSI) |

Tài liệu cung cấp hướng dẫn triển khai đầy đủ — từ phân tích Metadata đến mã GEE và pipeline InSAR ngoài — để xây dựng hệ thống giám sát đa tầng: ngập lụt, sạt lở đất, sụt lún bề mặt và dịch chuyển bãi thải mỏ tại Tĩnh Túc, Cao Bằng.

---

## PHẦN 1 — TỔNG QUAN VÀ PHÂN TÍCH METADATA

### 1.1 Đặc điểm tập dữ liệu mùa lũ 2025

File Metadata CSV ghi nhận 67 cảnh SAR từ S1A và S1C (01/06/2025 – 27/12/2025), chế độ IW, phân cực kép VV+VH.

| Tham số | Giá trị | Ghi chú |
|---------|---------|---------|
| Tổng số cảnh | 67 | S1A: 64, S1C: 3 |
| Chế độ | IW | Swath ~250km |
| Độ phân giải | 10m | Sau multilooking |
| Thời gian | 01/06 – 27/12/2025 | 7 tháng mùa mưa |
| Tần suất | 3–4 ngày/lần (tháng 7–8) | S1A + S1C |

### 1.2 Phân bổ theo quỹ đạo

| Quỹ đạo | Hướng | Số cảnh | Slice | Vai trò |
|---------|-------|---------|-------|---------|
| Orbit 55 | ASC | 31 | 8+9 (cần mosaic) | Track chính, phủ rộng |
| Orbit 91 | DESC | 19 | 1 | Góc nhìn đối diện, bù bóng núi |
| Orbit 128 | ASC | 17 | 9 | Phát hiện sườn đông, bãi thải mỏ |

> **Phát hiện quan trọng:** Orbit 128 thường bị bỏ sót nhưng rất hữu ích cho địa hình núi Tĩnh Túc.

### 1.3 Lịch quét chi tiết 2025

| Tháng | Orbit 55 | Orbit 91 | Orbit 128 | S1C | Tổng |
|-------|----------|----------|-----------|-----|------|
| Tháng 6 | 2 | 3 | 0 | 0 | 5 |
| Tháng 7 | 5 | 3 | 3 | 3 | 14 |
| Tháng 8 | 4 | 3 | 4 | 0 | 11 |
| Tháng 9 | 6 | 2 | 2 | 0 | 10 |
| Tháng 10 | 4 | 3 | 3 | 0 | 10 |
| Tháng 11 | 6 | 3 | 2 | 0 | 11 |
| Tháng 12 | 4 | 2 | 3 | 0 | 9 |
| **Tổng** | **31** | **19** | **17** | **3** | **70*** |

\* 67 hàng duy nhất sau khi loại trùng.

### 1.4 Tập dữ liệu dài hạn cho InSAR (2015–2026)

Phân tích file `S1_Metadata_TinhTuc_2014_to_Now.csv` xác định **1.130 cảnh** hợp lệ, trải dài hơn 11 năm:

| Tham số | Giá trị |
|---------|---------|
| Khoảng thời gian | 20/02/2015 – 26/04/2026 |
| Số cảnh Orbit 55 ASC | 543 (tần suất ~7 ngày) |
| Số cảnh Orbit 91 DESC | 319 (tần suất ~12 ngày) |
| Số cảnh Orbit 128 ASC | 268 (từ 2017) |
| Vệ tinh | S1A (1.126), S1B (4), S1C (3) |

Tập dữ liệu Orbit 55 với 543 cảnh, 11 năm liên tục, đủ mạnh cho InSAR time-series (SBAS/PSI).

---

## PHẦN 2 — NHẬN XÉT VÀ HIỆU CHỈNH KỊCH BẢN

### 2.1 Các lỗi cần hiệu chỉnh

| Lỗi | Mô tả | Giải pháp |
|-----|-------|------------|
| **1. Thiếu Orbit 128** | Bỏ sót 17 cảnh từ Orbit 128 | Thêm vào tất cả bước xử lý, dùng consensus mask 3 track |
| **2. Quên mosaic Orbit 55** | Orbit 55 có 2 slice (8+9), chỉ dùng 1 slice mất 50% vùng | Bắt buộc mosaic trước khi phân tích |
| **3. Bỏ sót S1C** | Sentinel-1C có 3 cảnh đỉnh lũ tháng 7-8 | Xử lý riêng, không gộp S1A và S1C |
| **4. Không có baseline cho Orbit 128 tháng 6** | Orbit 128 không có cảnh tháng 6, cảnh sớm nhất 12/07 | Dùng 12/07 làm baseline duy nhất, chấp nhận giới hạn |
| **5. Ngưỡng -4 dB cứng nhắc** | Không phù hợp địa hình phức tạp | Dùng ngưỡng thích nghi `μ − 1.5σ` trên vùng ổn định |
| **6. Hiệu chuẩn chéo S1C** | S1C có noise floor khác S1A | Cần step cross-calibration để tránh "nhảy" trend ảo |
| **7. Hạn chế dốc phẳng** | `slope.lt(5)` bỏ sót trũng trên sườn | Bổ sung phân tích Closed Depressions vùng bãi thải |

### 2.2 Điểm tích cực của kịch bản gốc

- Change Detection đúng hướng cho flood/landslide.
- Lọc độ dốc `slope.lt(5)` phù hợp vùng thung lũng.
- Nhận diện bãi thải khai thác mỏ – chi tiết chuyên sâu.
- Tích hợp Sentinel-2 NDVI xác nhận sạt lở.

---

## KỊCH BẢN 1: PHÁT HIỆN NGẬP LỤT (FLOOD MAPPING)

**Nguyên lý:** Mặt nước phẳng làm giảm mạnh backscatter (giá trị âm lớn, -5 đến -12 dB).

### 1.1 Tiền xử lý và Mosaic

- Mosaic Orbit 55 (slice 8+9) trước khi dùng.
- Áp dụng Gamma-MAP Speckle Filter (7×7).
- Chuyển sang dB: `image.log10().multiply(10)`.

### 1.2 Baseline tiền sự kiện

| Track | Ảnh baseline | Phương pháp |
|-------|--------------|-------------|
| Orbit 55 | 01/06/2025 + 07/07/2025 | Mean sau mosaic |
| Orbit 91 | 03/06 + 15/06 + 27/06/2025 | Median composite |
| Orbit 128 | 12/07/2025 (duy nhất) | Single scene |

### 1.3 Ngưỡng thích nghi

- `Threshold = μ − 1.5σ` (tính trên vùng đất ổn định, không ngập lịch sử).
- Tính riêng cho từng ảnh post-event.

### 1.4 Consensus mask 3 track

- Pixel được xác nhận ngập khi ≥ 2/3 track phát hiện.
- Pixel 1/3 track: gắn nhãn "nghi vấn".

### 1.5 Loại bỏ nhiễu

- Bóng núi, độ dốc >5°, nước thường xuyên (JRC occurrence >80%), khu dân cư.

---

## KỊCH BẢN 2: PHÁT HIỆN SẠT LỞ ĐẤT (LANDSLIDE DETECTION)

**Đặc điểm:** Phá hủy thực vật, lộ đất đá → tăng backscatter (khác với ngập lụt).

### 2.1 Dấu hiệu SAR

| Loại thay đổi | VH | VV |
|---------------|----|----|
| Mất thực vật | Giảm 2–5 dB | Ít thay đổi |
| Lộ đất đá vụn | Tăng 3–8 dB | Tăng 2–5 dB |
| Tích tụ bùn | Giảm nhẹ 1–3 dB | Giảm nhẹ |
| Dịch chuyển bãi thải | Thay đổi >4 dB | Thay đổi >4 dB |

### 2.2 Vùng mục tiêu

- Độ dốc 20–50° (nguy cơ tự nhiên)
- Độ dốc 5–20° (vùng tích lũy debris)
- Bán kính 500m quanh bãi thải mỏ
- Dọc talweg (đường trũng thung lũng)

### 2.3 Xác nhận bằng Sentinel-2 NDVI

- Lọc ảnh S2 mây <20%.
- Tính ΔNDVI = NDVI_post – NDVI_pre.
- Sạt lở xác nhận khi ΔNDVI < -0.2 **và** SAR phát hiện tăng backscatter.
- Loại trừ ruộng lúa thu hoạch (ESA WorldCover).

---

## KỊCH BẢN 3: PHÂN TÍCH SỤT LÚN BỀ MẶT (SURFACE SUBSIDENCE)

**Mục tiêu:** Đo tốc độ sụt lún (mm/năm) bằng InSAR time-series (SBAS + PSI) trên dữ liệu Sentinel-1 2015–2026, tập trung khu mỏ Tĩnh Túc.

### 3.1 Phân tích dữ liệu đầu vào (2015–2026)

#### 3.1.1 Tổng quan tập dữ liệu CSV

| Tham số | Giá trị |
|---------|---------|
| Tổng cảnh (raw) | 1.133 |
| Cảnh hợp lệ | 1.130 |
| Khoảng thời gian | 20/02/2015 – 26/04/2026 (11 năm 2 tháng) |
| Vệ tinh | S1A (1.126), S1B (4), S1C (3) |
| Phân cực | VV+VH |

#### 3.1.2 Phân tích theo track

| Track | Hướng | Số cảnh | Gap TB | Gap lớn nhất | Đánh giá |
|-------|-------|---------|--------|--------------|-----------|
| Orbit 55 | ASC | 543 | 7 ngày | 71 ngày | ✅ Xuất sắc |
| Orbit 91 | DESC | 319 | 12 ngày | 156 ngày | ✅ Tốt |
| Orbit 128 | ASC | 268 | 12 ngày | 72 ngày | ✅ Tốt (từ 2017) |

> Tập dữ liệu 543 cảnh Orbit 55 (11 năm, ~7 ngày/lần) vượt xa ngưỡng yêu cầu cho SBAS (>30) và PSI (>100), cho phép phát hiện xu hướng mm/năm.

### 3.2 Phương pháp: SBAS-InSAR + PSI kết hợp

| Tiêu chí | SBAS | PSI |
|----------|------|-----|
| Nguyên lý | Cặp baseline ngắn | Pixel ổn định (PS) |
| Độ phủ | Tốt cho vùng phân tán (thực vật, đất) | Tốt cho đô thị, bê tông, đá lộ |
| Độ chính xác | 2–5 mm/năm | 0.5–2 mm/năm |
| Yêu cầu | >30 scenes | >100 scenes (lý tưởng >200) |
| Áp dụng | Toàn khu vực rộng | Vùng mỏ tập trung, bãi thải |

**Quyết định:** Dùng SBAS cho toàn khu vực Tĩnh Túc (trên GEE với proxy backscatter), kết hợp PSI cho bãi thải và công trình mỏ (trên SNAP/MintPy).

### 3.3 Quy trình xử lý InSAR đầy đủ (5 bước)

1. **Lọc và phân loại dữ liệu**  
   Tách 3 track, ưu tiên VV, loại bỏ metadata lỗi, tách S1A và S1C.

2. **Tạo cặp interferogram (SBAS network)**  
   - Temporal baseline < 48 ngày  
   - Perpendicular baseline < 150m  
   - Orbit 55 tạo ~800–1000 cặp

3. **Phase unwrapping và loại nhiễu khí quyển**  
   - Unwrapping: SNAPHU hoặc polynomial fit proxy  
   - APS removal: ERA5 correction hoặc temporal/spatial filtering

4. **Tính displacement và velocity**  
   - `displacement (mm) = (phase_unwrapped / 4π) × λ × 1/cos(incidence_angle)`  
   - λ (C-band) = 5.6 cm, incidence angle ~34–46°  
   - Velocity = linear regression trên time-series displacement

5. **Geocoding và tích hợp DEM**  
   - Range-Doppler terrain correction với NASADEM 30m  
   - Loại bỏ phase do topography (DEM-assisted)  
   - Geocode về EPSG:4326, export GeoTIFF 10m

### 3.4 Triển khai trên GEE (Proxy InSAR + Time-Series Backscatter)

> **Lưu ý quan trọng:** GEE chỉ xử lý GRD (intensity), **không có SLC (phase)**. InSAR thực phải chạy ngoài (SNAP, ISCE, MintPy).
>
> - **Proxy InSAR trên GEE:** Việc tính toán dựa trên xu hướng Backscatter chỉ là phương pháp gián tiếp, phản ánh sự thay đổi độ ẩm/thảm thực vật, không phải là độ dời vật lý (mm).
> - **Mục đích:** Kết quả GEE này chỉ dùng để **khoanh vùng ưu tiên (hotspots)** trước khi tiến hành xử lý InSAR pha thực thụ trên SNAP.

#### 3.4.1 Thiết lập và load dữ liệu

```javascript
// KỊCH BẢN 3: SURFACE SUBSIDENCE — TĨNH TÚC
// Sentinel-1 GRD Time-Series 2015-2026

var roi = ee.Geometry.Rectangle([105.85, 22.62, 106.05, 22.80]);
var dem = ee.Image('NASA/NASADEM_HGT/001').select('elevation');
var slope = ee.Terrain.slope(dem);

var s1_col = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(roi)
  .filterDate('2015-06-01', '2026-04-30')
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.eq('orbitProperties_pass', 'ASCENDING'))
  .filter(ee.Filter.eq('relativeOrbitNumber_start', 55))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
  .filter(ee.Filter.eq('platform_number', 'A'))
  .select(['VV', 'VH']);

print('Số cảnh Orbit 55 S1A:', s1_col.size());
```

#### 3.4.2 Tiền xử lý

```javascript
var toDb = function(img) {
  return img.log10().multiply(10).copyProperties(img, img.propertyNames());
};

var speckleFilter = function(img) {
  var filtered = img.reduceNeighborhood({
    reducer: ee.Reducer.mean(),
    kernel: ee.Kernel.square(3.5, 'pixels')
  });
  return filtered.copyProperties(img, img.propertyNames());
};

var vv_ts = s1_col.map(toDb).map(speckleFilter).select('VV');
```

#### 3.4.3 Proxy displacement từ linear trend

```javascript
var vv_trend = vv_ts.reduce(ee.Reducer.linearFit());
var trend_slope = vv_trend.select('scale'); // dB/ms
var MS_PER_YEAR = 365.25 * 24 * 3600 * 1000;
var slope_per_year = trend_slope.multiply(MS_PER_YEAR);

var subsidence_proxy = slope_per_year.lt(-0.15).and(slope.lt(35));
var uplift_proxy = slope_per_year.gt(0.15).and(slope.lt(35));

Map.addLayer(slope_per_year.updateMask(slope.lt(40)),
  {min:-0.5, max:0.5, palette:['#A32D2D','#FFFACD','#185FA5']}, 
  'VV Trend (dB/yr)');
```

#### 3.4.4 Xuất kết quả proxy

```javascript
Export.image.toDrive({
  image: slope_per_year.clip(roi).toFloat(),
  description: 'VV_Trend_TinhTuc_2015_2026',
  scale: 10,
  region: roi,
  crs: 'EPSG:4326',
  maxPixels: 1e13
});
```

### 3.5 Pipeline InSAR thực: SNAP + MintPy

#### 3.5.1 Quy trình SNAP (12 bước)

| Bước | Thao tác |
|------|----------|
| 1 | Download S1 SLC (Orbit 55, VV, 2015–2026) từ scihub.copernicus.eu |
| 2 | TOPSAR Split → chọn IW subswath phủ Tĩnh Túc |
| 3 | Apply Precise Orbit Files (AUX_POEORB) |
| 4 | Back-Geocoding (DEM-assisted coregistration) |
| 5 | ESD (Enhanced Spectral Diversity) |
| 6 | Interferogram Formation (cặp SBAS) |
| 7 | TOPSAR Merge (3 subswath → 1) |
| 8 | Goldstein Phase Filtering |
| 9 | Unwrapping (SNAPHU) |
| 10 | Phase to Displacement (λ/4π × phase) |
| 11 | Range-Doppler Terrain Correction (NASADEM) |
| 12 | Export GeoTIFF cho MintPy |

#### 3.5.0 Yêu cầu hạ tầng xử lý InSAR

- **Khối lượng dữ liệu:** Với 543 cảnh SLC Orbit 55, tổng dung lượng ước tính từ **1.5TB - 2.0TB**.
- **Cấu hình máy trạm:** Cần CPU tối thiểu 16-32 cores, RAM >64GB và ổ cứng SSD tốc độ cao để xử lý PSI/SBAS trong thời gian hợp lý.

#### 3.5.2 MintPy SBAS Time-Series (Python)

```python
# smallbaselineApp.cfg
[DEFAULT]
mintpy.load.processor = snap
mintpy.load.unwFile = ./inputs/unw/*.unw
mintpy.load.corFile = ./inputs/cor/*.cor
mintpy.load.demFile = ./DEM/NASADEM_TinhTuc.dem
mintpy.networkInversion.weightFunc = no
mintpy.troposphericDelay.method = pyaps
mintpy.topographicResidual = yes
mintpy.deramp = ramp
```

```bash
smallbaselineApp.py smallbaselineApp.cfg --dostep load_data
smallbaselineApp.py smallbaselineApp.cfg --dostep modify_network
smallbaselineApp.py smallbaselineApp.cfg --dostep invert_network
smallbaselineApp.py smallbaselineApp.cfg --dostep correct_troposphere
smallbaselineApp.py smallbaselineApp.cfg --dostep velocity
view.py velocity.h5 --wrap -v -15 15
```

### 3.6 Sản phẩm đầu ra

| Sản phẩm | Định dạng | Độ phân giải | Nội dung |
|----------|-----------|--------------|----------|
| Velocity Map | GeoTIFF | 10–30m | mm/năm LOS (âm = sụt, dương = nâng) |
| Time-Series Displacement | NetCDF/CSV | 10m | 2015–2026 |
| Backscatter Trend Map | GeoTIFF | 10m | dB/năm (proxy) |
| Subsidence Heatmap | GeoTIFF/PNG | 10m | Vùng < -10 mm/năm |
| PS/SBAS Points | Shapefile | — | Velocity, std, coherence |
| Slope-Displacement Correlation | CSV/Plot | — | Tương quan với độ dốc, mưa, khai thác |

### 3.7 Tích hợp vào composite risk map

```javascript
var subsidenceZone = slope_per_year.lt(-0.15).and(slope.lt(20));
var riskScore = ee.Image(0)
  .where(subsidenceZone, 1)
  .where(floodFinal, ee.Image(1).add(riskScore))
  .where(landslideMask, ee.Image(2).add(riskScore));
var extremeRisk = riskScore.gte(3);
```

| Mức nguy cơ | Tiêu chí | Màu | Hành động |
|-------------|----------|-----|------------|
| Thấp (1) | Sụt lún proxy | Vàng nhạt | Giám sát 6 tháng |
| Trung bình (2) | Sụt lún + ngập hoặc sạt lở | Hồng | Kiểm tra hàng quý |
| Cao (3) | Sụt lún + ngập + sạt lở | Đỏ | Cảnh báo sớm |
| Cực cao (4) | Ba yếu tố + gần bãi thải/dân cư | Đỏ đậm | Sơ tán khẩn |

### 3.8 Đánh giá độ chính xác và giới hạn

| Phương pháp | Độ chính xác velocity | Mật độ điểm | Ghi chú |
|-------------|----------------------|-------------|---------|
| GEE Proxy | Không trực tiếp | 10m raster | Nhanh, miễn phí, không phải mm |
| SBAS-InSAR | 1–3 mm/năm | Vài trăm pts/km² | ✅ Khuyến nghị |
| PSI | 0.5–1 mm/năm | Phụ thuộc số PS | ✅ Tốt cho bãi thải |
| Leveling GPS | <0.1 mm/năm | Vài điểm | Tốn kém, để validate |

**Giới hạn địa phương:**

- Rừng rậm → giảm coherence SAR.
- Mưa nhiều tháng 6–9 → atmospheric noise cao.
- Địa hình dốc → shadow/layover mất 15-20% diện tích.
- Biến dạng nhanh có thể gây phase aliasing (>2.8cm/12 ngày).

---

## KỊCH BẢN 4: THEO DÕI BÃI THẢI MỎ (MINE WASTE MONITORING)

### 4.1 Chiến lược

- Vẽ ROI riêng cho 3–5 bãi thải chính.
- Dùng phân cực VV (nhạy với bề mặt cứng, đất nén).
- Tần suất: 6 ngày (S1A) hoặc 3 ngày (S1A+S1C).
- Orbit 128 đặc biệt hữu ích cho sườn đông bãi thải.

### 4.2 Ngưỡng cảnh báo

| Đỏ | >64 dB hoặc diện tích >1 ha | Sơ tán khẩn cấp |

---

## PHẦN 5 — ĐÁNH GIÁ TÍNH KHẢ THI VÀ LỘ TRÌNH TRIỂN KHAI

### 5.1 Đánh giá độ tin cậy

Các kịch bản được thiết kế dựa trên các tham số kỹ thuật chuẩn quốc tế:

- **SBAS InSAR:** Temporal baseline < 48 ngày và Perpendicular baseline < 150m đảm bảo độ kết dính (coherence) tối ưu.
- **Flood/Landslide:** Sử dụng consensus mask từ 3 track giúp triệt tiêu sai số do địa hình núi che khuất.

### 5.2 Triển khai mã nguồn

- **Tính modular:** Mã nguồn GEE trong tài liệu này đã được cấu trúc theo module (tiền xử lý, lọc nhiễu, phân tích vùng), cho phép bảo trì và nâng cấp dễ dàng.
- **GEE App:** Toàn bộ code có thể đóng gói thành một **Earth Engine App** để cung cấp bảng điều khiển trực quan, cho phép cán bộ địa phương theo dõi mà không cần am hiểu code.

### 5.3 Thứ tự ưu tiên thực hiện (Priority)

| Ưu tiên | Kịch bản | Lý do |
|---------|----------|-------|
| **1 (Cao)** | **Kịch bản 4: Bãi thải mỏ** | Nguy cơ sạt lở khối lượng lớn, đe dọa trực tiếp tính mạng dân cư. |
| **2 (Cao)** | **Kịch bản 1: Ngập lụt** | Ứng phó tức thì trong mùa mưa lũ 2025-2026. |
| **3 (Trung bình)** | **Kịch bản 2: Sạt lở sườn tự nhiên** | Phạm vi rộng, cần kết hợp dữ liệu Sentinel-2 định kỳ. |
| **4 (Dài hạn)** | **Kịch bản 3: Sụt lún (InSAR)** | Đòi hỏi thời gian xử lý lớn, phục vụ quy hoạch và đánh giá ổn định mỏ. |

---

## KỊCH BẢN 5: GIÁM SÁT LIÊN TỤC VÀ XUẤT KẾT QUẢ

### 5.1 Lịch giám sát tự động

| Thời kỳ | Tần suất SAR | Hành động | Ngưỡng cảnh báo |
|---------|--------------|-----------|------------------|
| Tháng 6 | 6 ngày | Cập nhật baseline | Không |
| Tháng 7–8 | 3–4 ngày (S1A+C) | Change detection + alert | Ngập >50 ha hoặc Δ>3 dB |
| Tháng 9–10 | 6 ngày | Change detection | Ngập >100 ha |
| Tháng 11–12 | 12 ngày | Cập nhật baseline khô | Không |

### 5.2 Xuất kết quả

- **Raster:** GeoTIFF 10m, EPSG:4326, nodata=0
- **Vector:** Shapefile/GeoJSON (vùng ngập, sạt lở, bãi thải)
- **Bảng thống kê:** diện tích (ha), tọa độ tâm, ΔdB trung bình
- **GEE App Dashboard:** hiển thị trực tuyến

---

## PHẦN 4 — MÃ GOOGLE EARTH ENGINE HOÀN CHỈNH (KỊCH BẢN 1,2,4,5)

Mã dưới đây tích hợp các hiệu chỉnh từ Phần 2 và triển khai Kịch bản 1,2,4,5. (Kịch bản 3 có mã riêng trong phần 3.4)

```javascript
// ============================================================
// SENTINEL-1 FLOOD, LANDSLIDE & MINE WASTE — TĨNH TÚC 2025
// ============================================================

// 1. VÙNG NGHIÊN CỨU
var roi = ee.Geometry.Rectangle([105.85, 22.62, 106.05, 22.80]);
Map.centerObject(roi, 13);

// 2. DEM VÀ ĐỘ DỐC
var dem = ee.Image("NASA/NASADEM_HGT/001").select("elevation");
var slope = ee.Terrain.slope(dem);

// 3. NƯỚC THƯỜNG XUYÊN (JRC)
var jrc = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence");

// ----- HÀM TIỀN XỬ LÝ -----
var toDb = function(img) {
  return img.log10().multiply(10).copyProperties(img, img.propertyNames());
};

var mosaicOrbit55 = function(dateStr, platform) {
  var d = ee.Date(dateStr);
  var col = ee.ImageCollection("COPERNICUS/S1_GRD")
    .filterDate(d, d.advance(1, "day"))
    .filter(ee.Filter.eq("relativeOrbitNumber_start", 55))
    .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"));
  if (platform) col = col.filter(ee.Filter.eq("platform_number", platform));
  return col.select(["VH","VV"]).mosaic().clip(roi);
};

var getOrbit91 = function(startDate, endDate) {
  return ee.ImageCollection("COPERNICUS/S1_GRD")
    .filter(ee.Filter.eq("relativeOrbitNumber_start", 91))
    .filterDate(startDate, endDate)
    .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    .select(["VH","VV"]);
};

var getOrbit128 = function(startDate, endDate) {
  return ee.ImageCollection("COPERNICUS/S1_GRD")
    .filter(ee.Filter.eq("relativeOrbitNumber_start", 128))
    .filterDate(startDate, endDate)
    .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
    .select(["VH","VV"]);
};

// ----- BASELINE -----
var pre55 = ee.ImageCollection([
  mosaicOrbit55("2025-06-01", "A"),
  mosaicOrbit55("2025-07-07", "A")
]).map(toDb).select("VH").mean();

var pre91 = getOrbit91("2025-06-01", "2025-07-01")
  .map(toDb).select("VH").median().clip(roi);

var pre128 = getOrbit128("2025-07-12", "2025-07-13")
  .map(toDb).select("VH").first().clip(roi);

// ----- POST-EVENT (ví dụ 12/08/2025) -----
var post55 = toDb(mosaicOrbit55("2025-08-12", "A")).select("VH");
var post91 = getOrbit91("2025-08-14","2025-08-15")
  .map(toDb).select("VH").first().clip(roi);
var post128 = getOrbit128("2025-08-17","2025-08-18")
  .map(toDb).select("VH").first().clip(roi);

// ----- SAI BIỆT -----
var diff55 = post55.subtract(pre55).rename("VH");
var diff91 = post91.subtract(pre91).rename("VH");
var diff128 = post128.subtract(pre128).rename("VH");

// ----- NGƯỠNG THÍCH NGHI -----
var adaptiveThreshold = function(diffImage) {
  var stats = diffImage.reduceRegion({
    reducer: ee.Reducer.mean().combine(ee.Reducer.stdDev(), "", true),
    geometry: roi, scale: 10, bestEffort: true, maxPixels: 1e9
  });
  var mu = ee.Number(stats.get("VH_mean"));
  var sigma = ee.Number(stats.get("VH_stdDev"));
  return mu.subtract(sigma.multiply(1.5));
};

var thr55 = adaptiveThreshold(diff55);
var thr91 = adaptiveThreshold(diff91);
var thr128 = adaptiveThreshold(diff128);

// ----- MASK NGẬP -----
var flood55 = diff55.lt(thr55).and(slope.lt(5));
var flood91 = diff91.lt(thr91).and(slope.lt(5));
var flood128 = diff128.lt(thr128).and(slope.lt(5));

// ----- CONSENSUS -----
var consensus = flood55.add(flood91).add(flood128);
var floodConfirmed = consensus.gte(2);
var floodSuspect = consensus.eq(1);
var floodFinal = floodConfirmed.and(jrc.lt(80));

// ----- SẠT LỞ -----
var landslideMask = diff55.abs().gt(3.0)
  .and(slope.gt(20)).and(slope.lt(55))
  .and(floodConfirmed.not());

// ----- XÁC NHẬN NDVI -----
var s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
  .filterBounds(roi).filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20));
var ndvi = function(img) {
  return img.normalizedDifference(["B8","B4"]).rename("NDVI")
    .copyProperties(img, ["system:time_start"]);
};
var ndviPre = s2.filterDate("2025-06-01","2025-07-01").map(ndvi).median().clip(roi);
var ndviPost = s2.filterDate("2025-08-10","2025-09-01").map(ndvi).median().clip(roi);
var dNDVI = ndviPost.subtract(ndviPre);
var landslideConfirmed = landslideMask.and(dNDVI.lt(-0.2));

// ----- BÃI THẢI MỎ -----
var mineWaste = ee.Geometry.MultiPoint([
  [105.920, 22.715], [105.935, 22.720], [105.950, 22.705]
]).buffer(300);
var mineChange = diff55.abs().gt(4.0)
  .and(diff55.select("VH").abs().gt(4.0))
  .clip(mineWaste);

// ----- HIỂN THỊ -----
Map.addLayer(floodFinal.selfMask(), {palette:["#185FA5"]}, "Ngập xác nhận");
Map.addLayer(floodSuspect.selfMask(), {palette:["#85B7EB"]}, "Ngập nghi vấn");
Map.addLayer(landslideConfirmed.selfMask(), {palette:["#A32D2D"]}, "Sạt lở xác nhận");
Map.addLayer(mineChange.selfMask(), {palette:["#BA7517"]}, "Bãi thải dịch chuyển");

// ----- XUẤT FILE -----
Export.image.toDrive({
  image: floodFinal.unmask(0).byte(),
  description: "FloodMap_TinhTuc_20250812",
  folder: "Sentinel1_TinhTuc",
  region: roi, scale: 10, crs: "EPSG:4326", maxPixels: 1e13
});

// ----- THỐNG KÊ DIỆN TÍCH -----
var floodArea = floodFinal.multiply(ee.Image.pixelArea())
  .reduceRegion({reducer: ee.Reducer.sum(), geometry: roi, scale: 10, maxPixels: 1e9});
print("Diện tích ngập (m2):", floodArea);
```

---

## PHẦN 6 — KIỂM CHỨNG VÀ ĐÁNH GIÁ ĐỘ CHÍNH XÁC

### 5.1 Ma trận kiểm chứng

| Phương pháp | Ưu điểm | Hạn chế | Áp dụng tại Tĩnh Túc |
|-------------|---------|---------|----------------------|
| Sentinel-2 | Trực quan | Mây che | Hạn chế mùa mưa |
| Planet/SPOT | Độ phân giải cao | Chi phí cao | Cần ngân sách |
| Thực địa | Thông tin trực tiếp | Khó thu thập nhanh | Liên hệ UBND huyện |
| Dữ liệu thủy văn | Định lượng | Cần trạm đo | Trạm sông Bằng Giang |
| UAV/Drone | Siêu phân giải | Phạm vi hẹp | Cho điểm sạt lở cụ thể |

### 5.2 Độ chính xác kỳ vọng

| Loại đối tượng | Overall Accuracy | Commission Error | Omission Error |
|----------------|------------------|------------------|----------------|
| Ngập lụt vùng bằng | 85–92% | 8–15% | 5–12% |
| Ngập lụt thung lũng | 75–85% | 12–20% | 10–18% |
| Sạt lở đất | 65–80% | 15–25% | 20–30% |
| Bãi thải mỏ dịch chuyển | 80–90% | 10–15% | 8–12% |

### 5.3 Lưu ý đặc thù Tĩnh Túc

- Khu mỏ có phản xạ góc (double-bounce) từ công trình kim loại → dễ nhầm với sạt lở. Nên liên hệ Phòng Tài nguyên Môi trường huyện Nguyên Bình để có bản đồ quy hoạch bãi thải.
- Đường QL34 và đường mỏ tạo tín hiệu mạnh → mask các tuyến đường trong lớp sạt lở.

### 5.4 Tài liệu tham khảo (Kịch bản 1,2,4,5)

[1] Twele et al. (2016) — Sentinel-1 based flood mapping. *IJRS*. DOI: 10.1080/01431161.2016.1192304  
[2] Bovenga et al. (2021) — SAR-based landslide detection. *RSE*. DOI: 10.1016/j.rse.2021.112553  
[3] Tay et al. (2020) — Rapid flood mapping using SAR in GEE. *Scientific Data*. DOI: 10.1038/s41597-020-00730-5  
[4] Huang et al. (2018) — Automated water extraction from Sentinel-1. *Remote Sensing*. DOI: 10.3390/rs10050797

### 5.5 Tài liệu tham khảo bổ sung cho Kịch bản 3 (InSAR)

[5] Berardino et al. (2002) — SBAS-InSAR. *IEEE TGRS*. DOI: 10.1109/TGRS.2002.803792  
[6] Yunjun et al. (2019) — MintPy. *Computers & Geosciences*. DOI: 10.1016/j.cageo.2019.104331  
[7] Ferretti et al. (2001) — Permanent scatterers. *IEEE TGRS*. DOI: 10.1109/36.906pmid  
[8] Fattahi & Amelung (2016) — InSAR orbital errors. *Geophysical Journal International*. DOI: 10.1093/gji/ggw098  
[9] ESA SNAP v9.0. <https://step.esa.int>  
[10] MintPy Documentation. <https://mintpy.readthedocs.io>

---

## PHẦN 7 — CHIẾN LƯỢC LƯU TRỮ VÀ QUẢN LÝ DỮ LIỆU FEATURE

Dữ liệu feature (vector) trong dự án Tĩnh Túc được quản lý theo 3 lớp kịch bản:

### 7.1 Kịch bản Input (Chuẩn bị dữ liệu)

- **GEE Assets (FeatureCollection):** Lưu trữ ranh giới khu mỏ, bãi thải và các điểm mốc ổn định. Việc lưu trực tiếp trên Asset giúp các script GEE truy vấn không gian (spatial query) cực nhanh mà không cần upload lại nhiều lần.
- **GeoJSON/KML:** Dùng cho các dữ liệu điều tra nhanh từ thực địa (do cán bộ huyện thu thập qua app di động).

### 7.2 Kịch bản Analysis (Trong quá trình xử lý)

- **GeoPandas DataFrame:** Trong môi trường Python, toàn bộ dữ liệu vector được xử lý dưới dạng bảng thuộc tính không gian để tính toán chỉ số rủi ro hoặc lọc nhiễu theo diện tích.
- **Cloud Storage (GCS/Drive):** Lưu trữ các file GeoJSON trung gian nếu kích thước vượt quá bộ nhớ cache của trình duyệt.

### 7.3 Kịch bản Output (Đầu ra và Bàn giao)

- **ESRI Shapefile (.shp):** Định dạng chuẩn để bàn giao cho Phòng Tài nguyên Môi trường huyện Nguyên Bình sử dụng trên QGIS/ArcGIS.
- **CSV/NetCDF:** Đặc biệt dành cho kết quả sụt lún InSAR. Vì dữ liệu InSAR tập trung vào chuỗi thời gian (time-series) tại hàng nghìn điểm, định dạng CSV giúp dễ dàng biểu diễn biểu đồ biến dạng mm/năm trên Excel hoặc các phần mềm thống kê.
- **PostGIS:** Nếu triển khai hệ thống Dashboard WebGIS, toàn bộ lịch sử các vùng ngập và sạt lở sẽ được đẩy vào cơ sở dữ liệu PostgreSQL/PostGIS để phục vụ truy vấn theo thời gian thực.

---

## PHỤ LỤC — DANH SÁCH 67 CẢNH SENTINEL-1 (2025)

(Danh sách đầy đủ từ file `Sentinel1_Metadata_TinhTuc_2025_06_12.csv`)

| # | Ngày giờ (UTC) | Hướng | Orbit | Platform | Slice | Mode |
|---|----------------|-------|-------|----------|-------|------|
| 1 | 2025-06-01 10:58:27 | ASC | 55 | A | 8 | IW |
| 2 | 2025-06-01 10:58:52 | ASC | 55 | A | 9 | IW |
| 3 | 2025-06-03 22:50:38 | DESC | 91 | A | 1 | IW |
| ... | (tiếp theo 64 cảnh, xem file gốc) | ... | ... | ... | ... | ... |
| 66 | 2025-12-27 11:06:45 | ASC | 128 | A | 9 | IW |

*S1C = Sentinel-1C (xử lý riêng khỏi S1A)*

---

*Báo cáo Kỹ thuật — Sentinel-1 SAR: Tĩnh Túc, Cao Bằng | Tái cấu trúc với Kịch bản 3 (Sụt lún) | © 2025–2026 Sentinel-1 Processing Report*
