"""
=============================================================================
qgis_scripts/01_load_insar_results.py
Load kết quả InSAR vào QGIS và tạo bản đồ chuyên nghiệp
━━ Chạy trong QGIS Python Console ━━

Hướng dẫn:
  1. Mở QGIS 3.x
  2. Menu Plugins → Python Console
  3. Nhấn nút "Show Editor" (biểu tượng tờ giấy)
  4. Copy-paste script này vào Editor
  5. Nhấn Run (Ctrl+Enter)
=============================================================================
"""

# ─── IMPORT QGIS MODULES ─────────────────────────────────────────────────
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsVectorLayer, QgsPointXY,
    QgsColorRampShader, QgsRasterBandStats, QgsSingleBandPseudoColorRenderer,
    QgsRasterShader, QgsCoordinateReferenceSystem, QgsWkbTypes,
    QgsFeature, QgsGeometry, QgsField, QgsFields
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
import os

# ─── CẤU HÌNH ─────────────────────────────────────────────────────────────
# Lấy đường dẫn động hoặc thay đổi trực tiếp (cập nhật theo thư mục thực tế)
import os
BASE_DIR = r"d:\tinhtuc_insar_project"

DATA_DIR = os.path.join(BASE_DIR, "data", "processed")
FIG_DIR  = os.path.join(BASE_DIR, "outputs", "figures")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs", "qgis")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# CRS: WGS84 / UTM Zone 48N (phù hợp Tĩnh Túc)
CRS_WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")
CRS_UTM48 = QgsCoordinateReferenceSystem("EPSG:32648")

print("=" * 55)
print("  QGIS InSAR Loader — Tĩnh Túc, Cao Bằng")
print("=" * 55)

# ─── HÀM TIỆN ÍCH ────────────────────────────────────────────────────────
def add_raster_layer(filepath, layer_name, group=None):
    """Load raster và thêm vào QGIS"""
    if not os.path.exists(filepath):
        print(f"  ⚠️  File không tồn tại: {filepath}")
        return None

    layer = QgsRasterLayer(filepath, layer_name)
    if not layer.isValid():
        print(f"  ❌ Lỗi load: {layer_name}")
        return None

    QgsProject.instance().addMapLayer(layer, False)
    if group:
        group.addLayer(layer)
    else:
        QgsProject.instance().layerTreeRoot().addLayer(layer)

    print(f"  ✅ Loaded: {layer_name}")
    return layer


def style_velocity_map(layer, min_val=-25, max_val=5):
    """Áp dụng color ramp cho velocity map (cm/năm)"""
    shader = QgsRasterShader()
    color_ramp = QgsColorRampShader()
    color_ramp.setColorRampType(QgsColorRampShader.Interpolated)

    # Color scheme: Xanh (lún mạnh) → Trắng (ổn định) → Đỏ (nâng)
    items = [
        QgsColorRampShader.ColorRampItem(min_val,    QColor(0,   0, 200),  f"{min_val} cm/yr"),
        QgsColorRampShader.ColorRampItem(min_val*0.6, QColor(0, 120, 255), ""),
        QgsColorRampShader.ColorRampItem(-5,          QColor(100, 200, 255), "-5"),
        QgsColorRampShader.ColorRampItem(-1,          QColor(220, 220, 255), "-1"),
        QgsColorRampShader.ColorRampItem(0,           QColor(255, 255, 255),  "0"),
        QgsColorRampShader.ColorRampItem(max_val,     QColor(200,   0,   0), f"+{max_val}"),
    ]
    color_ramp.setColorRampItemList(items)
    shader.setRasterShaderFunction(color_ramp)

    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def style_hazard_map(layer):
    """Áp dụng màu phân cấp cho hazard map"""
    shader = QgsRasterShader()
    color_ramp = QgsColorRampShader()
    color_ramp.setColorRampType(QgsColorRampShader.Exact)

    items = [
        QgsColorRampShader.ColorRampItem(0, QColor(44,  62,  80),  "Ổn định"),
        QgsColorRampShader.ColorRampItem(1, QColor(39, 174,  96),  "Cấp 1 - Thấp"),
        QgsColorRampShader.ColorRampItem(2, QColor(243, 156,  18), "Cấp 2 - TB"),
        QgsColorRampShader.ColorRampItem(3, QColor(230,  76,  60), "Cấp 3 - Cao"),
        QgsColorRampShader.ColorRampItem(4, QColor(192,  57,  43), "Cấp 4 - Rất cao"),
    ]
    color_ramp.setColorRampItemList(items)
    shader.setRasterShaderFunction(color_ramp)

    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def style_susceptibility(layer):
    """Style cho susceptibility map"""
    shader = QgsRasterShader()
    color_ramp = QgsColorRampShader()
    color_ramp.setColorRampType(QgsColorRampShader.Exact)
    items = [
        QgsColorRampShader.ColorRampItem(0, QColor(0, 184, 148),   "Ổn định"),
        QgsColorRampShader.ColorRampItem(1, QColor(253, 203, 110),  "Trượt nông"),
        QgsColorRampShader.ColorRampItem(2, QColor(225, 112,  85),  "Trượt sâu"),
        QgsColorRampShader.ColorRampItem(3, QColor(214,  48,  49),  "Đất chảy"),
    ]
    color_ramp.setColorRampItemList(items)
    shader.setRasterShaderFunction(color_ramp)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


