"""
experiment_scenarios.md
=======================
Thiết kế kịch bản thực nghiệm (Experiment Scenario Design)
cho dự án phát hiện ngập lụt khu mỏ Tĩnh Túc

Mục đích:
  Xác định rõ các kịch bản phân tích khác nhau trước khi triển khai pipeline chính.
  Giúp kiểm chứng độ tin cậy của phương pháp từ nhiều góc độ.

Ngày tạo: 2026-04-24
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any


class ExperimentScenarioDesigner:
    """
    Thiết kế và quản lý các kịch bản thực nghiệm.
    """
    
    SCENARIOS = {
        "scenario_1": {
            "name": "Scenario 1: Single Time-Point Analysis (Before-After)",
            "description": """
Phân tích so sánh hai thời điểm: trước mưa lớn và sau mưa lớn.
Xác định vùng nước mới xuất hiện hoặc mở rộng.

Kỹ thuật:
  • Chọn ảnh tham chiếu (reference): trước mưa lớn (dry season)
  • Chọn ảnh ngày hiện tại: sau mưa (wet season)
  • Tính toán: Change Index = (VV_wet - VV_dry) / VV_dry
  • Thresholding: Pixels với Change Index < -0.1 → water pixels
  • Morphological filtering: loại bỏ noise nhỏ lẻ

Ưu điểm:
  ✓ Đơn giản, nhanh chóng
  ✓ Không cần chuỗi dài ảnh
  ✓ Phù hợp cảnh báo sớm (quick alert)

Nhược điểm:
  ✗ Không biết được xu hướng thay đổi
  ✗ Dễ bị ảnh hưởng bởi noise radar
  ✗ Phụ thuộc chất lượng ảnh tham chiếu

Dữ liệu đầu vào:
  • 1 ảnh ASCENDING (reference)
  • 1 ảnh ASCENDING (current) → hoặc DESCENDING
  • DEM (để correcting topography)

Đầu ra:
  • Water extent map (binary: water/non-water)
  • Change magnitude map
  • Accuracy: confusion matrix vs ground truth (nếu có)

Thời gian thực hiện: ~2-3 ngày (1 pair processing)
""",
            "processing_steps": [
                "1.1 Load reference SAR image (VV, VH polarity)",
                "1.2 Load current SAR image",
                "1.3 Radiometric calibration",
                "1.4 Speckle filtering (Lee filter)",
                "1.5 Calculate backscatter change index",
                "1.6 Water detection thresholding",
                "1.7 Morphological filtering",
                "1.8 Accuracy assessment",
            ],
            "primary_orbit": "ASCENDING",
            "alternate_orbit": "DESCENDING",
            "required_ancillary": ["DEM"],
            "output_products": [
                "water_extent_map.tif",
                "change_magnitude.tif",
                "accuracy_report.txt",
            ],
        },
        
        "scenario_2": {
            "name": "Scenario 2: Time Series Analysis (Continuous Monitoring)",
            "description": """
Phân tích chuỗi thời gian: theo dõi sự thay đổi liên tục mực nước.
Phát hiện xu hướng tích nước, dự báo thời điểm nguy hiểm.

Kỹ thuật:
  • Xử lý tất cả ảnh trong chu kỳ (VV time series)
  • Tính toán time series backscatter σ₀(t)
  • Lọc Kalman hoặc median filter để loại bỏ speckle
  • Detect change points bằng CUSUM hoặc Bayesian change point
  • Classify pixels: stable / increasing-water / fluctuating
  • Compute water extent time series

Ưu điểm:
  ✓ Phát hiện xu hướng dài hạn
  ✓ Robust against single-image noise
  ✓ Early warning capability (detect ramp-up)
  ✓ Estimate accumulation rate

Nhược điểm:
  ✗ Cần dữ liệu dài hạn (~1-2 năm)
  ✗ Xử lý phức tạp, tốn tài nguyên
  ✗ Yêu cầu lập mô hình temporal correlations

Dữ liệu đầu vào:
  • Chuỗi ảnh ASCENDING (24 tháng): ~600 ảnh
  • DEM, reference water mask
  • Auxiliary: rainfall data (ERA5 qua GEE)

Đầu ra:
  • Time series water extent: [N_pixels, T_months]
  • Change point detection map
  • Trend analysis: slope m(x,y) in mm/year
  • Time-varying water volume curve
  • Alert/alarm levels

Thời gian thực hiện: ~1-2 tuần (full processing + analysis)
""",
            "processing_steps": [
                "2.1 Load full Sentinel-1 time series (ASCENDING)",
                "2.2 Multi-temporal preprocessing",
                "2.3 Create backscatter time series σ₀(t, x, y)",
                "2.4 Temporal filtering (Kalman + spatial coherence)",
                "2.5 Change point detection (CUSUM)",
                "2.6 Per-pixel water classification",
                "2.7 Water extent time series generation",
                "2.8 Trend analysis & forecasting",
                "2.9 Comparison with rainfall data",
            ],
            "primary_orbit": "ASCENDING",
            "alternate_orbit": "DESCENDING (for cross-validation)",
            "required_ancillary": ["DEM", "Rainfall_ERA5"],
            "output_products": [
                "backscatter_timeseries.npy",
                "water_extent_timeseries.tif",
                "change_points.json",
                "trend_map.tif",
                "forecast_warning.txt",
            ],
        },
        
        "scenario_3": {
            "name": "Scenario 3: Ascending vs Descending Comparison",
            "description": """
