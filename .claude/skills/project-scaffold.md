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
