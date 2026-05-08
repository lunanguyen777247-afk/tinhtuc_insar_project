// File cấu hình trung tâm cho generator script GEE.
// Sửa giá trị tại đây rồi chạy: node gee_scripts/generate_gee_scripts.js
module.exports = {
  // Tham số dùng chung cho cả script 01 và script 03.
  common: {
    // Vùng nghiên cứu (AOI).
    roi: {
      // Bounding box: [minLon, minLat, maxLon, maxLat].
      bbox: [105.85, 22.55, 106.1, 22.8],
      // Polygon chi tiết AOI (điểm cuối trùng điểm đầu để khép kín vùng).
      polygon: [
        [105.87, 22.57], // Góc 1 (Tây Nam)
        [106.08, 22.57], // Góc 2 (Đông Nam)
        [106.08, 22.78], // Góc 3 (Đông Bắc)
        [105.87, 22.78], // Góc 4 (Tây Bắc)
        [105.87, 22.57]  // Đóng polygon
      ],
      // Tâm mỏ tham chiếu cho việc set map/điểm quan trắc.
      mineCenter: [105.975, 22.675]
    },

    // Cấu hình export GeoTIFF từ Google Earth Engine.
    export: {
      // Hệ tọa độ UTM zone 48N phù hợp khu vực Cao Bằng.
      crs: 'EPSG:32648',
      // Ngưỡng số pixel tối đa cho task export (tránh lỗi quota).
      maxPixels: 10000000000,
      // Định dạng tệp đầu ra.
      fileFormat: 'GeoTIFF',
      // Thư mục trên Google Drive.
      folder: 'InSAR_TinhTuc'
    },

    // Cấu hình hiển thị bản đồ mặc định.
    map: {
      // Kinh độ tâm bản đồ.
      centerLon: 105.975,
      // Vĩ độ tâm bản đồ.
      centerLat: 22.675,
      // Mức zoom ban đầu.
      zoom: 12
    }
  },

  // Tham số riêng cho script 01 (Sentinel-1 acquisition/exploration).
  script01: {
    // Các mốc thời gian phân tích.
    dates: {
      // Toàn bộ chuỗi thời gian S1.
      fullStart: '2017-01-01',
      fullEnd: '2024-12-31',
      // Giai đoạn trước (baseline).
      preStart: '2017-01-01',
      preEnd: '2019-12-31',
      // Giai đoạn sau để so sánh biến đổi.
      postStart: '2020-01-01',
      postEnd: '2024-12-31',
      // Khoảng thời gian dùng cho composite Sentinel-2.
      s2Start: '2023-01-01',
      s2End: '2024-10-31'
    },

    // Cấu hình địa hình/sườn dốc.
    slope: {
      // Ngưỡng phân lớp slope: [10, 20, 35, 45] (độ).
      classBreaks: [10, 20, 35, 45],
      // Ngưỡng đánh dấu vùng nguy cơ cao.
      highRiskMin: 30
    },

    // Ngưỡng nhận diện khu khai thác.
    mining: {
      // BSI tối thiểu (đất trần/đá lộ).
      bsiMin: 0.1,
      // NDVI tối đa (ít phủ xanh).
      ndviMax: 0.2,
      // VV tối thiểu (dB) để nhận diện bề mặt phản xạ mạnh.
      vvMin: -12
    },

    // Lọc mây Sentinel-2 theo scene-level.
    s2: {
      // % mây tối đa cho mỗi scene.
      maxCloudPct: 20
    },

    // Cấu hình phát hiện hotspot biến động.
    hotspot: {
      // Phân vị dùng làm ngưỡng hotspot (|velocity|).
      percentile: 90,
      // Độ phân giải tính thống kê hotspot (m).
      scale: 100
    }
  },

  // Tham số riêng cho script 03 (optical landslide detection).
  script03: {
    // Các mốc thời gian pre/post cho S2 và S1.
    // ⚠️  QUAN TRỌNG: dùng cửa sổ NGẮN (1-3 tháng) quanh sự kiện cụ thể.
    // Composite dài (> 6 tháng) sẽ trung bình hóa tín hiệu sạt lở → ΔNDVI ≈ 0.
    // Giai đoạn khô (Nov–Apr) giảm nhiễu mây nhưng không nên kéo dài quá 6 tháng.
    dates: {
      // Sentinel-2 giai đoạn trước: cuối mùa khô trước sự kiện (3 tháng).
      s2PreStart: '2019-11-01',
      s2PreEnd: '2020-02-28',
      // Sentinel-2 giai đoạn sau: ngay sau mùa mưa có sạt lở (3 tháng).
      s2PostStart: '2020-10-01',
      s2PostEnd: '2021-01-31',
      // Sentinel-1 giai đoạn trước.
      s1PreStart: '2019-01-01',
      s1PreEnd: '2020-06-30',
      // Sentinel-1 giai đoạn sau.
      s1PostStart: '2020-07-01',
      s1PostEnd: '2021-12-31'
    },

    // Lọc mây S2 ở cấp scene (CLOUDY_PIXEL_PERCENTAGE).
    // Giá trị đủ cao vì sâu hơn có SCL pixel-level mask loại mây—cần đủ ảnh để đưa ra composite.
    // Cao Bằng mùa khô (Nov–Feb) vẫn thường > 20% mây cấp scene.
    // Nếu print '📊 S2 Pre/Post size' = 0, tăng tiếp lên 50–60.
    s2: {
      // % mây tối đa cho mỗi scene.
      maxCloudPct: 40
    },

    // Bộ ngưỡng multi-criteria cho phát hiện/phân loại sạt lở.
    landslide: {
      // Ngưỡng strict cho mất thực vật: dNDVI < -0.10.
      strictDNDVI: -0.10,
      // Ngưỡng relaxed cho mất thực vật: dNDVI < -0.09.
      relaxedDNDVI: -0.09,
      // Ngưỡng strict cho tăng đất trần: dBSI > 0.08.
      strictDBSI: 0.08,
      // Ngưỡng relaxed cho tăng đất trần: dBSI > 0.05.
      relaxedDBSI: 0.05,
      // Slope tối thiểu cho mask strict (độ).
      strictSlopeMin: 15,
      // Slope tối thiểu cho mask relaxed (độ).
      relaxedSlopeMin: 15,
      // Ngưỡng phân biệt trượt sâu (độ).
      deepSlopeMin: 30,
      // Ngưỡng slope cho debris flow (độ).
      debrisFlowSlope: 28,
      // Ngưỡng dBSI cho mở rộng mỏ.
      miningDBSI: 0.10,
      // Ngưỡng NDVI thấp cho vùng mỏ.
      miningNDVI: 0.18,
      // Slope tối đa cho mining expansion (độ).
      miningExpSlopeMax: 20,
      // Slope tối thiểu cho sạt lở do mỏ (độ).
      miningIndSlopeMin: 10,
      // Slope tối đa cho sạt lở do mỏ (độ).
      miningIndSlopeMax: 25,
      // Ngưỡng xác nhận bằng SAR: dVV > 2.0 dB.
      sarDVV: 2.0
    }
  }
};
