// =============================================================================
// gee_scripts/01_sentinel1_acquisition.js
// Thu thập và khám phá dữ liệu Sentinel-1 cho Xã Tĩnh Túc, Cao Bằng
// Khu vực đặc biệt: Mỏ thiếc + địa hình núi dốc + sạt lở
// Chạy tại: https://code.earthengine.google.com
// =============================================================================

// ╔══════════════════════════════════════════════════════════════════════════╗
// ║  CONFIG — AUTO-GENERATED từ config/gee_config.yaml                      ║
// ║  KHÔNG sửa trực tiếp — chạy: python config/generate_js_config.py       ║
// ╚══════════════════════════════════════════════════════════════════════════╝
var CONFIG = __CONFIG_01__;

// ─── 1. KHU VỰC NGHIÊN CỨU ───────────────────────────────────────────────
var ROI            = ee.Geometry.Rectangle(CONFIG.roi.bbox);
var TINHTUC_DETAIL = ee.Geometry.Polygon([CONFIG.roi.polygon]);
var MINE_CENTER    = ee.Geometry.Point(CONFIG.roi.mineCenter);

// ─── 2. THÔNG SỐ THỜI GIAN ────────────────────────────────────────────────
var PRE_PERIOD_START  = CONFIG.dates.preStart;
var PRE_PERIOD_END    = CONFIG.dates.preEnd;
var POST_PERIOD_START = CONFIG.dates.postStart;
var POST_PERIOD_END   = CONFIG.dates.postEnd;
var FULL_START        = CONFIG.dates.fullStart;
var FULL_END          = CONFIG.dates.fullEnd;

// ─── 3. TẢI SENTINEL-1 GRD ────────────────────────────────────────────────
function loadS1(orbit, startDate, endDate, roi) {
  // Hàm tiện ích chuẩn hóa truy vấn Sentinel-1 để tránh lặp code.
  // orbit: 'ASCENDING' hoặc 'DESCENDING'
  // startDate/endDate: khoảng thời gian lấy ảnh
  // roi: vùng lọc không gian
  return ee.ImageCollection('COPERNICUS/S1_GRD')
    // Chỉ lấy mode IW vì đây là mode phổ biến cho quan trắc mặt đất diện rộng.
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    // Đảm bảo ảnh có cả VV và VH để tính được các chỉ số phân cực.
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
    // Tách theo quỹ đạo để phân tích ổn định hình học chụp.
    .filter(ee.Filter.eq('orbitProperties_pass', orbit))
    .filterDate(startDate, endDate)
    .filterBounds(roi)
    // angle giữ lại để dùng khi cần chuẩn hóa theo góc tới.
    .select(['VV', 'VH', 'angle']);
}

var s1_asc_full  = loadS1('ASCENDING',  FULL_START, FULL_END, TINHTUC_DETAIL);
var s1_desc_full = loadS1('DESCENDING', FULL_START, FULL_END, TINHTUC_DETAIL);

print('=== Sentinel-1 — Tĩnh Túc, Cao Bằng ===');
print('ASCENDING  images:', s1_asc_full.size());
print('DESCENDING images:', s1_desc_full.size());

// Kiểm tra metadata ảnh đầu
print('Ảnh ASC đầu tiên:', s1_asc_full.first());

// ─── 4. TẢI DEM VÀ PHÂN TÍCH ĐỊA HÌNH ────────────────────────────────────
// Copernicus DEM 30m (chính xác hơn SRTM cho vùng núi)
var TERRAIN_CRS = CONFIG.export.crs;
var TERRAIN_SCALE = 30;

var demCollection = ee.ImageCollection('COPERNICUS/DEM/GLO30')
  .filterBounds(TINHTUC_DETAIL)
  .select('DEM');

var demNativeProj = ee.Image(demCollection.first()).projection();

var demRaw = demCollection
  .mosaic()
  .setDefaultProjection(demNativeProj);

// Tính terrain trên DEM chưa clip để giữ lân cận pixel (tránh slope bị mask/null).
var terrainRaw = ee.Terrain.products(demRaw);

