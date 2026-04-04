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

## Profiling Checklist

1. **Measure first** — don't guess where the bottleneck is
2. **Set a target** — "page load < 2s", "API response < 200ms"
3. **Fix the biggest bottleneck** — one change at a time
4. **Measure again** — verify improvement
5. **Stop when target is met** — don't over-optimize
