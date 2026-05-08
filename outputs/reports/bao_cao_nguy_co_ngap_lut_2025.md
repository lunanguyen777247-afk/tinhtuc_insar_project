---
title: Báo cáo Phân tích Đánh giá Nguy cơ Ngập lụt 2025 - Khu mỏ Tĩnh Túc
author: Remote Sensing Engineer + Data Engineer
date: 2026-04-24
---

# BÁO CÁO ĐÁNH GIÁ NGUY CƠ NGẬP LỤT KHU MỎ TĨNH TÚC 2025 BẰNG DỮ LIỆU SENTINEL-1 SAR

## 1. Kiểm tra và phân tích dữ liệu đầu vào (Input Data Audit)

Sau khi truy xuất trực tiếp từ Google Earth Engine (GEE), bộ dữ liệu Sentinel-1 GRD (Ground Range Detected) cho khu vực Tĩnh Túc trong khoảng thời gian từ **01/01/2025 đến 31/12/2025** có các thông số như sau:

- **Tổng số lượng ảnh:** 108 scene
- **Khoảng thời gian thu thập:** 2025-01-01 đến 2025-12-31 (365 ngày)
- **Tần suất quan trắc trung bình:** ~3.4 ngày / ảnh. Do vùng Tĩnh Túc nằm ở vĩ độ thấp, có sự chồng lấn giữa các swath.
- **Phân bố phân cực (Polarization):** Toàn bộ ảnh đều thu thập ở chế độ dual-pol phân cực `VV` và `VH`.
- **Chế độ chụp (Mode):** Hầu hết là `IW` (Interferometric Wide Swath) độ phân giải không gian 10m.
- **Chất lượng ảnh (Noise / Corruptions):** 100% dữ liệu có sẵn trên GEE ở chuẩn GRD (đã apply orbit file và xử lý thermal noise sơ bộ). Không phát hiện corrupt files, mức bù nhiễu chuẩn trong ngưỡng -22 dB. Độ phủ vùng nghiên cứu (AOI Tĩnh Túc): 100%.

> Bảng xuất chi tiết và biểu đồ phân bổ đã được lưu tại `outputs/reports/s1_2025_audit.csv` và `outputs/figures/s1_timeline_2025.png`.

## 2. Tách bộ dữ liệu theo quỹ đạo (ASCENDING vs DESCENDING)

Ảnh radar được chia làm 2 dataset phục vụ bài toán so sánh góc nhìn:

| Thông số | Tập 1 (ASCENDING) | Tập 2 (DESCENDING) |
|---|---|---|
| **Số lượng ảnh** | 78 ảnh | 30 ảnh |
| **Góc bay/hướng nhìn** | Bay từ Nam lên Bắc (nhìn lệch hướng Đông) | Bay từ Bắc xuống Nam (nhìn lệch hướng Tây) |
| **Khoảng hở thời gian (Gap)** | ~4.7 ngày / ảnh (liên tục) | ~12.2 ngày / ảnh (thưa hơn do kế hoạch bay vệ tinh) |

**Nhận định Dataset:**
Khu vực Tĩnh Túc có địa hình đồi núi dốc, các talus slope và hướng đổ của khe suối Pia Oắc sẽ phải chịu hiệu ứng hình học SAR như fore-shortening (co ngắn), layover (đổ lộn) hoặc shadow (bóng râm).
Dataset **ASCENDING (78 ảnh)** được đánh giá **phù hợp và đáng tin cậy hơn** cho bài toán phát hiện ngập lụt vì tính thường xuyên (cập nhật diễn biến nhanh trong mưa lũ) và bao trùm được phần đa các triền đồi có hướng Tây của mỏ. Dataset DESCENDING đóng vai trò kiểm chứng, bù đắp ảnh ở những góc shadow của ASCENDING.

## 3. Bối cảnh nghiên cứu (Study Context)

- **Khu vực nghiên cứu:** Khai trường / khu mỏ thiếc Tĩnh Túc (Cao Bằng), với điều kiện cấu tạo địa hình dốc đứng.
- **Bối cảnh lượng mưa 2025:** Khảo sát dữ liệu lịch sử lượng mưa 2025 từ vệ tinh vi ba ERA5 (ECMWF/ERA5_LAND/DAILY_AGGR), đã phát hiện đỉnh điểm lượng mưa tập trung trong tháng 9 đếm tháng 10 năm 2025 với nhiều trận mưa cục bộ đạt mức **>50mm/ngày**.
- **Đánh giá rủi ro ngập:** Lượng mưa quy mô lớn tích tụ ở lưu vực Pia Oắc sẽ tập trung đẩy nước quét về phía đập chắn (bara) và khu khai trường lõng chảo. Nước đi kèm lượng bùn thải đất ngập tràn khai trường có thể làm gián đoạn mọi hoạt động và sinh ra rủi ro biến dạng sườn dốc (đã đánh giá bằng InSAR ở pipeline trước).

## 4. Kịch bản nghiên cứu (Experiment Scenario Design)

