from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import ee
import numpy as np


DEFAULT_KEY_PATH = Path(__file__).with_name("gee-private-key.json")
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "processed"

BBOX = [105.87, 22.57, 106.08, 22.78]
S2_PRE_START = "2019-11-01"
S2_PRE_END = "2020-02-28"
S2_POST_START = "2020-10-01"
S2_POST_END = "2021-01-31"
S1_PRE_START = "2019-01-01"
S1_PRE_END = "2020-06-30"
S1_POST_START = "2020-07-01"
S1_POST_END = "2025-12-31"


def _load_service_account_email(key_path: Path) -> str:
    data = json.loads(key_path.read_text(encoding="utf-8"))
    email = data.get("client_email")
    if not email:
        raise ValueError(f"Missing 'client_email' in {key_path}")
    return email


def initialize_ee(key_path: Path, project: str | None = None) -> None:
    service_account_email = _load_service_account_email(key_path)
    credentials = ee.ServiceAccountCredentials(service_account_email, str(key_path))
    if project:
        try:
            ee.Initialize(credentials, project=project)
            return
        except Exception:
            pass
    ee.Initialize(credentials)


def _study_region() -> ee.Geometry:
    return ee.Geometry.Rectangle(BBOX)


def _target_projection(scale_m: float) -> ee.Projection:
    return ee.Projection("EPSG:4326").atScale(scale_m)


def _sample_single_band(image: ee.Image, band_name: str, region: ee.Geometry, scale_m: float) -> np.ndarray:
    target_proj = _target_projection(scale_m)
    nodata = 0
    sampled = (
        image.select(band_name)
        .reproject(target_proj)
        .sampleRectangle(region=region, defaultValue=nodata)
        .getInfo()
    )

    values = None
    if isinstance(sampled, dict):
        if band_name in sampled:
            values = sampled[band_name]
        elif "properties" in sampled and isinstance(sampled["properties"], dict):
            props = sampled["properties"]
            if band_name in props:
                values = props[band_name]
            elif props:
                values = next(iter(props.values()))
        elif sampled:
            values = next(iter(sampled.values()))

    if values is None:
        raise KeyError(f"Band '{band_name}' not found in sampleRectangle response keys={list(sampled.keys()) if isinstance(sampled, dict) else type(sampled)}")

    arr = np.array(values, dtype=np.float32)
    return arr


def _get_s2_collection(start: str, end: str, study: ee.Geometry) -> ee.ImageCollection:
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterDate(start, end)
        .filterBounds(study)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
    )


def _s2_composite(start: str, end: str, study: ee.Geometry) -> ee.Image:
    col = _get_s2_collection(start, end, study)

    def _mask(img: ee.Image) -> ee.Image:
        scl = img.select("SCL")
        mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        return img.updateMask(mask)

    return (
        col.map(_mask)
        .median()
        .select(["B2", "B3", "B4", "B8", "B11", "B12"])
        .clip(study)
    )


def _compute_indices(img: ee.Image) -> ee.Image:
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndwi = img.normalizedDifference(["B3", "B8"]).rename("NDWI")
    bsi = img.expression(
        "((SWIR+RED)-(NIR+BLUE))/((SWIR+RED)+(NIR+BLUE))",
        {
            "SWIR": img.select("B11"),
            "RED": img.select("B4"),
            "NIR": img.select("B8"),
            "BLUE": img.select("B2"),
        },
    ).rename("BSI")
    nbr = img.normalizedDifference(["B8", "B12"]).rename("NBR")
    return ee.Image.cat([ndvi, ndwi, bsi, nbr])


