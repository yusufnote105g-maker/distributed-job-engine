#!/usr/bin/env bash
# Run the test-suite.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "🧪 Running tests..."
python3 -m pytest "$@"