var dem = demRaw.clip(TINHTUC_DETAIL);
var slope = terrainRaw.select('slope').clip(TINHTUC_DETAIL).rename('slope');
var aspect = terrainRaw.select('aspect').clip(TINHTUC_DETAIL).rename('aspect');
var hillshade = terrainRaw.select('hillshade').clip(TINHTUC_DETAIL).rename('hillshade');
// slope/aspect/hillshade sẽ được dùng để:
// - đánh giá nguy cơ sạt lở theo độ dốc,
// - trực quan địa hình,
// - làm lớp phụ trợ cho phân tích điểm nóng.

// Thống kê địa hình
var demStats = dem.reduceRegion({
  reducer: ee.Reducer.percentile([5, 25, 50, 75, 95])
    .combine(ee.Reducer.minMax(), null, true),
  geometry: TINHTUC_DETAIL,
  crs: TERRAIN_CRS,
  scale: TERRAIN_SCALE,
  maxPixels: 1e10,
  bestEffort: false,
  tileScale: 4
});
print('Thống kê độ cao (m):', demStats);

// Fix slope null: dùng mask native của slope và reduce theo projection của slope.
var slopeMasked = slope.rename('slope');

var slopeValidCount = slopeMasked.reduceRegion({
  reducer: ee.Reducer.count(),
  geometry: TINHTUC_DETAIL,
  crs: TERRAIN_CRS,
  scale: TERRAIN_SCALE,
  maxPixels: 1e10,
  bestEffort: false,
  tileScale: 4
});
print('Số pixel slope hợp lệ:', slopeValidCount);

var slopeValid = ee.Number(ee.Algorithms.If(
  slopeValidCount.contains('slope'),
  slopeValidCount.get('slope'),
  0
));

// Fallback khi slope bị mask toàn vùng: fill DEM cục bộ rồi tính slope lại.
var demFilled = demRaw.unmask(
  demRaw.focal_mean({radius: 1, units: 'pixels'})
);
var slopeFallback = ee.Terrain.slope(demFilled)
  .clip(TINHTUC_DETAIL)
  .rename('slope');

var slopeForStats = ee.Image(ee.Algorithms.If(
  slopeValid.gt(0),
  slopeMasked,
  slopeFallback
));

print('Dùng slope fallback cho thống kê?:', slopeValid.lte(0));

var slopeStats = slopeForStats.reduceRegion({
  reducer: ee.Reducer.percentile([50, 75, 90, 95]),
  geometry: TINHTUC_DETAIL,
  crs: TERRAIN_CRS,
  scale: TERRAIN_SCALE,
  maxPixels: 1e10,
  bestEffort: false,
  tileScale: 4
});
print('Phân vị độ dốc (°):', slopeStats);

// Phân loại độ dốc theo ngưỡng sạt lở
// 0–10°: ổn định | 10–20°: nguy cơ thấp | 20–35°: nguy cơ trung bình
// 35–45°: nguy cơ cao | >45°: rất cao
var cb = CONFIG.slope.classBreaks;  // [10, 20, 35, 45]
var slopeClass = slope.where(slope.lt(cb[0]), 1)
  .where(slope.gte(cb[0]).and(slope.lt(cb[1])), 2)
  .where(slope.gte(cb[1]).and(slope.lt(cb[2])), 3)
  .where(slope.gte(cb[2]).and(slope.lt(cb[3])), 4)
  .where(slope.gte(cb[3]), 5)
  .rename('slope_class');
// Lưu ý: lớp này là phân hạng heuristic để mapping nhanh, không thay thế
// mô hình địa kỹ thuật chi tiết tại hiện trường.

// Vùng có nguy cơ cao (ngưỡng từ CONFIG.slope.highRiskMin)
var highRiskSlope = slope.gt(CONFIG.slope.highRiskMin).selfMask();

// ─── 5. CHỈ SỐ SAR ĐẶC TRƯNG CHO TĨNH TÚC ────────────────────────────────

