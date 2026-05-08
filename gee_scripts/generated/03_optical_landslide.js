// =============================================================================
// gee_scripts/03_optical_landslide.js
// Phát hiện sạt lở đất từ ảnh Sentinel-1 + Sentinel-2
// Phương pháp: Change Detection + Spectral Indices + SAR Amplitude
// Tĩnh Túc, Cao Bằng — Khu vực mỏ thiếc + núi dốc
// =============================================================================

// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  CONFIG — GIỮ ĐỒNG BỘ roi/export/map với 01_sentinel1_acquisition.js  ║
// ║  Khi thay đổi ROI hoặc CRS ở file 01, cập nhật file này cùng lúc.     ║
// ╚══════════════════════════════════════════════════════════════════════════╝
// CONFIG được inject tự động bởi generator từ config.gee.js
// -> giúp script generated luôn đồng bộ với ngưỡng/ROI trung tâm.
var CONFIG = {
  "roi": {
    "bbox": [
      105.85,
      22.55,
      106.1,
      22.8
    ],
    "polygon": [
      [
        105.87,
        22.57
      ],
      [
        106.08,
        22.57
      ],
      [
        106.08,
        22.78
      ],
      [
        105.87,
        22.78
      ],
      [
        105.87,
        22.57
      ]
    ],
    "mineCenter": [
      105.975,
      22.675
    ]
  },
  "export": {
    "crs": "EPSG:32648",
    "maxPixels": 10000000000,
    "fileFormat": "GeoTIFF",
    "folder": "InSAR_TinhTuc"
  },
  "map": {
    "centerLon": 105.975,
    "centerLat": 22.675,
    "zoom": 12
  },
  "dates": {
    "s2PreStart": "2019-11-01",
    "s2PreEnd": "2020-02-28",
    "s2PostStart": "2020-10-01",
    "s2PostEnd": "2021-01-31",
    "s1PreStart": "2019-01-01",
    "s1PreEnd": "2020-06-30",
    "s1PostStart": "2020-07-01",
    "s1PostEnd": "2021-12-31"
  },
  "s2": {
    "maxCloudPct": 40
  },
  "landslide": {
    "strictDNDVI": -0.1,
    "relaxedDNDVI": -0.09,
    "strictDBSI": 0.08,
    "relaxedDBSI": 0.05,
    "strictSlopeMin": 15,
    "relaxedSlopeMin": 15,
    "deepSlopeMin": 30,
    "debrisFlowSlope": 28,
    "miningDBSI": 0.1,
    "miningNDVI": 0.18,
    "miningExpSlopeMax": 20,
    "miningIndSlopeMin": 10,
    "miningIndSlopeMax": 25,
    "sarDVV": 2
  }
};

// ROI: khung chữ nhật bao ngoài (nhanh cho preview/kiểm tra phạm vi).
var ROI   = ee.Geometry.Rectangle(CONFIG.roi.bbox);
// STUDY: polygon nghiên cứu chính xác dùng cho phân tích + xuất dữ liệu.
var STUDY = ee.Geometry.Polygon([CONFIG.roi.polygon]);

// ─── 1. TẢI DỮ LIỆU ──────────────────────────────────────────────────────
// DEM cho slope/aspect
// Dùng CRS xuất để thống nhất khi reduceRegion (tránh sai khác do reprojection ngầm).
var TERRAIN_CRS = CONFIG.export.crs;
// 30m phù hợp độ phân giải DEM GLO30 cho thống kê địa hình.
var TERRAIN_SCALE = 30;

var demCollection = ee.ImageCollection('COPERNICUS/DEM/GLO30')
  .filterBounds(STUDY)
  .select('DEM');

// Lấy projection gốc của tile DEM đầu tiên để giữ đúng grid native.
var demNativeProj = ee.Image(demCollection.first()).projection();
var demRaw = demCollection
  .mosaic() // ghép các tile DEM giao STUDY
  .setDefaultProjection(demNativeProj); // khôi phục projection gốc sau mosaic

