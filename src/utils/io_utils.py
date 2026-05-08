"""
src/utils/io_utils.py
=====================
Tiện ích đọc/ghi dữ liệu SAR, DEM, khí tượng.
"""

import numpy as np
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, List, Optional, Dict

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 1. ĐỌC DỮ LIỆU INTERFEROGRAM
# ─────────────────────────────────────────────────────────────

def load_interferogram(filepath: Path) -> Tuple[np.ndarray, dict]:
    """
    Đọc interferogram từ file binary (định dạng GAMMA .flt hoặc .int).
    Trả về ma trận phase và metadata.

    Parameters
    ----------
    filepath : Path
        Đường dẫn đến file interferogram

    Returns
    -------
    phase : np.ndarray shape (rows, cols)
        Mảng pha đã unwrap (radian hoặc mm)
    meta : dict
        Metadata: width, lines, wavelength, dates, baselines
    """
    meta_file = filepath.with_suffix(".par")
    meta = _parse_gamma_par(meta_file) if meta_file.exists() else {}

    width = meta.get("range_samples", 500)
    lines = meta.get("azimuth_lines", 500)

    try:
        # GAMMA lưu float32 big-endian (»f4) theo mặc định
        data = np.fromfile(filepath, dtype=">f4")   # Big-endian float32 (GAMMA)
        if len(data) != width * lines:
            # Thử little-endian (một số phiên GAMMA mới hoặc thống kê hác)
            data = np.fromfile(filepath, dtype="<f4")
        phase = data.reshape(lines, width)
        logger.debug(f"Loaded interferogram: {filepath.name} ({lines}×{width})")
    except Exception as exc:
        # Không đọc được file thực → dùng dữ liệu tổng hợp để pipeline không sập
        logger.warning(f"Cannot load {filepath}: {exc}. Returning synthetic data.")
        phase = _synthetic_interferogram(lines, width)

    return phase, meta


def load_coherence(filepath: Path, shape: Tuple[int, int]) -> np.ndarray:
    """Đọc bản đồ coherence (0–1)."""
    try:
        data = np.fromfile(filepath, dtype=">f4")
        return data.reshape(shape).clip(0, 1)
    except Exception:
        logger.warning(f"Cannot load coherence {filepath}. Using ones.")
        return np.ones(shape, dtype=np.float32)


def load_dem(filepath: Path) -> Tuple[np.ndarray, dict]:
    """
    Đọc DEM (GeoTIFF hoặc binary).
    Trả về elevation array và geotransform dict.
    """
    try:
        # Thử đọc như binary float32
        data = np.fromfile(filepath, dtype="<f4")
        side = int(np.sqrt(len(data)))
        dem = data[:side * side].reshape(side, side)
        geo = {"dx": 30.0, "dy": 30.0, "origin_x": 105.85, "origin_y": 22.75}
        logger.info(f"Loaded DEM: {dem.shape}, range [{dem.min():.0f}, {dem.max():.0f}] m")
        return dem, geo
    except Exception as exc:
        logger.warning(f"DEM load failed: {exc}. Using synthetic terrain.")
        return _synthetic_dem(), {"dx": 30.0, "dy": 30.0}


def load_hydro_timeseries(csv_path: Path) -> Dict[str, np.ndarray]:
    """
    Đọc chuỗi thời gian khí tượng thủy văn từ CSV.
    Cột mong đợi: date, rainfall_mm, soil_moisture
    Trả về dict với arrays numpy.
    """
    import csv
    dates, rainfall, soil_moisture = [], [], []
    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                dates.append(datetime.strptime(row["date"], "%Y-%m-%d"))
                rainfall.append(float(row.get("rainfall_mm", 0.0)))
                soil_moisture.append(float(row.get("soil_moisture", 0.3)))
        logger.info(f"Loaded hydro data: {len(dates)} records from {csv_path.name}")
    except Exception as exc:
        # Không có file CSV thực → tạo dữ liệu tổng hợp với mùa mưa thực tế
        logger.warning(f"Cannot load hydro data: {exc}. Generating synthetic.")
        n = 365 * 5  # 5 năm dữ liệu (2019–2024)
        dates = [datetime(2019, 1, 1) + timedelta(days=i) for i in range(n)]
        rainfall = _synthetic_rainfall(n)           # Mùa mưa tháng 5–9
        soil_moisture = _synthetic_soil_moisture(rainfall)  # Phụ thuộc lượng mưa

    return {
        "dates": np.array(dates),
        "rainfall_mm": np.array(rainfall, dtype=np.float32),
        "soil_moisture": np.array(soil_moisture, dtype=np.float32),
    }


# ─────────────────────────────────────────────────────────────
# 2. GHI KẾT QUẢ
# ─────────────────────────────────────────────────────────────

