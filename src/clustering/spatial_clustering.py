"""
src/clustering/spatial_clustering.py
=====================================
Phân cụm không gian để xác định Moving Area Clusters (MACs).
Phương pháp: Festa et al. (2022) — điều chỉnh cho Tĩnh Túc.
"""

import numpy as np
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class MovingAreaCluster:
    """
    Đại diện một Moving Area Cluster (MAC).
    Tương đương polygon trong cơ sở dữ liệu GIS.
    """
    mac_id: int
    orbit: str                          # 'asc' hoặc 'desc'
    pixel_indices: List[Tuple[int,int]] # (row, col) các pixel thành viên
    area_km2: float = 0.0
    mean_velocity_mm_yr: float = 0.0
    mean_coherence: float = 0.0
    mean_vv_mm_yr: float = 0.0          # Thành phần thẳng đứng
    mean_vh_mm_yr: float = 0.0          # Thành phần nằm ngang E-W
    kvh: float = 0.0                    # |VV|/|VH|
    mean_slope_deg: float = 0.0
    mean_elevation_m: float = 0.0
    centroid_lon: float = 0.0
    centroid_lat: float = 0.0
    classification: str = "unclassified"
    confidence: int = 0                 # 1 = thấp, 2 = trung bình
    deformation_type: str = ""          # landslide / mine_subsidence / mixed
    overlapping_inventories: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pixel_indices"] = len(self.pixel_indices)  # Chỉ lưu số lượng
        return d