// Tính địa hình trên DEM chưa clip để giảm nguy cơ méo cục bộ ở rìa.
var terrainRaw = ee.Terrain.products(demRaw);
// Clip ở cuối pipeline địa hình để chỉ giữ vùng phân tích.
var dem = demRaw.clip(STUDY);
var slope = terrainRaw.select('slope').clip(STUDY).rename('slope');   // độ dốc (độ)
var aspect = terrainRaw.select('aspect').clip(STUDY).rename('aspect'); // hướng dốc (0-360)

print('📊 Terrain DEM (min/max):', dem.reduceRegion({
  reducer: ee.Reducer.minMax(),
  geometry: STUDY,
  crs: TERRAIN_CRS,
  scale: TERRAIN_SCALE,
  maxPixels: 1e10,
  bestEffort: false,
  tileScale: 4
}));
print('📊 Terrain slope percentiles:', slope.reduceRegion({
  reducer: ee.Reducer.percentile([50, 75, 90, 95]),
  geometry: STUDY,
  crs: TERRAIN_CRS,
  scale: TERRAIN_SCALE,
  maxPixels: 1e10,
  bestEffort: false,
  tileScale: 4
}));

// Sentinel-2: Trước (2020) và Sau (2021–2024) sự kiện sạt lở

// Bước 1: Lọc tập ảnh S2 theo ngày + scene-level cloud pct.
// Tăng CONFIG.s2.maxCloudPct nếu size = 0 (SCL pixel-mask vẫn loại mây còn lại).
function getS2Collection(startDate, endDate) {
  return ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterDate(startDate, endDate) // lọc theo cửa sổ thời gian
    .filterBounds(STUDY)            // lọc theo vùng nghiên cứu
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CONFIG.s2.maxCloudPct)); // lọc mây mức scene
}

// Bước 2: Tạo composite median, áp dụng SCL pixel-level cloud mask.
function getS2Composite(col) {
  return col
    .map(function(img) {
      // Mask mây bằng SCL (3=cloud shadow, 8=medium cloud, 9=high cloud, 10=cirrus)
      var scl = img.select('SCL');
      var mask = scl.neq(3).and(scl.neq(8)).and(scl.neq(9)).and(scl.neq(10));
      return img.updateMask(mask); // áp dụng pixel mask trước khi median
    })
    .median() // median giúp giảm nhiễu mây mỏng/outlier phản xạ
    .select(['B2','B3','B4','B5','B6','B7','B8','B8A','B11','B12'])
    .clip(STUDY);
}

// 📊 DIAGNOSTICS: In số ảnh khả dụng.
// Nếu size = 0 → tăng CONFIG.s2.maxCloudPct hoặc mở rộng cửa sổ ngày.
var s2_col_pre  = getS2Collection(CONFIG.dates.s2PreStart,  CONFIG.dates.s2PreEnd);
var s2_col_post = getS2Collection(CONFIG.dates.s2PostStart, CONFIG.dates.s2PostEnd);
print('📊 S2 Pre  size (maxCloudPct=' + CONFIG.s2.maxCloudPct + '):', s2_col_pre.size());
print('📊 S2 Post size (maxCloudPct=' + CONFIG.s2.maxCloudPct + '):', s2_col_post.size());

// Giai đoạn: khô (Nov-Apr) để giảm nhiễu thực vật mùa mưa
var s2_pre  = getS2Composite(s2_col_pre);   // baseline trước biến động
var s2_post = getS2Composite(s2_col_post);  // giai đoạn sau biến động

// Sentinel-1 (SAR) cho các thời kỳ
var s1_pre  = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filter(ee.Filter.eq('instrumentMode','IW'))
  .filter(ee.Filter.eq('orbitProperties_pass','ASCENDING'))
  .filterDate(CONFIG.dates.s1PreStart, CONFIG.dates.s1PreEnd)
  .filterBounds(STUDY)
  .select(['VV','VH']).mean().clip(STUDY); // mean SAR để ổn định tín hiệu backscatter