// 5a. Backscatter VV trung bình (nhạy cảm với bề mặt đất/đá lộ)
var meanVV_pre  = s1_asc_full.filterDate(PRE_PERIOD_START,  PRE_PERIOD_END).select('VV').mean();
var meanVV_post = s1_asc_full.filterDate(POST_PERIOD_START, POST_PERIOD_END).select('VV').mean();

// 5b. Thay đổi backscatter (chỉ thị khai thác mỏ + sạt lở)
// Tăng VV → mặt đất lộ (khai thác, sạt lở tươi)
// Giảm VV → tán thực vật tăng / sụt lún tạo hố nước
var deltaVV = meanVV_post.subtract(meanVV_pre).rename('delta_VV');

// 5c. Tỷ số VV/VH → phân biệt đất trống vs thực vật (RVI proxy)
var rvi_proxy_pre  = meanVV_pre.subtract(
  s1_asc_full.filterDate(PRE_PERIOD_START,  PRE_PERIOD_END).select('VH').mean()
).rename('VV_VH_diff_pre');
var rvi_proxy_post = meanVV_post.subtract(
  s1_asc_full.filterDate(POST_PERIOD_START, POST_PERIOD_END).select('VH').mean()
).rename('VV_VH_diff_post');

// 5d. Temporal coherence proxy (ổn định bề mặt)
var s1_linear = s1_asc_full.map(function(img) {
  // Chuyển dB -> linear:
  // sigma0_linear = 10^(dB/10)
  // giúp tính mean/std và CV có ý nghĩa vật lý hơn trên miền biên độ.
  return ee.Image(10).pow(img.select('VV').divide(10))
    .rename('VV_lin')
    .copyProperties(img, ['system:time_start']);
});

var mean_lin = s1_linear.mean();
var std_lin  = s1_linear.reduce(ee.Reducer.stdDev()).rename('std');
var cv_map   = std_lin.divide(mean_lin).rename('CV');
// Coherence proxy: thấp CV = bề mặt ổn định, phù hợp InSAR
var coherence_proxy = ee.Image(1).divide(cv_map.add(1)).rename('coherence_proxy');
// coherence_proxy ∈ (0,1]:
// - gần 1  -> ổn định theo thời gian (ít biến động backscatter)
// - gần 0  -> biến động mạnh (thực vật, nước, hoạt động bề mặt)

// ─── 6. TẢI ẢNH QUANG HỌC SENTINEL-2 ────────────────────────────────────
// Để mapping sạt lở và phân loại đất đai
var s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterDate(CONFIG.dates.s2Start, CONFIG.dates.s2End)
  .filterBounds(TINHTUC_DETAIL)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CONFIG.s2.maxCloudPct))
  .select(['B2','B3','B4','B8','B11','B12']);
// Ở bước này dùng CLOUDY_PIXEL_PERCENTAGE để lọc thô theo scene-level.
// Nếu cần khắt khe hơn cho nghiên cứu chi tiết, có thể bổ sung mask mây theo SCL/QA60.

// Hợp thành ảnh không mây
var s2_composite = s2.median().clip(TINHTUC_DETAIL);

// Chỉ số thực vật NDVI
var ndvi = s2_composite.normalizedDifference(['B8','B4']).rename('NDVI');
// Chỉ số đất trần BSI (Bare Soil Index) — quan trọng cho mapping khu mỏ
var bsi = s2_composite.expression(
  '((SWIR1 + RED) - (NIR + BLUE)) / ((SWIR1 + RED) + (NIR + BLUE))',
  {SWIR1: s2_composite.select('B11'),
   RED:   s2_composite.select('B4'),
   NIR:   s2_composite.select('B8'),
   BLUE:  s2_composite.select('B2')}
).rename('BSI');

// Chỉ số đá lộ (Mining/Bare Rock Index)
var ndbi = s2_composite.normalizedDifference(['B11','B8']).rename('NDBI');

print('Sentinel-2 composite bands:', s2_composite.bandNames());

