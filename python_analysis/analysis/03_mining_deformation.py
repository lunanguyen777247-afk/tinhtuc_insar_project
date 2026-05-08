"""
=============================================================================
python_analysis/analysis/03_mining_deformation.py
Phân tích biến dạng do khai thác mỏ thiếc Tĩnh Túc
━━ Profile lún, subsidence bowl, tốc độ khai thác ━━

Tham khảo: Peng & Meng (2021), He et al. (2017)
Phương pháp: Profile analysis + Subsidence bowl fitting +
             Time-acceleration detection + Hazard zoning
=============================================================================
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
from scipy.ndimage import gaussian_filter, label
from scipy.optimize import curve_fit
from scipy import stats
import os, warnings
warnings.filterwarnings('ignore')

print("=" * 65)
print("  ⛏️   Phân tích Biến dạng Khai thác Mỏ Thiếc Tĩnh Túc")
print("  Subsidence Bowl · Profile · Time-Series · Hazard Zones")
print("=" * 65)

# ─── TẢI DỮ LIỆU ─────────────────────────────────────────────────────────
data_dir = "data/processed"
velocity       = np.load(f"{data_dir}/velocity_true.npy")
displacement   = np.load(f"{data_dir}/displacement.npy")
source_map     = np.load(f"{data_dir}/source_type_map.npy")
dem            = np.load(f"{data_dir}/dem.npy")
slope_deg      = np.load(f"{data_dir}/slope_deg.npy")
time_days      = np.load(f"{data_dir}/time_days.npy")
LON            = np.load(f"{data_dir}/lon_grid.npy")
LAT            = np.load(f"{data_dir}/lat_grid.npy")

NY, NX = velocity.shape
LON_MIN, LON_MAX = LON.min(), LON.max()
LAT_MIN, LAT_MAX = LAT.min(), LAT.max()
years = time_days / 365.25

lons = LON[0, :]
lats = LAT[:, 0]

def lonlat_to_px(lon, lat):
    col = int((lon - LON_MIN) / (LON_MAX - LON_MIN) * NX)
    row = int((lat - LAT_MIN) / (LAT_MAX - LAT_MIN) * NY)
    return np.clip(col, 0, NX-1), np.clip(row, 0, NY-1)

# Vị trí mỏ thiếc chính
MINE_LON, MINE_LAT = 105.975, 22.675
mine_col, mine_row = lonlat_to_px(MINE_LON, MINE_LAT)

# ─── 1. PHÂN VÙNG MỎ VÀ TÍNH THỐNG KÊ ───────────────────────────────────
print("\n📊 Thống kê biến dạng vùng mỏ...")

# Mask các loại khai thác
mask_shaft = source_map == 1   # Hầm lò
mask_pit   = source_map == 2   # Lộ thiên
mask_waste = source_map == 3   # Bãi thải
mask_mine_all = mask_shaft | mask_pit | mask_waste


def _safe_mean(values):
    return float(np.mean(values)) if values.size > 0 else np.nan


def _safe_min(values):
    return float(np.min(values)) if values.size > 0 else np.nan


def _fmt(value):
    return f"{value:.1f}" if np.isfinite(value) else "N/A"

print(f"\n  Khai thác hầm lò:")
print(f"    Diện tích: {mask_shaft.sum() * (0.1**2):.2f} km²")
print(f"    Tốc độ lún trung bình: {_fmt(_safe_mean(velocity[mask_shaft]))} cm/năm")
print(f"    Tốc độ lún tối đa:     {_fmt(_safe_min(velocity[mask_shaft]))} cm/năm")

print(f"\n  Khai thác lộ thiên:")
print(f"    Diện tích: {mask_pit.sum() * (0.1**2):.2f} km²")
print(f"    Tốc độ lún trung bình: {_fmt(_safe_mean(velocity[mask_pit]))} cm/năm")

print(f"\n  Bãi thải:")
print(f"    Diện tích: {mask_waste.sum() * (0.1**2):.2f} km²")
print(f"    Tốc độ lún: {_fmt(_safe_mean(velocity[mask_waste]))} cm/năm")

# ─── 2. SUBSIDENCE BOWL FITTING ───────────────────────────────────────────
print("\n🥣 Fitting Subsidence Bowl (Gaussian model)...")

# Mô hình Gaussian 2D cho subsidence bowl
def gaussian_bowl_2d(xy, amplitude, xc, yc, sigma_x, sigma_y, background):
    x, y = xy
    bowl = amplitude * np.exp(
        -((x - xc)**2 / (2*sigma_x**2) + (y - yc)**2 / (2*sigma_y**2))
    ) + background
    return bowl.ravel()

# Lấy vùng xung quanh mỏ chính
r_fit = 40  # pixel radius
r_min, r_max = max(0, mine_row-r_fit), min(NY, mine_row+r_fit)
c_min, c_max = max(0, mine_col-r_fit), min(NX, mine_col+r_fit)

vel_sub = velocity[r_min:r_max, c_min:c_max]
lon_sub = LON[r_min:r_max, c_min:c_max]
lat_sub = LAT[r_min:r_max, c_min:c_max]
ny_s, nx_s = vel_sub.shape

# Initial guess
x_c0 = (MINE_LON - LON_MIN) / (LON_MAX - LON_MIN) * NX - c_min
y_c0 = (MINE_LAT - LAT_MIN) / (LAT_MAX - LAT_MIN) * NY - r_min
x_grid = np.arange(nx_s); y_grid = np.arange(ny_s)
XX, YY = np.meshgrid(x_grid, y_grid)

try:
    popt, pcov = curve_fit(
        gaussian_bowl_2d,
        (XX.ravel(), YY.ravel()), vel_sub.ravel(),
        p0=[-8, x_c0, y_c0, 10, 10, -0.5],
        bounds=([-30, 0, 0, 2, 2, -5], [0, nx_s, ny_s, 40, 40, 5]),
        maxfev=5000
    )
    bowl_fit = gaussian_bowl_2d((XX, YY), *popt).reshape(ny_s, nx_s)
    perr = np.sqrt(np.diag(pcov))
    print(f"  Amplitude bowl: {popt[0]:.2f} ± {perr[0]:.2f} cm/năm")
    print(f"  Sigma_x: {popt[3]*100:.0f}m, Sigma_y: {popt[4]*100:.0f}m")
    fit_success = True
except Exception as e:
    print(f"  ⚠️  Fitting không hội tụ: {e}")
    bowl_fit = vel_sub.copy()
    fit_success = False

# ─── 3. PROFILE PHÂN TÍCH ────────────────────────────────────────────────
print("\n📏 Phân tích profile qua tâm mỏ...")

# Profile Đông–Tây qua mỏ
profile_EW = velocity[mine_row, :]
profile_dist_EW = (lons - MINE_LON) * 111 * np.cos(np.radians(MINE_LAT))  # km

# Profile Bắc–Nam
profile_NS = velocity[:, mine_col]
profile_dist_NS = (lats - MINE_LAT) * 111  # km

# Bán kính ảnh hưởng (R0.5: khoảng cách tại đó lún = 50% max)
max_lun = profile_EW.min()
half_max = max_lun * 0.5
r_influence = np.abs(profile_dist_EW[
    np.argmin(np.abs(profile_EW - half_max))
])
print(f"  Bán kính ảnh hưởng (R₅₀%): ±{r_influence:.2f} km")
print(f"  Lún cực đại: {max_lun:.1f} cm/năm")

# ─── 4. PHÁT HIỆN TĂNG TỐC BIẾN DẠNG ────────────────────────────────────
print("\n⚡ Phát hiện tăng tốc khai thác...")

# Time-series tại mỏ chính
ts_mine = displacement[:, mine_row, mine_col]
pit_col, pit_row = lonlat_to_px(105.990, 22.680)
ts_pit = displacement[:, pit_row, pit_col]

# Chia 2 giai đoạn: Pre-2020 (trước tăng cường) và Post-2020
pre_mask  = years < 3.0
post_mask = years >= 3.0

v_pre  = np.polyfit(years[pre_mask],  ts_mine[pre_mask],  1)[0]
v_post = np.polyfit(years[post_mask], ts_mine[post_mask], 1)[0]

print(f"  Vận tốc 2017–2020: {v_pre:.1f} cm/năm")
print(f"  Vận tốc 2020–2024: {v_post:.1f} cm/năm")
print(f"  Tăng tốc:          {v_post - v_pre:.1f} cm/năm ({(v_post/v_pre-1)*100:.0f}%)")

# Sliding window velocity (phát hiện thay đổi tức thời)
window = 8  # ~3 tháng
vel_slide = []
for i in range(len(ts_mine) - window):
    v_w = np.polyfit(years[i:i+window], ts_mine[i:i+window], 1)[0]
    vel_slide.append(v_w)
vel_slide = np.array(vel_slide)

# ─── 5. PHÂN VÙNG NGUY HIỂM DO KHAI THÁC ────────────────────────────────
print("\n🚨 Phân vùng nguy hiểm do khai thác mỏ...")

# Cấp độ nguy hiểm dựa theo tốc độ lún (cm/năm) và slope
# Tham chiếu: TCVN/tiêu chuẩn khai thác mỏ
def mining_hazard_level(vel, slope):
    """
    Level 1 (Xanh):  lún < 2 cm/yr và slope < 15°
    Level 2 (Vàng):  2–5 cm/yr hoặc slope 15–25°
    Level 3 (Cam):   5–10 cm/yr hoặc slope 25–35°
    Level 4 (Đỏ):   >10 cm/yr hoặc slope > 35°
    """
    hazard = np.ones_like(vel, dtype=int)
    hazard = np.where((np.abs(vel) > 2)  | (slope > 15), 2, hazard)
    hazard = np.where((np.abs(vel) > 5)  | (slope > 25), 3, hazard)
    hazard = np.where((np.abs(vel) > 10) | (slope > 35), 4, hazard)
    return hazard

# Chỉ tính cho vùng xung quanh mỏ
hazard_map = mining_hazard_level(velocity, slope_deg)
hazard_map[source_map == 0] = 0  # Vùng ổn định = 0

print(f"  Vùng nguy hiểm cấp 4 (Đỏ):  {(hazard_map==4).sum()*(0.1**2):.2f} km²")
print(f"  Vùng nguy hiểm cấp 3 (Cam):  {(hazard_map==3).sum()*(0.1**2):.2f} km²")
print(f"  Vùng nguy hiểm cấp 2 (Vàng): {(hazard_map==2).sum()*(0.1**2):.2f} km²")

# ─── 6. LƯU KẾT QUẢ ─────────────────────────────────────────────────────
np.save(f"{data_dir}/hazard_map.npy",  hazard_map)
np.save(f"{data_dir}/bowl_fit.npy",    bowl_fit)

# ─── 7. VISUALIZATION ────────────────────────────────────────────────────
print("\n🎨 Vẽ kết quả phân tích mỏ...")

fig = plt.figure(figsize=(22, 15))
fig.suptitle("Phân tích Biến dạng Mỏ Thiếc Tĩnh Túc\n"
             "Subsidence Bowl · Profile · Tăng tốc · Phân vùng Nguy hiểm",
             fontsize=14, fontweight='bold')

gs = gridspec.GridSpec(3, 4, figure=fig, hspace=0.45, wspace=0.35)

# (a) Velocity map + hazard zones overlay
ax = fig.add_subplot(gs[0, :2])
im = ax.pcolormesh(LON, LAT, velocity,
    cmap='RdBu_r', vmin=-22, vmax=3, shading='auto')
plt.colorbar(im, ax=ax, label='cm/năm', shrink=0.85)
# Overlay hazard contours
hazard_colors = {4:'red', 3:'orange', 2:'yellow'}
for lvl, col in hazard_colors.items():
    cs = ax.contour(LON, LAT, hazard_map,
        levels=[lvl-0.5, lvl+0.5], colors=[col], linewidths=1.5)
ax.axhline(lats[mine_row], color='white', lw=1.5, linestyle='--', alpha=0.7,
           label='Profile E–W')
ax.axvline(lons[mine_col], color='cyan', lw=1.5, linestyle='--', alpha=0.7,
           label='Profile N–S')
ax.plot(MINE_LON, MINE_LAT, 'w*', ms=14, zorder=5, label='Tâm mỏ')
hazard_legend = [
    mpatches.Patch(color='red',    label='Cấp 4: Rất cao'),
    mpatches.Patch(color='orange', label='Cấp 3: Cao'),
    mpatches.Patch(color='yellow', label='Cấp 2: Trung bình'),
]
ax.legend(handles=hazard_legend, loc='upper right', fontsize=7)
ax.set_title('(a) Bản đồ vận tốc + Phân vùng nguy hiểm', fontweight='bold')
ax.set_xlabel('Kinh độ °E'); ax.set_ylabel('Vĩ độ °N')

# (b) Subsidence bowl fitting
ax = fig.add_subplot(gs[0, 2])
extent = [lon_sub.min(), lon_sub.max(), lat_sub.min(), lat_sub.max()]
im2 = ax.imshow(vel_sub, cmap='RdBu_r', vmin=-12, vmax=2,
    aspect='auto', extent=extent, origin='lower')
plt.colorbar(im2, ax=ax, label='cm/năm', shrink=0.85)
if fit_success:
    lon_fit_center = LON_MIN + (c_min + popt[1]) / NX * (LON_MAX - LON_MIN)
    lat_fit_center = LAT_MIN + (r_min + popt[2]) / NY * (LAT_MAX - LAT_MIN)
    from matplotlib.patches import Ellipse
    ell = Ellipse((lon_fit_center, lat_fit_center),
        popt[3]/NX*(LON_MAX-LON_MIN)*4, popt[4]/NY*(LAT_MAX-LAT_MIN)*4,
        fill=False, color='yellow', lw=2)
    ax.add_patch(ell)
    ax.plot(lon_fit_center, lat_fit_center, 'y*', ms=12)
ax.set_title(f'(b) Subsidence Bowl Fit\nAmpl={popt[0] if fit_success else "N/A":.1f} cm/yr',
             fontweight='bold')
ax.set_xlabel('Lon'); ax.set_ylabel('Lat')

# (c) E-W profile
ax = fig.add_subplot(gs[0, 3])
ax.fill_between(profile_dist_EW, profile_EW, 0,
    where=profile_EW < 0, alpha=0.4, color='tomato', label='Sụt lún')
ax.plot(profile_dist_EW, profile_EW, 'r-', lw=2, label='Profile E–W')
ax.axhline(max_lun*0.5, color='orange', lw=1.5, linestyle='--',
           label=f'50% max = {max_lun*0.5:.1f} cm/yr')
ax.axvline(0, color='gray', lw=1, alpha=0.5)
ax.axvline( r_influence, color='orange', lw=1, linestyle=':')
ax.axvline(-r_influence, color='orange', lw=1, linestyle=':')
ax.set_xlabel('Khoảng cách từ tâm mỏ (km)')
ax.set_ylabel('Vận tốc (cm/năm)')
ax.set_title(f'(c) Profile E–W\nR₅₀% = ±{r_influence:.2f} km', fontweight='bold')
ax.legend(fontsize=7); ax.grid(alpha=0.3)

# (d) Time-series + acceleration detection
ax = fig.add_subplot(gs[1, :2])
ax.plot(years, ts_mine, 'r-o', ms=3, lw=1.5, label='Hầm lò 1 (TT-01)', alpha=0.8)
ax.plot(years, ts_pit,  'b-s', ms=3, lw=1.5, label='Lộ thiên (TT-02)', alpha=0.8)

# Trendlines theo giai đoạn
yr_pre  = years[pre_mask];  fit_pre  = np.polyfit(yr_pre, ts_mine[pre_mask], 1)
yr_post = years[post_mask]; fit_post = np.polyfit(yr_post, ts_mine[post_mask], 1)
ax.plot(yr_pre,  np.polyval(fit_pre,  yr_pre),  'k--', lw=2,
        label=f'Trend pre:  {fit_pre[0]:.1f} cm/yr')
ax.plot(yr_post, np.polyval(fit_post, yr_post), 'k-',  lw=2,
        label=f'Trend post: {fit_post[0]:.1f} cm/yr')
ax.axvspan(0, 3, alpha=0.05, color='green', label='Pre-2020')
ax.axvspan(3, years.max(), alpha=0.05, color='red', label='Post-2020')
ax.set_xlabel('Năm từ 2017'); ax.set_ylabel('Displacement (cm)')
ax.set_title('(d) Chuỗi thời gian và Phát hiện tăng tốc', fontweight='bold')
ax.legend(fontsize=7); ax.grid(alpha=0.3)

# (e) Sliding window velocity
ax = fig.add_subplot(gs[1, 2:])
t_slide = years[window//2:len(years)-window//2]
ax.plot(t_slide, vel_slide, 'r-', lw=2, label='Vận tốc tức thời')
ax.fill_between(t_slide, vel_slide, vel_slide.mean(),
    where=vel_slide < vel_slide.mean(), alpha=0.3, color='red')
ax.axhline(vel_slide.mean(), color='gray', lw=1.5, linestyle='--',
           label=f'Trung bình: {vel_slide.mean():.1f} cm/yr')
ax.axvline(3.0, color='orange', lw=2, linestyle='--', label='Tăng cường 2020')
anomaly_thresh = vel_slide.mean() - 1.5 * vel_slide.std()
ax.axhline(anomaly_thresh, color='red', lw=1.5, linestyle=':',
           label=f'Ngưỡng dị thường: {anomaly_thresh:.1f}')
ax.set_xlabel('Năm từ 2017'); ax.set_ylabel('Vận tốc (cm/năm)')
ax.set_title('(e) Vận tốc tức thời (sliding window 3 tháng)\n'
             '[Phát hiện đột biến khai thác]', fontweight='bold')
ax.legend(fontsize=7); ax.grid(alpha=0.3)

# (f) Hazard map final
ax = fig.add_subplot(gs[2, :2])
haz_colors = ['#2d3436', '#00b894', '#fdcb6e', '#e17055', '#d63031']
haz_labels = ['Ổn định', 'Cấp 1 (Thấp)', 'Cấp 2 (TB)', 'Cấp 3 (Cao)', 'Cấp 4 (Rất cao)']
haz_cmap = LinearSegmentedColormap.from_list('hazard', haz_colors, N=5)
im_h = ax.pcolormesh(LON, LAT, hazard_map,
    cmap=haz_cmap, vmin=0, vmax=4, shading='auto')
plt.colorbar(im_h, ax=ax, label='Cấp độ nguy hiểm', shrink=0.85,
             ticks=[0,1,2,3,4])
ax.plot(MINE_LON, MINE_LAT, 'w*', ms=14, zorder=5)
# Contour DEM
cs_dem = ax.contour(LON, LAT, dem, levels=range(500, 1800, 200),
    colors='white', linewidths=0.5, alpha=0.3)
ax.set_title('(f) Bản đồ Phân vùng Nguy hiểm\n[Khai thác mỏ + Địa hình]',
             fontweight='bold')
ax.set_xlabel('Kinh độ °E'); ax.set_ylabel('Vĩ độ °N')

# (g) Area by hazard level (donut chart)
ax = fig.add_subplot(gs[2, 2])
haz_areas = [(hazard_map == i).sum() * (0.1**2) for i in range(5)]
non_zero_idx = [i for i in range(5) if haz_areas[i] > 0]
wedges, texts, autotexts = ax.pie(
    [haz_areas[i] for i in non_zero_idx],
    labels=[haz_labels[i] for i in non_zero_idx],
    colors=[haz_colors[i] for i in non_zero_idx],
    autopct='%1.1f%%', startangle=90,
    wedgeprops=dict(width=0.5)
)
ax.set_title('(g) Phân bố diện tích\ntheo cấp nguy hiểm (km²)', fontweight='bold')

# (h) N-S profile
ax = fig.add_subplot(gs[2, 3])
ax.fill_between(profile_dist_NS, profile_NS, 0,
    where=profile_NS < 0, alpha=0.4, color='steelblue')
ax.plot(profile_dist_NS, profile_NS, 'b-', lw=2, label='Profile N–S')
ax.plot(profile_dist_EW, profile_EW, 'r--', lw=1.5, alpha=0.7, label='Profile E–W')
ax.axvline(0, color='gray', lw=1, alpha=0.5, label='Tâm mỏ')
ax.set_xlabel('Khoảng cách (km)')
ax.set_ylabel('Vận tốc (cm/năm)')
ax.set_title('(h) So sánh Profile N–S vs E–W\n[Bất đối xứng do địa hình]',
             fontweight='bold')
ax.legend(fontsize=7); ax.grid(alpha=0.3)

os.makedirs("results/figures", exist_ok=True)
plt.savefig("results/figures/03_mining_deformation.png",
            dpi=150, bbox_inches='tight')
plt.close()
print("✅ Đã lưu: results/figures/03_mining_deformation.png")