var s1_post = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filter(ee.Filter.eq('instrumentMode','IW'))
  .filter(ee.Filter.eq('orbitProperties_pass','ASCENDING'))
  .filterDate(CONFIG.dates.s1PostStart, CONFIG.dates.s1PostEnd)
  .filterBounds(STUDY)
  .select(['VV','VH']).mean().clip(STUDY);

// ─── 2. TÍNH CHỈ SỐ QUANG HỌC ─────────────────────────────────────────────
function computeIndices(img) {
  // NDVI: giảm mạnh khi mất thảm thực vật.
  var ndvi = img.normalizedDifference(['B8','B4']).rename('NDVI');
  // NDWI: hỗ trợ nhận diện vùng ẩm/suối (hữu ích cho debris flow).
  var ndwi = img.normalizedDifference(['B3','B8']).rename('NDWI');
  // NDBI: thông tin built-up/đất trần đô thị (tham khảo phụ).
  var ndbi = img.normalizedDifference(['B11','B8']).rename('NDBI');
  // BSI — Bare Soil Index (đất trần, đặc biệt quan trọng cho khu mỏ)
  var bsi  = img.expression(
    '((SWIR+RED)-(NIR+BLUE))/((SWIR+RED)+(NIR+BLUE))',
    {SWIR:img.select('B11'),RED:img.select('B4'),
     NIR:img.select('B8'), BLUE:img.select('B2')}
  ).rename('BSI'); // BSI tăng khi bề mặt lộ đất/đá
  // NBR — Normalized Burn Ratio (sạt lở tươi trông giống vùng cháy)
  var nbr  = img.normalizedDifference(['B8','B12']).rename('NBR'); // giảm khi bề mặt bị xáo trộn mạnh
  // SAVI — Soil Adjusted Vegetation Index
  var savi = img.expression(
    '1.5*(NIR-RED)/(NIR+RED+0.5)',
    {NIR:img.select('B8'), RED:img.select('B4')}
  ).rename('SAVI'); // chỉ số TV hiệu chỉnh nền đất trần
  return img.addBands([ndvi, ndwi, ndbi, bsi, nbr, savi]);
}

var pre_idx  = computeIndices(s2_pre);
var post_idx = computeIndices(s2_post);

// ─── 3. CHANGE DETECTION ─────────────────────────────────────────────────
// ΔNDVI < 0 → mất thực vật (sạt lở, khai thác)
// dNDVI âm: thực vật giảm sau sự kiện.
var dNDVI = post_idx.select('NDVI').subtract(pre_idx.select('NDVI')).rename('dNDVI');
// ΔBSI  > 0 → tăng đất trần (sạt lở lộ đất, khai thác mở rộng)
// dBSI dương: xu hướng lộ đất/đá tăng.
var dBSI  = post_idx.select('BSI').subtract(pre_idx.select('BSI')).rename('dBSI');
// ΔNBR  < 0 → giảm NBR = mặt đất lộ
// dNBR âm: bề mặt bị suy giảm/biến động cấu trúc.
var dNBR  = post_idx.select('NBR').subtract(pre_idx.select('NBR')).rename('dNBR');
// ΔVV (SAR) > 0 → tăng phản xạ = đất/đá lộ
// dVV dương: SAR backscatter tăng (đất/đá lộ, độ nhám tăng).
var dVV   = s1_post.select('VV').subtract(s1_pre.select('VV')).rename('dVV');

