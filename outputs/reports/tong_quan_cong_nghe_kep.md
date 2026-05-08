# 🛰️ KIẾN TRÚC CÔNG NGHỆ KÉP: GIÁM SÁT BIẾN DẠNG & KHOANH VÙNG NGẬP LỤT BẰNG SAR

## Khu vực: Mỏ Tĩnh Túc, Cao Bằng

---

> [!NOTE]
> Dự án này mang tính đột phá nhờ việc khai thác **hai thuộc tính vật lý khác nhau của cùng một sóng Radar (Sentinel-1)** để tạo ra hệ thống giám sát thảm họa khép kín.

### 🔬 Nguyên lý khai thác đa tầng

- **Pha (Phase):** Tính toán độ dời milimet để giám sát sụt lún, trượt lở (**Biến dạng**).
- **Biên độ (Amplitude/Backscatter):** Tính toán thay đổi mức độ phản xạ để khoanh vùng vũng nước (**Ngập lụt**).

---

## 🏗️ 1. HỆ THỐNG GIÁM SÁT BIẾN DẠNG BỀ MẶT MỎ (DEFORMATION)

*Hệ thống này phát hiện các vách đất, mái talus, hay hầm lò mỏ đang bị "trồi sụt" hoặc có nguy cơ sạt lở tốc độ cao.*

### A. Công nghệ Interferometric SAR (InSAR) & P-SBAS

- **Nguyên lý:** Khi vệ tinh chiếu cùng một điểm vào hai thời điểm khác nhau, sự phồng/lún của bề mặt đất làm thay đổi khoảng cách vệ tinh bay, sinh ra sự **"lệch pha" (Phase Shift)**.
- **P-SBAS (Pixel-based Small Baseline Subset):**
  - Thuật toán kết mạng các ảnh sát ngày nhau (khoảng baseline ngắn) giúp khử nhiễu thực vật.
  - Giữ lại những pixel có hệ số kết dính (**Coherence**) > 0.20 bằng giải Least Squares.
- **Xóa màng Khí quyển:** Tự động tải bản đồ hơi nước **ERA5 (Zenith Wet Delay - ZWD)** từ GEE để bù trừ màng lỗi khí quyển (APS), đảm bảo độ chính xác cấp milimet.

### B. Lọc Động Học - Adaptive Kalman Filter 4D

- Kalman Filter chạy bộ vi phân vận tốc, gia tốc, khoảng cách theo từng mốc thời gian pixel độc lập.
- **Hệ số Thích ứng (Q):** Tự động tăng độ nhạy nếu phát hiện các đỉnh gia tốc bất thường đột ngột tại sườn dốc do tác động của mưa, tránh việc hàm dự báo bị "cạo phẳng" rủi ro.

### C. Cơ chế Máy Học - Transformer Hydromet (Deep Learning)

- Kiến trúc **Attention Transformer (PyTorch)** huấn luyện để hiểu mối quan hệ phi tuyến giữa **Lượng mưa (ERA5)** và **Độ ẩm đất (SMAP)**.
- Phân tích rủi ro biến dạng thực chứ không chỉ là sự nở trương mùa vụ do nước vào đất.

---

## 🌊 2. HỆ THỐNG KHOANH VÙNG NGẬP LỤT LÒNG MỎ (FLOOD DETECTION)

*Được kích hoạt để đánh giá thiệt hại khi nước từ suối Pia Oắc hoặc đập tràn phá vỡ ồ ạt xuống khai trường.*

### A. Phân tích Tán xạ ngược Radar (Log-Ratio ΔVV)

- **Nguyên lý Phản xạ Gương (Specular Reflection):**
  - Đất nhám/thực vật sẽ khuếch tán sóng radar dội về vệ tinh (tín hiệu sáng).
  - **Mặt nước phẳng** làm tia radar bật văng theo hướng khác $\rightarrow$ Vệ tinh không hứng được sóng, điểm ảnh bị tối đen.
- **Thuật toán Cắt Ngưỡng:** So sánh độ lệch $\Delta VV = VV_{post} - VV_{pre}$. Bất cứ điểm nào rớt điểm sáng > -3dB được coi là có nguy cơ ngập nước cao.

### B. Thuật toán Cắt ngưỡng Tự động (Otsu & Image Masking)

- **Otsu's Thresholding:** Tự động phân mảng đen trắng dựa trên Histogram, chẻ làm 2 nhóm: Lớp ngập nước và không ngập một cách khách quan.
- **Terrain Shadow Masking:** Sử dụng dữ liệu **DEM GLO-30** cắt bóng radar để tránh nhận diện nhầm các sườn núi dốc là mặt nước.

### C. Mô phỏng Dòng chảy Tích lũy (Flow Accumulation)

- Map địa hình **DEM** bằng công cụ vi phân bề mặt để tính độ dốc Slope/Aspect. Gộp lượng mưa thực vào phân tích dòng chảy tích lũy để dẫn tuyến từ Suối Pia Oắc trực diện về bờ khai trường.

---

## ⚙️ 3. KIẾN TRÚC IT VÀ DATA PIPELINE (END-TO-END)

| Lớp (Layer) | Chức năng | Công nghệ sử dụng |
| :--- | :--- | :--- |
| **Data Ingestion** | Xử lý dữ liệu vệ tinh song song | Google Earth Engine (GEE Python API) |
| **InSAR Core** | Tính toán cấu trúc InSAR | SNAP / MintPy Framework |
| **AI Module** | Dự đoán biến dạng phi tuyến | PyTorch Stack (Transformer) |
| **GIS Analysis** | Cắt trích ảnh và lọc Mask lũ | Rasterio / GeoPandas |

---

## 💡 KẾT LUẬN TỔNG THỂ

Đây là một **Hybrid Pipeline thông minh**. Nó cho phép tận dụng duy nhất một lượt bay của Sentinel-1 để giải toán hoàn chỉnh: Khi trời mưa lớn, module Biên độ khoanh ngay vùng ngập tĩnh, trong khi module Pha InSAR + AI sẽ báo động các chu vi xung quanh vùng ngập đó có dấu hiệu rung chấn/sụt lún do mất kết cấu dưới chân mỏ.

---
*Báo cáo Công nghệ Kép - Dự án Tĩnh Túc SAR 2026*
