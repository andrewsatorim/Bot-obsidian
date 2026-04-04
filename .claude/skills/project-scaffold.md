---
name: project-scaffold
description: Use when starting a new project, setting up project structure, configuring linters, formatters, TypeScript, build tools, or establishing initial conventions.
---

# Project Scaffolding

## Decision Tree

```
What are you building?
├── Web app (full-stack) → Next.js + Tailwind + Prisma/Drizzle
├── Web app (SPA) → Vite + React + React Router + Tailwind
├── API only → FastAPI (Python) / Hono (TS) / Express (Node)
├── CLI tool → Python (click/typer) / Node (commander)
├── Library/SDK → TypeScript with tsup/tsdown bundler
├── Mobile → React Native + Expo
└── Desktop → Electron / Tauri
```

## Next.js Project Setup

```bash
npx create-next-app@latest my-app --typescript --tailwind --eslint --app --src-dir
cd my-app
```

### Recommended Structure

```
src/
├── app/                  # Routes and layouts
│   ├── (auth)/           # Route group: auth pages
│   ├── (dashboard)/      # Route group: protected pages
│   ├── api/              # API routes
│   ├── layout.tsx        # Root layout
│   └── page.tsx          # Home page
├── components/           # Shared UI components
│   ├── ui/               # Primitives (Button, Input, Card)
│   └── features/         # Feature-specific components
├── lib/                  # Utilities, helpers, configs
│   ├── db.ts             # Database client
│   ├── auth.ts           # Auth config
│   └── utils.ts          # General utilities
├── hooks/                # Custom React hooks
├── types/                # TypeScript type definitions
├── styles/               # Global styles
└── constants/            # App-wide constants
```

## Python Project Setup

```bash
mkdir my-project && cd my-project
python -m venv .venv && source .venv/bin/activate
```

### pyproject.toml

```toml
[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8", "black>=24", "ruff>=0.4", "mypy>=1.10"]

[tool.black]
line-length = 100

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "UP", "B"]

[tool.mypy]
strict = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### Python Structure

```
my_project/
├── app/
│   ├── __init__.py
│   ├── models/           # Data models
│   ├── services/         # Business logic
│   ├── api/              # Routes/endpoints
│   └── core/             # Config, dependencies
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   └── test_services.py
├── pyproject.toml
├── .gitignore
└── README.md
```

## Essential Config Files

### TypeScript (tsconfig.json)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"],
  "exclude": ["node_modules"]
}
```

### ESLint (eslint.config.js)

```js
import js from "@eslint/js"
import tseslint from "typescript-eslint"

export default tseslint.config(
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { ignores: ["dist/", "node_modules/", ".next/"] }
)
```

### Prettier (.prettierrc)

```json
{
  "semi": false,
  "singleQuote": false,
  "tabWidth": 2,
  "trailingComma": "all",
  "printWidth": 100
}
```

### .gitignore (universal)

```
node_modules/
dist/
build/
.next/
.env
.env.*
!.env.example
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.mypy_cache/
coverage/
.DS_Store
*.log
```

## First Commit Checklist

- [ ] `.gitignore` configured
- [ ] `.env.example` with all required vars (no secrets)
- [ ] Linter + formatter configured and passing
- [ ] TypeScript strict mode enabled (if TS project)
- [ ] README with: what, why, setup instructions, dev commands
- [ ] `package.json` scripts: `dev`, `build`, `lint`, `test`
- [ ] CI pipeline stub (GitHub Actions)
- [ ] License file (if open source)

## Package.json Scripts Convention

```json
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "eslint . && tsc --noEmit",
    "format": "prettier --write .",
    "test": "vitest run",
    "test:watch": "vitest",
    "db:migrate": "prisma migrate dev",
    "db:seed": "tsx scripts/seed.ts"
  }
}
```

## Go Project Setup

```bash
mkdir my-service && cd my-service
go mod init github.com/user/my-service
```

### Go Structure
```
my-service/
├── cmd/
│   └── server/main.go        # Entry point
├── internal/
│   ├── handler/               # HTTP handlers
│   ├── service/               # Business logic
│   ├── repository/            # Data access
│   └── model/                 # Domain types
├── pkg/                       # Public reusable packages
├── api/                       # OpenAPI specs, proto files
├── go.mod
├── go.sum
├── Makefile
└── Dockerfile
```

### Makefile (Go)
```makefile
.PHONY: run build test lint

run:
	go run cmd/server/main.go

build:
	CGO_ENABLED=0 go build -o bin/server cmd/server/main.go

test:
	go test ./... -race -cover

lint:
	golangci-lint run
```

## Rust Project Setup

```bash
cargo init my-project
# or with template
cargo generate --git https://github.com/rust-cli/cli-template
```

## GitHub Actions CI Template (Universal)

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      # Node.js project
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm }
      - run: npm ci
      - run: npm run lint
      - run: npm test
      - run: npm run build

      # Python project (uncomment if needed)
      # - uses: actions/setup-python@v5
      #   with: { python-version: "3.12" }
      # - run: pip install -e ".[dev]"
      # - run: ruff check .
      # - run: pytest --cov
```

## Monorepo Setup (Turborepo)

```bash
npx create-turbo@latest my-monorepo
cd my-monorepo
```

```
my-monorepo/
├── apps/
│   ├── web/            # Next.js
│   └── api/            # Backend
├── packages/
│   ├── ui/             # Shared components
│   ├── config-eslint/  # Shared ESLint config
│   ├── config-ts/      # Shared tsconfig
│   └── types/          # Shared types
├── turbo.json
├── package.json        # workspace root
└── pnpm-workspace.yaml
```

## Project Health Checklist (Week 1)

- [ ] Repository initialized with proper `.gitignore`
- [ ] README with: description, setup, dev commands, architecture
- [ ] `.env.example` with documented variables
- [ ] Linter + formatter running and enforced
- [ ] TypeScript / mypy strict mode enabled
- [ ] CI pipeline: lint → test → build on every PR
- [ ] First test written and passing
- [ ] Docker setup (Dockerfile + docker-compose) if needed
- [ ] Deployment pipeline (at least to staging)
- [ ] Error tracking setup (Sentry or similar)
- [ ] CLAUDE.md with project conventions (for AI-assisted development)
```