// ─── DIAGNOSTICS: Kiểm tra dải giá trị delta trước khi apply ngưỡng ───────
// Đọc kết quả này TRƯỚC khi kết luận "không có sạt lở":
//   • dNDVI_min chưa vượt ngưỡng strict/relaxed → tín hiệu mất TV yếu hoặc theo mùa
//   • dBSI_max  chưa vượt ngưỡng strict/relaxed → tín hiệu đất trần còn yếu/gần nhiễu
//   • Tất cả null/NaN   → composite rỗng (S2 size = 0) → nới maxCloudPct hoặc đổi ngày
print('📊 === DIAGNOSTICS (scale=500m để nhanh) ===');
print('📊 dNDVI (min/mean/max):', dNDVI.reduceRegion({
  reducer: ee.Reducer.min().combine(ee.Reducer.mean(), null, true)
                           .combine(ee.Reducer.max(),  null, true),
  geometry: STUDY, scale: 500, bestEffort: true, maxPixels: 1e7
}));
print('📊 dBSI  (min/mean/max):', dBSI.reduceRegion({
  reducer: ee.Reducer.min().combine(ee.Reducer.mean(), null, true)
                           .combine(ee.Reducer.max(),  null, true),
  geometry: STUDY, scale: 500, bestEffort: true, maxPixels: 1e7
}));
print('📊 dVV   (min/mean/max):', dVV.reduceRegion({
  reducer: ee.Reducer.min().combine(ee.Reducer.mean(), null, true)
                           .combine(ee.Reducer.max(),  null, true),
  geometry: STUDY, scale: 100, bestEffort: true, maxPixels: 1e8,
  tileScale: 8
}));

// ─── 4. PHÁT HIỆN SẠT LỞ (MULTI-CRITERIA) ────────────────────────────────
/*
 Tiêu chí phát hiện sạt lở ở Tĩnh Túc:
 A. Mất thực vật:    ΔNDVI < -0.15
 B. Tăng đất trần:   ΔBSI  >  0.05
 C. Độ dốc đủ lớn:  slope > 15°   (sườn núi)
 D. Không phải vùng mỏ đang khai thác (BSI_post < 0.3 hoặc dBSI lớn đột ngột)
 E. Tăng backscatter SAR: dVV > 2 dB (xác nhận từ SAR)
*/

// Landslide mask (strict: cần thỏa đồng thời A+B+C)
// Strict: yêu cầu đồng thời mất TV + tăng đất trần + địa hình dốc.
var landslide_strict = dNDVI.lt(CONFIG.landslide.strictDNDVI)
  .and(dBSI.gt(CONFIG.landslide.strictDBSI))
  .and(slope.gt(CONFIG.landslide.strictSlopeMin))
  .rename('landslide_strict');

// Landslide mask (relaxed: A hoặc B, và C)
// Relaxed: nới điều kiện quang học (A hoặc B) nhưng vẫn ràng buộc theo slope.
var landslide_relaxed = (dNDVI.lt(CONFIG.landslide.relaxedDNDVI).or(dBSI.gt(CONFIG.landslide.relaxedDBSI)))
  .and(slope.gt(CONFIG.landslide.relaxedSlopeMin))
  .rename('landslide_relaxed');

// Mining expansion (đất trần nhưng độ dốc thấp)
// Mở rộng mỏ: tăng đất trần rõ nhưng thường ở độ dốc thấp-trung bình và NDVI thấp.
var mining_expansion = dBSI.gt(CONFIG.landslide.miningDBSI)
  .and(slope.lt(CONFIG.landslide.miningExpSlopeMax))
  .and(post_idx.select('NDVI').lt(CONFIG.landslide.miningNDVI))
  .rename('mining_expansion');

// Confirmed với SAR
// SAR-confirmed: lớp tin cậy cao (strict + tăng VV).
var landslide_sar_confirmed = landslide_strict
  .and(dVV.gt(CONFIG.landslide.sarDVV))
  .rename('landslide_sar_confirmed');

