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