# ─── 1. TẠO PROJECT STRUCTURE ────────────────────────────────────────────
print("\n📁 Tạo cấu trúc layers...")
root = QgsProject.instance().layerTreeRoot()

# Tạo groups
groups = {}
for gname in ["🏔️ Base Layers", "📡 InSAR Results",
              "🚨 Hazard Maps", "📍 Monitoring Points"]:
    groups[gname] = root.addGroup(gname)

# ─── 2. LOAD BASE LAYERS ─────────────────────────────────────────────────
print("\n🌍 Load base layers...")

# DEM
dem_file = os.path.join(DATA_DIR, "dem.tif")
if os.path.exists(dem_file):
    dem_layer = add_raster_layer(dem_file, "DEM Copernicus 30m", groups["🏔️ Base Layers"])

# Slope
slope_file = os.path.join(DATA_DIR, "slope_deg.tif")
if os.path.exists(slope_file):
    slope_lyr = add_raster_layer(slope_file, "Độ dốc (°)", groups["🏔️ Base Layers"])
    if slope_lyr:
        # Style slope map
        shader = QgsRasterShader()
        cr = QgsColorRampShader()
        cr.setColorRampType(QgsColorRampShader.Interpolated)
        cr.setColorRampItemList([
            QgsColorRampShader.ColorRampItem(0,  QColor(255, 255, 255), "0°"),
            QgsColorRampShader.ColorRampItem(15, QColor(255, 255, 0),   "15°"),
            QgsColorRampShader.ColorRampItem(25, QColor(255, 165, 0),   "25°"),
            QgsColorRampShader.ColorRampItem(35, QColor(255, 69,  0),   "35°"),
            QgsColorRampShader.ColorRampItem(50, QColor(139, 0,   0),   "50°"),
        ])
        shader.setRasterShaderFunction(cr)
        renderer = QgsSingleBandPseudoColorRenderer(
            slope_lyr.dataProvider(), 1, shader)
        slope_lyr.setRenderer(renderer)
        slope_lyr.triggerRepaint()

# ─── 3. LOAD InSAR RESULTS ───────────────────────────────────────────────
print("\n📡 Load kết quả InSAR...")

# Velocity map
vel_tif = os.path.join(DATA_DIR, "velocity_filtered.tif")
if os.path.exists(vel_tif):
    vel_lyr = add_raster_layer(vel_tif, "Velocity LOS (cm/yr)", groups["📡 InSAR Results"])
    if vel_lyr:
        style_velocity_map(vel_lyr, min_val=-20, max_val=5)

# Temporal coherence
coh_tif = os.path.join(DATA_DIR, "temporal_coherence.tif")
if os.path.exists(coh_tif):
    coh_lyr = add_raster_layer(coh_tif, "Temporal Coherence", groups["📡 InSAR Results"])
    if coh_lyr:
        shader = QgsRasterShader()
        cr = QgsColorRampShader()
        cr.setColorRampType(QgsColorRampShader.Interpolated)
        cr.setColorRampItemList([
            QgsColorRampShader.ColorRampItem(0.0, QColor(255, 0,   0),   "0 (incoherent)"),
            QgsColorRampShader.ColorRampItem(0.4, QColor(255, 165, 0),   "0.4"),
            QgsColorRampShader.ColorRampItem(0.7, QColor(255, 255, 0),   "0.7"),
            QgsColorRampShader.ColorRampItem(1.0, QColor(0,   200, 0),   "1 (coherent)"),
        ])
        shader.setRasterShaderFunction(cr)
        renderer = QgsSingleBandPseudoColorRenderer(
            coh_lyr.dataProvider(), 1, shader)
        coh_lyr.setRenderer(renderer)
        coh_lyr.triggerRepaint()

