"""
config/settings.py
==================
Cấu hình trung tâm toàn dự án InSAR Tĩnh Túc.
Tất cả tham số quan trọng được quản lý tại đây —
chỉ cần sửa file này khi thay đổi khu vực hoặc tham số xử lý.
"""

from pathlib import Path
import numpy as np

# ─────────────────────────────────────────────
# 1. ĐƯỜNG DẪN DỰ ÁN
# ─────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent  # Thư mục gốc của repository
DATA_DIR = ROOT_DIR / "data"             # Gốc lưu toàn bộ dữ liệu đầu vào/đầu ra trung gian
RAW_DIR = DATA_DIR / "raw"               # Dữ liệu gốc chưa qua xử lý
PROCESSED_DIR = DATA_DIR / "processed"   # Dữ liệu trung gian sau các bước tiền xử lý
OUTPUT_DIR = ROOT_DIR / "outputs"        # Sản phẩm cuối: bản đồ, báo cáo, chuỗi thời gian
LOG_DIR = ROOT_DIR / "logs"              # Nhật ký chạy pipeline và lỗi

# Dữ liệu thô
SAR_ASC_DIR = RAW_DIR / "sentinel1" / "ascending"   # Sentinel-1 quỹ đạo bay lên
SAR_DESC_DIR = RAW_DIR / "sentinel1" / "descending" # Sentinel-1 quỹ đạo bay xuống
ALOS2_DIR = RAW_DIR / "alos2"                         # Dữ liệu ALOS-2 phục vụ kiểm chứng chéo
DEM_DIR = RAW_DIR / "dem"                             # DEM dùng khử pha địa hình và tính slope/aspect
ANCILLARY_DIR = RAW_DIR / "ancillary"                 # Lớp phụ trợ: địa chất, sử dụng đất, thủy hệ...

# Dữ liệu đã xử lý
IFGRAM_ASC_DIR = PROCESSED_DIR / "interferograms" / "asc"   # Interferogram ASC đã tạo
IFGRAM_DESC_DIR = PROCESSED_DIR / "interferograms" / "desc" # Interferogram DESC đã tạo
SBAS_DIR = PROCESSED_DIR / "sbas_results"                     # Sản phẩm chuỗi thời gian từ P-SBAS
KF_STATE_DIR = PROCESSED_DIR / "kalman_states"                # Trạng thái ước lượng sau Kalman 4D

# ─────────────────────────────────────────────
# 2. KHU VỰC NGHIÊN CỨU (AOI)
# ─────────────────────────────────────────────
AOI = {
    "name": "Tinh_Tuc_CaoBang",  # Tên AOI dùng để đặt tên file/sản phẩm
    "lon_min": 105.85,             # Biên trái AOI theo kinh độ (WGS84)
    "lon_max": 105.95,             # Biên phải AOI theo kinh độ (WGS84)
    "lat_min": 22.65,              # Biên dưới AOI theo vĩ độ (WGS84)
    "lat_max": 22.75,              # Biên trên AOI theo vĩ độ (WGS84)
    "epsg": 32648,                 # Hệ quy chiếu đích (UTM 48N) cho tính khoảng cách/diện tích
    "center_lon": 105.90,          # Kinh độ tâm AOI để zoom bản đồ
    "center_lat": 22.70,           # Vĩ độ tâm AOI để zoom bản đồ
}

# ─────────────────────────────────────────────
# 3. THAM SỐ SENTINEL-1
# ─────────────────────────────────────────────
SENTINEL1 = {
    "wavelength_m": 0.056,       # Bước sóng C-band (m), dùng chuyển đổi pha <-> dịch chuyển
    "incidence_angle_deg": 38.0, # Góc tới trung bình tại AOI (độ)
    "heading_asc_deg": -12.0,    # Hướng bay tương đối của quỹ đạo ASC (độ)
    "heading_desc_deg": -168.0,  # Hướng bay tương đối của quỹ đạo DESC (độ)
    "revisit_days": 12,          # Chu kỳ lặp danh nghĩa Sentinel-1 tại khu vực nghiên cứu
    "pixel_spacing_m": 80,       # Kích thước pixel hiệu dụng sau multilook
    # Tham số xử lý interferogram
    "temporal_baseline_max_days": 36, # Ngưỡng baseline thời gian tối đa để chọn cặp ảnh
    "spatial_baseline_max_m": 150,    # Ngưỡng baseline không gian tối đa để giữ tương quan
    "coherence_threshold": 0.20,      # Loại pixel nhiễu có coherence thấp hơn ngưỡng này
    "multilook_range": 4,             # Số look theo hướng range để giảm speckle
    "multilook_azimuth": 1,           # Số look theo hướng azimuth (giữ chi tiết theo dọc quỹ đạo)
}

