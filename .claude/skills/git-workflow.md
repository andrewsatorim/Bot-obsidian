---
name: git-workflow
description: Use when creating commits, branches, pull requests, resolving merge conflicts, or establishing git conventions for a project.
---

# Git Workflow

## Conventional Commits

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

| Type | When |
|------|------|
| `feat` | New feature for the user |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `refactor` | Code change, no new feature or fix |
| `perf` | Performance improvement |
| `test` | Adding or fixing tests |
| `build` | Build system, dependencies |
| `ci` | CI/CD configuration |
| `chore` | Maintenance, tooling |

### Examples

```
feat(auth): add Google OAuth login
fix(cart): prevent negative quantity on decrement
refactor(api): extract validation middleware
docs(readme): add deployment instructions
perf(queries): add index on orders.user_id
test(auth): add login failure edge cases
```

### Rules

- Subject line ≤ 72 characters
- Imperative mood: "add" not "added" or "adds"
- No period at end of subject
- Body explains **why**, not what (the diff shows what)
- Breaking changes: `feat!:` or `BREAKING CHANGE:` footer

## Branching Strategy

### GitHub Flow (recommended for most projects)

```
main (always deployable)
 └── feature/add-auth
 └── fix/cart-quantity
 └── chore/update-deps
```

- `main` is always deployable
- Create branch from `main` for every change
- Open PR when ready for review
- Merge to `main` after approval + CI pass
- Deploy from `main`

### Branch Naming

```
<type>/<short-description>

feature/user-auth
fix/payment-timeout
refactor/extract-api-client
chore/upgrade-react-19
```

## Pull Request Best Practices

### PR Title
- Same as conventional commit: `feat(auth): add Google OAuth`
- Under 72 characters

### PR Description Template

```markdown
## Summary
What changed and why (1-3 bullet points).

## Changes
- Added OAuth callback handler
- Created user session on first login
- Added Google provider config

## Test plan
- [ ] Manual: sign in with Google account
- [ ] Manual: verify session persists on refresh
- [ ] Automated: unit tests pass
```

### PR Rules

- **Small PRs** — under 400 lines changed (ideal: 100-200)
- **One concern** — don't mix refactoring with features
- **Self-review first** — read your own diff before requesting review
- **Screenshots** — for any visual change
- **Link issues** — `Closes #123` in description

## Code Review

### As Reviewer

- **Be kind** — suggest, don't demand. "What about..." not "You should..."
- **Focus on** — logic errors, edge cases, security, naming, missing tests
- **Don't focus on** — style (automate with linters), personal preference
- **Approve with comments** — minor nits shouldn't block

### As Author

- **Respond to all comments** — even if just "done"
- **Don't take it personally** — review is about the code
- **Explain decisions** — help the reviewer understand context

## Merge Strategy

| Strategy | When |
|----------|------|
| **Squash merge** | Feature branches with messy commits |
| **Merge commit** | Want to preserve branch history |
| **Rebase** | Linear history, clean commits |

Recommendation: **Squash merge** for feature branches, keeps `main` history clean.

## Git Hygiene

- Never commit secrets, `.env`, credentials
- Don't commit generated files (build output, `node_modules`)
- Write `.gitignore` before first commit
- Pull before push, rebase over merge for local branches
- Tag releases: `git tag -a v1.0.0 -m "Release 1.0.0"`
