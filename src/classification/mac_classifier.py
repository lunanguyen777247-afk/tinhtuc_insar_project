"""
src/classification/mac_classifier.py
======================================
Phân loại nguyên nhân biến dạng cho Moving Area Clusters.
Dựa trên cây quyết định từ Festa et al. (2022),
bổ sung lớp "mine_subsidence" đặc thù cho Tĩnh Túc.
"""

import numpy as np
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── 11 lớp phân loại (mở rộng từ Festa et al. 2022) ───
CLASSES = {
    # Dựa trên lớp phụ trợ (confidence = 2)
    "landslide":              {"confidence": 2, "color": "#E74C3C"},
    "earthquake_deformation": {"confidence": 2, "color": "#8E44AD"},
    "volcanic":               {"confidence": 2, "color": "#E67E22"},
    "mine_subsidence":        {"confidence": 2, "color": "#2C3E50"},   # Thêm cho Tĩnh Túc
    "dump_site":              {"confidence": 2, "color": "#795548"},
    "construction_site":      {"confidence": 2, "color": "#607D8B"},
    # Dựa trên KVH + slope (confidence = 1)
    "potential_landslide":    {"confidence": 1, "color": "#F39C12"},
    "potential_subsidence":   {"confidence": 1, "color": "#3498DB"},
    "potential_uplift":       {"confidence": 1, "color": "#27AE60"},
    "mixed_deformation":      {"confidence": 1, "color": "#9B59B6"},   # Thêm cho khu vực mỏ
    "unclassified":           {"confidence": 0, "color": "#95A5A6"},
}