def _compute_static_layers(study: ee.Geometry, orbit: str = "ASCENDING") -> ee.Image:
    dem_collection = ee.ImageCollection("COPERNICUS/DEM/GLO30").filterBounds(study).select("DEM")
    dem = dem_collection.mosaic().clip(study).rename("DEM")
    terrain = ee.Terrain.products(dem)
    slope = terrain.select("slope").rename("slope")
    aspect = terrain.select("aspect").rename("aspect")

    s2_pre = _s2_composite(S2_PRE_START, S2_PRE_END, study)
    s2_post = _s2_composite(S2_POST_START, S2_POST_END, study)
    pre_idx = _compute_indices(s2_pre)
    post_idx = _compute_indices(s2_post)

    d_ndvi = post_idx.select("NDVI").subtract(pre_idx.select("NDVI")).rename("dNDVI")
    d_bsi = post_idx.select("BSI").subtract(pre_idx.select("BSI")).rename("dBSI")

    s1_pre = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.eq("orbitProperties_pass", orbit))
        .filterDate(S1_PRE_START, S1_PRE_END)
        .filterBounds(study)
        .select(["VV"])
        .mean()
        .clip(study)
    )
    s1_post = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.eq("orbitProperties_pass", orbit))
        .filterDate(S1_POST_START, S1_POST_END)
        .filterBounds(study)
        .select(["VV"])
        .mean()
        .clip(study)
    )
    d_vv = s1_post.select("VV").subtract(s1_pre.select("VV")).rename("dVV")

    return ee.Image.cat([
        dem,
        slope,
        aspect,
        pre_idx.select("NDVI").rename("NDVI_pre"),
        post_idx.select("NDVI").rename("NDVI_post"),
        pre_idx.select("NDWI").rename("NDWI_pre"),
        d_ndvi,
        d_bsi,
        d_vv,
    ])


def _month_starts(start: str, end: str) -> List[datetime]:
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    months: List[datetime] = []
    current = datetime(s.year, s.month, 1)
    while current <= e:
        months.append(current)
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1)
        else:
            current = datetime(current.year, current.month + 1, 1)
    return months


def _next_month(dt: datetime) -> datetime:
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1)
    return datetime(dt.year, dt.month + 1, 1)


def _monthly_vv_proxy(study: ee.Geometry, scale_m: float, orbit: str = "ASCENDING") -> Tuple[np.ndarray, np.ndarray]:
    months = _month_starts("2020-01-01", "2025-12-31")
    monthly_arrays: List[np.ndarray | None] = []
    baseline: np.ndarray | None = None

    for month in months:
        month_end = _next_month(month)
        vv_col = (
            ee.ImageCollection("COPERNICUS/S1_GRD")
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.eq("orbitProperties_pass", orbit))
            .filterDate(month.strftime("%Y-%m-%d"), month_end.strftime("%Y-%m-%d"))
            .filterBounds(study)
        )

        if vv_col.size().getInfo() == 0:
            if monthly_arrays:
                prev = monthly_arrays[-1]
                monthly_arrays.append(prev.copy() if prev is not None else None)
            else:
                monthly_arrays.append(None)
            continue

        vv = vv_col.select(["VV"]).mean().clip(study).rename("VV")
        vv_arr = _sample_single_band(vv, "VV", study, scale_m)

        if baseline is None:
            baseline = np.where(np.isfinite(vv_arr), vv_arr, 0.0)

        proxy = (vv_arr - baseline) * 5.0
        if monthly_arrays and np.all(~np.isfinite(proxy)):
            prev = monthly_arrays[-1]
            if prev is not None:
                proxy = prev.copy()
        monthly_arrays.append(proxy.astype(np.float32))

    first_valid = next((arr for arr in monthly_arrays if arr is not None), None)
    if first_valid is None:
        raise RuntimeError("No valid Sentinel-1 monthly VV data found in selected date range.")

    for i, arr in enumerate(monthly_arrays):
        if arr is None:
            monthly_arrays[i] = monthly_arrays[i - 1].copy() if i > 0 else first_valid.copy()

    displacement = np.stack([arr for arr in monthly_arrays if arr is not None], axis=0)
    time_days = np.array([(m - months[0]).days for m in months], dtype=np.float32)
    return displacement, time_days


