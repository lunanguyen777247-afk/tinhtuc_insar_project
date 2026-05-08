"""
web_app.py
==========
Flask web app — Cổng Giám Sát Địa Chất Tĩnh Túc
Phục vụ dữ liệu pipeline InSAR thực tế cho cộng đồng.
"""

import os
import re
import json
import glob
import subprocess
from datetime import datetime
from pathlib import Path

import math
import numpy as np
from flask import Flask, render_template, send_file, abort, Response
from flask import json as flask_json

# ── Cấu hình ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUTS_DIR = ROOT / "outputs"
FIGURES_DIR = OUTPUTS_DIR / "figures"
REPORTS_DIR = OUTPUTS_DIR / "reports"

# Nhập thông tin hotspot từ cấu hình trung tâm
from config.settings import HOTSPOTS, AOI

app = Flask(__name__)


# ── Tiện ích đọc dữ liệu pipeline ─────────────────────────────────────────────

def _load_npy(name: str):
    """Nạp mảng numpy từ thư mục đã xử lý, trả None nếu không tìm thấy."""
    p = PROCESSED_DIR / f"{name}.npy"
    if p.exists():
        return np.load(str(p))
    return None


def _latest_report() -> dict:
    """Phân tích báo cáo tóm tắt pipeline mới nhất, trả dict kết quả."""
    reports = sorted(REPORTS_DIR.glob("summary_*.txt"))
    if not reports:
        return {}
    text = reports[-1].read_text(encoding="utf-8")
    result = {"report_date": reports[-1].stem.replace("summary_", "")}

    m = re.search(r"Tổng số MACs phát hiện:\s*(\d+)", text)
    result["mac_count"] = int(m.group(1)) if m else 0

    m = re.search(r"Cảnh báo gia tốc:\s*(\d+)", text)
    result["alert_count"] = int(m.group(1)) if m else 0

    # Đọc E_max, V_max cho từng hotspot
    hotspot_data = {}
    for pid in ["P1", "P2", "P3"]:
        pat = rf"{pid} \([^)]+\)\s*:\s*E_max=([\d.nan]+)mm,\s*V_max=([\d.nan]+)mm"
        m = re.search(pat, text)
        if m:
            def _safe(v):
                try: return float(v)
                except: return None
            hotspot_data[pid] = {"e_max_mm": _safe(m.group(1)), "v_max_mm": _safe(m.group(2))}
    result["hotspots"] = hotspot_data
    return result


def _timeseries_at_hotspot(pid: str) -> list:
    """Trích chuỗi thời gian dịch chuyển tại vị trí hotspot pid."""
    displacement = _load_npy("displacement")   # (T, H, W)
    lat_grid = _load_npy("lat_grid")            # (H, W)
    lon_grid = _load_npy("lon_grid")            # (H, W)
    time_days = _load_npy("time_days")          # (T,)

    if displacement is None or lat_grid is None or lon_grid is None:
        return []

    hs = HOTSPOTS.get(pid, {})
    target_lat, target_lon = hs.get("lat", AOI["center_lat"]), hs.get("lon", AOI["center_lon"])

    dist = np.sqrt((lat_grid - target_lat) ** 2 + (lon_grid - target_lon) ** 2)
    row, col = np.unravel_index(np.argmin(dist), dist.shape)

    ts = displacement[:, row, col].tolist()

    if time_days is not None:
        t0 = time_days[0]
        dates = [(datetime(2020, 6, 1).toordinal() + int(d - t0)) for d in time_days]
        dates_str = [datetime.fromordinal(d).strftime("%Y-%m-%d") for d in dates]
    else:
        n = len(ts)
        dates_str = [f"T{i}" for i in range(n)]

    return [{"date": d, "value": round(float(v), 2)} for d, v in zip(dates_str, ts)]


