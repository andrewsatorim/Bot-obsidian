21st Search Engine

Overview
- This server searches local files stored under the data/ directory inside the container.
- Search is powered by ripgrep.
- Default search mode is substring.
- Search results are sorted by path and then by line number.
- Search result limit is fixed at 50 items.
- Search context is fixed at 2 lines before and 2 lines after each match.

Search Priorities
- For exact behavior, API details, and implementation truth, rely on public source code first when it is available.
- Documentation is a high-level summary of the codebase and architecture.
- IMPORTANT: Some parts of the system are private and are not present in this public source tree. For those parts, rely on documentation because it may describe behavior and mechanisms that you cannot verify in code here.
- If the user asks you to implement something, start with examples first. The examples are working reference implementations and are usually the best guide for how code should be written and wired together.
- After checking examples, verify important details against the underlying source code.

Knowledge Base Layout
- docs/* — public documentation for 21st Agents and the SDK: concepts, API reference, templates, troubleshooting, and architecture notes. Some behaviors for private parts of the system may only be described here.
- 21st-sdk-examples/* — complete working example apps and agents. Use these first when the user asks you to implement something or wants to see recommended integration patterns.
- sources/* — public source code for the SDK libraries.
- sources/agent/* — agent authoring layer: define agents, tools, runtime settings, hooks, sandbox options, and shared agent types.
- sources/cli/* — terminal CLI for initializing projects, finding agents in ./agents/, bundling code, deploying agents, and managing env/logs.
- sources/golang-sdk/* — Go SDK for programmatic access to sandboxes, threads, tokens, and related API operations.
- sources/nextjs/* — Next.js integration layer, especially token route helpers and framework-specific chat setup.
- sources/node/* — server-side JavaScript/TypeScript SDK for sandboxes, threads, tokens, and core API access.
- sources/python-sdk/* — Python SDK for sandboxes, threads, tokens, command execution, file operations, and related API access.
- sources/react/* — React UI layer: chat components, tool renderers, theming, message rendering, and client-side helpers.

Docs Sections
- docs/introduction.md — top-level overview of 21st Agents and the overall platform.
- docs/get-started-quickstart.md — the main onboarding path for learning the SDK, project setup, and the recommended starting workflow.
- docs/get-started-core-concepts.md — explains the main building blocks and architecture: agents, skills, sandboxes, threads, runtime model, and how the pieces fit together.
- docs/get-started-try-it-out.md — fast hands-on path for trying the SDK and runtime end to end.
- docs/api-reference*.md — API-level reference for core backend concepts like sandboxes, threads, chat, operations, and errors.
- docs/build-*.md — how to author and configure agents, system prompts, skills, sandbox behavior, themes, and tools/MCP integrations.
- docs/deploy-*.md — how to deploy and operate agents, connect backend/frontend integrations, and use logs and observability.
- docs/security-*.md — security model, API keys, and environment variable guidance.
- docs/templates*.md — template overviews and example-specific docs for ready-made agent/app patterns.
- docs/reference-server.md — server SDK reference material.
- docs/knowledge-base.md — entry point for practical guidance, caveats, and operational notes that are useful when the answer is not obvious from public source code.
- docs/knowledge-base-best-practices.md — recommended implementation patterns, tradeoffs, and guidance on using the SDK correctly.
- docs/knowledge-base-claude-code-agent.md — guidance for building production agents with Claude Code and the expected project/runtime setup around that workflow.
- docs/knowledge-base-messages-and-history.md — how conversations, message history, and related runtime behavior are expected to work.
- docs/knowledge-base-models-and-providers.md — guidance on model/provider choices, tradeoffs, and runtime considerations.
- docs/knowledge-base-sandboxes.md — sandbox lifecycle, infrastructure behavior, and operational details around sandboxes and related systems.
- docs/knowledge-base-troubleshooting.md — common failure modes, debugging steps, and issue diagnosis guidance.

Routes

IMPORTANT: Most data routes on this server use POST, not GET.
- If you are an agent and need actual data from this server, call the routes directly with curl and send a JSON body when required.
- Do not rely on opening the route in a browser or sending GET requests to data routes like /search, /read, or /list. Those requests will not work correctly for fetching results.

GET /health
- Returns basic liveness information.
- Response:
  {"status":"ok","timestamp":"2026-04-02T12:00:00.000Z"}

GET /help
- Returns this help text as plain text.

POST /search
- Searches across all indexed sources.
- Request body:
  {
    "query": "createThread",
    "mode": "substring"
  }
- Fields:
  - query: required string
  - mode: optional, "substring" or "regex"
- Defaults:
  - mode defaults to "substring"
- Notes:
  - substring mode uses fixed-string ripgrep search
  - regex mode uses ripgrep regex search
  - regex errors return HTTP 400
- Response:
  {
    "query": "createThread",
    "count": 1,
    "results": [
      {
        "path": "sources/node/src/client.ts",
        "source": "sources/node",
        "lineNumber": 42,
        "line": "export async function createThread() {",
        "before": ["..."],
        "after": ["..."]
      }
    ]
  }

POST /read
- Reads a full file or a line range from data/.
- Request body:
  {
    "path": "sources/node/src/client.ts",
    "startLine": 35,
    "endLine": 60
  }
- Fields:
  - path: required string
  - startLine: optional 1-based number
  - endLine: optional 1-based number
- Response:
  {
    "path": "sources/node/src/client.ts",
    "source": "sources/node",
    "startLine": 35,
    "endLine": 60,
    "lines": ["..."]
  }

POST /list
- Lists files under data/.
- Request body:
  {
    "path": "sources/node/src"
  }
- Fields:
  - path: optional string
- Behavior:
  - if omitted, lists all files in data/ recursively
  - if path points to a directory, lists all nested files recursively
  - if path points to a file, returns that single file
- Response:
  {
    "path": "sources/node/src",
    "count": 3,
    "files": [
      "sources/node/src/client.ts",
      "sources/node/src/index.ts",
      "sources/node/src/types.ts"
    ]
  }