// ─── 7. PHÁT HIỆN KHU VỰC MỎ KHAI THÁC ─────────────────────────────────
// Đặc trưng: BSI cao, NDVI thấp, backscatter VV cao
var miningMask = bsi.gt(CONFIG.mining.bsiMin)
  .and(ndvi.lt(CONFIG.mining.ndviMax))
  .and(meanVV_post.gt(CONFIG.mining.vvMin))
  .selfMask()
  .rename('mining_area');
// Ý nghĩa ngưỡng:
// - BSI > 0.1: xu hướng đất trần/đá lộ
// - NDVI < 0.2: ít phủ xanh
// - VV > -12 dB: phản xạ radar tương đối mạnh (bề mặt thô/rắn)
// Đây là ngưỡng kinh nghiệm để screening nhanh, nên hiệu chỉnh theo thực địa.

// Tính diện tích vùng mỏ ước tính
var miningArea = miningMask.multiply(ee.Image.pixelArea())
  .reduceRegion({
    reducer: ee.Reducer.sum(),
    geometry: TINHTUC_DETAIL,
    scale: 10, maxPixels: 1e9
  });
print('Ước tính diện tích vùng khai thác (m²):', miningArea);

// ─── 8. VELOCITY PROXY (THAY ĐỔI THEO THỜI GIAN) ─────────────────────────
// Tính velocity proxy từ linear regression Sentinel-1
var s1_withTime = s1_linear.map(function(img) {
  // Chuẩn hóa thời gian về số thực nhỏ để regression ổn định số học.
  // 1e13 giúp giảm bậc lớn của timestamp millis mà vẫn giữ thứ tự thời gian.
  var t = img.metadata('system:time_start').divide(1e13);
  return img.addBands(t.rename('time'))
            .addBands(ee.Image(1).rename('constant'));
});

var regression = s1_withTime.select(['time','constant','VV_lin'])
  .reduce(ee.Reducer.linearRegression({numX:2, numY:1}));
// Hồi quy tuyến tính theo từng pixel:
// VV_lin = slope * time + intercept
// slope là proxy xu thế biến đổi dài hạn của backscatter.

var velocityProxy = regression.select('coefficients')
  .arrayProject([0]).arrayFlatten([['slope','intercept']])
  .select('slope').rename('velocity_proxy');

// Vùng có thay đổi mạnh (potential displacement hotspots)
var hotspotStats = velocityProxy.abs().reduceRegion({
  reducer: ee.Reducer.percentile([CONFIG.hotspot.percentile]),
  geometry: TINHTUC_DETAIL,
  scale: CONFIG.hotspot.scale,
  maxPixels: 1e8,
  bestEffort: true
});
var hotspotThreshold = ee.Number(ee.Algorithms.If(
  hotspotStats.size().gt(0),
  hotspotStats.values().get(0),
  0.0
));
// Dùng phân vị 90% để tự động thích ứng theo dữ liệu từng AOI,
// tránh hard-code ngưỡng tuyệt đối khi điều kiện địa hình/chuỗi ảnh thay đổi.
var hotspots = velocityProxy.abs()
  .gt(ee.Image.constant(hotspotThreshold))
  .selfMask()
  .rename('hotspots');

// ─── 9. HIỂN THỊ BẢN ĐỒ ─────────────────────────────────────────────────
Map.setCenter(CONFIG.map.centerLon, CONFIG.map.centerLat, CONFIG.map.zoom);
Map.setOptions('SATELLITE');

// DEM & hillshade
Map.addLayer(hillshade, {min:0, max:255}, '🏔️ Hillshade', false);
Map.addLayer(dem, {min:400, max:1800, palette:['green','yellow','brown','white']},
  '⛰️  DEM Copernicus 30m', false);

// Độ dốc — quan trọng cho sạt lở
Map.addLayer(slope,
  {min:0, max:50, palette:['white','yellow','orange','red','darkred']},
  '📐 Độ dốc (degree)', true);

// Vùng nguy cơ sạt lở cao
Map.addLayer(highRiskSlope, {palette:['red']}, '🚨 Slope > 30° (nguy cơ cao)', true);

// Sentinel-2 RGB
Map.addLayer(s2_composite, {bands:['B4','B3','B2'], min:0, max:3000},
  '🛰️ Sentinel-2 RGB 2023-24', false);

