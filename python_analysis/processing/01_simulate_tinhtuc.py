"""
=============================================================================
python_analysis/processing/01_simulate_tinhtuc.py
Mô phỏng dữ liệu InSAR thực tế cho Xã Tĩnh Túc, Cao Bằng
━━ Đặc thù: Mỏ thiếc + địa hình dốc + sạt lở nhiệt đới ━━

Các nguồn biến dạng được mô phỏng:
  A. Sụt lún do khai thác hầm lò (mining subsidence)
  B. Mở rộng khai thác lộ thiên (open-pit expansion)
  C. Sạt lở đất sườn dốc (shallow + deep-seated)
  D. Trượt lở đất chảy (debris flow)
  E. Biến dạng nền (background seasonal)
=============================================================================
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap, BoundaryNorm
from scipy.ndimage import gaussian_filter, label
import os, warnings
warnings.filterwarnings('ignore')

print("=" * 65)
print("  🛰️  Mô phỏng InSAR — Tĩnh Túc, Cao Bằng")
print("  Mỏ thiếc + Sạt lở + Địa hình núi dốc")
print("=" * 65)

# ─── CẤU HÌNH KHU VỰC ────────────────────────────────────────────────────
# Miền không gian nghiên cứu (AOI) theo lon/lat.
# Dải này bám theo polygon GEE của khu Tĩnh Túc.
LON_MIN, LON_MAX = 105.87, 106.08
LAT_MIN, LAT_MAX = 22.57,  22.78
NX, NY   = 210, 210          # ~100m/pixel
NTIME    = 96                # 8 năm × 12 ảnh/năm (12-day)
DT       = 12                # ngày
WAVELENGTH = 0.056           # C-band (m)

lons = np.linspace(LON_MIN, LON_MAX, NX)
lats = np.linspace(LAT_MIN, LAT_MAX, NY)
LON, LAT = np.meshgrid(lons, lats)

np.random.seed(2024)
print(f"\n✅ Grid: {NX}×{NY} pixels | {NTIME} time steps")
print(f"   Pixel size: ~{(LON_MAX-LON_MIN)/NX*111:.2f} km")

# ─── 1. TẠO ĐỊA HÌNH THỰC TẾ (DEM GIẢ LẬP) ─────────────────────────────
def create_dem(lon_grid, lat_grid):
    """
    DEM giả lập cho Tĩnh Túc:
    - Thung lũng sông Bắc Vọng ở trung tâm (400–500m)
    - Dãy núi phía Bắc và Nam (1200–1800m)
    - Khu mỏ thiếc trên sườn đồi (600–900m)
    """
    ny, nx = lon_grid.shape
    x_norm = (lon_grid - LON_MIN) / (LON_MAX - LON_MIN)
    y_norm = (lat_grid - LAT_MIN) / (LAT_MAX - LAT_MIN)

    # Nền: thung lũng hình chữ U
    dem = 600 + 800 * (0.5 - np.abs(y_norm - 0.5))**0.5 * 0.5

    # Dãy núi phía Bắc (lat > 22.73)
    north_ridge = 1200 * np.exp(-((y_norm - 1.0)**2) / 0.04)
    dem += north_ridge

    # Dãy núi phía Nam (lat < 22.60)
    south_ridge = 900 * np.exp(-((y_norm - 0.0)**2) / 0.03)
    dem += south_ridge

    # Đỉnh núi phía Tây
    west_peak = 600 * np.exp(-((x_norm - 0.0)**2 + (y_norm - 0.6)**2) / 0.02)
    dem += west_peak

    # Thung lũng trung tâm (khu mỏ) — thấp hơn
    mine_valley = -300 * np.exp(-((x_norm - 0.43)**2 + (y_norm - 0.55)**2) / 0.015)
    dem += mine_valley

    # Làm mịn tự nhiên
    dem = gaussian_filter(dem, sigma=4.0)
    dem = np.clip(dem, 350, 1850)
    return dem

dem = create_dem(LON, LAT)

# Tính slope từ DEM
# gradient theo lat/lon được đổi về m/m bằng hệ số ~111 km/độ.
# Đây là xấp xỉ đủ tốt cho mô phỏng quy mô xã.
dy = np.gradient(dem, axis=0) / ((LAT_MAX-LAT_MIN)/NY*111000)  # m/m
dx = np.gradient(dem, axis=1) / ((LON_MAX-LON_MIN)/NX*111000)
slope_deg = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
aspect_deg = np.degrees(np.arctan2(-dx, dy)) % 360

print(f"\n✅ DEM: {dem.min():.0f}–{dem.max():.0f} m")
print(f"   Slope: mean={slope_deg.mean():.1f}°, max={slope_deg.max():.1f}°")
print(f"   >30°: {(slope_deg>30).mean()*100:.1f}% diện tích")

# ─── 2. ĐỊNH NGHĨA VỊ TRÍ CÁC NGUỒN BIẾN DẠNG ───────────────────────────
def lonlat_to_px(lon, lat):
    # Chuyển tọa độ địa lý -> chỉ số pixel trên lưới mô phỏng.
    # Kết quả được clip để luôn nằm trong [0, NX-1] và [0, NY-1].
    col = int((lon - LON_MIN) / (LON_MAX - LON_MIN) * NX)
    row = int((lat - LAT_MIN) / (LAT_MAX - LAT_MIN) * NY)
    return np.clip(col, 0, NX-1), np.clip(row, 0, NY-1)

# Vị trí khu mỏ thiếc và các điểm sạt lở (tọa độ thực tế ước tính)
SOURCES = {
    # Khai thác hầm lò chính (mining shaft subsidence)
    'mine_shaft_1': {'lon': 105.975, 'lat': 22.675, 'type': 'mining',
                     'velocity': -8.5, 'radius': 12, 'depth': 'deep'},
    'mine_shaft_2': {'lon': 105.960, 'lat': 22.660, 'type': 'mining',
                     'velocity': -5.2, 'radius': 8,  'depth': 'medium'},
    # Khu lộ thiên (open pit)
    'open_pit':     {'lon': 105.990, 'lat': 22.680, 'type': 'openpit',
                     'velocity': -3.8, 'radius': 15, 'depth': 'surface'},
    # Bãi thải (waste dump) — nén lún
    'waste_dump':   {'lon': 105.955, 'lat': 22.645, 'type': 'waste',
                     'velocity': -4.2, 'radius': 10, 'depth': 'medium'},
    # Sạt lở sườn Tây Bắc (trượt nông)
    'landslide_NW': {'lon': 105.935, 'lat': 22.720, 'type': 'shallow_slide',
                     'velocity': -12.0, 'radius': 7, 'depth': 'surface'},
    # Trượt sâu sườn phía Nam
    'deepslide_S':  {'lon': 105.980, 'lat': 22.580, 'type': 'deep_slide',
                     'velocity': -18.5, 'radius': 9, 'depth': 'deep'},
    # Đất chảy (debris flow) dọc sườn dốc
    'debris_E':     {'lon': 106.050, 'lat': 22.650, 'type': 'debris_flow',
                     'velocity': -25.0, 'radius': 5, 'depth': 'surface'},
    # Nứt đất nhỏ gần mỏ
    'crack_mine':   {'lon': 105.968, 'lat': 22.695, 'type': 'crack',
                     'velocity': -6.8, 'radius': 6, 'depth': 'surface'},
}

# ─── 3. TẠO TRƯỜNG VẬN TỐC THỰC TẾ ─────────────────────────────────────
print("\n🔧 Tạo trường vận tốc...")

velocity_total = np.zeros((NY, NX))
# Mask loại nguồn
source_type_map = np.zeros((NY, NX), dtype=int)
# 0=stable, 1=mining, 2=openpit, 3=waste, 4=shallow_slide, 5=deep_slide,
# 6=debris_flow, 7=crack

type_to_int = {'mining':1, 'openpit':2, 'waste':3, 'shallow_slide':4,
               'deep_slide':5, 'debris_flow':6, 'crack':7}

y_idx, x_idx = np.ogrid[:NY, :NX]

for name, src in SOURCES.items():
    col, row = lonlat_to_px(src['lon'], src['lat'])
    # Khoảng cách Euclid từ mọi pixel đến tâm nguồn biến dạng.
    r = np.sqrt((x_idx - col)**2 + (y_idx - row)**2)
    sigma = src['radius']
    # Mô hình không gian Gaussian: biên độ lớn nhất ở tâm và giảm dần theo khoảng cách.
    # velocity âm => lún/trượt theo hướng xuống.
    contribution = src['velocity'] * np.exp(-r**2 / (sigma**2))
    velocity_total += contribution

    # Cập nhật type map (ưu tiên loại biến dạng mạnh nhất)
    mask_src = r < sigma * 1.2
    stype = type_to_int[src['type']]
    source_type_map = np.where(
        mask_src & (np.abs(contribution) > 1.0),
        stype, source_type_map
    )

# Làm mịn (gradient tự nhiên)
velocity_total = gaussian_filter(velocity_total, sigma=1.5)

# Nền nhỏ: biến dạng tổng thể do trọng lực + mưa
# Thành phần nền dạng sin theo trục đông-tây để tạo bất đồng nhất nhẹ toàn vùng.
background = 0.3 * np.sin(np.pi * (LON - LON_MIN) / (LON_MAX - LON_MIN))
velocity_total += background

print(f"  Velocity range: {velocity_total.min():.1f} – {velocity_total.max():.1f} cm/năm")
print(f"  Phân vùng:")
for tname, tint in type_to_int.items():
    n = (source_type_map == tint).sum()
    pct = n / (NX*NY) * 100
    if n > 0:
        print(f"    {tname:<20}: {n:5d} pixels ({pct:.1f}%)")

# ─── 4. TẠO CHUỖI THỜI GIAN VỚI DYNAMICS ─────────────────────────────────
print("\n📅 Tạo chuỗi thời gian...")

time_days = np.arange(0, NTIME * DT, DT)
years     = time_days / 365.25

def create_timeseries_tinhtuc(velocity, time_years, source_type_map):
    """
    Chuỗi thời gian đặc thù cho Tĩnh Túc:
    - Khai thác mỏ: tuyến tính + tăng dần (khai thác mở rộng sau 2020)
    - Sạt lở: đột ngột + tăng dần (creep trước khi xảy ra)
    - Mùa mưa: tăng tốc biến dạng (tháng 6–9)
    """
    ny, nx = velocity.shape
    n_t = len(time_years)
    ts = np.zeros((n_t, ny, nx))

    for t_idx, t in enumerate(time_years):
        # Tuyến tính cơ bản
        # disp(t) = v * t, với v theo đơn vị cm/năm.
        disp = velocity * t

        # Tăng tốc khai thác sau 2020 (year 3+)
        mining_mask = (source_type_map == 1) | (source_type_map == 2)
        if t > 3.0:
            extra_mining = velocity * np.where(mining_mask, 0.2 * (t - 3.0), 0)
            disp += extra_mining

        # Đột biến sạt lở: debris flow xảy ra năm thứ 4 (2021)
        debris_mask = (source_type_map == 6)
        if t >= 4.0:
            slide_event = velocity * np.where(debris_mask, 1.5, 0)
            disp += slide_event  # Dịch chuyển đột ngột

        # Creep trước sạt lở sâu (tăng tốc trước năm 5)
        deep_mask = (source_type_map == 5)
        if 3.0 < t < 5.0:
            creep = velocity * np.where(deep_mask, 0.4 * (t - 3.0), 0)
            disp += creep
        elif t >= 5.0:
            # Tăng mạnh sau sự kiện
            post_event = velocity * np.where(deep_mask, 0.6 * (t - 5.0) + 0.8, 0)
            disp += post_event

        # Mùa vụ: mưa Cao Bằng (tháng 5–10)
        # Biên độ mùa vụ phụ thuộc loại: sạt lở > mỏ > ổn định
        # np.select tạo bản đồ biên độ theo từng loại nguồn, giúp không gian không đồng nhất.
        amp_map = np.select(
            [source_type_map == 4, source_type_map == 5, source_type_map == 6,
             source_type_map == 1, source_type_map == 3],
            [0.25, 0.30, 0.40, 0.10, 0.15],
            default=0.05
        )
        seasonal_amp = np.abs(velocity) * amp_map
        seasonal = seasonal_amp * np.sin(2*np.pi*t - np.pi/4)  # Cao điểm tháng 8
        disp += seasonal

        # Nhiễu đại khí quyển (lớn hơn vì địa hình núi)
        # Tổ hợp tương quan xa + gần để gần với đặc tính nhiễu pha InSAR thực tế.
        atm = gaussian_filter(
            np.random.normal(0, 0.5, (ny, nx)), sigma=6.0  # Long-range corr.
        )
        atm += gaussian_filter(
            np.random.normal(0, 0.2, (ny, nx)), sigma=2.0  # Short-range
        )
        ts[t_idx] = disp + atm

    return ts

displacement = create_timeseries_tinhtuc(velocity_total, years, source_type_map)
print(f"  ✅ Shape: {displacement.shape}")
print(f"  Displacement range (year 8): {displacement[-1].min():.1f} – {displacement[-1].max():.1f} cm")

# ─── 5. CHIẾU SAR LOS ────────────────────────────────────────────────────
# Sentinel-1 Ascending Track 18 (cho vùng Cao Bằng)
INC_ASC  = np.radians(39.0)
AZ_ASC   = np.radians(-10.5)

# Tính LOS projection (chủ yếu thẳng đứng, có thành phần ngang)
cos_inc = np.cos(INC_ASC)
sin_inc = np.sin(INC_ASC)
los_factor = cos_inc  # cho chuyển động thẳng đứng

# Giả định chuyển động chi phối theo phương đứng: LOS ≈ vertical * cos(incidence).
# Nếu cần mô hình đầy đủ 3D (E, N, U), cần vector nhìn và trường dịch chuyển 3 thành phần.
los_disp = displacement * los_factor

# ─── 6. LƯU DỮ LIỆU ─────────────────────────────────────────────────────
os.makedirs("data/processed", exist_ok=True)
np.save("data/processed/velocity_true.npy",    velocity_total)
np.save("data/processed/displacement.npy",     displacement)
np.save("data/processed/los_disp.npy",         los_disp)
np.save("data/processed/source_type_map.npy",  source_type_map)
np.save("data/processed/dem.npy",              dem)
np.save("data/processed/slope_deg.npy",        slope_deg)
np.save("data/processed/aspect_deg.npy",       aspect_deg)
np.save("data/processed/time_days.npy",        time_days)
np.save("data/processed/lon_grid.npy",         LON)
np.save("data/processed/lat_grid.npy",         LAT)
print("\n💾 Tất cả dữ liệu đã lưu vào data/processed/")

# ─── 7. VISUALIZATION ────────────────────────────────────────────────────
print("\n🎨 Tạo visualization...")

fig = plt.figure(figsize=(22, 16))
fig.patch.set_facecolor('#1a1a2e')
fig.suptitle("Mô phỏng InSAR — Xã Tĩnh Túc, Tỉnh Cao Bằng\n"
             "Mỏ thiếc · Sạt lở · Địa hình Núi | Sentinel-1 2017–2024",
             fontsize=15, fontweight='bold', color='white')

gs = gridspec.GridSpec(3, 4, figure=fig, hspace=0.45, wspace=0.35)

plot_kwargs = dict(shading='auto')
cbar_kw = dict(shrink=0.85)

# (a) DEM
ax = fig.add_subplot(gs[0, 0])
ax.set_facecolor('#1a1a2e')
im = ax.pcolormesh(LON, LAT, dem,
    cmap='terrain', vmin=300, vmax=1900, **plot_kwargs)
plt.colorbar(im, ax=ax, label='m', **cbar_kw).ax.yaxis.label.set_color('white')
ax.set_title('(a) DEM Copernicus 30m', fontweight='bold', color='white')
ax.tick_params(colors='white'); ax.set_xlabel('Lon°E', color='white')
ax.set_ylabel('Lat°N', color='white')
for src in SOURCES.values():
    c, r = lonlat_to_px(src['lon'], src['lat'])
    ax.plot(lons[c], lats[r], 'w+', ms=8, mew=1.5)

# (b) Slope
ax = fig.add_subplot(gs[0, 1])
ax.set_facecolor('#1a1a2e')
im = ax.pcolormesh(LON, LAT, slope_deg,
    cmap='YlOrRd', vmin=0, vmax=50, **plot_kwargs)
plt.colorbar(im, ax=ax, label='độ (°)', **cbar_kw)
cs = ax.contour(LON, LAT, slope_deg,
    levels=[15, 25, 35], colors='white', linewidths=0.7, alpha=0.6)
ax.clabel(cs, fmt='%d°', fontsize=7, colors='white')
ax.set_title('(b) Độ dốc\n[Đỏ đậm = nguy cơ sạt lở cao]', fontweight='bold', color='white')
ax.tick_params(colors='white')

# (c) Velocity field
ax = fig.add_subplot(gs[0, 2])
ax.set_facecolor('#1a1a2e')
im = ax.pcolormesh(LON, LAT, velocity_total,
    cmap='RdBu_r', vmin=-25, vmax=5, **plot_kwargs)
plt.colorbar(im, ax=ax, label='cm/năm', **cbar_kw)
ax.set_title('(c) Trường vận tốc biến dạng\n[Ground Truth]', fontweight='bold', color='white')
ax.tick_params(colors='white')
# Label nguồn
source_labels = {
    'mine_shaft_1': 'Hầm lò 1', 'open_pit': 'Lộ thiên',
    'landslide_NW': 'Sạt lở TN', 'deepslide_S': 'Trượt sâu',
    'debris_E': 'Đất chảy'
}
for key, label in source_labels.items():
    s = SOURCES[key]; c, r = lonlat_to_px(s['lon'], s['lat'])
    ax.annotate(label, (lons[c], lats[r]), fontsize=6.5,
        color='yellow', fontweight='bold',
        xytext=(5, 5), textcoords='offset points')

# (d) Source type map
ax = fig.add_subplot(gs[0, 3])
ax.set_facecolor('#1a1a2e')
type_colors = ['#2d3436','#d63031','#e17055','#fdcb6e',
               '#74b9ff','#0984e3','#a29bfe','#fd79a8']
type_labels = ['Ổn định','Hầm lò','Lộ thiên','Bãi thải',
               'Trượt nông','Trượt sâu','Đất chảy','Nứt đất']
cmap_type = ListedColormap(type_colors)
norm_type = BoundaryNorm(range(9), len(type_colors))
im = ax.pcolormesh(LON, LAT, source_type_map,
    cmap=cmap_type, norm=norm_type, **plot_kwargs)
patches = [mpatches.Patch(color=type_colors[i], label=type_labels[i])
           for i in range(len(type_labels)) if (source_type_map == i).sum() > 0]
ax.legend(handles=patches, loc='upper right', fontsize=6,
          framealpha=0.7, facecolor='#2d3436', labelcolor='white')
ax.set_title('(d) Phân loại nguồn biến dạng', fontweight='bold', color='white')
ax.tick_params(colors='white')

# (e) Displacement map cuối kỳ
ax = fig.add_subplot(gs[1, :2])
ax.set_facecolor('#1a1a2e')
im = ax.pcolormesh(LON, LAT, displacement[-1],
    cmap='RdBu_r', vmin=-180, vmax=20, **plot_kwargs)
plt.colorbar(im, ax=ax, label='Displacement tích lũy (cm)', **cbar_kw)
cs2 = ax.contour(LON, LAT, displacement[-1],
    levels=[-150,-100,-50,-20], colors='yellow', linewidths=0.8, alpha=0.7)
ax.clabel(cs2, fmt='%d cm', fontsize=7, colors='yellow')
ax.set_title('(e) Chuyển vị tích lũy 2017–2024\n[Tổng 8 năm]',
             fontweight='bold', color='white')
ax.tick_params(colors='white')

# (f) Time-series tại các điểm quan trắc
ax = fig.add_subplot(gs[1, 2:])
ax.set_facecolor('#1a1a2e')
monitor_points = [
    (105.975, 22.675, '#d63031', 'Hầm lò 1 (-8.5 cm/yr)'),
    (105.990, 22.680, '#e17055', 'Lộ thiên (-3.8 cm/yr)'),
    (105.935, 22.720, '#74b9ff', 'Sạt lở TN (-12 cm/yr)'),
    (105.980, 22.580, '#0984e3', 'Trượt sâu (-18.5 cm/yr)'),
    (106.050, 22.650, '#a29bfe', 'Đất chảy (-25 cm/yr)'),
]
for mlon, mlat, mcolor, mlabel in monitor_points:
    mc, mr = lonlat_to_px(mlon, mlat)
    # Lấy chuỗi thời gian tại pixel gần nhất với điểm quan trắc.
    ax.plot(years, displacement[:, mr, mc], '-', color=mcolor,
            lw=1.5, label=mlabel, alpha=0.9)
ax.axvline(3.0, color='orange', lw=1.5, linestyle='--', alpha=0.7,
           label='Tăng cường KT (2020)')
ax.axvline(4.0, color='yellow', lw=1.5, linestyle=':', alpha=0.7,
           label='Sự kiện đất chảy (2021)')
ax.set_xlabel('Năm từ 2017', color='white')
ax.set_ylabel('Displacement (cm)', color='white')
ax.set_title('(f) Chuỗi thời gian tại điểm quan trắc', fontweight='bold', color='white')
ax.legend(fontsize=7, facecolor='#2d3436', labelcolor='white')
ax.grid(alpha=0.2); ax.tick_params(colors='white')
ax.set_facecolor('#0d1117')

# (g) Velocity histogram by type
ax = fig.add_subplot(gs[2, :2])
ax.set_facecolor('#1a1a2e')
type_colors_plot = ['#d63031','#e17055','#fdcb6e','#74b9ff','#0984e3','#a29bfe','#fd79a8']
type_names_plot  = ['Hầm lò','Lộ thiên','Bãi thải','Trượt nông','Trượt sâu','Đất chảy','Nứt đất']
for tidx, (tc, tn) in enumerate(zip(type_colors_plot, type_names_plot), 1):
    mask = source_type_map == tidx
    if mask.sum() > 10:
        v_subset = velocity_total[mask]
        ax.hist(v_subset, bins=25, alpha=0.7, color=tc,
                label=f'{tn} (n={mask.sum()})', edgecolor='none')
ax.set_xlabel('Vận tốc biến dạng (cm/năm)', color='white')
ax.set_ylabel('Số pixel', color='white')
ax.set_title('(g) Phân phối vận tốc theo loại biến dạng', fontweight='bold', color='white')
ax.legend(fontsize=7, facecolor='#2d3436', labelcolor='white')
ax.grid(alpha=0.2); ax.tick_params(colors='white')
ax.set_facecolor('#0d1117')

# (h) Seasonal decomposition
ax = fig.add_subplot(gs[2, 2:])
ax.set_facecolor('#1a1a2e')
mc_mine, mr_mine = lonlat_to_px(105.975, 22.675)
mc_slide, mr_slide = lonlat_to_px(105.935, 22.720)
ts_mine  = displacement[:, mr_mine,  mc_mine]
ts_slide = displacement[:, mr_slide, mc_slide]

# Tách mùa vụ
# Ước lượng trend tuyến tính bằng polyfit bậc 1,
# sau đó phần dư được coi là thành phần mùa vụ dao động quanh 0.
trend_mine  = np.polyval(np.polyfit(years, ts_mine,  1), years)
trend_slide = np.polyval(np.polyfit(years, ts_slide, 1), years)
seasonal_mine  = ts_mine  - trend_mine
seasonal_slide = ts_slide - trend_slide

ax.fill_between(years, seasonal_mine, 0, alpha=0.5, color='#d63031',
                label='Hầm lò (mùa vụ)')
ax.fill_between(years, seasonal_slide, 0, alpha=0.5, color='#74b9ff',
                label='Sạt lở (mùa vụ)')
ax.axhline(0, color='white', lw=1)
# Highlight mùa mưa
for yr in range(8):
    ax.axvspan(yr + 4/12, yr + 9/12, alpha=0.08, color='cyan')
ax.text(0.3, ax.get_ylim()[1]*0.85 if ax.get_ylim()[1] != 0 else 1,
    'Mùa mưa\n(T5–T9)', fontsize=7, color='cyan', ha='center')
ax.set_xlabel('Năm từ 2017', color='white')
ax.set_ylabel('Thành phần mùa vụ (cm)', color='white')
ax.set_title('(h) Phân tách mùa vụ\n[Nền xanh = mùa mưa Cao Bằng]',
             fontweight='bold', color='white')
ax.legend(fontsize=8, facecolor='#2d3436', labelcolor='white')
ax.grid(alpha=0.2); ax.tick_params(colors='white')
ax.set_facecolor('#0d1117')

for ax in fig.get_axes():
    for spine in ax.spines.values():
        spine.set_edgecolor('#444')

os.makedirs("results/figures", exist_ok=True)
plt.savefig("results/figures/01_tinhtuc_simulation.png",
            dpi=150, bbox_inches='tight', facecolor='#1a1a2e')
plt.close()
print("✅ Đã lưu: results/figures/01_tinhtuc_simulation.png")

print(f"\n📊 Thống kê biến dạng:")
print(f"   Sụt lún khai thác (max): {velocity_total[source_type_map==1].min():.1f} cm/năm")
print(f"   Trượt sâu (max):         {velocity_total[source_type_map==5].min():.1f} cm/năm")
print(f"   Đất chảy (max):          {velocity_total[source_type_map==6].min():.1f} cm/năm")
print(f"   Diện tích nguy hiểm:     {(velocity_total < -5).mean()*100:.1f}% tổng khu vực")