def save_velocity_map(velocity: np.ndarray, filepath: Path,
                      metadata: Optional[dict] = None) -> None:
    """Lưu bản đồ vận tốc LOS (mm/yr) dạng binary float32."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    velocity.astype(np.float32).tofile(filepath)
    if metadata:
        _write_simple_header(filepath.with_suffix(".hdr"), metadata)
    logger.info(f"Saved velocity map: {filepath} {velocity.shape}")


def save_timeseries(ts: np.ndarray, dates: List[datetime],
                    filepath: Path) -> None:
    """Lưu chuỗi thời gian dịch chuyển dạng CSV."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        f.write("date,displacement_mm\n")
        for d, v in zip(dates, ts):
            f.write(f"{d.strftime('%Y-%m-%d')},{v:.4f}\n")
    logger.info(f"Saved time series: {filepath} ({len(dates)} epochs)")


def save_mac_database(macs: List[dict], filepath: Path) -> None:
    """Lưu cơ sở dữ liệu MAC phân loại dạng CSV."""
    import csv
    filepath.parent.mkdir(parents=True, exist_ok=True)
    if not macs:
        logger.warning("Empty MAC list, nothing to save.")
        return
    fields = list(macs[0].keys())
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(macs)
    logger.info(f"Saved {len(macs)} MACs to {filepath}")


def save_4d_movements(movements: Dict[str, np.ndarray],
                      dates: List[datetime],
                      filepath: Path) -> None:
    """
    Lưu kết quả 4D movements (East, North, Vertical theo ngày).
    Format: numpy .npz để dễ load lại.
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    date_strs = np.array([d.strftime("%Y-%m-%d") for d in dates])
    np.savez_compressed(
        filepath,
        east=movements["east"].astype(np.float32),
        north=movements["north"].astype(np.float32),
        vertical=movements["vertical"].astype(np.float32),
        dates=date_strs,
    )
    logger.info(f"Saved 4D movements: {filepath} ({len(dates)} epochs)")


# ─────────────────────────────────────────────────────────────
# 3. HÀM NỘI BỘ VÀ DỮ LIỆU TỔNG HỢP (CHO TEST/DEV)
# ─────────────────────────────────────────────────────────────

def _parse_gamma_par(par_file: Path) -> dict:
    """Đọc file tham số GAMMA (.par)."""
    meta = {}
    try:
        with open(par_file) as f:
            for line in f:
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip().split()[0]
        meta["range_samples"] = int(meta.get("range_samples", 500))
        meta["azimuth_lines"] = int(meta.get("azimuth_lines", 500))
    except Exception:
        pass
    return meta


def _write_simple_header(filepath: Path, meta: dict) -> None:
    with open(filepath, "w") as f:
        for k, v in meta.items():
            f.write(f"{k}: {v}\n")


def _synthetic_interferogram(rows: int = 300, cols: int = 300) -> np.ndarray:
    """Tạo interferogram tổng hợp để test."""
    rng = np.random.default_rng(42)
    x, y = np.meshgrid(np.linspace(0, 4 * np.pi, cols),
                       np.linspace(0, 4 * np.pi, rows))
    signal = 15.0 * np.sin(x / 3) * np.cos(y / 4)
    noise = rng.normal(0, 2.0, (rows, cols))
    return (signal + noise).astype(np.float32)


def _synthetic_dem(rows: int = 300, cols: int = 300) -> np.ndarray:
    """Tạo DEM tổng hợp địa hình núi."""
    rng = np.random.default_rng(0)
    x, y = np.meshgrid(np.linspace(0, 1, cols), np.linspace(0, 1, rows))
    base = 400 + 600 * np.exp(-((x - 0.5)**2 + (y - 0.4)**2) / 0.08)
    noise = rng.normal(0, 15.0, (rows, cols))
    return (base + noise).astype(np.float32)


def _synthetic_rainfall(n: int) -> List[float]:
    """Lượng mưa tổng hợp với mùa mưa tháng 5–9."""
    rng = np.random.default_rng(7)
    vals = []
    for i in range(n):
        month = ((i % 365) // 30 + 1)
        intensity = 8.0 if month in [5, 6, 7, 8, 9] else 1.5
        rain = rng.exponential(intensity) if rng.random() < 0.4 else 0.0
        vals.append(float(min(rain, 120.0)))
    return vals


def _synthetic_soil_moisture(rainfall: List[float]) -> List[float]:
    """Độ ẩm đất ước tính từ lượng mưa (model đơn giản)."""
    sm = [0.25]
    for r in rainfall[1:]:
        new_sm = sm[-1] * 0.95 + r / 300.0
        sm.append(float(np.clip(new_sm, 0.10, 0.60)))
    return sm
