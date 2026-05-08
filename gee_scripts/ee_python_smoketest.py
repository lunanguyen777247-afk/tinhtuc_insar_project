from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import ee


DEFAULT_KEY_PATH = Path(__file__).with_name("gee-private-key.json")
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_service_account_email(key_path: Path) -> str:
    data = json.loads(key_path.read_text(encoding="utf-8"))
    email = data.get("client_email")
    if not email:
        raise ValueError(f"Missing 'client_email' in {key_path}")
    return email


def initialize_ee(key_path: Path, project: str | None = None) -> None:
    if not key_path.exists():
        raise FileNotFoundError(f"Service account key not found: {key_path}")

    service_account_email = _load_service_account_email(key_path)
    credentials = ee.ServiceAccountCredentials(service_account_email, str(key_path))

    if project:
        try:
            ee.Initialize(credentials, project=project)
            return
        except Exception:
            pass

    ee.Initialize(credentials)


def _get_study_geometry_from_settings() -> ee.Geometry:
    try:
        from config.settings import AOI  # type: ignore

        lon_min = AOI["lon_min"]
        lon_max = AOI["lon_max"]
        lat_min = AOI["lat_min"]
        lat_max = AOI["lat_max"]
        return ee.Geometry.Rectangle([lon_min, lat_min, lon_max, lat_max])
    except Exception:
        return ee.Geometry.Polygon([
            [
                [105.87, 22.57],
                [106.08, 22.57],
                [106.08, 22.78],
                [105.87, 22.78],
                [105.87, 22.57],
            ]
        ])


def _get_date_range_from_settings() -> tuple[str, str]:
    try:
        from config.settings import GEE_CONFIG  # type: ignore

        script01_dates = GEE_CONFIG.get("script01", {}).get("dates", {})
        if script01_dates.get("s2Start") and script01_dates.get("s2End"):
            return script01_dates["s2Start"], script01_dates["s2End"]

        script03_dates = GEE_CONFIG.get("script03", {}).get("dates", {})
        if script03_dates.get("s2PreStart") and script03_dates.get("s2PostEnd"):
            return script03_dates["s2PreStart"], script03_dates["s2PostEnd"]

        dates = GEE_CONFIG.get("dates", {})
        if dates.get("s2Start") and dates.get("s2End"):
            return dates["s2Start"], dates["s2End"]
        if dates.get("fullStart") and dates.get("fullEnd"):
            return dates["fullStart"], dates["fullEnd"]
    except Exception:
        pass

    return "2024-01-01", "2024-12-31"


def run_smoke_test(start_date: str, end_date: str) -> dict:
    study = _get_study_geometry_from_settings()

    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(study)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
    )

    image_count = s2.size().getInfo()
    if image_count == 0:
        return {"image_count": 0, "message": "No Sentinel-2 images found for query."}

    median = s2.median().clip(study)
    ndvi = median.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndvi_stats = ndvi.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
        geometry=study,
        scale=30,
        maxPixels=1e9,
        bestEffort=True,
        tileScale=4,
    ).getInfo()

    return {
        "start_date": start_date,
        "end_date": end_date,
        "image_count": image_count,
        "ndvi_mean": ndvi_stats.get("NDVI_mean"),
        "ndvi_min": ndvi_stats.get("NDVI_min"),
        "ndvi_max": ndvi_stats.get("NDVI_max"),
    }


def main() -> None:
    default_start, default_end = _get_date_range_from_settings()

    parser = argparse.ArgumentParser(description="Smoke test Google Earth Engine Python connection.")
    parser.add_argument(
        "--key-file",
        type=Path,
        default=DEFAULT_KEY_PATH,
        help="Path to service account JSON key file.",
    )
    parser.add_argument(
        "--project",
        type=str,
        default="driven-torus-431807-u3",
        help="Google Cloud project for Earth Engine initialization.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=default_start,
        help="Query start date (YYYY-MM-DD). Default from config/settings.py.",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=default_end,
        help="Query end date (YYYY-MM-DD). Default from config/settings.py.",
    )
    args = parser.parse_args()

    initialize_ee(args.key_file, args.project)
    result = run_smoke_test(args.start_date, args.end_date)
    print("✅ Earth Engine Python smoke test result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
