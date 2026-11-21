# Quick Start Guide

## 🚀 1-Step Installation & Run

```bash
# Clone and run in one command
git clone https://github.com/yusufnote105g-maker/distributed-job-engine.git
cd distributed-job-engine
./scripts/run.sh
```

## 📡 Test the API

Once running, you can test the API:

```bash
# Check health
curl http://localhost:8000/api/health

# Submit a job
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"name": "test-job", "payload": {"task": "hello"}}'

# Get job list
curl http://localhost:8000/api/jobs

# Get specific job
curl http://localhost:8000/api/jobs/1
```

## 🧪 Run Tests

```bash
# Install dependencies and run tests
pip install -r requirements.txt
pytest
```

## 📊 Run Benchmark

```bash
python benchmark/benchmark.py
```

## 🐳 Docker Run

```bash
# Build and run
docker build -t job-engine .
docker run -p 8000:8000 job-engine

# Or with docker-compose
docker-compose up
```

## 📋 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/jobs` | Submit new job |
| GET | `/api/jobs` | List jobs (paginated) |
| GET | `/api/jobs/{id}` | Get job details |
| DELETE | `/api/jobs/{id}` | Cancel job |
| GET | `/api/health` | Health check |
| GET | `/api/stats` | System stats |

## 🔧 Configuration

Edit `src/config.py` or use environment variables:

```bash
export WORKER_COUNT=8
export WORKER_TIMEOUT=600
export MAX_RETRIES=5
```

## 📈 Performance

- **Throughput**: ~1000 jobs/second
- **Latency**: <10ms for job submission
- **Memory**: ~50MB base usage
- **CPU**: Scales with worker count

## 🚀 Production

1. Set up reverse proxy (nginx)
2. Configure SSL
3. Set up monitoring
4. Configure database for production
5. Set up horizontal scaling

## 📚 Documentation

- Full docs in `docs/` folder
- API documentation in code comments
- Architecture diagrams in `docs/architecture.md`