def _velocity_stats() -> dict:
    """Thống kê vận tốc từ dữ liệu đã xử lý."""
    vel = _load_npy("velocity_true")
    if vel is None:
        return {"min": -9.4, "max": 11.1, "mean": 0.0}
    valid = vel[np.isfinite(vel)]
    return {
        "min": round(float(valid.min()), 1),
        "max": round(float(valid.max()), 1),
        "mean": round(float(valid.mean()), 2),
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def api_data():
    """Endpoint JSON tổng hợp — cung cấp mọi dữ liệu cho dashboard."""
    report = _latest_report()
    vel_stats = _velocity_stats()

    # Chuỗi thời gian cho từng hotspot
    timeseries = {}
    for pid in ["P1", "P2", "P3"]:
        timeseries[pid] = _timeseries_at_hotspot(pid)

    # Thông tin hotspot kết hợp config + kết quả pipeline
    hotspot_list = []
    risk_labels = {
        "mixed": {"vi": "Hỗn hợp", "level": "medium", "color": "orange"},
        "landslide": {"vi": "Trượt lở", "level": "high", "color": "red"},
        "mine_subsidence": {"vi": "Lún mỏ", "level": "medium", "color": "yellow"},
    }
    for pid, cfg in HOTSPOTS.items():
        rtype = cfg.get("risk_type", "mixed")
        rl = risk_labels.get(rtype, {"vi": rtype, "level": "medium", "color": "orange"})
        hs_report = report.get("hotspots", {}).get(pid, {})
        hotspot_list.append({
            "id": pid,
            "lat": cfg["lat"],
            "lon": cfg["lon"],
            "description": cfg["description"],
            "risk_type": rtype,
            "risk_label_vi": rl["vi"],
            "risk_level": rl["level"],
            "risk_color": rl["color"],
            "e_max_mm": hs_report.get("e_max_mm"),
            "v_max_mm": hs_report.get("v_max_mm"),
        })

    # Danh sách báo cáo có thể tải xuống
    downloads = []
    for fname, label, desc in [
        ("velocity_asc.png", "Bản đồ Vận tốc", "Bản đồ lún/trồi bề mặt từ Sentinel-1 quỹ đạo lên"),
        ("timeseries_4d.png", "Chuỗi thời gian 4D", "Dịch chuyển hàng ngày từ bộ lọc Kalman 4D"),
        ("strain_invariants.png", "Biến dạng Tensor", "Tensor biến dạng và phân tích kinematics"),
        ("mac_classification.png", "Phân loại MAC", "Vùng dịch chuyển đồng nhất (MAC)"),
    ]:
        path = FIGURES_DIR / fname
        if path.exists():
            downloads.append({
                "filename": fname,
                "label": label,
                "description": desc,
                "size_kb": round(path.stat().st_size / 1024, 1),
                "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
            })

    # Kiểm tra pipeline đang chạy không
    pipeline_running = False
    try:
        result = subprocess.run(["pgrep", "-f", "run_pipeline.py"], capture_output=True)
        pipeline_running = result.returncode == 0
    except Exception:
        pass

    payload = {
        "generated_at": datetime.now().isoformat(),
        "pipeline_running": pipeline_running,
        "aoi": AOI,
        "summary": {
            "mac_count": report.get("mac_count", 0),
            "alert_count": report.get("alert_count", 0),
            "daily_records": 1645,
            "monitoring_points": 3,
            "velocity_stats": vel_stats,
            "report_date": report.get("report_date", ""),
        },
        "hotspots": hotspot_list,
        "timeseries": timeseries,
        "downloads": downloads,
    }
    def _sanitize(obj):
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(i) for i in obj]
        return obj

    return Response(
        json.dumps(_sanitize(payload), ensure_ascii=False),
        mimetype="application/json",
    )


@app.route("/api/download/<filename>")
def download_file(filename: str):
    """Phục vụ file báo cáo/hình cho tải xuống."""
    # Chỉ cho phép file trong outputs/figures/
    allowed_exts = {".png", ".txt", ".csv", ".md"}
    path = FIGURES_DIR / filename
    if not path.exists() or path.suffix not in allowed_exts:
        # Thử trong reports/
        path = REPORTS_DIR / filename
    if not path.exists() or path.suffix not in allowed_exts:
        abort(404)
    return send_file(str(path), as_attachment=True)


@app.route("/api/run-pipeline", methods=["POST"])
def run_pipeline():
    """Kích hoạt pipeline chạy lại trong nền (non-blocking)."""
    try:
        subprocess.Popen(
            ["python3", "run_pipeline.py"],
            cwd=str(ROOT),
            stdout=open(ROOT / "logs" / "web_trigger.log", "a"),
            stderr=subprocess.STDOUT,
        )
        return jsonify({"status": "started", "message": "Pipeline đã được khởi động."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
