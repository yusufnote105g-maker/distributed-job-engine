# Cache Cleanup Guide

## Overview
This document provides instructions for cleaning up Python cache and build artifacts from the distributed job engine project.

## Files Modified

### 1. requirements.txt
- Removed `pydantic-settings==2.1.0` (causes dependency issues)
- Downgraded `pydantic==2.5.0` to `pydantic==1.10.13` for better compatibility
- Removed commented line about psutil

### 2. .gitignore
Added additional patterns to exclude:
- More Python bytecode files (*.pyo, *.pyd)
- pip log files
- Virtual environment backup files
- .cache directories
- site-packages directories

### 3. New Scripts
- `scripts/clean_cache.sh`: Script to clean all cache files

## Cache Cleanup Commands

### Using the provided script:
```bash
./scripts/clean_cache.sh
```

### Manual cleanup:
```bash
# Remove Python cache directories
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true

# Remove Python bytecode files
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Remove build artifacts
find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
```

## pip Cache Cleanup
To clean pip cache system-wide:
```bash
pip cache purge
```

## Virtual Environment Cleanup
If using virtual environments:
```bash
# Remove existing venv
rm -rf venv/
# Create fresh environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Benefits
- Reduced repository size
- Cleaner build environment
- Avoids conflicts from cached bytecode
- Ensures clean builds
- Better dependency management