# ─────────────────────────────────────────────
# 4. THAM SỐ ALOS2 PALSAR2
# ─────────────────────────────────────────────
ALOS2 = {
    "wavelength_m": 0.236,          # Bước sóng L-band dài hơn, xuyên tán lá tốt hơn C-band
    "incidence_angle_deg": 36.0,    # Góc tới trung bình của ALOS-2 tại AOI
    "heading_asc_deg": -10.0,       # Hướng bay tương đối quỹ đạo ASC của ALOS-2
    "temporal_baseline_max_days": 800, # Cho phép baseline thời gian lớn hơn do tính ổn định L-band
    "spatial_baseline_max_m": 500,  # Baseline không gian tối đa cho cặp ALOS-2
    "coherence_threshold": 0.15,    # Ngưỡng coherence cho ALOS-2 (thấp hơn S1 vì bối cảnh khác)
    "role": "cross_validation",    # Vai trò: kiểm chứng chéo, không tham gia huấn luyện chính
}

# ─────────────────────────────────────────────
# 5. THAM SỐ P-SBAS
# ─────────────────────────────────────────────
SBAS = {
    "min_coherence": 0.20,         # Ngưỡng coherence tối thiểu để giữ điểm trong inversion SBAS
    "reference_point": {          # Điểm tham chiếu ổn định ngoài vùng biến dạng
        "lon": 105.870,            # Kinh độ điểm chuẩn đặt mốc dịch chuyển tương đối = 0
        "lat": 22.720,             # Vĩ độ điểm chuẩn
        "description": "Outcrop đá gốc ổn định, phía Tây AOI" # Mô tả thực địa của điểm chuẩn
    },
    "atm_correction": "height_dependent",  # Mô hình hiệu chỉnh nhiễu khí quyển phụ thuộc cao độ
    "velocity_unit": "mm/yr",              # Đơn vị chuẩn hóa vận tốc biến dạng đầu ra
}

# ─────────────────────────────────────────────
# 6. THAM SỐ PHÂN CỤM KHÔNG GIAN
# ─────────────────────────────────────────────
# Nguồn: Festa et al. (2022), điều chỉnh cho Tĩnh Túc
CLUSTERING = {
    "velocity_threshold_cm_yr": 1.0, # Ngưỡng biên độ vận tốc để nhận diện vùng hoạt động có ý nghĩa
    "buffer_radius_m": 100,          # Bán kính gom lân cận không gian khi tạo cụm MAC
    "min_cluster_size_pixels": 3,    # Số pixel tối thiểu để một cụm được giữ lại
    "min_mac_area_km2": 0.02,        # Diện tích nhỏ nhất của một MAC để loại nhiễu cụm nhỏ
    "overlap_threshold_pct": 50,     # Tỷ lệ chồng phủ tối thiểu khi đối chiếu với dữ liệu phụ trợ
    "slope_threshold_deg": 5.0,      # Ngưỡng slope để tách cơ chế trượt lở và lún/trồi
    "kvh_threshold": 1.0,            # Ngưỡng đặc trưng tán xạ VV/VH hỗ trợ phân loại cơ chế
}