# ─── 4. LOAD HAZARD MAPS ─────────────────────────────────────────────────
print("\n🚨 Load hazard maps...")

haz_tif = os.path.join(DATA_DIR, "hazard_map.tif")
if os.path.exists(haz_tif):
    haz_lyr = add_raster_layer(haz_tif, "Phân vùng Nguy hiểm", groups["🚨 Hazard Maps"])
    if haz_lyr:
        style_hazard_map(haz_lyr)

susc_tif = os.path.join(DATA_DIR, "susceptibility_map.tif")
if os.path.exists(susc_tif):
    susc_lyr = add_raster_layer(susc_tif, "Susceptibility Sạt lở", groups["🚨 Hazard Maps"])
    if susc_lyr:
        style_susceptibility(susc_lyr)

# ─── 5. TẠO MONITORING POINTS LAYER ─────────────────────────────────────
print("\n📍 Tạo điểm quan trắc...")

MONITORING_POINTS = [
    (105.975, 22.675, "TT-01", "Hầm lò 1",    "mining",   -8.5),
    (105.990, 22.680, "TT-02", "Lộ thiên",     "openpit",  -3.8),
    (105.960, 22.660, "TT-03", "Hầm lò 2",     "mining",   -5.2),
    (105.955, 22.645, "TT-04", "Bãi thải",     "waste",    -4.2),
    (105.935, 22.720, "TT-06", "Sạt lở TN",    "landslide",-12.0),
    (105.980, 22.580, "TT-07", "Trượt sâu S",  "landslide",-18.5),
    (106.050, 22.650, "TT-08", "Đất chảy E",   "landslide",-25.0),
    (105.968, 22.695, "TT-09", "Nứt đất",      "crack",    -6.8),
    (106.070, 22.760, "TT-REF","Điểm tham chiếu","stable",  0.0),
]

# Tạo memory layer
fields = QgsFields()
fields.append(QgsField("id",       QVariant.String))
fields.append(QgsField("name",     QVariant.String))
fields.append(QgsField("type",     QVariant.String))
fields.append(QgsField("velocity", QVariant.Double))
fields.append(QgsField("priority", QVariant.Int))

mon_layer = QgsVectorLayer("Point?crs=EPSG:4326", "Điểm Quan trắc", "memory")
mon_provider = mon_layer.dataProvider()
mon_provider.addAttributes(fields)
mon_layer.updateFields()

features = []
for lon, lat, pid, name, ptype, vel in MONITORING_POINTS:
    feat = QgsFeature()
    feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
    priority = 1 if ptype == 'landslide' else 2 if ptype == 'mining' else 3
    feat.setAttributes([pid, name, ptype, vel, priority])
    features.append(feat)

mon_provider.addFeatures(features)
mon_layer.updateExtents()
QgsProject.instance().addMapLayer(mon_layer, False)
groups["📍 Monitoring Points"].addLayer(mon_layer)
print(f"  ✅ {len(features)} điểm quan trắc đã tạo")

# ─── 6. CẤU HÌNH MAP CANVAS ──────────────────────────────────────────────
# Zoom đến vùng nghiên cứu
from qgis.utils import iface
if iface:
    canvas = iface.mapCanvas()
    extent = QgsRectangle(105.85, 22.55, 106.10, 22.80)
    canvas.setExtent(extent)
    canvas.refresh()
    print("\n✅ Map canvas đã zoom đến Tĩnh Túc")

# ─── 7. LƯU PROJECT ──────────────────────────────────────────────────────
project_file = os.path.join(OUTPUT_DIR, "TinhTuc_InSAR.qgz")
QgsProject.instance().setTitle("InSAR — Tĩnh Túc, Cao Bằng")
QgsProject.instance().setCrs(CRS_WGS84)
QgsProject.instance().write(project_file)
print(f"\n💾 Project đã lưu: {project_file}")

print("\n" + "=" * 55)
print("  ✅ QGIS project sẵn sàng!")
print("\n  Bước tiếp theo:")
print("  1. Chạy 02_styling.py để thêm labels và scale bar")
print("  2. Chạy 03_layout_export.py để xuất bản đồ A3")
print("=" * 55)
