#!/bin/bash

# Script to clean Python cache and build artifacts
echo "Cleaning Python cache files..."

# Remove Python cache directories
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true

# Remove Python bytecode files
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Remove cache files
find . -name "*.cache" -delete 2>/dev/null || true

echo "Cache cleaning completed!"