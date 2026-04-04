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

## Real-World System Breakdowns

### URL Shortener (bit.ly) — 100M links/day
```
Write path:
  Client → API → Generate short ID (base62) → Store in DB → Return short URL

Read path (99% of traffic):
  Client → CDN/Cache → API → Redis cache (hit?) → DB (miss) → 301 Redirect

Key decisions:
  - Base62 encoding (a-z, A-Z, 0-9) → 7 chars = 3.5 trillion combinations
  - Read-heavy (100:1) → cache aggressively in Redis
  - Consistent hashing for cache distribution
  - Pre-generate IDs in batches (avoid collision at scale)

Scale:
  - 100M writes/day ≈ 1,200 writes/sec
  - 10B reads/day ≈ 115K reads/sec
  - Storage: 100M × 500 bytes ≈ 50GB/day → 18TB/year
```

### Chat System (Slack/Discord) — 10M concurrent users
```
Architecture:
  Client ←WebSocket→ Connection Server ←Pub/Sub→ Message Broker → Storage

  Connection servers: stateful WebSocket per user
  Message broker: Redis Pub/Sub or Kafka for channel fan-out
  Storage: hot messages in Redis, cold in Cassandra/ScyllaDB
  Presence: heartbeat every 30s → Redis sorted set with TTL

Key decisions:
  - WebSocket for real-time (not polling)
  - Channel-based pub/sub (not user-to-user routing)
  - Eventually consistent message ordering (timestamp + Lamport clock)
  - Message retention: 90 days hot, archive to S3

Scale math:
  - 10M users × 10 channels × 5 msgs/min = 500M msgs/min
  - Each message ≈ 1KB → 500GB/min raw throughput
  - Solution: partition by channel, shard by channel_id
```

### News Feed (Twitter/X) — Fan-out problem
```
Approach 1: Fan-out on WRITE (push)
  User posts → Write to ALL followers' timelines
  ✓ Fast reads (timeline is pre-computed)
  ✗ Celebrity problem: user with 50M followers = 50M writes

Approach 2: Fan-out on READ (pull)
  User reads feed → Query all followed users' posts → Merge & sort
  ✓ No write amplification
  ✗ Slow reads (N queries per feed load)

Approach 3: Hybrid (Twitter's actual approach)
  - Regular users (<10K followers): fan-out on write
  - Celebrities (>10K followers): fan-out on read
  - Merge at read time

Data model:
  tweets: {id, user_id, text, media_urls, created_at}
  timeline: {user_id, tweet_id, created_at}  ← pre-computed for push
  follows: {follower_id, followee_id}
```

### E-Commerce (Amazon) — Inventory & Orders
```
Services:
  ├── Product Catalog (read-heavy, CDN-cached)
  ├── Inventory (strong consistency needed)
  ├── Cart (session-based, Redis)
  ├── Order (saga pattern for multi-step)
  ├── Payment (idempotent, retry-safe)
  └── Notification (async, queue-based)

Key challenge: inventory consistency
  Problem: 2 users buy last item simultaneously
  Solution: optimistic locking with version counter
    UPDATE inventory SET quantity = quantity - 1, version = version + 1
    WHERE product_id = ? AND version = ? AND quantity > 0

Order saga:
  Reserve inventory → Charge payment → Confirm order → Send notification
  If payment fails → Release inventory (compensating transaction)
```

### Video Streaming (YouTube) — Upload & Delivery
```
Upload pipeline:
  Client → Upload Server → Object Storage (S3)
    → Transcode Queue (SQS/Kafka)
      → Transcode Workers (multiple resolutions: 360p, 720p, 1080p, 4K)
        → CDN Origin → CDN Edge

Playback:
  Client → CDN Edge (cached?) → CDN Origin → Object Storage
  Adaptive bitrate: client measures bandwidth → requests appropriate quality

Storage math:
  - 500 hours uploaded/min
  - Each hour ≈ 5GB (multiple resolutions) = 2.5TB/min = 3.6PB/day
  - Solution: tiered storage (hot SSD → warm HDD → cold Glacier)
```

## Distributed Systems Patterns

### CAP Theorem (Pick 2 of 3)
```
Consistency ←→ Availability ←→ Partition Tolerance

In practice (network partitions are inevitable):
  CP: Consistency + Partition Tolerance (PostgreSQL, MongoDB)
      → System may reject writes during partition
  AP: Availability + Partition Tolerance (Cassandra, DynamoDB)
      → System always accepts writes, may have stale reads

Choose based on use case:
  Banking/payments → CP (consistency critical)
  Social feed/cache → AP (availability critical)
```