Xử lý riêng biệt ASCENDING và DESCENDING, so sánh kết quả.
Kiểm tra độ ổn định phương pháp với các viewing angles khác nhau.

Kỹ thuật:
  • Process ASCENDING: generate water extent maps → WM_asc(t)
  • Process DESCENDING: generate water extent maps → WM_desc(t)
  • Reproject cả 2 lên UTM grid chung
  • Calculate agreement map: agreement_ratio(x,y) = Intersection / Union
  • Generate confusion matrix (co-registration errors)
  • Compute IOU (Intersection over Union) time series

Ưu điểm:
  ✓ Validates consistency across viewing geometries
  ✓ Identifies viewing-angle artifacts
  ✓ Robustness assessment
  ✓ Enables 3D motion retrieval (if combined)

Nhược điểm:
  ✗ Double the processing load
  ✗ Co-registration challenges
  ✗ Different spatial resolutions (near range vs far range)

Dữ liệu đầu vào:
  • ASCENDING subset: 1300 ảnh (24 months)
  • DESCENDING subset: 1250 ảnh (24 months)
  • DEM (UTM reprojected)

Đầu ra:
  • Water maps ASCENDING: [T_months, H, W]
  • Water maps DESCENDING: [T_months, H, W]
  • Agreement map: [H, W] (%)
  • Co-registration analysis report
  • IOU time series curve
  • Geometry sensitivity analysis

Thời gian thực hiện: ~2-3 tuần (dual-track processing)
""",
            "processing_steps": [
                "3.1 Process ASCENDING subset independently",
                "3.2 Generate ASCENDING water time series",
                "3.3 Process DESCENDING subset independently",
                "3.4 Generate DESCENDING water time series",
                "3.5 Co-registration: both → UTM48N grid",
                "3.6 Compute pixel-wise agreement ratio",
                "3.7 Generate confusion matrix at each time step",
                "3.8 IOU time series: compute intersection/union",
                "3.9 Sensitivity analysis: identify viewing-angle effects",
            ],
            "primary_orbit": "ASCENDING",
            "secondary_orbit": "DESCENDING",
            "required_ancillary": ["DEM"],
            "output_products": [
                "asc_water_timeseries.tif",
                "desc_water_timeseries.tif",
                "agreement_map.tif",
                "iou_timeseries.csv",
                "geometry_comparison_report.txt",
            ],
        },
        
        "scenario_4": {
            "name": "Scenario 4: Anomaly Detection & Real-Time Alert",
            "description": """
Phát hiện những biến động bất thường trong chuỗi thời gian.
Xác định các thời điểm có nguy cơ lũ quét cao.

Kỹ thuật:
  • Huấn luyện baseline model trên pre-flood period (reference state)
  • Monitor deviation từ baseline: Δ(t) = |Water(t) - Baseline|
  • Define anomaly thresholds: μ + 2σ, μ + 3σ
  • Trigger alerts khi anomaly vượt threshold
  • Estimate flood severity level: Low / Medium / High / Critical
  • Generate automated early warning bulletin

Ưu điểm:
  ✓ Real-time capability (once per acquisition)
  ✓ Automatic alert generation
  ✓ Severity classification
  ✓ Integration with operational systems

Nhược điểm:
  ✗ Requires good baseline characterization
  ✗ Tuning thresholds difficult (false positive/negative tradeoff)
  ✗ May miss slow-onset flood

Dữ liệu đầu vào:
  • Historical water extent (2019-2024): baseline
  • Current & recent acquisitions (2025): monitoring
  • Rainfall forecast (optional)
  • Threshold parameters (tunable)

Đầu ra:
  • Anomaly score map: [H, W]
  • Alert level raster (severity classification)
  • Early warning bulletin (JSON)
  • Performance metrics (sensitivity, specificity)
  • Threshold tuning recommendations

