#!/bin/bash

# Distributed Job Engine - Production Startup Script
# This script sets up and runs the job engine with proper configuration

set -e

echo "🚀 Starting Distributed Job Engine..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create database directory if it doesn't exist
mkdir -p data

# Set environment variables
export DATABASE_URL="sqlite:///./data/jobs.db"
export WORKER_COUNT=4
export WORKER_TIMEOUT=300
export MAX_RETRIES=3
export API_PORT=8000
export LOG_LEVEL="INFO"

echo "🗄️ Setting up database..."
python -c "
from src.services.database import DatabaseService
import asyncio
async def setup():
    db = DatabaseService()
    await db.create_tables()
    print('✅ Database tables created successfully')
asyncio.run(setup())
"

echo "🏃 Starting job engine..."
echo "📊 API will be available at: http://localhost:8000"
echo "🔗 Health check: http://localhost:8000/api/health"
echo "📈 Stats: http://localhost:8000/api/stats"
echo "⏹️  Press Ctrl+C to stop"

# Run the application
python -m src.main