class SpatialClusterer:
    """
    Phân cụm không gian các điểm đo biến dạng thành MACs.

    Biến:
        vel_thresh (float): Ngưỡng vận tốc (mm/năm) để xác định pixel hoạt động.
        buffer_px (int): Bán kính buffer (pixel) để kết nối các điểm lân cận.
        min_size (int): Số pixel tối thiểu để tạo thành một cluster.
        pixel_m (float): Kích thước pixel (mét).
        pixel_km2 (float): Diện tích pixel (km²).
    """

    def __init__(self,
                 velocity_threshold_cm_yr: float = 1.0,
                 buffer_radius_px: int = 2,
                 min_cluster_size: int = 3,
                 pixel_size_m: float = 80.0):
        """
        Parameters
        ----------
        velocity_threshold_cm_yr : ngưỡng vận tốc (±1 cm/yr = ±10 mm/yr)
        buffer_radius_px         : bán kính buffer tính bằng pixel
        min_cluster_size         : số pixel tối thiểu trong một cluster
        pixel_size_m             : kích thước pixel (m)
        """
        self.vel_thresh = velocity_threshold_cm_yr * 10   # → mm/yr
        self.buffer_px = buffer_radius_px
        self.min_size = min_cluster_size
        self.pixel_m = pixel_size_m
        self.pixel_km2 = (pixel_size_m / 1000) ** 2

    def cluster(self,
                velocity: np.ndarray,
                coherence: Optional[np.ndarray] = None,
                orbit: str = "asc") -> List[MovingAreaCluster]:
        """
        Thực hiện phân cụm không gian.

        Parameters
        ----------
        velocity  : np.ndarray (H, W) — vận tốc LOS (mm/yr)
        coherence : np.ndarray (H, W) — coherence (0–1), tùy chọn
        orbit     : 'asc' hoặc 'desc'

        Returns
        -------
        List[MovingAreaCluster]
        """
        H, W = velocity.shape
        if coherence is None:
            coherence = np.ones_like(velocity)  # Giả định coherence = 1 nếu không có

        # Bước 1: Xác định active pixels (|v| > ngưỡng)
        # Ngưỡng ±1 cm/yr ≈ 3σ noise — theo Festa et al. (2022)
        active = np.abs(velocity) >= self.vel_thresh
        active &= np.isfinite(velocity)  # Loại NaN (no-data)
        n_active = np.sum(active)
        logger.info(f"Active pixels (|v| ≥ {self.vel_thresh:.0f} mm/yr): "
                    f"{n_active}/{H*W} ({100*n_active/(H*W):.1f}%)")

        # Bước 2: Giãn nở (dilation) — kết nối các điểm gần nhau
        # Buffer radius 2px ≈ 160m → tương đương độ phân giải GIS
        dilated = self._dilate(active, radius=self.buffer_px)

        # Bước 3: Gán nhãn connected components (BFS flood-fill)
        labels = self._connected_components(dilated)

        # Bước 4: Lọc cluster nhỏ + tính thống kê cho từng MAC
        macs = self._build_macs(labels, velocity, coherence, orbit)

        logger.info(f"Spatial clustering: {len(macs)} MACs found "
                    f"(min size = {self.min_size} pixels)")
        return macs

    def _dilate(self, mask: np.ndarray, radius: int) -> np.ndarray:
        """Giãn nở binary mask với structuring element hình vuông."""
        result = mask.copy()  # Bắt đầu từ mask gốc
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                if dr == 0 and dc == 0:
                    continue  # Bỏ qua vị trí gốc (không dịch chuyển)
                # Shift mask theo (dr, dc) và OR vào kết quả: pixel lân cận được gộp vào
                shifted = np.roll(np.roll(mask, dr, axis=0), dc, axis=1)
                result |= shifted
        return result

    def _connected_components(self, mask: np.ndarray) -> np.ndarray:
        """BFS labeling để tìm connected components."""
        H, W = mask.shape
        labels = np.zeros((H, W), dtype=np.int32)  # 0 = chưa gán nhãn
        current_label = 0
        # 8-connectivity: kết nối cả pixel chéo góc (quan trọng cho sạt lở lưu vực dọc)
        directions = [(-1,0),(1,0),(0,-1),(0,1),
                      (-1,-1),(-1,1),(1,-1),(1,1)]

        for r in range(H):
            for c in range(W):
                # Chỉ xử lý pixel chưa được gán nhãn nằm trong mask
                if mask[r, c] and labels[r, c] == 0:
                    current_label += 1  # Nhãn mới cho cluster mới
                    queue = [(r, c)]
                    labels[r, c] = current_label
                    while queue:
                        cr, cc = queue.pop(0)  # Lấy phần tử đầu hàng (BFS)
                        for dr, dc in directions:
                            nr, nc = cr + dr, cc + dc
                            if (0 <= nr < H and 0 <= nc < W
                                    and mask[nr, nc]
                                    and labels[nr, nc] == 0):
                                labels[nr, nc] = current_label  # Gán nhãn pixel lân cận
                                queue.append((nr, nc))

        return labels  # Mảng nhãn: giá trị 1..N là các cluster khác nhau

    def _build_macs(self,
                    labels: np.ndarray,
                    velocity: np.ndarray,
                    coherence: np.ndarray,
                    orbit: str) -> List[MovingAreaCluster]:
        """Xây dựng MAC objects từ labeled regions."""
        # np.unique bao gồm cả 0 (background), lọc chỉ lấy nhãn > 0
        unique_labels = np.unique(labels)
        unique_labels = unique_labels[unique_labels > 0]
        macs = []

        for mac_id, lbl in enumerate(unique_labels, start=1):
            # Boolean mask cho từng cluster
            pixel_mask = labels == lbl
            # Chuyển (row_array, col_array) → list của (row, col) tuples
            pixels = list(zip(*np.where(pixel_mask)))

            # Lọc bỏ cluster quá nhỏ (nhiễu không gian)
            if len(pixels) < self.min_size:
                continue

            # Trích xuất vận tốc và coherence tại các pixel của cluster
            vel_vals = velocity[pixel_mask]
            coh_vals = coherence[pixel_mask]

            # Tạo MovingAreaCluster với thống kê cơ bản
            # area_km2: số pixel × diện tích mỗi pixel (phụ thuộc vào độ phân giải)
            mac = MovingAreaCluster(
                mac_id=mac_id,
                orbit=orbit,
                pixel_indices=pixels,
                area_km2=len(pixels) * self.pixel_km2,
                mean_velocity_mm_yr=float(np.nanmean(vel_vals)),
                mean_coherence=float(np.nanmean(coh_vals)),
            )
            macs.append(mac)

        return macs

    def enrich_with_decomposition(self,
                                   macs: List[MovingAreaCluster],
                                   vv: np.ndarray,
                                   vh: np.ndarray,
                                   slope: np.ndarray,
                                   dem: np.ndarray) -> List[MovingAreaCluster]:
        """
        Bổ sung thông tin VV, VH, KVH, slope, elevation cho các MAC.
        Cần thiết cho bước phân loại.
        """
        for mac in macs:
            if not mac.pixel_indices:
                continue
            # Tách chỉ số hàng và cột để lấy giá trị mảng
            rows = [p[0] for p in mac.pixel_indices]
            cols = [p[1] for p in mac.pixel_indices]

            # VV: thành phần thẳng đứng; trung bình toàn cluster
            mac.mean_vv_mm_yr = float(np.nanmean(vv[rows, cols]))
            # VH: thành phần nằm ngang E-W; dùng giá trị tuyệt đối
            mac.mean_vh_mm_yr = float(np.nanmean(np.abs(vh[rows, cols])))
            # KVH = |VV| / |VH|: tỷ số phân biệt lún (KVH>1) vs trượt (KVH<1)
            # eps tránh chia cho 0 khi VH = 0
            eps = 1e-6
            mac.kvh = abs(mac.mean_vv_mm_yr) / (abs(mac.mean_vh_mm_yr) + eps)
            # Độ dốc và độ cao trung bình → dùng trong cây phân loại
            mac.mean_slope_deg = float(np.nanmean(slope[rows, cols]))
            mac.mean_elevation_m = float(np.nanmean(dem[rows, cols]))
            # Centroid: trọng tâm pixel (dùng cho hiển thị và ghép Asc/Desc)
            mac.centroid_lat = float(np.mean(rows))
            mac.centroid_lon = float(np.mean(cols))

        logger.debug(f"Enriched {len(macs)} MACs with decomposition data")
        return macs

    def merge_asc_desc(self,
                        macs_asc: List[MovingAreaCluster],
                        macs_desc: List[MovingAreaCluster],
                        overlap_threshold: float = 0.30
                        ) -> List[Dict]:
        """
        Ghép MACs từ ascending và descending dựa trên chồng lấp không gian.
        Trả về danh sách MAC đã ghép với thông tin từ cả 2 quỹ đạo.
        """
        merged = []
        used_desc = set()  # Theo dõi MAC desc đã ghép để không dùng lại

        for mac_a in macs_asc:
            set_a = set(mac_a.pixel_indices)  # Tập pixel của MAC ascending
            best_overlap = 0.0
            best_desc = None

            # So sánh từng MAC descending chưa được ghép
            for i, mac_d in enumerate(macs_desc):
                if i in used_desc:
                    continue  # Bỏ qua MAC desc đã ghép
                set_d = set(mac_d.pixel_indices)
                if not set_a or not set_d:
                    continue
                # Tỷ lệ chồng lấp Jaccard biến thể: |A∩D| / min(|A|,|D|)
                # Dùng min thay vì union để không phạt MAC lớn hơn
                overlap = len(set_a & set_d) / min(len(set_a), len(set_d))
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_desc_idx = i
                    best_desc = mac_d

            if best_desc is not None and best_overlap >= overlap_threshold:
                # Ghép thành công: MAC có đủ cả ascending và descending
                # → dùng diện tích lớn hơn (conservative estimate)
                merged.append({
                    "mac_id": mac_a.mac_id,
                    "area_km2": max(mac_a.area_km2, best_desc.area_km2),
                    "vel_asc_mm_yr": mac_a.mean_velocity_mm_yr,   # LOS Asc (mm/yr)
                    "vel_desc_mm_yr": best_desc.mean_velocity_mm_yr,  # LOS Desc (mm/yr)
                    "mean_vv": mac_a.mean_vv_mm_yr,    # Thẳng đứng từ 2D decomp
                    "mean_vh": mac_a.mean_vh_mm_yr,    # Nằm ngang từ 2D decomp
                    "kvh": mac_a.kvh,                  # Tỷ số lún/trượt
                    "slope_deg": mac_a.mean_slope_deg,
                    "elevation_m": mac_a.mean_elevation_m,
                    "spatial_overlap": best_overlap,
                    "has_both_orbits": True,  # Flag: đủ dữ liệu cho phân loại đầy đủ
                    "classification": "unclassified",
                })
                used_desc.add(best_desc_idx)
            else:
                # MAC chỉ có một quỹ đạo → phân loại sẽ ít chắc chắn hơn
                merged.append({
                    "mac_id": mac_a.mac_id,
                    "area_km2": mac_a.area_km2,
                    "vel_asc_mm_yr": mac_a.mean_velocity_mm_yr,
                    "vel_desc_mm_yr": None,
                    "mean_vv": mac_a.mean_vv_mm_yr,
                    "mean_vh": mac_a.mean_vh_mm_yr,
                    "kvh": mac_a.kvh,
                    "slope_deg": mac_a.mean_slope_deg,
                    "elevation_m": mac_a.mean_elevation_m,
                    "pixel_indices": mac_a.pixel_indices,  # Lưu list pixel
                    "has_both_orbits": False,
                    "spatial_overlap": 0.0,
                    "classification": "unclassified",
                })

        logger.info(f"Merged MACs: {len(merged)} total "
                    f"({sum(1 for m in merged if m['has_both_orbits'])} with both orbits)")
        return merged