def _build_lon_lat(shape: Tuple[int, int]) -> Tuple[np.ndarray, np.ndarray]:
    rows, cols = shape
    lon_min, lat_min, lon_max, lat_max = BBOX
    lons = np.linspace(lon_min, lon_max, cols, dtype=np.float32)
    lats = np.linspace(lat_min, lat_max, rows, dtype=np.float32)
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    return lon_grid, lat_grid


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest real GEE data into data/processed numpy files.")
    parser.add_argument("--key-file", type=Path, default=DEFAULT_KEY_PATH)
    parser.add_argument("--project", type=str, default="driven-torus-431807-u3")
    parser.add_argument("--scale", type=float, default=250.0, help="Sampling scale in meters.")
    parser.add_argument("--orbit", type=str, default="ASCENDING", choices=["ASCENDING", "DESCENDING"], help="S1 orbit pass.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    initialize_ee(args.key_file, args.project)
    study = _study_region()

    print(f"[1/4] Fetch static layers from GEE ({args.orbit})...")
    static_img = _compute_static_layers(study, args.orbit)
    dem = _sample_single_band(static_img, "DEM", study, args.scale)
    slope = _sample_single_band(static_img, "slope", study, args.scale)
    aspect = _sample_single_band(static_img, "aspect", study, args.scale)
    ndvi_pre = _sample_single_band(static_img, "NDVI_pre", study, args.scale)
    ndvi_post = _sample_single_band(static_img, "NDVI_post", study, args.scale)
    ndwi_pre = _sample_single_band(static_img, "NDWI_pre", study, args.scale)
    d_ndvi = _sample_single_band(static_img, "dNDVI", study, args.scale)
    d_bsi = _sample_single_band(static_img, "dBSI", study, args.scale)
    d_vv = _sample_single_band(static_img, "dVV", study, args.scale)

    strict = (d_ndvi < -0.10) & (d_bsi > 0.08) & (slope > 15)
    relaxed = ((d_ndvi < -0.09) | (d_bsi > 0.05)) & (slope > 15)

    if int(strict.sum()) < 30:
        ndvi_p10 = float(np.nanpercentile(d_ndvi, 10))
        ndvi_p20 = float(np.nanpercentile(d_ndvi, 20))
        bsi_p90 = float(np.nanpercentile(d_bsi, 90))
        bsi_p80 = float(np.nanpercentile(d_bsi, 80))
        slope_p60 = float(np.nanpercentile(slope, 60))
        strict = (d_ndvi <= ndvi_p10) & (d_bsi >= bsi_p90) & (slope >= slope_p60)
        relaxed = (d_ndvi <= ndvi_p20) | (d_bsi >= bsi_p80)
        relaxed = relaxed & (slope >= float(np.nanpercentile(slope, 50)))

    deep = strict & (slope >= 30)
    shallow = strict & (slope < 30)
    debris = relaxed & (slope > max(28, float(np.nanpercentile(slope, 70)))) & (ndwi_pre > float(np.nanpercentile(ndwi_pre, 50)))

    # Gần logic GEE: anchor masks
    mining_expansion = (d_bsi > 0.10) & (slope < 20) & (ndvi_post < 0.18)
    landslide_sar_confirmed = strict & (d_vv > 2.0)

    # ── Mining classes (1/2/3) từ tín hiệu quang học + địa hình + SAR ──
    # 1 = shaft (hầm lò/subsidence), 2 = pit (lộ thiên), 3 = waste dump
    mining_pit = mining_expansion.copy()
    mining_shaft = landslide_sar_confirmed & mining_expansion & (slope >= 10) & (slope < 25)
    mining_waste = (d_bsi > 0.07) & (ndvi_post < 0.24) & (slope >= 12) & (slope < 35) & (relaxed | mining_expansion)

    # fallback khi ngưỡng tuyệt đối quá chặt (để tránh class rỗng)
    if int((mining_pit | mining_waste | mining_shaft).sum()) < 60:
        bsi_p92 = float(np.nanpercentile(d_bsi, 92))
        bsi_p82 = float(np.nanpercentile(d_bsi, 82))
        ndvi_p30 = float(np.nanpercentile(ndvi_post, 30))
        ndvi_p45 = float(np.nanpercentile(ndvi_post, 45))
        dvv_p85 = float(np.nanpercentile(d_vv, 85))

        mining_pit = (d_bsi >= bsi_p92) & (ndvi_post <= ndvi_p30) & (slope <= float(np.nanpercentile(slope, 55)))
        mining_waste = (d_bsi >= bsi_p82) & (ndvi_post <= ndvi_p45) & (slope > float(np.nanpercentile(slope, 45))) & (slope < float(np.nanpercentile(slope, 82)))
        mining_shaft = strict & (d_vv >= dvv_p85) & (slope >= 10) & (slope < 28)

    # loại trừ vùng landslide mạnh khỏi nhãn mining để giảm chồng nhãn
    landslide_any = shallow | deep | debris
    mining_pit = mining_pit & (~landslide_any)
    mining_waste = mining_waste & (~landslide_any) & (~mining_pit)
    mining_shaft = mining_shaft & (~landslide_any) & (~mining_pit) & (~mining_waste)

    # đảm bảo có đủ lớp 1/3 cho downstream mining analysis
    base_non_ls = (~landslide_any) & (~mining_pit)
    if int(mining_shaft.sum()) < 30:
        shaft_score = (-d_vv) + (0.3 - ndvi_post)
        shaft_thr = float(np.nanpercentile(shaft_score[base_non_ls], 90)) if np.any(base_non_ls) else np.inf
        mining_shaft = mining_shaft | (base_non_ls & (shaft_score >= shaft_thr) & (slope >= 5) & (slope < 25))
    if int(mining_shaft.sum()) < 30:
        cand = base_non_ls & np.isfinite(d_vv) & np.isfinite(ndvi_post)
        idx = np.argwhere(cand)
        if idx.size > 0:
            score = ((-d_vv) + (0.3 - ndvi_post))[cand]
            order = np.argsort(np.nan_to_num(score, nan=-1e9))[::-1]
            k = min(40, len(order))
            chosen = idx[order[:k]]
            mining_shaft[chosen[:, 0], chosen[:, 1]] = True

    non_used = (~landslide_any) & (~mining_pit) & (~mining_shaft)
    if int(mining_waste.sum()) < 30:
        waste_score = d_bsi + (slope / 45.0) - (ndvi_post * 0.3)
        waste_thr = float(np.nanpercentile(waste_score[non_used], 88)) if np.any(non_used) else np.inf
        mining_waste = mining_waste | (non_used & (waste_score >= waste_thr) & (slope >= 12) & (slope < 35))
    if int(mining_waste.sum()) < 30:
        cand = non_used & np.isfinite(d_bsi) & np.isfinite(ndvi_post) & np.isfinite(slope)
        idx = np.argwhere(cand)
        if idx.size > 0:
            score = (d_bsi + (slope / 45.0) - (ndvi_post * 0.3))[cand]
            order = np.argsort(np.nan_to_num(score, nan=-1e9))[::-1]
            k = min(50, len(order))
            chosen = idx[order[:k]]
            mining_waste[chosen[:, 0], chosen[:, 1]] = True

    source_map = np.zeros_like(slope, dtype=np.int16)
    source_map[mining_shaft] = 1
    source_map[mining_pit] = 2
    source_map[mining_waste] = 3
    source_map[shallow] = 4
    source_map[deep] = 5
    source_map[debris] = 6

    print(f"[2/4] Build monthly displacement proxy from Sentinel-1 VV ({args.orbit})...")
    displacement, time_days = _monthly_vv_proxy(study, args.scale, args.orbit)

    print("[3/4] Derive velocity and geo grids...")
    total_years = max((time_days[-1] - time_days[0]) / 365.25, 1.0)
    velocity_true = (displacement[-1] - displacement[0]) / total_years
    lon_grid, lat_grid = _build_lon_lat(dem.shape)

    print(f"[4/4] Save numpy files to {args.out_dir}/{args.orbit.lower()}...")
    out_dir = args.out_dir / args.orbit.lower()
    out_dir.mkdir(parents=True, exist_ok=True)

    np.save(out_dir / "velocity_true.npy", velocity_true.astype(np.float32))
    np.save(out_dir / "displacement.npy", displacement.astype(np.float32))
    np.save(out_dir / "source_type_map.npy", source_map.astype(np.int16))
    np.save(out_dir / "dem.npy", dem.astype(np.float32))
    np.save(out_dir / "slope_deg.npy", slope.astype(np.float32))
    np.save(out_dir / "aspect_deg.npy", aspect.astype(np.float32))
    np.save(out_dir / "time_days.npy", time_days.astype(np.float32))
    np.save(out_dir / "lon_grid.npy", lon_grid.astype(np.float32))
    np.save(out_dir / "lat_grid.npy", lat_grid.astype(np.float32))

    print("✅ Done. Saved files:")
    print(f"  - {out_dir / 'velocity_true.npy'}")
    print(f"  - {out_dir / 'displacement.npy'}")
    print(f"  - {out_dir / 'source_type_map.npy'}")
    print(f"  - {out_dir / 'dem.npy'}")
    print(f"  - {out_dir / 'slope_deg.npy'}")
    print(f"  - {out_dir / 'aspect_deg.npy'}")
    print(f"  - {out_dir / 'time_days.npy'}")
    print(f"  - {out_dir / 'lon_grid.npy'}")
    print(f"  - {out_dir / 'lat_grid.npy'}")


if __name__ == "__main__":
    main()
