# Distributed Job Engine

Production-oriented distributed job engine built with FastAPI, SQLite, and comprehensive testing.

## 🚀 Features

- **FastAPI REST API** with validation and pagination
- **SQLite database** with concurrent access support
- **Multiple workers** for parallel job processing
- **Job priorities** and retry policies
- **Timeout handling** and graceful shutdown
- **Comprehensive testing** including race conditions
- **Performance benchmarking** with metrics
- **Docker containerization**
- **GitHub Actions CI/CD**

## 📋 Requirements

- Python 3.11+
- SQLite3

## 🛠️ Installation

1. Clone the repository:
```bash
git clone https://github.com/yusufnote105g-maker/distributed-job-engine.git
cd distributed-job-engine
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python -m src.main
```

The API will be available at `http://localhost:8000`

## 📊 API Endpoints

### Jobs
- `POST /api/jobs` - Submit a new job
- `GET /api/jobs` - List jobs with pagination
- `GET /api/jobs/{job_id}` - Get job details
- `DELETE /api/jobs/{job_id}` - Cancel a job

### System
- `GET /api/health` - Health check
- `GET /api/stats` - System statistics

## 🧪 Testing

Run the test suite:
```bash
pytest
```

Run specific test categories:
```bash
pytest tests/test_api.py
pytest tests/test_concurrency.py
pytest tests/test_retries_and_timeouts.py
```

## 📈 Benchmarking

Run performance benchmark:
```bash
python benchmark/benchmark.py
```

## 🐳 Docker

Build and run with Docker:
```bash
docker build -t job-engine .
docker run -p 8000:8000 job-engine
```

Or use Docker Compose:
```bash
docker-compose up
```

## 📁 Project Structure

```
src/
├── main.py              # Application entry point
├── config.py            # Configuration management
├── api/
│   └── routes.py        # API endpoints
├── models/
│   └── job.py           # Database models
├── services/
│   ├── database.py      # Database service
│   └── job_processor.py # Job processing logic
└── utils/
    └── logging.py       # Logging utilities

tests/                   # Test suite
benchmark/               # Performance benchmarks
docs/                   # Documentation
scripts/                # Utility scripts
```

## 🔧 Configuration

Environment variables:
- `DATABASE_URL` - Database connection string
- `WORKER_COUNT` - Number of worker processes (default: 4)
- `WORKER_TIMEOUT` - Worker timeout in seconds (default: 300)
- `MAX_RETRIES` - Maximum retry attempts (default: 3)
- `API_PORT` - API port (default: 8000)

## 📊 Performance

The engine is optimized for:
- High throughput job processing
- Concurrent worker operations
- Efficient database access with proper indexing
- Memory-efficient job handling

## 🔒 Security

- Input validation using Pydantic
- SQL injection protection
- Secure API key authentication
- Proper error handling

## 📚 Documentation

- [Architecture](docs/architecture.md)
- [Database Schema](docs/database_schema.md)
- [Security Analysis](docs/security_analysis.md)
- [Known Limitations](docs/known_limitations.md)
- [Production Risks](docs/production_risks.md)
- [Dependencies](docs/dependencies.md)
- [Optimization Guide](docs/optimization.md)

## 🚀 Deployment

1. Set up environment variables
2. Configure database connection
3. Set up reverse proxy (nginx recommended)
4. Configure SSL certificates
5. Set up monitoring and logging

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is open source and available under the MIT License.