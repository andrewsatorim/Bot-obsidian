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

## Red Flags

- Test mirrors implementation line-by-line → test behavior instead
- Test breaks when refactoring without behavior change → too coupled
- Test passes when code is deleted → test asserts nothing useful
- Test requires complex setup (>10 lines of arrange) → simplify design
- Flaky test → fix or delete, never skip permanently
