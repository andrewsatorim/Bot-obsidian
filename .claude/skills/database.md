---
name: database
description: Use when designing database schemas, writing migrations, optimizing queries, choosing databases, working with ORMs, or modeling data relationships.
---

# Database Design

## Schema Design Process

1. **Identify entities** — nouns in requirements (User, Order, Product)
2. **Define attributes** — properties of each entity
3. **Map relationships** — one-to-one, one-to-many, many-to-many
4. **Choose primary keys** — UUID vs auto-increment vs natural key
5. **Add indexes** — based on query patterns
6. **Add constraints** — NOT NULL, UNIQUE, CHECK, FOREIGN KEY
7. **Consider time** — created_at, updated_at, deleted_at (soft delete)

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Tables | plural snake_case | `users`, `order_items` |
| Columns | singular snake_case | `first_name`, `created_at` |
| Primary key | `id` | `users.id` |
| Foreign key | `<singular_table>_id` | `orders.user_id` |
| Booleans | `is_` or `has_` prefix | `is_active`, `has_verified` |
| Timestamps | `_at` suffix | `created_at`, `deleted_at` |
| Indexes | `idx_<table>_<columns>` | `idx_users_email` |
| Unique | `uniq_<table>_<columns>` | `uniq_users_email` |

## Common Patterns

### Soft Delete
```sql
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP NULL;
-- Query active: WHERE deleted_at IS NULL
```

### Polymorphic Association
```sql
-- Avoid: comments.commentable_type + commentable_id
-- Prefer: separate join tables
CREATE TABLE post_comments (post_id INT, comment_id INT);
CREATE TABLE photo_comments (photo_id INT, comment_id INT);
```

### Enum vs Lookup Table
```sql
-- Small, stable set → enum/check constraint
status VARCHAR(20) CHECK (status IN ('draft', 'published', 'archived'))

-- Growing set, needs metadata → lookup table
CREATE TABLE order_statuses (id SERIAL, name VARCHAR, display_name VARCHAR);
```

### Audit Trail
```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR NOT NULL,
    record_id UUID NOT NULL,
    action VARCHAR(10) NOT NULL, -- INSERT, UPDATE, DELETE
    old_data JSONB,
    new_data JSONB,
    changed_by UUID REFERENCES users(id),
    changed_at TIMESTAMP DEFAULT now()
);
```

## Indexing Strategy

| Query pattern | Index type |
|---------------|-----------|
| `WHERE email = ?` | B-tree (default) |
| `WHERE status IN (...)` | B-tree |
| `WHERE name ILIKE '%foo%'` | GIN trigram (`pg_trgm`) |
| `WHERE tags @> '["x"]'` | GIN (jsonb) |
| `WHERE ST_Within(...)` | GiST (spatial) |
| `ORDER BY created_at DESC LIMIT 20` | B-tree on `created_at` |
| Composite: `WHERE user_id = ? AND created_at > ?` | `(user_id, created_at)` |

**Rules:**
- Index columns in WHERE, JOIN ON, ORDER BY
- Composite index order: equality columns first, range last
- Don't over-index — each index slows writes
- Partial indexes for filtered subsets: `WHERE is_active = true`

## Migrations Best Practices

1. **One migration per change** — don't bundle unrelated changes
2. **Always reversible** — write both `up` and `down`
3. **No data loss** — add columns as nullable first, backfill, then add NOT NULL
4. **Zero-downtime** — add new column → deploy code that writes both → backfill → drop old
5. **Test on production-size data** — migrations that work on 100 rows may lock on 10M

## ORM Guidelines

- Use ORM for CRUD, raw SQL for complex queries
- Always eager-load relationships to avoid N+1
- Use `.select()` / `.only()` to fetch needed columns
- Profile generated SQL in development
- Never trust ORM to generate optimal queries for analytics

## PostgreSQL vs MySQL vs SQLite