// Backscatter change
Map.addLayer(deltaVV,
  {min:-5, max:5, palette:['blue','white','red']},
  '📡 ΔBackscatter VV (2017→2024)\n[Đỏ=tăng=khai thác/sạt lở, Xanh=giảm]', true);

// Temporal coherence
Map.addLayer(coherence_proxy,
  {min:0, max:1, palette:['red','orange','yellow','green']},
  '🎯 Coherence proxy (xanh=ổn định=tốt cho InSAR)', true);

// Vùng khai thác mỏ
Map.addLayer(miningMask, {palette:['#FF6600']}, '⛏️  Vùng khai thác ước tính', true);

// Hotspots
Map.addLayer(hotspots, {palette:['magenta']}, '🔥 Displacement Hotspots', true);

// NDVI
Map.addLayer(ndvi,
  {min:-0.2, max:0.8, palette:['brown','yellow','lightgreen','darkgreen']},
  '🌿 NDVI (thực vật)', false);

// ─── 10. PHÂN TÍCH THỜI GIAN TẠI CÁC ĐIỂM QUAN TRẮC ────────────────────
var monitoringPts = ee.FeatureCollection([
  ee.Feature(ee.Geometry.Point([105.975, 22.675]), {name:'Mỏ thiếc TT (TT-01)'}),
  ee.Feature(ee.Geometry.Point([105.960, 22.690]), {name:'Sườn Tây (TT-02)'}),
  ee.Feature(ee.Geometry.Point([105.990, 22.660]), {name:'Hạ lưu mỏ (TT-03)'}),
  ee.Feature(ee.Geometry.Point([105.940, 22.710]), {name:'Khu dân cư (TT-04)'}),
  ee.Feature(ee.Geometry.Point([106.020, 22.640]), {name:'Đất nông nghiệp (TT-05)'}),
]);
Map.addLayer(monitoringPts, {color:'yellow'}, '📍 Điểm quan trắc');

// Biểu đồ time-series VV tại các điểm
var nMonths = ee.Number(
  ee.Date(FULL_END).difference(ee.Date(FULL_START), 'month')
).round();

var monthStarts = ee.List.sequence(0, nMonths.subtract(1));

var s1AscMonthly = ee.ImageCollection.fromImages(
  monthStarts.map(function(m) {
    m = ee.Number(m);
    var start = ee.Date(FULL_START).advance(m, 'month');
    var end = start.advance(1, 'month');
    var ic = s1_asc_full.filterDate(start, end).select('VV');

    var img = ee.Image(ee.Algorithms.If(
      ic.size().gt(0),
      ic.median().rename('VV')
        .set('system:time_start', start.millis())
        .set('n_obs', ic.size())
        .set('is_empty', 0),
      ee.Image.constant(0).rename('VV')
        .updateMask(ee.Image.constant(0))
        .set('system:time_start', start.millis())
        .set('n_obs', 0)
        .set('is_empty', 1)
    ));
    return img;
  })
).filter(ee.Filter.eq('is_empty', 0));

print('Số mốc monthly composite:', s1AscMonthly.size());

var tsChart = ui.Chart.image.seriesByRegion({
  imageCollection: s1AscMonthly,
  regions: monitoringPts,
  reducer: ee.Reducer.mean(),
  scale: 100,
  seriesProperty: 'name',
  xProperty: 'system:time_start'
}).setOptions({
  title: '📈 Chuỗi thời gian Sentinel-1 VV (monthly median) — Tĩnh Túc (2017–2024)',
  vAxis: {title: 'Backscatter VV (dB)', viewWindow:{min:-25, max:-3}},
  hAxis: {title: 'Thời gian'},
  lineWidth: 2.0, pointSize: 2,
  series: {
    0:{color:'FF0000'}, 1:{color:'FF6600'},
    2:{color:'0066FF'}, 3:{color:'009900'}, 4:{color:'9900FF'}
  }
});
// Biểu đồ dùng trung bình vùng tại mỗi điểm (thực chất là pixel lân cận theo scale=100m)
// để giảm nhiễu speckle so với lấy đúng 1 pixel.
print(tsChart);

