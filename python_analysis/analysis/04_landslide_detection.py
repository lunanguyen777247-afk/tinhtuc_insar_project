"""
=============================================================================
python_analysis/analysis/04_landslide_detection.py
Phát hiện và Phân loại Sạt lở — Tĩnh Túc, Cao Bằng
━━ Susceptibility mapping · Event detection · Early warning ━━

Phương pháp:
  - Multi-criteria landslide susceptibility (slope+aspect+velocity+geology)
  - Threshold-based event detection từ InSAR time-series
  - Creep detection (pre-failure acceleration)
  - Inventory mapping từ velocity field
=============================================================================
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
from scipy.ndimage import gaussian_filter, label, binary_dilation
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
from sklearn.metrics import classification_report
import os, warnings
warnings.filterwarnings('ignore')

print("=" * 65)
print("  🏔️   Phát hiện và Phân tích Sạt lở — Tĩnh Túc")
print("  Susceptibility · Event Detection · Early Warning")
print("=" * 65)

# ─── TẢI DỮ LIỆU ─────────────────────────────────────────────────────────
data_dir = "data/processed"
velocity    = np.load(f"{data_dir}/velocity_true.npy")
displacement= np.load(f"{data_dir}/displacement.npy")
source_map  = np.load(f"{data_dir}/source_type_map.npy")
dem         = np.load(f"{data_dir}/dem.npy")
slope_deg   = np.load(f"{data_dir}/slope_deg.npy")
aspect_deg  = np.load(f"{data_dir}/aspect_deg.npy")
time_days   = np.load(f"{data_dir}/time_days.npy")
LON         = np.load(f"{data_dir}/lon_grid.npy")
LAT         = np.load(f"{data_dir}/lat_grid.npy")

NY, NX = velocity.shape
years = time_days / 365.25
LON_MIN, LON_MAX = LON.min(), LON.max()
LAT_MIN, LAT_MAX = LAT.min(), LAT.max()
lons = LON[0, :]; lats = LAT[:, 0]

# ─── 1. TÍNH CÁC ĐẶC TRƯNG ĐỊA HÌNH ────────────────────────────────────
print("\n🗺️  Tính đặc trưng địa hình...")

# Curvature (độ cong bề mặt — quan trọng cho sạt lở)
dy = np.gradient(dem, axis=0)
dx = np.gradient(dem, axis=1)
dyy = np.gradient(dy, axis=0)
dxx = np.gradient(dx, axis=1)
curvature = -(dxx + dyy) / ((1 + dx**2 + dy**2)**1.5)
curvature = gaussian_filter(curvature, sigma=1.5)

# TWI — Topographic Wetness Index (chỉ số ẩm ướt địa hình)
slope_rad = np.radians(np.clip(slope_deg, 0.01, 89))
# Upstream area proxy (simplified)
upstream_area = gaussian_filter(
    np.exp(-dem / 200) * 100, sigma=5.0
) + 1.0
twi = np.log(upstream_area / np.tan(slope_rad))
twi = np.clip(twi, 0, 20)

# Hướng đón mưa (aspect 45–225° = hướng S/E đón gió mùa)
rain_aspect = np.sin(np.radians(aspect_deg - 135))  # +1 = trực tiếp đón mưa

print(f"  TWI range: {twi.min():.1f} – {twi.max():.1f}")
print(f"  Curvature range: {curvature.min():.4f} – {curvature.max():.4f}")

# ─── 2. LANDSLIDE SUSCEPTIBILITY (Machine Learning) ───────────────────────
print("\n🤖 Huấn luyện mô hình Susceptibility (Random Forest)...")

# ── Chuẩn bị features ──
features = np.stack([
    slope_deg,                           # F1: Độ dốc
    aspect_deg / 360.0,                  # F2: Hướng dốc (normalized)
    dem / 1800.0,                        # F3: Độ cao (normalized)
    curvature * 1000,                    # F4: Độ cong
    twi,                                 # F5: TWI
    rain_aspect,                         # F6: Đón mưa
    np.abs(velocity),                    # F7: Tốc độ biến dạng |v|
    velocity,                            # F8: Chiều biến dạng
    gaussian_filter(np.abs(velocity), 3), # F9: Smoothed |v|
], axis=-1)  # (NY, NX, 9)

# ── Ground truth labels (từ source_map) ──
# 0=stable, 1=shallow_slide, 2=deep_slide, 3=debris_flow, 4=other
label_map = np.zeros((NY, NX), dtype=int)
label_map[source_map == 4] = 1   # Trượt nông → class 1
label_map[source_map == 5] = 2   # Trượt sâu  → class 2
label_map[source_map == 6] = 3   # Đất chảy   → class 3

# Thêm dữ liệu stable (class 0) để cân bằng
stable_mask = (source_map == 0) & (slope_deg < 5)

# Sample pixels
n_per_class = 500
np.random.seed(42)
all_rows, all_cols, all_labels = [], [], []

for cls, mask in [(0, stable_mask), (1, source_map==4),
                   (2, source_map==5), (3, source_map==6)]:
    r_idx, c_idx = np.where(mask)
    if len(r_idx) > n_per_class:
        sel = np.random.choice(len(r_idx), n_per_class, replace=False)
        r_idx = r_idx[sel]; c_idx = c_idx[sel]
    all_rows.extend(r_idx); all_cols.extend(c_idx)
    all_labels.extend([cls] * len(r_idx))

all_rows = np.array(all_rows)
all_cols = np.array(all_cols)
all_labels = np.array(all_labels)

X = features[all_rows, all_cols, :]  # (N, 9)
y = all_labels

# Chuẩn hóa
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Huấn luyện Random Forest
rf = RandomForestClassifier(
    n_estimators=200, max_depth=12,
    class_weight='balanced', random_state=42, n_jobs=-1
)
rf.fit(X_scaled, y)

# Cross-validation
cv_scores = cross_val_score(rf, X_scaled, y, cv=5, scoring='f1_macro')
print(f"  F1-macro CV: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

# Feature importance
feat_names = ['Slope','Aspect','Elevation','Curvature','TWI',
              'Rain_aspect','|Velocity|','Velocity','Smooth|v|']
importances = rf.feature_importances_
print("\n  Feature importances:")
for name, imp in sorted(zip(feat_names, importances),
                        key=lambda x: x[1], reverse=True):
    bar = '█' * int(imp * 40)
    print(f"    {name:<15}: {bar} {imp:.3f}")

# ── Predict trên toàn bộ grid ──
feat_flat = features.reshape(-1, 9)
feat_scaled = scaler.transform(feat_flat)
pred_flat = rf.predict(feat_scaled)
proba_flat = rf.predict_proba(feat_scaled)

susceptibility_map = pred_flat.reshape(NY, NX)
# Xác suất tổng hợp (landslide prob = P(class 1) + P(class 2) + P(class 3))
landslide_prob = proba_flat[:, 1:].sum(axis=1).reshape(NY, NX)

print(f"\n  Diện tích nguy cơ cao (prob>0.6): "
      f"{(landslide_prob>0.6).sum()*(0.1**2):.2f} km²")

# ─── 3. PHÁT HIỆN SỰ KIỆN SẠT LỞ TỪ TIME-SERIES ─────────────────────────
print("\n🔍 Phát hiện sự kiện sạt lở...")

def detect_slide_events(ts_pixel, time_years, threshold_sigma=2.0):
    """
    Phát hiện sự kiện đột ngột từ chuỗi thời gian
    Dùng velocity thay đổi đột biến > threshold_sigma
    """
    # Tính velocity từng bước
    dv = np.diff(ts_pixel) / np.diff(time_years)

    # Phát hiện dị thường
    dv_mean, dv_std = dv.mean(), dv.std()
    threshold = dv_mean - threshold_sigma * dv_std  # âm = sụt lún nhanh

    events = np.where(dv < threshold)[0]
    return events, dv, threshold

# Phân tích tại các điểm sạt lở
def lonlat_to_px(lon, lat):
    col = int((lon - LON_MIN) / (LON_MAX - LON_MIN) * NX)
    row = int((lat - LAT_MIN) / (LAT_MAX - LAT_MIN) * NY)
    return np.clip(col, 0, NX-1), np.clip(row, 0, NY-1)

slide_sites = {
    'Sạt lở TN (TT-06)': (105.935, 22.720),
    'Trượt sâu S (TT-07)': (105.980, 22.580),
    'Đất chảy E (TT-08)': (106.050, 22.650),
}

print("\n  Kết quả phát hiện sự kiện:")
event_results = {}
for name, (slon, slat) in slide_sites.items():
    sc, sr = lonlat_to_px(slon, slat)
    ts_site = displacement[:, sr, sc]
    events, dv, thresh = detect_slide_events(ts_site, years)
    event_results[name] = {'ts': ts_site, 'events': events, 'dv': dv,
                           'thresh': thresh, 'col': sc, 'row': sr}
    if len(events) > 0:
        event_times = [f"{years[e]:.1f}yr" for e in events[:3]]
        print(f"    {name}: {len(events)} sự kiện tại {', '.join(event_times)}")
    else:
        print(f"    {name}: Không phát hiện sự kiện đột ngột")

# ─── 4. CREEP DETECTION (Phát hiện tăng tốc trước sự kiện) ───────────────
print("\n⚡ Phát hiện Creep (pre-failure acceleration)...")

def detect_creep(ts_pixel, time_years, window_days=180):
    """
    Creep: tăng tốc đều đặn trước khi xảy ra sạt lở lớn
    Tính velocity từng cửa sổ rolling → nếu velocity tăng liên tục → warning
    """
    window = max(3, int(window_days / (time_years[1] - time_years[0]) / 365.25))
    velocities = []
    times = []
    for i in range(len(ts_pixel) - window):
        v_w = np.polyfit(time_years[i:i+window], ts_pixel[i:i+window], 1)[0]
        velocities.append(v_w)
        times.append(time_years[i + window//2])

    velocities = np.array(velocities)
    times = np.array(times)

    # Phát hiện xu hướng tăng tốc (hồi quy tuyến tính trên velocity)
    slope_vel, intercept, r, p, se = stats.linregress(times, velocities)

    is_creep = (slope_vel < -0.5) and (p < 0.05)  # Tăng tốc âm (lún nhanh hơn)
    return velocities, times, slope_vel, p, is_creep

for name, res in event_results.items():
    vels, times_w, slope_v, p_val, is_creep = detect_creep(res['ts'], years)
    status = "⚠️  CREEP DETECTED" if is_creep else "✅ Ổn định"
    print(f"  {name}: slope={slope_v:.2f} cm/yr², p={p_val:.3f} → {status}")

# ─── 5. LƯU ─────────────────────────────────────────────────────────────
np.save(f"{data_dir}/susceptibility_map.npy",  susceptibility_map)
np.save(f"{data_dir}/landslide_prob.npy",       landslide_prob)

# ─── 6. VISUALIZATION ─────────────────────────────────────────────────────
print("\n🎨 Vẽ kết quả phân tích sạt lở...")

fig = plt.figure(figsize=(22, 16))
fig.suptitle("Phân tích Sạt lở — Xã Tĩnh Túc, Cao Bằng\n"
             "Susceptibility Mapping · Event Detection · Creep Analysis",
             fontsize=14, fontweight='bold')

gs = gridspec.GridSpec(3, 4, figure=fig, hspace=0.45, wspace=0.35)

# (a) Slope + susceptibility overlay
ax = fig.add_subplot(gs[0, :2])
im = ax.pcolormesh(LON, LAT, slope_deg,
    cmap='YlOrRd', vmin=0, vmax=50, shading='auto')
plt.colorbar(im, ax=ax, label='Độ dốc (°)', shrink=0.85)
# Overlay landslide probability
lp_masked = np.ma.masked_less(landslide_prob, 0.4)
im2 = ax.pcolormesh(LON, LAT, lp_masked,
    cmap='hot_r', vmin=0.4, vmax=1.0, alpha=0.6, shading='auto')
plt.colorbar(im2, ax=ax, label='P(sạt lở)', shrink=0.85)
# Đường đồng mức DEM
ax.contour(LON, LAT, dem, levels=range(500,1800,200),
    colors='gray', linewidths=0.5, alpha=0.4)
ax.set_title('(a) Độ dốc + Xác suất Sạt lở\n[Overlay]', fontweight='bold')
ax.set_xlabel('Lon°E'); ax.set_ylabel('Lat°N')

# (b) Susceptibility classes
ax = fig.add_subplot(gs[0, 2])
sclass_colors = ['#00b894','#fdcb6e','#e17055','#d63031']
sclass_labels = ['Ổn định (0)','Trượt nông (1)','Trượt sâu (2)','Đất chảy (3)']
scmap = LinearSegmentedColormap.from_list('sc', sclass_colors, N=4)
im3 = ax.pcolormesh(LON, LAT, susceptibility_map,
    cmap=scmap, vmin=0, vmax=3, shading='auto')
patches = [mpatches.Patch(color=sclass_colors[i], label=sclass_labels[i])
           for i in range(4)]
ax.legend(handles=patches, loc='upper right', fontsize=7, framealpha=0.9)
ax.set_title('(b) Phân loại Susceptibility\n(Random Forest)', fontweight='bold')
ax.set_xlabel('Lon°E')

# (c) Feature importance
ax = fig.add_subplot(gs[0, 3])
sorted_idx = np.argsort(importances)[::-1]
ax.barh(range(len(feat_names)),
        importances[sorted_idx], color='steelblue', alpha=0.8)
ax.set_yticks(range(len(feat_names)))
ax.set_yticklabels([feat_names[i] for i in sorted_idx], fontsize=8)
ax.set_xlabel('Feature Importance')
ax.set_title(f'(c) Feature Importance\nRF Classifier\nF1={cv_scores.mean():.3f}',
             fontweight='bold')
ax.grid(alpha=0.3, axis='x')

# (d) TWI map
ax = fig.add_subplot(gs[1, 0])
im4 = ax.pcolormesh(LON, LAT, twi,
    cmap='Blues', vmin=0, vmax=15, shading='auto')
plt.colorbar(im4, ax=ax, label='TWI', shrink=0.85)
ax.set_title('(d) Topographic Wetness Index\n[Xanh đậm = ẩm ướt]', fontweight='bold')
ax.set_xlabel('Lon°E'); ax.set_ylabel('Lat°N')

# (e-g) Time-series + event detection
site_colors = ['#d63031', '#0984e3', '#a29bfe']
for i, (name, res) in enumerate(event_results.items()):
    ax = fig.add_subplot(gs[1, i+1])
    ax.plot(years, res['ts'], '-', color=site_colors[i], lw=1.5, alpha=0.9)
    # Mark events
    for ev in res['events']:
        ax.axvline(years[ev], color='orange', lw=1.5, linestyle='--', alpha=0.7)
        ax.annotate('⚡', (years[ev], res['ts'][ev]),
            fontsize=10, ha='center', color='orange')
    ax.set_xlabel('Năm', fontsize=8)
    ax.set_ylabel('Disp. (cm)', fontsize=8)
    short_name = name.split('(')[0].strip()
    ax.set_title(f'({chr(101+i)}) {short_name}\n'
                 f'[{len(res["events"])} sự kiện ⚡]', fontweight='bold', fontsize=9)
    ax.grid(alpha=0.3)

# (h) Velocity change over time (spatial)
ax = fig.add_subplot(gs[2, :2])
# Tính velocity cho 2 nửa giai đoạn
half = len(years) // 2
v_first  = np.polyfit(years[:half],  displacement[:half].mean(axis=(1,2)), 1)[0]  # scalar
# Pixel-wise velocity first half vs second half
vel_h1 = np.zeros((NY, NX))
vel_h2 = np.zeros((NY, NX))
for r in range(0, NY, 5):  # subsample for speed
    for c in range(0, NX, 5):
        ts = displacement[:, r, c]
        vel_h1[r:r+5, c:c+5] = np.polyfit(years[:half], ts[:half], 1)[0]
        vel_h2[r:r+5, c:c+5] = np.polyfit(years[half:], ts[half:], 1)[0]

vel_change = vel_h2 - vel_h1
vel_change = gaussian_filter(vel_change, sigma=1.5)
im5 = ax.pcolormesh(LON, LAT, vel_change,
    cmap='RdBu', vmin=-15, vmax=15, shading='auto')
plt.colorbar(im5, ax=ax, label='Δvelocity (cm/yr)', shrink=0.85)
ax.set_title('(h) Thay đổi vận tốc: Giai đoạn 2 – Giai đoạn 1\n'
             '[Đỏ = tăng tốc, Xanh = giảm tốc]', fontweight='bold')
ax.set_xlabel('Lon°E'); ax.set_ylabel('Lat°N')

# (i) Creep analysis summary
ax = fig.add_subplot(gs[2, 2:])
site_cols_2 = ['#d63031', '#0984e3', '#a29bfe']
for i, (name, res) in enumerate(event_results.items()):
    vels, tw, sv, pv, ic = detect_creep(res['ts'], years)
    ax.plot(tw, vels, '-', color=site_cols_2[i], lw=1.5,
            label=f"{name.split('(')[0].strip()}")
    if ic:
        ax.text(tw[-1], vels[-1], ' ⚠️ CREEP',
                fontsize=8, color=site_cols_2[i], fontweight='bold')

ax.axhline(0, color='gray', lw=1, linestyle='--')
ax.axvline(3.0, color='orange', lw=2, linestyle='--', alpha=0.7, label='2020')
ax.set_xlabel('Năm từ 2017')
ax.set_ylabel('Vận tốc tức thời (cm/năm)')
ax.set_title('(i) Phân tích Creep (Tăng tốc trước sự kiện)\n'
             '[⚠️ = cảnh báo]', fontweight='bold')
ax.legend(fontsize=7); ax.grid(alpha=0.3)

plt.savefig("results/figures/04_landslide_analysis.png",
            dpi=150, bbox_inches='tight')
plt.close()
print("✅ Đã lưu: results/figures/04_landslide_analysis.png")
