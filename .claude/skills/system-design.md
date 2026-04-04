---
name: system-design
description: Use when designing system architecture, API contracts, database schemas, microservices, scalability patterns, or making architectural decisions.
---

# System Design

## Design Process

1. **Clarify requirements** — functional (what it does), non-functional (scale, latency, availability), constraints (budget, team, timeline).
2. **Estimate scale** — users, requests/sec, data size, read/write ratio.
3. **Define API contract** — endpoints, request/response schemas, error codes.
4. **Design data model** — entities, relationships, indexes, partitioning strategy.
5. **High-level architecture** — components, data flow, communication patterns.
6. **Deep dive** — address bottlenecks, failure modes, scaling strategies.

## Architecture Patterns

| Pattern | When to use |
|---------|-------------|
| **Monolith** | MVP, small team, simple domain |
| **Modular monolith** | Growing complexity, one deploy unit, clear boundaries |
| **Microservices** | Independent scaling, large teams, polyglot requirements |
| **Event-driven** | Async workflows, decoupled producers/consumers |
| **CQRS** | Different read/write patterns, complex queries |
| **Hexagonal (Ports & Adapters)** | Testability, swappable infrastructure |
| **Serverless** | Sporadic traffic, zero-ops requirement |

## API Design

### REST Conventions

- **Nouns for resources** — `/users`, `/orders`, `/products`
- **HTTP verbs for actions** — GET (read), POST (create), PUT (replace), PATCH (update), DELETE
- **Plural resource names** — `/users/123`, not `/user/123`
- **Nested for relationships** — `/users/123/orders`
- **Query params for filtering** — `?status=active&sort=-created_at&limit=20`
- **Consistent error format**:
  ```json
  {"error": {"code": "NOT_FOUND", "message": "User not found", "details": []}}
  ```
- **Versioning** — `/api/v1/` prefix or `Accept: application/vnd.api.v1+json`

### Status Codes

- `200` OK, `201` Created, `204` No Content
- `400` Bad Request, `401` Unauthorized, `403` Forbidden, `404` Not Found, `409` Conflict, `422` Validation Error, `429` Rate Limited
- `500` Internal Error, `502` Bad Gateway, `503` Service Unavailable

## Database Selection

| Type | Use case | Examples |
|------|----------|---------|
| **Relational** | Structured data, transactions, joins | PostgreSQL, MySQL |
| **Document** | Flexible schema, nested data | MongoDB, Firestore |
| **Key-Value** | Cache, sessions, counters | Redis, DynamoDB |
| **Wide-Column** | Time series, high write throughput | Cassandra, ScyllaDB |
| **Graph** | Relationships, social networks | Neo4j, Neptune |
| **Vector** | Embeddings, similarity search | Pinecone, pgvector |

## Scaling Strategies

- **Vertical** — bigger machine (quick, limited ceiling)
- **Horizontal** — more machines behind load balancer
- **Caching** — Redis/Memcached for hot data, CDN for static assets
- **Database** — read replicas, sharding, connection pooling
- **Async processing** — message queues (SQS, RabbitMQ, Kafka) for background jobs
- **Rate limiting** — token bucket or sliding window per user/IP

## Reliability

- **Health checks** — `/health` endpoint, readiness vs liveness
- **Circuit breaker** — fail fast when downstream is unhealthy
- **Retries** — exponential backoff with jitter, max attempts
- **Idempotency** — idempotency keys for POST/payment operations
- **Graceful degradation** — fallback responses, feature flags
- **Observability** — structured logging, metrics (RED: Rate/Error/Duration), distributed tracing