// ─── 11. XUẤT DỮ LIỆU ────────────────────────────────────────────────────
var exportParams = {
  region:     TINHTUC_DETAIL,
  crs:        CONFIG.export.crs,
  maxPixels:  CONFIG.export.maxPixels,
  fileFormat: CONFIG.export.fileFormat
};
// Gom tham số export chung để:
// - tránh lặp cấu hình giữa các task,
// - đảm bảo tất cả lớp xuất cùng hệ tọa độ và cùng AOI.

// Xuất coherence proxy
Export.image.toDrive({
  image: coherence_proxy.float(),
  description: 'TinhTuc_CoherenceProxy_2017_2024',
  folder: CONFIG.export.folder,
  fileNamePrefix: 'tinhtuc_coherence',
  region: exportParams.region,
  crs: exportParams.crs,
  maxPixels: exportParams.maxPixels,
  fileFormat: exportParams.fileFormat,
  scale: 100
});

// Xuất delta backscatter
Export.image.toDrive({
  image: deltaVV.float(),
  description: 'TinhTuc_DeltaBackscatter_VV',
  folder: CONFIG.export.folder,
  fileNamePrefix: 'tinhtuc_delta_vv',
  region: exportParams.region,
  crs: exportParams.crs,
  maxPixels: exportParams.maxPixels,
  fileFormat: exportParams.fileFormat,
  scale: 100
});

// Xuất DEM + slope + aspect + hillshade
Export.image.toDrive({
  image: ee.Image([dem, slope, aspect, hillshade]).float(),
  description: 'TinhTuc_DEM_Terrain_30m',
  folder: CONFIG.export.folder,
  fileNamePrefix: 'tinhtuc_dem_terrain',
  region: exportParams.region,
  crs: exportParams.crs,
  maxPixels: exportParams.maxPixels,
  fileFormat: exportParams.fileFormat,
  scale: 30
});

// Xuất velocity proxy
Export.image.toDrive({
  image: velocityProxy.float(),
  description: 'TinhTuc_VelocityProxy_2017_2024',
  folder: CONFIG.export.folder,
  fileNamePrefix: 'tinhtuc_velocity_proxy',
  region: exportParams.region,
  crs: exportParams.crs,
  maxPixels: exportParams.maxPixels,
  fileFormat: exportParams.fileFormat,
  scale: 100
});

// Xuất Sentinel-2 + chỉ số
Export.image.toDrive({
  image: ee.Image([
    s2_composite.select(['B4','B3','B2','B8','B11']),
    ndvi,
    bsi,
    ndbi
  ]).float(),
  description: 'TinhTuc_Sentinel2_Indices_2023_24',
  folder: CONFIG.export.folder,
  fileNamePrefix: 'tinhtuc_s2_indices',
  region: exportParams.region,
  crs: exportParams.crs,
  maxPixels: exportParams.maxPixels,
  fileFormat: exportParams.fileFormat,
  scale: 10
});

// Xuất vùng khai thác + hotspots
Export.image.toDrive({
  image: ee.Image([
    miningMask.unmask(0),
    hotspots.unmask(0),
    slopeClass
  ]).byte(),
  description: 'TinhTuc_Mining_Hotspot_SlopeClass',
  folder: CONFIG.export.folder,
  fileNamePrefix: 'tinhtuc_hazard_layers',
  region: exportParams.region,
  crs: exportParams.crs,
  maxPixels: exportParams.maxPixels,
  fileFormat: exportParams.fileFormat,
  scale: 30
});

print('✅ 6 export tasks đã sẵn sàng!');
print('👉 Vào tab Tasks → nhấn RUN cho từng task');
print('📁 Kết quả lưu trong Google Drive: InSAR_TinhTuc/');
// Gợi ý thao tác: nên chạy task nhẹ trước (coherence, deltaVV),
// sau đó chạy task nặng (Sentinel-2 indices, hazard layers) để dễ theo dõi lỗi quota.
