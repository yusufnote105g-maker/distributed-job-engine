#!/usr/bin/env python3
"""
Script to clean Python cache files from the project.
This removes __pycache__ directories and .pyc files.
"""

import os
import shutil
from pathlib import Path

def clean_cache():
    """Remove Python cache files and directories."""
    project_root = Path(__file__).parent.parent
    removed_count = 0
    
    print("Cleaning Python cache files...")
    
    # Find and remove __pycache__ directories
    for cache_dir in project_root.rglob("__pycache__"):
        try:
            shutil.rmtree(cache_dir)
            removed_count += 1
            print(f"Removed: {cache_dir}")
        except Exception as e:
            print(f"Failed to remove {cache_dir}: {e}")
    
    # Find and remove .pyc files
    for pyc_file in project_root.rglob("*.pyc"):
        try:
            pyc_file.unlink()
            removed_count += 1
            print(f"Removed: {pyc_file}")
        except Exception as e:
            print(f"Failed to remove {pyc_file}: {e}")
    
    print(f"\nTotal cache files removed: {removed_count}")
    return removed_count

if __name__ == "__main__":
    clean_cache()