# ─────────────────────────────────────────────
# 7. THAM SỐ KALMAN FILTER
# ─────────────────────────────────────────────
# Nguồn: Zheng et al. (2026)
KALMAN = {
    "n_prev_steps": 5,       # Số mốc thời gian quá khứ dùng để dự báo trạng thái kế tiếp
    "m_poly_order": 2,       # Bậc mô hình xu thế theo thời gian trong pha dự báo
    "outlier_method": "huber", # Cách làm bền vững với ngoại lai trong cập nhật quan trắc
    "huber_delta": 1.5,      # Điểm chuyển giữa loss bậc 2 và bậc 1 của Huber
    # Ràng buộc SPF (Surface-Parallel Flow)
    "use_spf_constraint": True, # Bật ràng buộc dòng trượt song song bề mặt địa hình
    "spf_applicable_types": ["landslide", "potential_landslide"], # Loại điểm áp dụng SPF
    # Với lún mỏ: dùng ràng buộc thẳng đứng thay SPF
    "vertical_constraint_types": ["mine_subsidence"], # Nhóm điểm dùng ràng buộc chuyển vị thẳng đứng
    "update_interval_days": 1,          # Chu kỳ cập nhật trạng thái (ngày)
    "initial_state_method": "sbas",   # Cách khởi tạo trạng thái ban đầu từ nghiệm SBAS
}

# ─────────────────────────────────────────────
# 8. THAM SỐ TRANSFORMER
# ─────────────────────────────────────────────
# Nguồn: Zheng et al. (2026), điều chỉnh cho Tĩnh Túc
TRANSFORMER = {
    # Kiến trúc
    "d_model": 64,                  # Kích thước embedding/ẩn của mô hình
    "n_heads": 8,                   # Số đầu attention đa đầu
    "n_encoder_layers_feature": 2,  # Số tầng encoder cho trích xuất đặc trưng ban đầu
    "n_encoder_layers_estimation": 4, # Số tầng encoder cho khối ước lượng chính
    "dropout": 0.1,                 # Tỷ lệ dropout chống overfitting
    # Đầu vào — ĐIỀU CHỈNH SO VỚI BÀI GỐC
    # Bài gốc: [LOS, rainfall, reservoir_level]
    # Tĩnh Túc: [LOS, rainfall, soil_moisture_proxy]
    "input_features": ["los_displacement", "rainfall_mm", "soil_moisture_proxy"], # Danh sách biến đầu vào
    "n_features": 3,                 # Số chiều đặc trưng đầu vào (phải khớp input_features)
    "sequence_length": 30,           # Số bước quá khứ đưa vào mô hình cho mỗi mẫu
    # Huấn luyện
    "train_ratio": 0.75,             # Tỷ lệ dữ liệu dùng huấn luyện
    "test_ratio": 0.25,              # Tỷ lệ dữ liệu dùng đánh giá độc lập
    "batch_size": 32,                # Kích thước lô huấn luyện
    "max_epochs": 500,               # Số epoch tối đa
    "learning_rate": 1e-3,           # Tốc độ học của optimizer
    "patience_early_stop": 50,       # Số epoch chờ trước khi dừng sớm nếu không cải thiện
    # Yêu cầu dữ liệu (từ phân tích Zheng et al.)
    "min_slc_scenes": 147,           # Số cảnh tối thiểu để mô hình đạt độ chính xác chấp nhận được
    "recommended_slc_scenes": 200,   # Số cảnh khuyến nghị để ổn định hơn
    "max_estimation_days": 420,      # Cửa sổ ngoại suy tối đa trước khi cần huấn luyện lại
}

# ─────────────────────────────────────────────
# 9. CÁC ĐIỂM QUAN TRẮC ƯU TIÊN (HOT SPOTS)
# ─────────────────────────────────────────────
HOTSPOTS = {
    "P1": {
        "lon": 105.892, "lat": 22.682, # Tọa độ điểm ưu tiên P1
        "description": "Sườn dốc khu khai thác thiếc phía Đông", # Mô tả vị trí/hiện trạng
        "risk_type": "mixed",          # Kiểu rủi ro chính: kết hợp nhiều cơ chế
        "apply_spf": False,             # Có/không áp dụng ràng buộc SPF cho điểm này
    },
    "P2": {
        "lon": 105.905, "lat": 22.695, # Tọa độ điểm ưu tiên P2
        "description": "Talus slope có dấu hiệu trượt", # Mô tả địa hình/vấn đề chính
        "risk_type": "landslide",      # Cơ chế rủi ro chủ đạo
        "apply_spf": True,               # Bật SPF vì phù hợp cơ chế trượt lở
    },
    "P3": {
        "lon": 105.878, "lat": 22.671, # Tọa độ điểm ưu tiên P3
        "description": "Khu dân cư cạnh mỏ kẽm", # Mô tả bối cảnh phơi lộ rủi ro
        "risk_type": "mine_subsidence", # Cơ chế chính: lún do khai thác mỏ
        "apply_spf": False,               # Không dùng SPF cho cơ chế lún thẳng đứng
    },
}

