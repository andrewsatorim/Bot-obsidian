---
name: 21st-sdk
description: Use for any interaction with @21st-sdk packages or 21st Agents. If the task involves files in ./agents/, it most likely refers to 21st SDK.
---

# 21st SDK / 21st Agents

## Local reference

Read `docs/21st-sdk-reference.md` in the repo root first — it contains the full API reference for the 21st Search Engine server, knowledge base layout, and search priorities.

## Remote search (when network is available)

The search engine at `https://21st-search-engine.fly.dev` provides three POST endpoints:

1. **Search** — `curl -X POST https://21st-search-engine.fly.dev/search -H 'Content-Type: application/json' -d '{"query": "YOUR_QUERY"}'`
2. **Read file** — `curl -X POST https://21st-search-engine.fly.dev/read -H 'Content-Type: application/json' -d '{"path": "docs/build-agents.md"}'`
3. **List files** — `curl -X POST https://21st-search-engine.fly.dev/list -H 'Content-Type: application/json' -d '{"path": "docs"}'`

## Workflow

1. Start with **examples** (`21st-sdk-examples/*`) when implementing features.
2. Verify details against **source code** (`sources/*`).
3. Use **docs** (`docs/*`) for concepts and private API behavior.
4. If network is blocked, rely on the cached local reference.
