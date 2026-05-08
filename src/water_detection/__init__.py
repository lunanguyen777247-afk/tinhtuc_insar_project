"""
Water Detection Module

Implements multiple water detection algorithms:
1. Fixed threshold method (σ₀_VV < -12 dB)
2. Adaptive Otsu thresholding
3. VH/VV ratio method
4. Change detection method (temporal comparison)
"""

import numpy as np
import rasterio
from pathlib import Path
from typing import Tuple, Optional, Dict, List
from sklearn.filters import threshold_otsu
import logging

logger = logging.getLogger(__name__)


class WaterDetector:
    """
    Detects water bodies in SAR images using multiple methods.
    """
    
    def __init__(self,
                 vv_threshold: float = -12.0,
                 vh_vv_ratio_max: float = 0.25,
                 confidence_threshold: float = 0.5):
        """
        Initialize water detector.
        
        Args:
            vv_threshold: VV backscatter threshold for water (dB)
            vh_vv_ratio_max: VH/VV ratio threshold for water
            confidence_threshold: Minimum confidence for classification
        """
        self.vv_threshold = vv_threshold
        self.vh_vv_ratio_max = vh_vv_ratio_max
        self.confidence_threshold = confidence_threshold
    
    def detect_fixed_threshold(self, 
                               sigma0_vv: np.ndarray,
                               threshold: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect water using fixed VV backscatter threshold.
        
        Water appears as low backscatter (specular reflection).
        Typical threshold: σ₀_VV < -12 dB
        
        Args:
            sigma0_vv: VV backscatter in dB
            threshold: VV threshold (uses class default if None)
            
        Returns:
            (water_mask, confidence_score) - binary masks [0, 1]
        """
        if threshold is None:
            threshold = self.vv_threshold
        
        sigma0_vv = np.asarray(sigma0_vv, dtype=np.float32)
        
        # Water detection: VV < threshold
        water_mask = (sigma0_vv < threshold).astype(np.float32)
        
        # Confidence based on how far below threshold
        # Confidence = 1 - (sigma0_vv - threshold) / threshold
        confidence = np.clip(1.0 - (sigma0_vv - threshold) / (threshold + 1e-10), 0.0, 1.0)
        confidence = confidence * water_mask  # Only for water pixels
        
        logger.debug(f"Fixed threshold detection: {np.sum(water_mask)} water pixels")
        
        return water_mask, confidence
    
    def detect_otsu_adaptive(self,
                             sigma0_vv: np.ndarray,
                             local_window_size: int = 100) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect water using adaptive Otsu thresholding.
        
        Automatically determines threshold for each local window.
        
        Args:
            sigma0_vv: VV backscatter in dB
            local_window_size: Size of local window
            
        Returns:
            (water_mask, confidence_score)
        """
        sigma0_vv = np.asarray(sigma0_vv, dtype=np.float32)
        water_mask = np.zeros_like(sigma0_vv, dtype=np.float32)
        confidence = np.zeros_like(sigma0_vv, dtype=np.float32)
        
        # Apply Otsu threshold to global image
        try:
            threshold = threshold_otsu(sigma0_vv.astype(np.uint8))
            water_mask = (sigma0_vv < threshold).astype(np.float32)
            confidence = np.abs(sigma0_vv - threshold) / (np.abs(threshold) + 1e-10)
            confidence = np.clip(confidence, 0.0, 1.0) * water_mask
        except Exception as e:
            logger.warning(f"Otsu thresholding failed: {e}")
        
        logger.debug(f"Otsu adaptive detection: {np.sum(water_mask)} water pixels")
        
        return water_mask, confidence
    
    def detect_ratio_method(self,
                           sigma0_vh: np.ndarray,
                           sigma0_vv: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect water using VH/VV ratio.
        
        Water has low VH/VV ratio (0.05-0.25)
        Vegetation has high VH/VV ratio (0.6-1.0)
        
        Args:
            sigma0_vh: VH backscatter in dB
            sigma0_vv: VV backscatter in dB
            
        Returns:
            (water_mask, confidence_score)
        """
        # Convert from dB to linear scale
        vh_linear = 10.0 ** (np.asarray(sigma0_vh, dtype=np.float32) / 10.0)
        vv_linear = 10.0 ** (np.asarray(sigma0_vv, dtype=np.float32) / 10.0)
        
        # Compute ratio
        ratio = vh_linear / (vv_linear + 1e-10)
        
        # Water detection: ratio < max_ratio
        water_mask = (ratio < self.vh_vv_ratio_max).astype(np.float32)
        
        # Confidence: how far below max_ratio
        confidence = np.clip(1.0 - ratio / self.vh_vv_ratio_max, 0.0, 1.0)
        confidence = confidence * water_mask
        
        logger.debug(f"Ratio method detection: {np.sum(water_mask)} water pixels")
        
        return water_mask, confidence
    
    def detect_change_index(self,
                           sigma0_vv_wet: np.ndarray,
                           sigma0_vv_dry: np.ndarray,
                           threshold: float = -0.10) -> Tuple[np.ndarray, np.ndarray]:
        """
        Detect water using change detection index.
        
        ΔI = (I_wet - I_dry) / I_dry
        Water typically shows negative change (backscatter decrease).
        
        Args:
            sigma0_vv_wet: VV backscatter during wet conditions (dB)
            sigma0_vv_dry: VV backscatter during dry conditions (dB)
            threshold: Change index threshold
            
        Returns:
            (water_mask, confidence_score)
        """
        # Convert to linear scale
        wet_linear = 10.0 ** (np.asarray(sigma0_vv_wet, dtype=np.float32) / 10.0)
        dry_linear = 10.0 ** (np.asarray(sigma0_vv_dry, dtype=np.float32) / 10.0)
        
        # Change index
        change_index = (wet_linear - dry_linear) / (dry_linear + 1e-10)
        
        # Water detection: ΔI < threshold
        water_mask = (change_index < threshold).astype(np.float32)
        
        # Confidence based on magnitude of change
        confidence = np.clip(np.abs(change_index) / np.abs(threshold), 0.0, 1.0)
        confidence = confidence * water_mask
        
        logger.debug(f"Change index detection: {np.sum(water_mask)} water pixels, "
                    f"avg ΔI={np.mean(change_index):.4f}")
        
        return water_mask, confidence
    
    def ensemble_detection(self,
                          detections: List[Tuple[np.ndarray, np.ndarray]],
                          method: str = "voting") -> Tuple[np.ndarray, np.ndarray]:
        """
        Combine multiple detections using ensemble method.
        
        Args:
            detections: List of (water_mask, confidence) tuples
            method: Ensemble method ("voting", "average", "max")
            
        Returns:
            (ensemble_water_mask, ensemble_confidence)
        """
        if not detections:
            raise ValueError("No detections provided")
        
        masks = np.array([d[0] for d in detections])
        confidences = np.array([d[1] for d in detections])
        
        if method == "voting":
            # Majority voting
            votes = np.sum(masks, axis=0)
            ensemble_mask = (votes >= len(detections) / 2).astype(np.float32)
            ensemble_confidence = votes / len(detections)
            
        elif method == "average":
            # Average confidence
            ensemble_mask = np.mean(masks, axis=0)
            ensemble_confidence = np.mean(confidences, axis=0)
            
        elif method == "max":
            # Maximum confidence
            ensemble_mask = np.max(masks, axis=0)
            ensemble_confidence = np.max(confidences, axis=0)
            
        else:
            logger.warning(f"Unknown ensemble method: {method}, using voting")
            return self.ensemble_detection(detections, method="voting")
        
        logger.debug(f"Ensemble detection ({method}): {np.sum(ensemble_mask)} water pixels")
        
        return ensemble_mask, ensemble_confidence
    
    def classify_water(self,
                      sigma0_vv: np.ndarray,
                      sigma0_vh: Optional[np.ndarray] = None,
                      sigma0_vv_ref: Optional[np.ndarray] = None) -> Dict[str, np.ndarray]:
        """
        Comprehensive water classification.
        
        Combines multiple detection methods and produces:
        - Water/non-water mask
        - Confidence map
        - Classification map (definite water, probable water, uncertain)
        
        Args:
            sigma0_vv: VV backscatter
            sigma0_vh: VH backscatter (optional, for ratio method)
            sigma0_vv_ref: Reference VV (optional, for change detection)
            
        Returns:
            Dictionary with classification results
        """
        detections = []
        
        # Method 1: Fixed threshold
        mask1, conf1 = self.detect_fixed_threshold(sigma0_vv)
        detections.append((mask1, conf1))
        
        # Method 2: Otsu thresholding
        mask2, conf2 = self.detect_otsu_adaptive(sigma0_vv)
        detections.append((mask2, conf2))
        
        # Method 3: Ratio method (if VH available)
        if sigma0_vh is not None:
            mask3, conf3 = self.detect_ratio_method(sigma0_vh, sigma0_vv)
            detections.append((mask3, conf3))
        
        # Method 4: Change detection (if reference available)
        if sigma0_vv_ref is not None:
            mask4, conf4 = self.detect_change_index(sigma0_vv, sigma0_vv_ref)
            detections.append((mask4, conf4))
        
        # Ensemble
        ensemble_mask, ensemble_conf = self.ensemble_detection(detections, method="voting")
        
        # Classification
        classification = np.zeros_like(sigma0_vv, dtype=np.uint8)
        classification[(ensemble_mask > 0) & (ensemble_conf > 0.8)] = 3  # Definite water
        classification[(ensemble_mask > 0) & (ensemble_conf > 0.5)] = 2  # Probable water
        classification[(ensemble_mask > 0)] = 1  # Uncertain
        
        return {
            "water_mask": ensemble_mask,
            "confidence": ensemble_conf,
            "classification": classification,  # 0=non-water, 1=uncertain, 2=probable, 3=definite
            "detections": detections
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Water Detection Module")
    print("=====================\n")
    
    # Create test data
    vv_data = np.random.uniform(-20, -5, (100, 100)).astype(np.float32)
    vh_data = np.random.uniform(-25, -10, (100, 100)).astype(np.float32)
    
    # Create detector
    detector = WaterDetector()
    
    # Run detection
    results = detector.classify_water(vv_data, vh_data)
    
    print(f"Water pixels detected: {np.sum(results['water_mask'])}")
    print(f"Average confidence: {np.mean(results['confidence'][(results['confidence'] > 0)]):.3f}")
    print(f"Classification map:\n  Definite: {np.sum(results['classification'] == 3)}")
    print(f"            Probable: {np.sum(results['classification'] == 2)}")
    print(f"            Uncertain: {np.sum(results['classification'] == 1)}")