# ─────────────────────────────────────────────
# 10. LỰA CHỌN CẢM BIẾN VÀ DỮ LIỆU KHÍ TƯỢNG
# ─────────────────────────────────────────────
HYDROMET = {
    # ĐIỀU CHỈNH quan trọng: Tĩnh Túc không có hồ chứa lớn
    # → dùng soil_moisture thay reservoir_level
    "variables": {
        "rainfall": {
            "source": "CHIRPS",  # Nguồn mưa vệ tinh (có thể thay bằng trạm khí tượng địa phương)
            "unit": "mm/day",   # Đơn vị mưa ngày
            "lag_days": 15,       # Độ trễ giả định giữa mưa và phản ứng biến dạng
        },
        "soil_moisture_proxy": {
            "source": "SMAP_L4", # Nguồn độ ẩm đất (sản phẩm đồng hóa của NASA)
            "unit": "m³/m³",     # Đơn vị hàm lượng thể tích nước trong đất
            "note": "Thay thế mực nước hồ chứa trong mô hình Zheng et al." # Lý do chọn biến thay thế
        },
    },
    "wet_season_months": [5, 6, 7, 8, 9],   # Danh sách tháng mùa mưa để phân tích theo mùa
    "dry_season_months": [11, 12, 1, 2, 3], # Danh sách tháng mùa khô đối chiếu nền ổn định
}

# ─────────────────────────────────────────────
# 11. THAM SỐ KINEMATICS
# ─────────────────────────────────────────────
KINEMATICS = {
    "strain_window_pixels": 3,       # Kích thước cửa sổ lân cận để tính strain tensor/invariants
    "thickness_method": "mass_conservation", # Cách ước lượng bề dày khối trượt theo bảo toàn khối lượng
    "ica_n_components": 3,           # Số thành phần độc lập khi tách nguồn tín hiệu động học
    "wtc_significance_level": 0.05,  # Mức ý nghĩa thống kê cho wavelet coherence
    "acceleration_threshold_mm_day2": 0.5, # Ngưỡng gia tốc dùng phát cảnh báo sớm
}

# ─────────────────────────────────────────────
# 12. THÔNG SỐ ĐẦU RA
# ─────────────────────────────────────────────
OUTPUT = {
    "map_dpi": 300,                    # Độ phân giải ảnh bản đồ xuất ra
    "figure_format": "png",           # Định dạng hình mặc định cho biểu đồ/bản đồ
    "colormap_velocity": "RdYlGn_r",  # Bảng màu cho trường vận tốc biến dạng
    "colormap_coherence": "viridis",  # Bảng màu cho trường coherence/chất lượng
    "velocity_range_cm_yr": (-5, 5),   # Khoảng hiển thị vận tốc (cm/năm) khi vẽ bản đồ
}

# ─────────────────────────────────────────────
# 13. GEE CONFIG (đồng bộ YAML ↔ JS)
# ─────────────────────────────────────────────
# Tham số GEE được đọc từ config/gee_config.yaml — cùng nguồn với JS.
# Cập nhật YAML rồi chạy:  python config/generate_js_config.py
import yaml as _yaml
GEE_CONFIG: dict = _yaml.safe_load(
    (Path(__file__).parent / "gee_config.yaml").read_text(encoding="utf-8")
)
# Dùng trong Python:
#   from config.settings import GEE_CONFIG
#   full_start = GEE_CONFIG['dates']['fullStart']
#   bbox       = GEE_CONFIG['roi']['bbox']
