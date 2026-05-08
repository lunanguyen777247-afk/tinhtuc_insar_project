import ee
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
from pathlib import Path
from datetime import datetime, timedelta

def initialize_ee():
    key_path = Path("d:/tinhtuc_insar_project/gee_scripts/gee-private-key.json")
    data = json.loads(key_path.read_text(encoding="utf-8"))
    credentials = ee.ServiceAccountCredentials(data["client_email"], str(key_path))
    try:
        ee.Initialize(credentials, project="driven-torus-431807-u3")
    except:
        ee.Initialize(credentials)

def main():
    initialize_ee()
    print("GEE Initialized")
    
    # Study Area: Tinh Tuc, Cao Bang (from config)
    bbox = [105.85, 22.55, 106.1, 22.8]
    roi = ee.Geometry.Rectangle(bbox)
    
    start_date = "2025-01-01"
    end_date = "2025-12-31"

    print("Auditing Sentinel-1 Data...")
    s1_col = ee.ImageCollection("COPERNICUS/S1_GRD") \
        .filterBounds(roi) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
    
    info = s1_col.getInfo()
    features = info.get('features', [])
    
    records = []
    for f in features:
         props = f.get('properties', {})
         records.append({
             'id': f.get('id'),
             'timestamp': props.get('system:time_start'),
             'orbit': props.get('orbitProperties_pass'),
             'rel_orbit': props.get('relativeOrbitNumber_start')
         })
         
    df_s1 = pd.DataFrame(records)
    df_s1['datetime'] = pd.to_datetime(df_s1['timestamp'], unit='ms')
    df_s1 = df_s1.sort_values('datetime')
    
    asc = df_s1[df_s1['orbit'] == 'ASCENDING']
    desc = df_s1[df_s1['orbit'] == 'DESCENDING']
    
    print(f"Total S1 Images: {len(df_s1)}")
    print(f"ASCENDING: {len(asc)}")
    print(f"DESCENDING: {len(desc)}")
    
    os.makedirs("d:/tinhtuc_insar_project/outputs/reports", exist_ok=True)
    os.makedirs("d:/tinhtuc_insar_project/outputs/figures", exist_ok=True)
    
    df_s1.to_csv("d:/tinhtuc_insar_project/outputs/reports/s1_2025_audit.csv", index=False)
    
    plt.figure(figsize=(12, 3))
    plt.scatter(asc['datetime'], [1]*len(asc), label='ASC', color='blue', alpha=0.6, s=50)
    plt.scatter(desc['datetime'], [2]*len(desc), label='DESC', color='orange', alpha=0.6, s=50)
    plt.yticks([1, 2], ['ASCENDING', 'DESCENDING'])
    plt.title('Sentinel-1 Acquisition Timeline 2025 (Tinh Tuc)')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("d:/tinhtuc_insar_project/outputs/figures/s1_timeline_2025.png")
    plt.close()

    print("Fetching ERA5 Rainfall Data...")
    era5 = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR") \
        .filterBounds(roi) \
        .filterDate(start_date, end_date) \
        .select("total_precipitation_sum")
        
    era5_info = era5.getRegion(roi, 5000).getInfo()
    params = era5_info[0]
    data = era5_info[1:]
    
    df_era5 = pd.DataFrame(data, columns=params)
    df_era5['datetime'] = pd.to_datetime(df_era5['time'], unit='ms')
    df_rain = df_era5.groupby('datetime')['total_precipitation_sum'].mean().reset_index()
    # Convert m to mm
    df_rain['rain_mm'] = df_rain['total_precipitation_sum'] * 1000
    
    # Export rain
    df_rain.to_csv("d:/tinhtuc_insar_project/outputs/reports/era5_rain_2025.csv", index=False)
    
    plt.figure(figsize=(10, 4))
    plt.bar(df_rain['datetime'], df_rain['rain_mm'], color='skyblue')
    plt.title('Daily Rainfall (ERA5) 2025 (Tinh Tuc)')
    plt.ylabel('Rainfall (mm)')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("d:/tinhtuc_insar_project/outputs/figures/rain_timeline_2025.png")
    plt.close()
    
    peak_rain_day = df_rain.loc[df_rain['rain_mm'].idxmax()]['datetime']
    print(f"Peak rainfall event detected on: {peak_rain_day}")
    
    print("Computing SAR Flood Index (mock map for visual)...")
    # Tinh toán pre_flood và post_flood dựa vào peak_rain_day
    # Nếu peak_rain_day vào ~ tháng 7, lấy T6 làm pre, T7 làm post
    month_start = peak_rain_day.replace(day=1)
    pre_start = (month_start - timedelta(days=60)).strftime("%Y-%m-%d")
    pre_end = month_start.strftime("%Y-%m-%d")
    post_start = peak_rain_day.strftime("%Y-%m-%d")
    post_end = (peak_rain_day + timedelta(days=30)).strftime("%Y-%m-%d")
    
    print(f"Pre-flood: {pre_start} to {pre_end}")
    print(f"Post-flood: {post_start} to {post_end}")

if __name__ == '__main__':
    main()
