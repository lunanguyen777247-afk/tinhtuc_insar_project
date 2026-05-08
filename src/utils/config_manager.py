"""
Configuration Management System
For SAR-Based Flood Detection Pipeline

This module provides centralized configuration management using YAML files
and environment variables with hierarchical loading.
"""

import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml
from dotenv import load_dotenv


class ConfigManager:
    """
    Centralized configuration manager for the flood detection pipeline.
    
    Loads configuration from:
    1. YAML files (config/*.yaml)
    2. Environment variables (.env)
    3. Runtime overrides
    
    Usage:
        config = ConfigManager()
        config.load_all()
        
        # Access config values
        vv_threshold = config.get("water_detection.methods.fixed_threshold.vv_threshold")
        
        # Override runtime
        config.set("water_detection.methods.fixed_threshold.vv_threshold", -11.0)
    """
    
    def __init__(self, config_dir: str = "config", env_file: str = ".env"):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Directory containing YAML config files
            env_file: Path to .env file
        """
        self.config_dir = Path(config_dir)
        self.env_file = Path(env_file)
        self.config = {}
        self.logger = logging.getLogger(__name__)
        
    def load_all(self) -> Dict[str, Any]:
        """
        Load all configuration sources in order of precedence.
        
        Order:
        1. YAML files from config/ directory
        2. Environment variables from .env
        
        Returns:
            Complete configuration dictionary
        """
        # Load YAML files
        self._load_yaml_files()
        
        # Load environment variables
        self._load_env_variables()
        
        self.logger.info(f"Configuration loaded successfully")
        return self.config
    
    def _load_yaml_files(self) -> None:
        """Load all YAML configuration files from config directory."""
        if not self.config_dir.exists():
            self.logger.warning(f"Config directory not found: {self.config_dir}")
            return
            
        yaml_files = sorted(self.config_dir.glob("*.yaml"))
        
        for yaml_file in yaml_files:
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f) or {}
                    self.config.update(yaml_config)
                    self.logger.info(f"Loaded config from {yaml_file.name}")
            except Exception as e:
                self.logger.error(f"Error loading {yaml_file}: {e}")
    
    def _load_env_variables(self) -> None:
        """Load environment variables from .env file."""
        if self.env_file.exists():
            load_dotenv(self.env_file)
            self.logger.info(f"Loaded environment variables from {self.env_file}")
        else:
            self.logger.debug(f".env file not found: {self.env_file}")
        
        # Map specific environment variables to config
        env_mapping = {
            "water_detection.methods.fixed_threshold.vv_threshold": "WATER_VV_THRESHOLD",
            "water_detection.methods.ratio_method.water_ratio_max": "WATER_VH_VV_RATIO",
            "water_detection.confidence.min_confidence": "CONFIDENCE_MIN",
            "global.logging.level": "LOG_LEVEL",
            "global.logging.log_file": "LOG_FILE",
        }
        
        for config_key, env_key in env_mapping.items():
            env_value = os.getenv(env_key)
            if env_value:
                try:
                    # Try to convert to appropriate type
                    if env_value.lower() in ["true", "false"]:
                        env_value = env_value.lower() == "true"
                    elif env_value.replace("-", "").replace(".", "").isdigit():
                        env_value = float(env_value) if "." in env_value else int(env_value)
                except:
                    pass
                
                self._set_nested(self.config, config_key, env_value)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        
        Args:
            key: Configuration key in dot notation (e.g., "water_detection.methods.fixed_threshold.vv_threshold")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
            
        Example:
            >>> config.get("water_detection.methods.fixed_threshold.vv_threshold")
            -12.0
        """
        return self._get_nested(self.config, key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value using dot notation.
        
        Args:
            key: Configuration key in dot notation
            value: Value to set
            
        Example:
            >>> config.set("water_detection.methods.fixed_threshold.vv_threshold", -11.0)
        """
        self._set_nested(self.config, key, value)
        self.logger.debug(f"Set {key} = {value}")
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get entire configuration section.
        
        Args:
            section: Section name (e.g., "water_detection")
            
        Returns:
            Section dictionary
        """
        return self.config.get(section, {})
    
    def to_dict(self) -> Dict[str, Any]:
        """Get complete configuration as dictionary."""
        return self.config.copy()
    
    def to_json(self, output_file: str) -> None:
        """
        Save configuration to JSON file.
        
        Args:
            output_file: Output JSON file path
        """
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)
        self.logger.info(f"Configuration saved to {output_file}")
    
    @staticmethod
    def _get_nested(d: Dict, key: str, default: Any = None) -> Any:
        """Helper: Get nested dictionary value using dot notation."""
        keys = key.split(".")
        value = d
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
                
        return value if value is not None else default
    
    @staticmethod
    def _set_nested(d: Dict, key: str, value: Any) -> None:
        """Helper: Set nested dictionary value using dot notation."""
        keys = key.split(".")
        
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        
        d[keys[-1]] = value


# Global configuration instance
_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """
    Get or create global configuration manager.
    
    Returns:
        Global ConfigManager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load_all()
    return _config_manager


# Setup logging with config
def setup_logging(config: ConfigManager) -> logging.Logger:
    """
    Setup logging based on configuration.
    
    Args:
        config: Configuration manager
        
    Returns:
        Logger instance
    """
    log_level = config.get("global.logging.level", "INFO")
    log_file = config.get("global.logging.log_file", "logs/pipeline.log")
    console_output = config.get("global.logging.console_output", True)
    
    # Create logs directory
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    logger = logging.getLogger("flood_detection_pipeline")
    logger.setLevel(getattr(logging, log_level))
    
    # File handler
    fh = logging.FileHandler(log_file)
    fh.setLevel(getattr(logging, log_level))
    
    # Console handler (if enabled)
    ch = logging.StreamHandler() if console_output else None
    if ch:
        ch.setLevel(getattr(logging, log_level))
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    fh.setFormatter(formatter)
    if ch:
        ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    if ch:
        logger.addHandler(ch)
    
    return logger


if __name__ == "__main__":
    # Example usage
    config = get_config()
    logger = setup_logging(config)
    
    print("Configuration loaded successfully!")
    print("\nWater Detection Settings:")
    print(f"  VV Threshold: {config.get('water_detection.methods.fixed_threshold.vv_threshold')} dB")
    print(f"  Confidence Min: {config.get('water_detection.confidence.min_confidence')}")
    
    print("\nScenarios Enabled:")
    for i in range(1, 5):
        key = f"scenarios.scenario{i}_before_after" if i == 1 else f"scenarios.scenario{i}_time_series" if i == 2 else f"scenarios.scenario{i}_asc_desc_comparison" if i == 3 else f"scenarios.scenario{i}_anomaly_detection"
        section = config.get_section(key.split('.')[0])
        print(f"  Scenario {i}: {section.get(f'scenario{i}', {}).get('name', 'N/A')}")