class MACClassifier:
    """
    Phân loại MAC theo cây quyết định phân cấp:
    1. Đối chiếu với lớp phụ trợ sẵn có
    2. Dùng KVH + slope nếu thiếu lớp phụ trợ
    3. Phát hiện lún mỏ đặc thù cho Tĩnh Túc

    Biến:
        overlap_thresh (float): Ngưỡng tỷ lệ chồng lấp để xác định trùng inventory.
        slope_thresh (float): Ngưỡng độ dốc để phân biệt lún/trượt.
        kvh_thresh (float): Ngưỡng tỷ số KVH để phân biệt lún/trượt.
    """

    def __init__(self,
                 overlap_threshold_pct: float = 50.0,
                 slope_threshold_deg: float = 5.0,
                 kvh_threshold: float = 1.0):
        self.overlap_thresh = overlap_threshold_pct / 100.0
        self.slope_thresh = slope_threshold_deg
        self.kvh_thresh = kvh_threshold

    def classify(self,
                 macs: List[Dict],
                 ancillary: Optional[Dict] = None) -> List[Dict]:
        """
        Phân loại toàn bộ danh sách MAC.

        Parameters
        ----------
        macs      : List[Dict] — output từ SpatialClusterer.merge_asc_desc()
        ancillary : dict với các lớp phụ trợ (tùy chọn):
                    {
                        "landslide_inventory": set of pixel tuples,
                        "mine_areas": set of pixel tuples,
                        "earthquake_areas": set of pixel tuples,
                    }

        Returns
        -------
        List[Dict] — MACs đã phân loại (field 'classification' được cập nhật)
        """
        if ancillary is None:
            ancillary = {}

        results = []
        class_counts = {k: 0 for k in CLASSES}

        for mac in macs:
            classified_mac = self._classify_single(mac, ancillary)
            results.append(classified_mac)
            cls = classified_mac.get("classification", "unclassified")
            class_counts[cls] = class_counts.get(cls, 0) + 1

        self._log_summary(class_counts, len(results))
        return results

    def _classify_single(self, mac: Dict, ancillary: Dict) -> Dict:
        """Phân loại một MAC theo thứ tự ưu tiên."""
        mac = mac.copy()
        pixel_set = set(mac.get("pixel_indices", []))

        # ── Ưu tiên 1: Đối chiếu với kiểm kê sạt lở ──
        if "landslide_inventory" in ancillary:
            overlap = self._compute_overlap(pixel_set,
                                            ancillary["landslide_inventory"],
                                            mac.get("area_km2", 1))
            if overlap >= self.overlap_thresh:
                mac["classification"] = "landslide"
                mac["confidence"] = 2
                mac["spatial_overlap_landslide"] = overlap
                mac["overlapping_inventories"] = ["landslide_inventory"]
                return mac

        # ── Ưu tiên 2: Đối chiếu với bản đồ khu mỏ (đặc thù Tĩnh Túc) ──
        if "mine_areas" in ancillary:
            overlap = self._compute_overlap(pixel_set,
                                            ancillary["mine_areas"],
                                            mac.get("area_km2", 1))
            if overlap >= self.overlap_thresh:
                # Phân biệt lún mỏ thuần túy vs hỗn hợp
                slope = mac.get("slope_deg", 0) or mac.get("mean_slope_deg", 0)
                kvh = mac.get("kvh", 0)
                if slope < self.slope_thresh and kvh > self.kvh_thresh:
                    mac["classification"] = "mine_subsidence"
                else:
                    mac["classification"] = "mixed_deformation"
                mac["confidence"] = 2
                mac["overlapping_inventories"] = ["mine_areas"]
                return mac

        # ── Ưu tiên 3: Đối chiếu với vùng động đất ──
        if "earthquake_areas" in ancillary:
            overlap = self._compute_overlap(pixel_set,
                                            ancillary["earthquake_areas"],
                                            mac.get("area_km2", 1))
            if overlap >= self.overlap_thresh:
                mac["classification"] = "earthquake_deformation"
                mac["confidence"] = 2
                return mac

        # ── Ưu tiên 4: Không có lớp phụ trợ → dùng KVH + slope ──
        if not mac.get("has_both_orbits", True):
            mac["classification"] = "unclassified"
            mac["confidence"] = 0
            return mac

        kvh = mac.get("kvh", 1.0)
        slope = mac.get("slope_deg", 0) or mac.get("mean_slope_deg", 0)
        vv = mac.get("mean_vv", 0) or mac.get("mean_vv_mm_yr", 0)

        if kvh < self.kvh_thresh and slope >= self.slope_thresh:
            mac["classification"] = "potential_landslide"
            mac["confidence"] = 1
        elif kvh > self.kvh_thresh and vv < 0 and slope < self.slope_thresh:
            mac["classification"] = "potential_subsidence"
            mac["confidence"] = 1
        elif kvh > self.kvh_thresh and vv > 0:
            mac["classification"] = "potential_uplift"
            mac["confidence"] = 1
        else:
            mac["classification"] = "unclassified"
            mac["confidence"] = 0

        return mac

    def _compute_overlap(
                          self,
                          mac_pixels: set,
                          inventory_pixels: set,
                          mac_area_km2: float) -> float:
        """
        Tính tỷ lệ chồng lấp giữa MAC và lớp phụ trợ.
        overlap = |intersection| / |MAC| (Festa et al., 2022)
        """
        # Nếu một trong hai tập rỗng: không thể tính → trả về 0
        if not mac_pixels or not inventory_pixels:
            return 0.0
        # Đếm pixel chảy qua cả hai tập (set intersection)
        intersection = len(mac_pixels & inventory_pixels)
        # Chia cho kích thước MAC (không phải union) theo Festa et al.
        return intersection / len(mac_pixels)

    def _log_summary(self, counts: Dict[str, int], total: int) -> None:
        """In tóm tắt kết quả phân loại."""
        logger.info(f"Classification summary ({total} MACs):")
        for cls, count in sorted(counts.items(), key=lambda x: -x[1]):
            if count > 0:
                pct = 100 * count / max(total, 1)
                conf = CLASSES.get(cls, {}).get("confidence", 0)
                logger.info(f"  {cls:25s}: {count:4d} ({pct:5.1f}%)  "
                             f"[confidence={conf}]")

    def compute_risk_score(self, mac: Dict) -> float:
        """
        Tính điểm rủi ro (0–10) cho MAC dựa trên:
        - Tốc độ biến dạng
        - Loại biến dạng
        - Diện tích
        """
        vel = abs(mac.get("mean_velocity_mm_yr", 0))
        cls = mac.get("classification", "unclassified")
        area = mac.get("area_km2", 0)

        # Điểm theo tốc độ (Hungr et al., 2014 velocity scale)
        # Ngưỡng: 10 mm/yr (chậm), 20 (trung bình), 50 (nhanh)
        if vel < 10:
            vel_score = 2.0        # Chậm: ít nguy hiểm
        elif vel < 20:
            vel_score = 4.0        # Trung bình
        elif vel < 50:
            vel_score = 6.0        # Nhanh
        else:
            vel_score = 9.0        # Rất nhanh: cần giám sát khẩn cấp

        # Điểm theo loại biến dạng
        # landslide + mixed: nguy hiểm nhất vì có thể đột ngột gia tốc
        type_scores = {
            "landslide": 3.0, "potential_landslide": 2.0,
            "mine_subsidence": 2.5, "mixed_deformation": 3.0,
            "earthquake_deformation": 2.0,
            "potential_subsidence": 1.5, "potential_uplift": 0.5,
            "unclassified": 1.0,
        }
        type_score = type_scores.get(cls, 1.0)

        # Điểm theo diện tích (log scale tính theo km²)
        # log tớp tỼ các MAC quá lớn để tránh điểm bị chi phối bởi diện tích
        area_score = min(np.log10(max(area, 0.001) + 1) * 3, 3.0)

        # Tổng hợp trọng số: 0.5 tốc độ + 0.3 loại + 0.2 diện tích
        # Tốc độ được ưu tiên nhất vì đo lường trực tiếp mức độ hoạt động
        total = (vel_score * 0.5 + type_score * 0.3 + area_score * 0.2)
        return round(min(total, 10.0), 2)  # Giới hạn tối đa 10.0


def generate_synthetic_ancillary(H: int, W: int) -> Dict:
    """
    Tạo lớp phụ trợ tổng hợp để test/demo.
    Mô phỏng: khu mỏ ở góc dưới phải, sạt lở ở góc trên trái.
    """
    # Sạt lở: góc trên trái (0–30% H, 0–30% W)
    landslide_pixels = set()
    for r in range(0, int(H * 0.35)):
        for c in range(0, int(W * 0.35)):
            landslide_pixels.add((r, c))

    # Khu mỏ: góc dưới phải (60–100% H, 60–100% W)
    mine_pixels = set()
    for r in range(int(H * 0.55), H):
        for c in range(int(W * 0.55), W):
            mine_pixels.add((r, c))

    return {
        "landslide_inventory": landslide_pixels,
        "mine_areas": mine_pixels,
    }
