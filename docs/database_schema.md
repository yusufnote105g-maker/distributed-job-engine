# Database Schema Documentation

## Overview

The Distributed Job Engine uses SQLite as its primary database. The schema is designed to be simple, efficient, and support all job processing requirements while maintaining data integrity.

## Schema Design Principles

1. **Simplicity**: Minimal tables with clear relationships
2. **Performance**: Optimized for frequent read/write operations
3. **Integrity**: Ensure data consistency through constraints
4. **Scalability**: Designed to handle growing job volumes
5. **Observability**: Rich metadata for monitoring and debugging

## Database Schema

### Jobs Table

The main table storing all job information.

```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    idempotency_key TEXT,
    payload TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'normal',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    claimed_at DATETIME,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    next_retry_at DATETIME,
    worker_id TEXT,
    timeout INTEGER NOT NULL DEFAULT 300,
    result TEXT,
    error TEXT,
    execution_time REAL
);
```

#### Indexes

```sql
-- Primary index for job lookup
CREATE INDEX idx_jobs_job_id ON jobs(job_id);

-- Index for idempotency checks
CREATE INDEX idx_jobs_idempotency_key ON jobs(idempotency_key);

-- Index for job status filtering
CREATE INDEX idx_jobs_status ON jobs(status);

-- Index for priority ordering
CREATE INDEX idx_jobs_priority ON jobs(priority);

-- Index for creation time ordering
CREATE INDEX idx_jobs_created_at ON jobs(created_at);

-- Composite index for pending jobs with retry logic
CREATE INDEX idx_jobs_pending_retry ON jobs(status, next_retry_at) 
WHERE status = 'pending' OR status = 'retrying';
```

#### Column Descriptions

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Auto-incrementing primary key |
| job_id | TEXT | Unique UUID for job identification |
| idempotency_key | TEXT | Optional key for duplicate prevention |
| payload | TEXT | Job payload data |
| priority | TEXT | Job priority: 'low', 'normal', 'high', 'critical' |
| status | TEXT | Current job status |
| created_at | DATETIME | Job creation timestamp |
| started_at | DATETIME | Job execution start time |
| completed_at | DATETIME | Job completion time |
| claimed_at | DATETIME | Job claiming time |
| retry_count | INTEGER | Number of retry attempts |
| max_retries | INTEGER | Maximum allowed retries |
| next_retry_at | DATETIME | When to retry failed jobs |
| worker_id | TEXT | ID of worker processing the job |
| timeout | INTEGER | Job timeout in seconds |
| result | TEXT | Job execution result |
| error | TEXT | Error message if job failed |
| execution_time | REAL | Job execution time in seconds |

### Job Status Transitions

```
PENDING → CLAIMED → RUNNING → COMPLETED
                ↘ RETRYING → PENDING (retry)
                ↘ FAILED → DEAD_LETTER (max retries)
                ↘ CANCELLED (user cancelled)
```

### Query Patterns

#### Get Next Available Job
```sql
SELECT * FROM jobs 
WHERE status = 'pending' 
   AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
ORDER BY 
    CASE priority 
        WHEN 'critical' THEN 1 
        WHEN 'high' THEN 2 
        WHEN 'normal' THEN 3 
        ELSE 4 
    END,
    created_at ASC
LIMIT 1;
```

#### Claim Job Atomically
```sql
UPDATE jobs 
SET status = 'claimed', 
    worker_id = 'worker-1', 
    claimed_at = CURRENT_TIMESTAMP,
    next_retry_at = NULL
WHERE id = ? AND status = 'pending';
```

#### Get Jobs by Status
```sql
SELECT * FROM jobs 
WHERE status = ? 
ORDER BY created_at DESC 
LIMIT ? OFFSET ?;
```

#### Get Metrics
```sql
-- Count jobs by status
SELECT status, COUNT(*) as count 
FROM jobs 
GROUP BY status;

-- Calculate average execution time
SELECT AVG(execution_time) 
FROM jobs 
WHERE status = 'completed' AND execution_time IS NOT NULL;
```