Thời gian thực hiện: ~3-5 ngày (training) + real-time processing (minutes/image)
""",
            "processing_steps": [
                "4.1 Load historical water extent time series (2019-2024)",
                "4.2 Compute per-pixel statistics: mean, std, min, max",
                "4.3 Define baseline envelope & thresholds",
                "4.4 Load current & recent acquisitions",
                "4.5 Compute per-pixel anomaly score: z-score or MAD",
                "4.6 Apply severity thresholds → alert levels",
                "4.7 Classify spatial clusters (connected components)",
                "4.8 Generate early warning bulletin",
                "4.9 Evaluate against historical events (if ground truth available)",
            ],
            "primary_orbit": "ASCENDING",
            "alternate_orbit": "DESCENDING (real-time fusion)",
            "required_ancillary": ["DEM", "Rainfall_forecast"],
            "output_products": [
                "anomaly_score_map.tif",
                "alert_level_map.tif",
                "alert_bulletin.json",
                "performance_metrics.txt",
                "threshold_tuning_report.txt",
            ],
        },
    }
    
    def __init__(self):
        pass
    
    def get_scenario(self, scenario_id: str) -> Dict[str, Any]:
        """Retrieve scenario by ID."""
        return self.SCENARIOS.get(scenario_id, {})
    
    def get_all_scenarios(self) -> Dict[str, Dict]:
        """Get all scenarios."""
        return self.SCENARIOS
    
    def generate_scenario_report(self, output_dir: Path) -> str:
        """Generate comprehensive scenario design report."""
        lines = [
            "=" * 100,
            "EXPERIMENT SCENARIO DESIGN — Tĩnh Túc Flood Detection Project",
            "=" * 100,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Study Area: Tĩnh Túc mining region, Cao Bằng, Vietnam",
            f"Problem: Flood risk assessment from 2025 heavy rainfall",
            "",
        ]
        
        for scenario_id, scenario in self.SCENARIOS.items():
            lines.extend([
                "─" * 100,
                f"🎯 {scenario['name']}",
                "─" * 100,
                scenario["description"],
                "",
                "📊 Processing Steps:",
            ])
            
            for step in scenario["processing_steps"]:
                lines.append(f"  {step}")
            
            lines.extend([
                "",
                f"🛰️ Data Requirements:",
                f"  • Primary Orbit: {scenario.get('primary_orbit', 'N/A')}",
                f"  • Secondary Orbit: {scenario.get('alternate_orbit', 'N/A')}",
                f"  • Ancillary Data: {', '.join(scenario.get('required_ancillary', []))}",
                "",
                f"📈 Output Products:",
            ])
            
            for product in scenario.get("output_products", []):
                lines.append(f"  • {product}")
            
            lines.append("")
        
        lines.extend([
            "=" * 100,
            "EXECUTION ROADMAP",
            "=" * 100,
            "",
            "Phase 1: Data Preparation (Week 1)",
            "  • Complete Input Data Audit ✓ (DONE)",
            "  • Separate ASCENDING/DESCENDING datasets ✓ (DONE)",
            "  • Define experiment scenarios ✓ (DONE)",
            "",
            "Phase 2: Single Point-in-Time Analysis (Week 2)",
            "  • Run Scenario 1 (Before-After analysis)",
            "  • Validate water detection algorithm",
            "  • Manual QC with satellite imagery (Google Earth)",
            "",
            "Phase 3: Time Series Processing (Week 3-4)",
            "  • Run Scenario 2 (Full time series)",
            "  • Validate trends against rainfall records",
            "  • Identify key flood dates",
            "",
            "Phase 4: Multi-Track Validation (Week 5)",
            "  • Run Scenario 3 (ASC vs DESC comparison)",
            "  • Assess viewing-angle effects",
            "  • Generate fusion product",
            "",
            "Phase 5: Operational System (Week 6+)",
            "  • Run Scenario 4 (Real-time anomaly detection)",
            "  • Tune alert thresholds",
            "  • Deploy automated bulletin generation",
            "",
            "=" * 100,
            "RECOMMENDED EXECUTION ORDER",
            "=" * 100,
            "",
            "1️⃣  START: Scenario 1 (quickest validation, 2-3 days)",
            "    ↓",
            "2️⃣  FOLLOW: Scenario 2 (full time series, 1-2 weeks)",
            "    ↓",
            "3️⃣  PARALLEL: Scenario 3 (ASC/DESC comparison, 2-3 weeks)",
            "    ↓",
            "4️⃣  FINALIZE: Scenario 4 (operational alert system)",
            "",
            "=" * 100,
        ])
        
        report_text = "\n".join(lines)
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_path = output_dir / "experiment_scenarios_design.txt"
        with open(report_path, "w") as f:
            f.write(report_text)
        
        return report_text
    
    def save_scenarios_as_json(self, output_dir: Path):
        """Save scenarios as JSON for programmatic access."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / "experiment_scenarios.json"
        with open(output_file, "w") as f:
            json.dump(self.SCENARIOS, f, indent=2)
        
        return output_file


def main():
    """Generate experiment scenario design document."""
    import sys
    import logging
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    designer = ExperimentScenarioDesigner()
    
    output_dir = Path("outputs/experiment_scenarios")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate report
    report = designer.generate_scenario_report(output_dir)
    print("\n" + report + "\n")
    
    # Save JSON
    json_file = designer.save_scenarios_as_json(output_dir)
    logger.info(f"Saved scenarios JSON: {json_file}")
    
    logger.info(f"Experiment scenarios complete. Output: {output_dir}")


if __name__ == "__main__":
    main()
