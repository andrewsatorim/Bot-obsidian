---
name: testing
description: Use when writing tests, designing test strategy, choosing what to test, setting up test infrastructure, TDD, mocking, or debugging test failures.
---

# Testing

## What to Test

| Priority | What | Why |
|----------|------|-----|
| **Always** | Business logic, state machines, calculations | Core value, breaks silently |
| **Always** | API contracts (request/response shapes) | Integration boundary |
| **Always** | Edge cases (empty, null, boundary values) | Common bug source |
| **Usually** | Error handling and recovery paths | Users hit these |
| **Sometimes** | UI interactions (click, submit, navigate) | Catches regressions |
| **Rarely** | Implementation details, private methods | Brittle, couples to internals |

## Test Pyramid

```
        /  E2E  \          Few, slow, high confidence
       /  Integ  \         Some, medium speed
      /   Unit    \        Many, fast, isolated
```

- **Unit** (70%) — pure functions, class methods, isolated logic. No I/O.
- **Integration** (20%) — components with dependencies, API routes, DB queries.
- **E2E** (10%) — critical user flows only (signup, checkout, core workflow).

## Naming Convention

```
test_<unit>_<scenario>_<expected_result>

test_calculate_total_with_discount_returns_reduced_price
test_login_with_invalid_password_returns_401
test_cart_when_empty_shows_empty_state
```

## Test Structure (AAA)

```python
def test_example():
    # Arrange — set up data and dependencies
    user = create_user(role="admin")
    
    # Act — execute the thing being tested
    result = user.can_access("/admin")
    
    # Assert — verify the outcome
    assert result is True
```

## Mocking Rules

1. **Mock at boundaries** — external APIs, databases, file system, time, randomness
2. **Don't mock what you own** — use fakes/stubs for your own code
3. **One mock per test** — if you need 5 mocks, the code needs refactoring
4. **Verify behavior, not implementation** — assert results, not that method X was called N times
5. **Prefer dependency injection** — pass dependencies in, don't patch globals

## Fixtures and Factories

```python
# Factory — creates test data with sensible defaults
def make_user(**overrides) -> User:
    defaults = {"name": "Test User", "email": "test@example.com", "role": "user"}
    return User(**(defaults | overrides))

# Usage — override only what matters for THIS test
def test_admin_access():
    admin = make_user(role="admin")
    assert admin.can_access("/admin")
```

## Testing Async Code (Python)

```python
import pytest

@pytest.mark.asyncio
async def test_fetch_data():
    result = await fetch_data("BTC")
    assert result.symbol == "BTC"
```

## Testing React Components

```tsx
import { render, screen, fireEvent } from "@testing-library/react"

test("submit button calls onSubmit", () => {
  const onSubmit = vi.fn()
  render(<Form onSubmit={onSubmit} />)
  
  fireEvent.click(screen.getByRole("button", { name: /submit/i }))
  
  expect(onSubmit).toHaveBeenCalledOnce()
})
```

## E2E Testing (Playwright)

```typescript
import { test, expect } from "@playwright/test"

test("user can sign up and see dashboard", async ({ page }) => {
  await page.goto("/signup")
  await page.fill('[name="email"]', "test@example.com")
  await page.fill('[name="password"]', "SecureP@ss123")
  await page.click('button[type="submit"]')
  
  await expect(page).toHaveURL("/dashboard")
  await expect(page.getByRole("heading")).toContainText("Welcome")
})
```

### Playwright Setup
```bash
npm init playwright@latest
npx playwright test                    # run all
npx playwright test --ui               # interactive UI
npx playwright test --project=chromium # single browser
npx playwright codegen localhost:3000  # record actions
```

### Cypress Alternative
```bash
npx cypress open     # interactive
npx cypress run      # headless CI
```

## Snapshot & Visual Regression

```typescript
// Component snapshot (Vitest)
import { render } from "@testing-library/react"
test("Button matches snapshot", () => {
  const { container } = render(<Button>Click</Button>)
  expect(container).toMatchSnapshot()
})

// Visual regression (Playwright)
test("homepage visual", async ({ page }) => {
  await page.goto("/")
  await expect(page).toHaveScreenshot("homepage.png", { maxDiffPixels: 100 })
})
```

## Coverage Strategy

```bash
# Python
pytest --cov=app --cov-report=html --cov-fail-under=80

# JavaScript/TypeScript
vitest run --coverage
# or
npx c8 node --test
```

| Coverage target | When |
|----------------|------|
| 80%+ lines | Most projects — good balance |
| 90%+ lines | Critical systems (payments, auth) |
| 100% branches | State machines, parsers |
| Don't chase | 100% lines everywhere — diminishing returns |

Focus coverage on **business logic**, not boilerplate/config.

## Testing Tools Reference

| Language | Unit | Integration | E2E | Mocking |
|----------|------|-------------|-----|---------|
| **Python** | pytest | pytest + httpx | Playwright | unittest.mock, pytest-mock |
| **TypeScript** | Vitest | Supertest | Playwright, Cypress | vi.fn(), msw |
| **React** | Vitest + RTL | Storybook interaction | Playwright | msw (API mocks) |
| **Go** | testing pkg | testcontainers | Playwright | gomock |

### MSW (Mock Service Worker) — API Mocking for Frontend
```typescript
import { http, HttpResponse } from "msw"
import { setupServer } from "msw/node"

const server = setupServer(
  http.get("/api/users", () => HttpResponse.json([{ id: 1, name: "Alice" }]))
)
beforeAll(() => server.listen())
afterAll(() => server.close())
```

## Test Quality Checklist

- [ ] Tests run in < 30 seconds (unit suite)
- [ ] No test depends on another test's state
- [ ] No hardcoded sleep/wait — use assertions with timeout
- [ ] CI runs tests on every PR
- [ ] Coverage report generated and tracked
- [ ] Flaky tests are fixed within 48 hours or deleted
- [ ] New features always include tests
- [ ] Edge cases covered: empty, null, max, min, unicode, concurrent

## Red Flags

- Test mirrors implementation line-by-line → test behavior instead
- Test breaks when refactoring without behavior change → too coupled
- Test passes when code is deleted → test asserts nothing useful
- Test requires complex setup (>10 lines of arrange) → simplify design
- Flaky test → fix or delete, never skip permanently
