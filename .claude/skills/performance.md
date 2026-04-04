---
name: performance
description: Use when optimizing load times, runtime performance, bundle size, database queries, memory usage, or Core Web Vitals. Also use when profiling or diagnosing slowness.
---

# Performance Optimization

## Core Web Vitals

| Metric | Target | What it measures |
|--------|--------|------------------|
| **LCP** (Largest Contentful Paint) | < 2.5s | Main content visible |
| **INP** (Interaction to Next Paint) | < 200ms | Responsiveness to input |
| **CLS** (Cumulative Layout Shift) | < 0.1 | Visual stability |

## Frontend Performance

### Loading
- **Code splitting** — `React.lazy()` + `Suspense`, dynamic `import()`
- **Tree shaking** — use ESM imports, avoid barrel files (`index.ts` re-exports)
- **Images** — `<Image>` (Next.js), `loading="lazy"`, `srcset`, WebP/AVIF, explicit `width`/`height`
- **Fonts** — `font-display: swap`, preload critical fonts, subset unused glyphs
- **Critical CSS** — inline above-the-fold styles, defer the rest
- **Prefetch** — `<link rel="prefetch">` for likely next pages

### Runtime
- **Memoization** — `useMemo` for expensive computations, `React.memo` for pure components
- **Virtualization** — `react-window` or `tanstack-virtual` for long lists (>100 items)
- **Debounce** — search inputs, resize handlers (150-300ms)
- **Throttle** — scroll handlers, mousemove (16ms = 60fps)
- **Web Workers** — offload heavy computation from main thread
- **Avoid layout thrashing** — batch DOM reads, then DOM writes

### Bundle Size
- `import { specific } from "library"` not `import library`
- Replace moment.js → date-fns or dayjs
- Replace lodash → lodash-es or native methods
- Analyze with `npx @next/bundle-analyzer` or `npx vite-bundle-visualizer`

## Backend Performance

### Database
- **Indexes** — on columns used in WHERE, JOIN, ORDER BY
- **N+1 queries** — use eager loading / `JOIN` / `SELECT ... IN (...)`
- **Pagination** — cursor-based for infinite scroll, offset for page numbers
- **Connection pooling** — reuse connections, don't open/close per query
- **Query analysis** — `EXPLAIN ANALYZE` to check execution plans
- **Denormalize** — when read speed > write consistency for specific use cases

### API
- **Compression** — gzip/brotli for responses > 1KB
- **Caching** — `Cache-Control` headers, ETags, Redis for computed results
- **Pagination** — never return unbounded lists
- **Field selection** — `?fields=id,name,email` to reduce payload
- **Batch endpoints** — one request for multiple resources

### Python Specific
- **Async I/O** — `asyncio` + `aiohttp`/`httpx` for concurrent requests
- **Generators** — `yield` instead of building large lists in memory
- **`__slots__`** — reduce memory per instance for many objects
- **Profile first** — `cProfile`, `line_profiler`, `py-spy` before optimizing

## Caching Strategy

```
Request → CDN Cache → App Cache (Redis) → Database
```

| Layer | TTL | Use for |
|-------|-----|---------|
| **Browser** | seconds-hours | Static assets, API responses |
| **CDN** | minutes-days | Static files, public pages |
| **Application** | seconds-minutes | Computed results, session data |
| **Database** | varies | Query result cache |

**Invalidation:** time-based (TTL), event-based (publish on write), versioned keys.

## Profiling Tools & Commands

### Frontend
```bash
# Lighthouse CI (automated performance audits)
npm install -g @lhci/cli
lhci autorun --collect.url=http://localhost:3000

# Next.js bundle analysis
ANALYZE=true next build    # with @next/bundle-analyzer

# Vite bundle analysis
npx vite-bundle-visualizer

# Chrome DevTools
# Performance tab → Record → Interact → Stop → Analyze flame chart
# Network tab → Throttle to "Slow 3G" → Check waterfall
```

### Backend
```bash
# Python profiling
python -m cProfile -s cumtime app.py          # built-in profiler
py-spy top --pid $(pgrep -f "python app.py")  # live top-like view
py-spy record -o profile.svg -- python app.py # flame graph

# Node.js profiling
node --prof app.js                  # V8 profiler
node --prof-process isolate-*.log   # process output
clinic doctor -- node app.js       # automatic diagnosis

# Load testing
k6 run load-test.js                # k6 (recommended)
ab -n 1000 -c 50 http://localhost:3000/api/users  # Apache Bench (quick)
```

### k6 Load Test Example
```javascript
import http from "k6/http"
import { check, sleep } from "k6"

export const options = {
  stages: [
    { duration: "30s", target: 20 },   // ramp up
    { duration: "1m", target: 20 },    // sustain
    { duration: "10s", target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ["p(95)<500"],   // 95th percentile < 500ms
    http_req_failed: ["rate<0.01"],     // error rate < 1%
  },
}

export default function () {
  const res = http.get("http://localhost:3000/api/users")
  check(res, { "status 200": (r) => r.status === 200 })
  sleep(1)
}
```

## Real-World Optimization Cases

### Case: Slow React list (10,000 items)
- **Problem:** Full DOM render, 3s paint time
- **Fix:** `@tanstack/react-virtual` → only renders visible rows
- **Result:** 16ms render, 60fps scroll

### Case: N+1 API queries
- **Problem:** `/api/orders` made 1 query for orders + 1 per order for user
- **Fix:** `SELECT orders.*, users.name FROM orders JOIN users ON ...`
- **Result:** 200ms → 15ms, 101 queries → 1

### Case: Large bundle (2.5MB)
- **Problem:** importing entire lodash + moment.js
- **Fix:** `lodash-es` specific imports + `dayjs` replacement
- **Result:** 2.5MB → 380KB gzipped

## Performance Budget

| Asset type | Budget | Tool to enforce |
|-----------|--------|-----------------|
| Total JS | < 200KB gzipped | bundlesize, size-limit |
| Total CSS | < 50KB gzipped | bundlesize |
| Hero image | < 100KB | imagemin, sharp |
| Web font | < 50KB per weight | subsetting |
| LCP | < 2.5s | Lighthouse CI |
| TTI | < 3.5s | Lighthouse CI |
| API response | < 200ms p95 | k6, Datadog |

## Profiling Checklist

1. **Measure first** — don't guess where the bottleneck is
2. **Set a target** — "page load < 2s", "API response < 200ms"
3. **Fix the biggest bottleneck** — one change at a time
4. **Measure again** — verify improvement
5. **Stop when target is met** — don't over-optimize

## Performance Verification

- [ ] Lighthouse score > 90 (Performance)
- [ ] LCP < 2.5s on 3G throttle
- [ ] No layout shifts (CLS < 0.1)
- [ ] Bundle size within budget
- [ ] API p95 latency < target
- [ ] No N+1 queries (check query count in dev)
- [ ] Images lazy-loaded below fold
- [ ] Fonts preloaded with `font-display: swap`
- [ ] Static assets have cache headers (1 year for hashed, no-cache for HTML)