// ─── 5. PHÂN LOẠI NGUYÊN NHÂN SẠT LỞ ────────────────────────────────────
/*
 Phân loại dựa trên hướng mặt trượt + độ dốc:
 - Trượt nông (shallow): slope 15–30°, sườn hướng S/SE/E (mưa gió mùa đông)
 - Trượt sâu (deep-seated): slope > 30°, kết hợp với địa chất
 - Đất chảy (debris flow): slope > 25°, gần suối (NDWI cao ở pre)
 - Sạt lở do mỏ: gần vùng mining, slope 10–25°
*/

// Hướng (aspect): 45–180° là sườn đón mưa gió mùa ở Cao Bằng
// (Biến dự phòng) sườn đón mưa, có thể thêm vào rule nếu cần siết false-positive.
var rain_facing = aspect.gte(45).and(aspect.lte(225));

var shallow_slide = landslide_strict
  .and(slope.gte(CONFIG.landslide.strictSlopeMin)).and(slope.lt(CONFIG.landslide.deepSlopeMin))
  .rename('shallow_slide');

var deep_slide = landslide_strict
  .and(slope.gte(CONFIG.landslide.deepSlopeMin))
  .rename('deep_slide');

var debris_flow = landslide_relaxed
  .and(slope.gt(CONFIG.landslide.debrisFlowSlope))
  .and(pre_idx.select('NDWI').gt(-0.1))  // tiền điều kiện ẩm -> nguy cơ đất chảy cao hơn
  .rename('debris_flow');

var mining_induced = landslide_relaxed
  .and(slope.gte(CONFIG.landslide.miningIndSlopeMin)).and(slope.lt(CONFIG.landslide.miningIndSlopeMax))
  .and(mining_expansion)
  .rename('mining_induced');

// ─── 6. TÍNH DIỆN TÍCH ───────────────────────────────────────────────────
function calcAreaHa(mask, label) {
  var area = mask.selfMask().multiply(ee.Image.pixelArea())
    .reduceRegion({
      reducer: ee.Reducer.sum(),
      geometry: STUDY, scale: 10,
      maxPixels: 1e9, bestEffort: true  // bestEffort tránh lỗi time-out trên vùng lớn
    });
  // Đổi m² sang ha (1 ha = 10,000 m²).
  var ha = ee.Number(area.values().get(0)).divide(1e4);
  print(label + ' (ha):', ha);
  return ha;
}

print('=== Diện tích phát hiện ===');
calcAreaHa(landslide_strict,        '🔴 Sạt lở (strict)');
calcAreaHa(landslide_relaxed,       '🟠 Sạt lở (relaxed)');
calcAreaHa(landslide_sar_confirmed, '✅ Sạt lở xác nhận SAR');
calcAreaHa(mining_expansion,        '⛏️  Mở rộng khai thác');
calcAreaHa(shallow_slide,           '  Trượt nông');
calcAreaHa(deep_slide,              '  Trượt sâu');
calcAreaHa(debris_flow,             '  Đất chảy');
calcAreaHa(mining_induced,          '  Sạt lở do mỏ');
print('⚠️  Lớp relaxed chỉ dùng làm mask sơ bộ, KHÔNG dùng trực tiếp cho báo cáo diện tích chính thức.');

// ─── 7. HIỂN THỊ ─────────────────────────────────────────────────────────
Map.setCenter(CONFIG.map.centerLon, CONFIG.map.centerLat, CONFIG.map.zoom); // vị trí camera khởi tạo
Map.setOptions('SATELLITE'); // nền ảnh vệ tinh để kiểm tra trực quan tốt hơn

// RGB trước / sau
Map.addLayer(s2_pre,  {bands:['B4','B3','B2'], min:200, max:2500},
  '📅 Sentinel-2 PRE (2018–2020)', false);
Map.addLayer(s2_post, {bands:['B4','B3','B2'], min:200, max:2500},
  '📅 Sentinel-2 POST (2022–2024)', true);

// ΔNDVI
Map.addLayer(dNDVI, {min:-0.5, max:0.3,
  palette:['darkred','red','orange','white','lightgreen','green']},
  '🌿 ΔNDVI (đỏ=mất TV)', true);

