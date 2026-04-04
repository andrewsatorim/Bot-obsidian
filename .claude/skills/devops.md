---
name: devops
description: Use when working with Docker, CI/CD pipelines, deployment, infrastructure, monitoring, logging, or containerization.
---

# DevOps

## Docker

### Dockerfile Best Practices

```dockerfile
# 1. Use specific base image tag (not :latest)
FROM node:22-alpine AS base

# 2. Set working directory
WORKDIR /app

# 3. Copy dependency files first (cache layer)
COPY package.json package-lock.json ./
RUN npm ci --production

# 4. Copy source after deps (changes more often)
COPY . .

# 5. Build step in separate stage
FROM base AS build
RUN npm run build

# 6. Production image — minimal
FROM node:22-alpine AS production
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
EXPOSE 3000
USER node
CMD ["node", "dist/server.js"]
```

**Rules:**
- Multi-stage builds to reduce final image size
- `.dockerignore` — exclude `node_modules`, `.git`, `.env`, tests
- One process per container
- Non-root user (`USER node` or `USER 1000`)
- Health check: `HEALTHCHECK CMD curl -f http://localhost:3000/health`
- Pin dependency versions in `RUN apt-get install package=version`

### Docker Compose

```yaml
services:
  app:
    build: .
    ports: ["3000:3000"]
    env_file: .env
    depends_on:
      db: { condition: service_healthy }
    restart: unless-stopped
    
  db:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: app
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 5

volumes:
  pgdata:
```

## CI/CD (GitHub Actions)

```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm }
      - run: npm ci
      - run: npm run lint
      - run: npm test
      - run: npm run build

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./deploy.sh
```

### CI Pipeline Stages

```
Lint → Test → Build → Security Scan → Deploy Staging → E2E → Deploy Production
```

1. **Lint** — formatting + static analysis (fast fail)
2. **Test** — unit + integration tests
3. **Build** — compile, bundle, Docker image
4. **Security** — `npm audit`, dependency scan, SAST
5. **Deploy staging** — automatic on merge to main
6. **E2E** — smoke tests against staging
7. **Deploy production** — manual approval or automatic

## Deployment Strategies

| Strategy | Downtime | Risk | Rollback |
|----------|----------|------|----------|
| **Rolling** | Zero | Low | Slow |
| **Blue/Green** | Zero | Low | Instant (switch) |
| **Canary** | Zero | Lowest | Instant (route shift) |
| **Recreate** | Brief | Medium | Redeploy |

## Monitoring & Observability

### Three Pillars

1. **Logs** — structured JSON, correlation IDs, log levels (error > warn > info > debug)
2. **Metrics** — RED method: Rate, Errors, Duration per endpoint
3. **Traces** — distributed tracing across services (OpenTelemetry)

### Alerts

- **Error rate** > 1% for 5 min → page on-call
- **Latency p99** > 2s for 5 min → warn
- **CPU/Memory** > 80% for 10 min → scale alert
- **Disk** > 90% → critical
- **Health check** fails 3x → page

## Environment Management

```
development → staging → production
    ↓            ↓          ↓
  .env.dev   .env.staging  .env.prod (secrets manager)
```

- Feature flags for gradual rollout
- Same Docker image across all environments
- Environment-specific config via env vars only
- Never promote by rebuilding — promote the artifact