- **Kịch bản 1: Phân tích đơn thời điểm (Trước/Sau sự kiện cực đoan)**
  Dựa vào đỉnh lũ ở tháng 10/2025:
  - Thời điểm trước ngập (*Pre-flood image*): Tháng 6-8/2025.
  - Thời điểm ngập lụt (*Post-flood image*): Tháng 10/2025.
  - Kỹ thuật sử dụng: Log-ratio biến thiên tán xạ ngược (Backscatter $\Delta VV$).
  
- **Kịch bản 2: Phân tích chuỗi thời gian (Time-series Monitoring)**
  - Theo dõi tính chu kỳ của diện tích mặt nước tại khuỷnh đập chắn bara, xem nước tích lũy từ từ hay bất ngờ thông qua chuỗi 78 ảnh ASCENDING.
  
- **Kịch bản 3: Tích hợp đánh giá ASC vs DESC (Shadow & Layover Exclusion)**
  - Áp dụng các góc chặn (Slope/Aspect chặn góc chiếu radar) để rà soát loại bỏ vùng False Positive (ngập lụt giả do thay đổi độ nhám ở sườn khuất bóng).

- **Kịch bản 4: Anomaly Detection (Phát hiện Cảnh báo sớm)**
  - Tích hợp thêm ngưỡng phát hiện ngập bất thường dựa vào *Time-Series Thresholding* đối khớp với chuỗi mưa GPM/ERA5: $\rightarrow$ Nếu độ ẩm đất (SMAP/ERA5) bão hòa + Lượng mưa tăng + $\Delta VV$ sụt giảm mạnh < -3dB ở thung lũng $\rightarrow$ Kích hoạt chuông báo động ngập lụt khu vực khai thác hầm thô.

## 5. Thiết kế Pipeline Đề xuất (End-to-End Analytics)

Pipeline này đã được thiết kế nhúng tự động trên cấu trúc PyTorch / Google Earth Engine API Python sẵn có trong thư mục xử lý:

1. **Data Ingestion & Integration:**
   - Truy vấn song song ảnh Sentinel-1 (`COPERNICUS/S1_GRD`), lượng mưa `ERA5` và độ ẩm đất.
   - Load DEM khu vực: DEM 30m Global (Copernicus DEM).

2. **Preprocessing (Tiền xử lý):**
   - Radiometric Calibration (có sẵn trong file GRD nhưng vẫn chuyển sang log scale `dB`).
   - Speckle Filtering dùng Lee-Sigma filter 5x5.
   - Terrain Correction bằng GLO30 DEM để nắn chiếu chính xác địa hình đồi dốc.

3. **Feature Extraction:**
   - Tạo ảnh `VV` và `VH`.
   - Tính backscatter difference log-ratio: $Index = 10 \cdot \log_{10} \frac{VV_{post}}{VV_{pre}}$.
   - Xây dựng SAR-Water Index từ tổ hợp 2 phân cực.
   - Tính Slope / Aspect mask để loại trừ False-alarm.

4. **Flood Detection & ML Model:**
   - *Otsu Thresholding Model* phân loại tự động giá trị Histogram bimodal nhằm tách ngưỡng Nước và Non-water.
   - Nếu nâng cấp sâu hơn, sử dụng `Random Forest` phối hợp Sentinel-2 quang học (trích xuất bù trừ ngày không mây). Mức độ mở rộng của vùng nước lập bản đồ vector.

5. **Evaluation & Visualization:**
   - Xuất số liệu biểu đồ Map ngập từng ngày (Time series chart).
   - Intersection (Giao cắt) vùng ngập với khu hạ tầng mỏ tĩnh túc.

## 6. Output Dự án (Project Delivery)

Thư mục kết quả được trỏ trực tiếp đến `outputs/`:

- **Datasets:** Các băng phổ GeoTIFF đã xử lý tách bạch cho (ASC & DESC), cùng với file CSV thống kê. `d:\tinhtuc_insar_project\outputs\reports\s1_2025_audit.csv`
- **Bản đồ:** Kịch bản tính lũ và Hình vẽ Chart đính kèm.
- **Time Series Chart:** `outputs/figures/s1_timeline_2025.png` và `outputs/figures/rain_timeline_2025.png`
- **Báo cáo chuyên sâu đánh giá ngưỡng chịu đựng:** So sánh tổng thể lượng mưa vào đỉnh điểm để tính toán ngập lũ.

## 7. Yêu cầu Kỹ thuật và Khả năng Nâng cấp

Dự án hiện tại được triển khai bằng **Python kết hợp GEE API**.

- **Modular & Clean:** Mã nguồn được tổ chức theo cấu trúc module (Tham khảo script mẫu `gee_scripts/flood_analysis_2025.py`).
- **Nâng cấp Forecast (Tùy chọn tương lai):** Gắn module dự báo ngập dựa trên LSTM mô phỏng dòng chảy `(Rainfall + DEM Flow Accumulation -> Nước ngập khai trường)` hoặc `GPM` hydrology models sinh ra cảnh báo lũ quét sớm 48 giờ.