| Feature | PostgreSQL | MySQL | SQLite |
|---------|-----------|-------|--------|
| Best for | Complex queries, JSONB | Simple apps, replication | Embedded, dev, prototyping |
| JSON support | Excellent (JSONB) | Basic (JSON) | Basic (json functions) |
| Full-text search | Built-in (tsvector) | Built-in (FULLTEXT) | FTS5 extension |
| Concurrency | MVCC, excellent | OK with InnoDB | Single-writer |
| Extensions | Rich ecosystem | Limited | Limited |

## Redis Patterns

```bash
# Common operations
SET user:123:session "token_abc" EX 3600    # with 1h expiry
GET user:123:session
INCR rate:ip:1.2.3.4                        # rate limiting counter
EXPIRE rate:ip:1.2.3.4 60                   # 60s window
LPUSH queue:emails '{"to":"a@b.com"}'       # job queue
RPOP queue:emails                           # consume job
```

| Pattern | Redis structure | Use case |
|---------|----------------|----------|
| **Cache** | `SET key value EX ttl` | Query results, API responses |
| **Session** | `HSET session:{id} field value` | User sessions |
| **Rate limit** | `INCR + EXPIRE` | API throttling |
| **Queue** | `LPUSH + BRPOP` | Background jobs |
| **Pub/Sub** | `PUBLISH + SUBSCRIBE` | Real-time notifications |
| **Sorted set** | `ZADD leaderboard score user` | Rankings, feeds |
| **Lock** | `SET lock:resource NX EX 10` | Distributed locking |

## Connection Pooling

### PostgreSQL (pgBouncer)
```ini
# pgbouncer.ini
[databases]
mydb = host=localhost dbname=mydb

[pgbouncer]
pool_mode = transaction       # recommended for web apps
max_client_conn = 1000
default_pool_size = 20
min_pool_size = 5
```

### Python (asyncpg)
```python
import asyncpg

pool = await asyncpg.create_pool(
    dsn="postgresql://user:pass@localhost/mydb",
    min_size=5,
    max_size=20,
    command_timeout=10,
)

async with pool.acquire() as conn:
    rows = await conn.fetch("SELECT * FROM users WHERE id = $1", user_id)
```

### Prisma (Node.js)
```typescript
// Singleton pattern — never create multiple PrismaClient instances
import { PrismaClient } from "@prisma/client"

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient }
export const prisma = globalForPrisma.prisma ?? new PrismaClient()
if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma
```

## Backup & Recovery

```bash
# PostgreSQL
pg_dump -Fc mydb > backup.dump                    # compressed backup
pg_restore -d mydb backup.dump                    # restore
pg_dump --schema-only mydb > schema.sql           # schema only

# Automated daily backup (cron)
0 3 * * * pg_dump -Fc mydb > /backups/mydb_$(date +\%Y\%m\%d).dump
```

**Strategy:**
- Daily full backup + WAL archiving for point-in-time recovery
- Test restores monthly (untested backups = no backups)
- Keep 7 daily + 4 weekly + 3 monthly backups
- Store offsite (S3, GCS) with encryption

## Query Debugging Commands

```sql
-- PostgreSQL: analyze slow query
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders WHERE user_id = 123 ORDER BY created_at DESC LIMIT 20;

-- Find missing indexes (queries without index scans)
SELECT query, calls, mean_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;

-- Table bloat and maintenance
VACUUM ANALYZE users;                  -- update stats + reclaim space
REINDEX INDEX idx_users_email;         -- rebuild corrupted index
SELECT pg_size_pretty(pg_total_relation_size('users'));  -- table size
```

## Database Design Checklist

- [ ] Every table has a primary key
- [ ] Foreign keys have ON DELETE behavior defined (CASCADE, SET NULL, RESTRICT)
- [ ] Indexes exist for all WHERE/JOIN/ORDER BY columns in frequent queries
- [ ] No nullable columns that should be NOT NULL
- [ ] Timestamps use TIMESTAMPTZ (timezone-aware), not TIMESTAMP
- [ ] UUIDs used for public-facing IDs (auto-increment for internal)
- [ ] Migrations are reversible and tested on production-size data
- [ ] Connection pooling configured (not one connection per request)
- [ ] Backup strategy defined and tested
- [ ] Sensitive data encrypted at rest (PII, tokens, passwords)