// ΔBSI
Map.addLayer(dBSI, {min:-0.15, max:0.25,
  palette:['blue','white','yellow','orange','red']},
  '🏜️  ΔBSI (đỏ=tăng đất trần)', false);

// Slope
Map.addLayer(slope, {min:0, max:50,
  palette:['white','yellow','orange','red','darkred']},
  '📐 Slope', false);

// Kết quả phát hiện
Map.addLayer(mining_expansion.selfMask(),    {palette:['#FF6600']}, '⛏️  Mở rộng mỏ', true);
Map.addLayer(landslide_relaxed.selfMask(),   {palette:['#FFAA00']}, '🟠 Sạt lở (relaxed, sơ bộ)', false);
Map.addLayer(landslide_strict.selfMask(),    {palette:['#FF0000']}, '🔴 Sạt lở (strict)', true);
// Tạo lớp hiển thị nhẹ để giảm nguy cơ tile memory exceeded khi render.
var landslide_sar_confirmed_vis = landslide_sar_confirmed
  .unmask(0)
  .toByte()
  .reproject({crs: CONFIG.export.crs, scale: 20})
  .selfMask();
Map.addLayer(landslide_sar_confirmed_vis, {palette:['#CC00FF']}, '💜 Xác nhận SAR (ưu tiên kiểm tra thực địa)', true);

// Phân loại loại sạt lở
Map.addLayer(shallow_slide.selfMask(),  {palette:['#FF9900']}, '  Trượt nông', false);
Map.addLayer(deep_slide.selfMask(),     {palette:['#CC0000']}, '  Trượt sâu', false);
Map.addLayer(debris_flow.selfMask(),    {palette:['#6600CC']}, '  Đất chảy', false);
Map.addLayer(mining_induced.selfMask(), {palette:['#FF5500']}, '  Do khai thác', false);

// ─── 8. XUẤT KẾT QUẢ ─────────────────────────────────────────────────────
var hazardMap = ee.Image([
  landslide_strict.unmask(0),
  landslide_sar_confirmed.unmask(0),
  mining_expansion.unmask(0),
  shallow_slide.unmask(0),
  deep_slide.unmask(0),
  debris_flow.unmask(0),
  mining_induced.unmask(0)
]).rename(['landslide_strict','ls_sar_confirmed','mining_expansion',
           'shallow_slide','deep_slide','debris_flow','mining_induced']);
// Lưu ý: unmask(0) để export raster nhị phân sạch (0/1) cho từng lớp.

Export.image.toDrive({
  image: hazardMap.byte(), // ép kiểu byte giảm dung lượng xuất
  description: 'TinhTuc_Hazard_Classification',
  folder: CONFIG.export.folder,
  fileNamePrefix: 'tinhtuc_hazard_map',
  region: STUDY, scale: 10,
  crs: CONFIG.export.crs, maxPixels: CONFIG.export.maxPixels
});

Export.image.toDrive({
  image: ee.Image([dNDVI, dBSI, dNBR, dVV]).float(), // giữ số thực cho phân tích hậu kỳ
  description: 'TinhTuc_Change_Indices',
  folder: CONFIG.export.folder,
  fileNamePrefix: 'tinhtuc_change_indices',
  region: STUDY, scale: 10,
  crs: CONFIG.export.crs, maxPixels: CONFIG.export.maxPixels
});

// Export riêng dVV để hậu kiểm SAR nhanh mà không cần re-compute nặng trên Map tile.
Export.image.toDrive({
  image: dVV.float(),
  description: 'TinhTuc_dVV_only',
  folder: CONFIG.export.folder,
  fileNamePrefix: 'tinhtuc_dVV',
  region: STUDY, scale: 10,
  crs: CONFIG.export.crs, maxPixels: CONFIG.export.maxPixels
});

print('✅ Export tasks sẵn sàng!');
