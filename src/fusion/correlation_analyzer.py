"""
Correlation Analyzer Module
Analyzes the spatiotemporal relationship between flooding events and surface deformation.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class FloodDeformationFusion:
    """
    Analyzes how flooding events impact ground stability and deformation rates.
    """
    
    def __init__(self, pixel_size_m: float = 10.0):
        self.pixel_size_m = pixel_size_m

    def analyze_lagged_impact(self, 
                             flood_sequence: np.ndarray, 
                             velocity_sequence: np.ndarray,
                             time_days: np.ndarray,
                             lag_days: int = 30) -> Dict:
        """
        Calculates if flooding leads to increased deformation after a certain lag.
        
        Args:
            flood_sequence: Binary flood masks [T, H, W]
            velocity_sequence: Deformation velocity maps [T, H, W]
            time_days: Array of days for each time step
            lag_days: Number of days to look ahead for impact
            
        Returns:
            Dictionary with correlation statistics and impact maps.
        """
        # Find index offset for lag
        avg_dt = np.mean(np.diff(time_days))
        idx_lag = int(round(lag_days / avg_dt))
        
        if idx_lag >= len(flood_sequence):
            return {"error": "Lag duration exceeds dataset timeline"}

        # Impact mask: area that was flooded
        flood_ever = np.max(flood_sequence, axis=0)
        
        # Calculate velocity change
        # Base velocity (pre-flood average) vs Impact velocity (post-flood + lag)
        # For simplicity, we compare velocity at T and velocity at T + lag
        
        correlations = []
        for t in range(len(flood_sequence) - idx_lag):
            f_t = flood_sequence[t]
            v_post_lag = velocity_sequence[t + idx_lag]
            
            # Correlation between flooding at t and velocity at t+lag
            # Only consider areas near the flood (e.g. affected buffer)
            if np.sum(f_t) > 0:
                corr = np.corrcoef(f_t.flatten(), v_post_lag.flatten())[0, 1]
                correlations.append(corr)
                
        return {
            "avg_lag_correlation": np.nanmean(correlations) if correlations else 0.0,
            "lag_days": lag_days,
            "flood_footprint": flood_ever,
            "status": "Success"
        }

    def detect_acceleration_hotspots(self, 
                                   flood_extent: np.ndarray, 
                                   velocity_map: np.ndarray,
                                   slope_map: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Detects areas where flood-induced instability is highest (high slope + nearby flood).
        """
        # Logic: Areas high in velocity AND close to flood extent
        # If slope is provided, weight by slope risk
        risk_map = np.abs(velocity_map) * flood_extent
        if slope_map is not None:
            risk_map = risk_map * (slope_map / 90.0)
            
        return risk_map

if __name__ == "__main__":
    fusion = FloodDeformationFusion()
    print("Fusion Module Initialized")