### Consensus
| Algorithm | Used by | Use case |
|-----------|---------|----------|
| **Raft** | etcd, CockroachDB | Leader election, config |
| **Paxos** | Google Spanner | Distributed transactions |
| **Gossip** | Cassandra, Redis Cluster | Membership, failure detection |
| **ZAB** | ZooKeeper | Coordination |

### Event Sourcing
```
Instead of storing current state, store all events:

Events:
  1. OrderCreated { id: 1, items: [...], total: 99.00 }
  2. PaymentReceived { order_id: 1, amount: 99.00 }
  3. OrderShipped { order_id: 1, tracking: "ABC123" }

Current state = replay all events

Benefits: full audit trail, time-travel debugging, event replay
Tradeoff: complexity, eventual consistency, storage growth
```

### Saga Pattern (Distributed Transactions)
```
Choreography (events):
  OrderService → "OrderCreated" event
    → PaymentService listens → charges → "PaymentCompleted" event
      → InventoryService listens → reserves → "InventoryReserved" event
        → NotificationService listens → sends confirmation

  If PaymentService fails → "PaymentFailed" event
    → OrderService listens → cancels order (compensating action)

Orchestration (central coordinator):
  OrderOrchestrator:
    1. Create order → success
    2. Charge payment → success
    3. Reserve inventory → FAIL
    4. Refund payment (compensate step 2)
    5. Cancel order (compensate step 1)
```

## Message Queues & Streaming

| System | Best for | Ordering | Retention |
|--------|----------|----------|-----------|
| **SQS** | Simple job queue | Per-group | 14 days |
| **RabbitMQ** | Complex routing, priorities | Per-queue | Until consumed |
| **Kafka** | Event streaming, high throughput | Per-partition | Configurable |
| **Redis Streams** | Lightweight streaming | Per-stream | Configurable |
| **NATS** | Low-latency pub/sub | No guarantee | Optional |

### When to Use a Queue
- Decoupling: producer doesn't need to wait for consumer
- Spike absorption: queue buffers burst traffic
- Retry logic: failed jobs retry automatically
- Fan-out: one event → multiple consumers

## Back-of-Envelope Estimation

### Quick Math References
```
1 million requests/day  ≈ 12 req/sec
1 billion requests/day  ≈ 12,000 req/sec
1 request = 1KB payload → 1M req/day = 1GB/day

Storage:
  1 million users × 1KB profile = 1GB
  1 million users × 10 posts × 1KB = 10GB
  1 million images × 500KB = 500GB

Latency:
  Memory read: 100 ns
  SSD read: 100 μs
  Network (same datacenter): 500 μs
  Network (cross-region): 50-150 ms
  Disk seek: 10 ms
```

### Powers of 2
```
2^10 = 1K       (thousand)
2^20 = 1M       (million)
2^30 = 1G       (billion)
2^40 = 1T       (trillion)

Useful: 1 char = 1 byte, 1 int = 4 bytes, UUID = 16 bytes
```

## GraphQL (Alternative to REST)

```typescript
// Schema
type User {
  id: ID!
  name: String!
  posts: [Post!]!
}

type Query {
  user(id: ID!): User
  users(limit: Int = 10): [User!]!
}

type Mutation {
  createUser(name: String!, email: String!): User!
}
```

### When REST vs GraphQL
| Factor | REST | GraphQL |
|--------|------|---------|
| **Multiple resources** | N requests | 1 query |
| **Over-fetching** | Common | Client picks fields |
| **Caching** | HTTP cache (easy) | Custom (harder) |
| **File upload** | Native | Needs multipart spec |
| **Real-time** | SSE/WebSocket | Subscriptions built-in |
| **Learning curve** | Low | Medium |
| **Best for** | Simple CRUD, public APIs | Complex frontends, mobile |

## System Design Checklist

- [ ] Requirements clarified (functional + non-functional)
- [ ] Scale estimated (users, RPS, data size, read/write ratio)
- [ ] API contract defined (REST/GraphQL, endpoints, schemas)
- [ ] Data model designed (entities, relationships, indexes)
- [ ] Database chosen with justification
- [ ] Caching strategy defined (what, where, TTL, invalidation)
- [ ] Async processing identified (what goes in queues)
- [ ] Failure modes addressed (circuit breaker, retry, fallback)
- [ ] Consistency model chosen (strong vs eventual, per-feature)
- [ ] Observability planned (logs, metrics, traces, alerts)
- [ ] Security: auth, rate limiting, input validation
- [ ] Deployment: how to deploy, rollback, scale
- [ ] Cost estimate: hosting, DB, CDN, queues at target scale
