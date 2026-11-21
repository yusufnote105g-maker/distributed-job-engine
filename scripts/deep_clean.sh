#!/bin/bash

# Deep clean script for the distributed job engine project
# Removes all cache files, build artifacts, and temporary files

echo "Starting deep clean..."

# Remove Python cache
echo "Removing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Remove build artifacts
echo "Removing build artifacts..."
find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Remove test cache
echo "Removing test cache..."
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name ".coverage" -delete 2>/dev/null || true
find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true

# Remove benchmark results
echo "Removing benchmark results..."
find . -name "benchmark_results.json" -delete 2>/dev/null || true

# Remove temporary database files
echo "Removing temporary database files..."
find . -name "jobs.db" -delete 2>/dev/null || true
find . -name "*.db" -delete 2>/dev/null || true

# Remove log files
echo "Removing log files..."
find . -name "*.log" -delete 2>/dev/null || true

# Remove cache directories
echo "Removing cache directories..."
find . -type d -name ".cache" -exec rm -rf {} + 2>/dev/null || true

echo "Deep clean completed!"
echo "The project is now clean and ready for fresh deployment."