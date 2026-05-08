#!/usr/bin/env python
"""
run_input_data_audit.py
=======================
Convenience script to run the Input Data Audit from project root.

Usage:
  python run_input_data_audit.py
  python run_input_data_audit.py --use-gee  # Use real GEE data (requires auth)
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.data_audit.input_data_audit import main

if __name__ == "__main__":
    main()