#### Update Job Status
```sql
UPDATE jobs 
SET status = ?, 
    started_at = CASE WHEN ? = 'running' THEN CURRENT_TIMESTAMP ELSE NULL END,
    completed_at = CASE WHEN ? IN ('completed', 'failed', 'cancelled', 'dead_letter') THEN CURRENT_TIMESTAMP ELSE NULL END,
    retry_count = CASE WHEN ? = 'retrying' THEN retry_count + 1 ELSE retry_count END,
    next_retry_at = CASE WHEN ? = 'retrying' THEN DATETIME('now', '+? seconds') ELSE NULL END,
    result = ?,
    error = ?,
    execution_time = ?
WHERE job_id = ?;
```

## Database Optimization

### Performance Considerations

1. **Indexing Strategy**
   - Critical queries have appropriate indexes
   - Composite indexes for common query patterns
   - Avoid over-indexing to maintain write performance

2. **Query Optimization**
   - Use `LIMIT` for pagination
   - Select only needed columns
   - Use `ORDER BY` with indexed columns

3. **Transaction Management**
   - Keep transactions short
   - Use appropriate isolation levels
   - Batch operations where possible

### Concurrency Control

1. **Row Locking**
   - Use `SELECT ... FOR UPDATE` for job claiming
   - Ensure atomic status updates
   - Handle concurrent access gracefully

2. **Deadlock Prevention**
   - Access tables in consistent order
   - Keep transactions short
   - Use appropriate timeouts

3. **Isolation Levels**
   - Use SQLite's default isolation level
   - Consider explicit transactions for critical operations

### Data Integrity

1. **Constraints**
   - Unique constraints on critical fields
   - NOT NULL constraints for required fields
   - Check constraints for valid values

2. **Referential Integrity**
   - SQLite doesn't enforce foreign keys by default
   - Maintain consistency through application logic

3. **Transaction Safety**
   - Ensure all related updates happen in single transaction
   - Handle rollbacks appropriately
   - Use savepoints for complex operations

## Backup and Recovery

### Backup Strategy

1. **Regular Backups**
   - Daily full backups
   - Before major deployments
   - After significant data changes

2. **Backup Methods**
   - SQLite's `backup` API
   - File system snapshots
   - Database dumps

3. **Recovery Procedures**
   - Restore from latest backup
   - Apply transaction logs if available
   - Validate data integrity

### Recovery Scenarios

1. **Application Crash**
   - Jobs in progress will be retried
   - Database remains consistent
   - No data loss expected

2. **Database Corruption**
   - Restore from backup
   - Check database integrity
   - Rebuild indexes if needed

3. **Data Loss**
   - Restore from backup
   - Check for incomplete jobs
   - Verify system functionality

## Monitoring and Maintenance

### Performance Monitoring

1. **Query Performance**
   - Monitor slow queries
   - Track index usage
   - Analyze query plans

2. **Database Health**
   - Monitor connection count
   - Track transaction duration
   - Check for lock contention

3. **Space Usage**
   - Monitor database file size
   - Track growth patterns
   - Plan for capacity needs

### Maintenance Tasks

1. **Regular Maintenance**
   - Analyze database statistics
   - Rebuild indexes if needed
   - Clean up old data

2. **Data Management**
   - Archive completed jobs
   - Clean up dead letter jobs
   - Manage job history

3. **Performance Tuning**
   - Adjust indexes based on usage patterns
   - Optimize queries for common access patterns
   - Monitor and adjust cache settings

## Schema Evolution

### Versioning Strategy

1. **Version Tracking**
   - Maintain schema version in metadata table
   - Document all changes
   - Provide migration scripts

2. **Migration Process**
   - Test migrations in development
   - Apply migrations with downtime
   - Verify data integrity after migration

3. **Backward Compatibility**
   - Maintain API compatibility
   - Support old schema versions temporarily
   - Deprecate old versions gradually

### Future Schema Changes

1. **Planned Enhancements**
   - Support for job dependencies
   - Scheduled jobs support
   - Enhanced metadata storage

2. **Scaling Considerations**
   - Partitioning for large datasets
   - Sharding for horizontal scaling
   - Replication for high availability

3. **Feature Requests**
   - Job templates
   - Advanced retry policies
   - Custom job metadata

This schema provides a solid foundation for job processing while remaining flexible for future enhancements and scaling needs.