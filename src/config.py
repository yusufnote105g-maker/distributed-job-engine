from typing import Optional
import os


class JobEngineConfig:
    # Database
    database_url: str = "sqlite:///./jobs.db"
    
    # Worker configuration
    worker_count: int = 4
    worker_timeout: int = 300  # seconds
    
    # Job processing
    max_retries: int = 3
    initial_backoff: float = 1.0  # seconds
    max_backoff: float = 60.0  # seconds
    retry_jitter: bool = True
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Performance
    job_batch_size: int = 100
    health_check_interval: int = 30  # seconds
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Security
    secret_key: str = os.environ.get("SECRET_KEY", "your-secret-key-here")
    api_key_header: str = "X-API-Key"
    
    @classmethod
    def from_env(cls):
        """Create config from environment variables"""
        config = cls()
        
        # Override with environment variables if they exist
        if os.environ.get("DATABASE_URL"):
            config.database_url = os.environ.get("DATABASE_URL")
        if os.environ.get("WORKER_COUNT"):
            config.worker_count = int(os.environ.get("WORKER_COUNT"))
        if os.environ.get("WORKER_TIMEOUT"):
            config.worker_timeout = int(os.environ.get("WORKER_TIMEOUT"))
        if os.environ.get("MAX_RETRIES"):
            config.max_retries = int(os.environ.get("MAX_RETRIES"))
        if os.environ.get("INITIAL_BACKOFF"):
            config.initial_backoff = float(os.environ.get("INITIAL_BACKOFF"))
        if os.environ.get("MAX_BACKOFF"):
            config.max_backoff = float(os.environ.get("MAX_BACKOFF"))
        if os.environ.get("RETRY_JITTER"):
            config.retry_jitter = os.environ.get("RETRY_JITTER").lower() == "true"
        if os.environ.get("API_HOST"):
            config.api_host = os.environ.get("API_HOST")
        if os.environ.get("API_PORT"):
            config.api_port = int(os.environ.get("API_PORT"))
        if os.environ.get("JOB_BATCH_SIZE"):
            config.job_batch_size = int(os.environ.get("JOB_BATCH_SIZE"))
        if os.environ.get("HEALTH_CHECK_INTERVAL"):
            config.health_check_interval = int(os.environ.get("HEALTH_CHECK_INTERVAL"))
        if os.environ.get("LOG_LEVEL"):
            config.log_level = os.environ.get("LOG_LEVEL")
        if os.environ.get("LOG_FORMAT"):
            config.log_format = os.environ.get("LOG_FORMAT")
        if os.environ.get("SECRET_KEY"):
            config.secret_key = os.environ.get("SECRET_KEY")
        if os.environ.get("API_KEY_HEADER"):
            config.api_key_header = os.environ.get("API_KEY_HEADER")
            
        return config