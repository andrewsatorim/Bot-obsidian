---
name: security
description: Use when handling authentication, authorization, input validation, secrets management, or any security-sensitive code. Also use proactively when writing code that handles user input, API endpoints, or database queries.
---

# Security

## OWASP Top 10 — Prevention

| Vulnerability | Prevention |
|---------------|------------|
| **Injection** (SQL, NoSQL, OS) | Parameterized queries, ORMs, never string concat user input into queries/commands |
| **Broken Auth** | bcrypt/argon2 for passwords, short-lived JWTs, refresh token rotation, MFA |
| **Sensitive Data Exposure** | HTTPS everywhere, encrypt at rest, never log secrets/tokens/passwords |
| **XXE** | Disable external entity processing in XML parsers |
| **Broken Access Control** | Check permissions server-side on every request, deny by default |
| **Security Misconfiguration** | Minimal permissions, disable debug in prod, update dependencies |
| **XSS** | Escape output, CSP headers, avoid `dangerouslySetInnerHTML` / `v-html` |
| **Insecure Deserialization** | Validate/schema-check input, never deserialize untrusted data |
| **Known Vulnerabilities** | `npm audit` / `pip audit`, automated dependency updates |
| **Insufficient Logging** | Log auth events, access denials, input validation failures (never log secrets) |

## Input Validation

```python
# ALWAYS validate at system boundaries
from pydantic import BaseModel, Field, validator

class CreateUserRequest(BaseModel):
    email: str = Field(..., max_length=254)
    name: str = Field(..., min_length=1, max_length=100)
    age: int = Field(..., ge=0, le=150)
    
    @validator("email")
    def validate_email(cls, v):
        if "@" not in v:
            raise ValueError("Invalid email")
        return v.lower().strip()
```

**Rules:**
- Validate type, length, format, range
- Whitelist allowed values, don't blacklist bad ones
- Validate on server even if client validates too
- Sanitize for the output context (HTML, SQL, URL, shell)

## Authentication Patterns

### Password Storage
```python
# NEVER: md5, sha1, sha256, plain text
# ALWAYS: bcrypt, argon2, scrypt with salt
import bcrypt
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
```

### JWT Best Practices
- Short expiry (15 min access, 7 day refresh)
- Store refresh token in httpOnly secure cookie
- Never store in localStorage (XSS vulnerable)
- Include `iat`, `exp`, `sub`, `iss` claims
- Rotate refresh tokens on use (detect theft)

### Session Security
- `httpOnly` — JS can't read cookie
- `secure` — HTTPS only
- `sameSite: strict` — CSRF protection
- Regenerate session ID after login

## Authorization

```python
# Check on every request, not just UI
@require_role("admin")
async def delete_user(request):
    user_id = request.path_params["id"]
    # Also check: can THIS admin delete THIS user?
    if not can_delete(request.user, user_id):
        raise Forbidden()
```

- **RBAC** (Role-Based) — user has roles, roles have permissions
- **ABAC** (Attribute-Based) — rules based on user/resource/context attributes
- **Row-level** — user can only access their own data (`WHERE owner_id = ?`)

## Secrets Management

| DO | DON'T |
|----|-------|
| Environment variables | Hardcode in source |
| `.env` files (gitignored) | Commit `.env` to git |
| Secret managers (Vault, AWS SM) | Log secrets |
| Rotate keys regularly | Share keys in chat/email |
| Least privilege access | Use production keys in dev |

## HTTP Security Headers

```
Content-Security-Policy: default-src 'self'; script-src 'self'
Strict-Transport-Security: max-age=63072000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

## Rate Limiting

- Login endpoints: 5 attempts per minute per IP
- API endpoints: 100 requests per minute per user
- Password reset: 3 per hour per email
- Use token bucket or sliding window algorithm
- Return `429 Too Many Requests` with `Retry-After` header

## OAuth2 / OIDC Flow

```
User → App → Authorization Server (Google, GitHub)
  1. App redirects to /authorize?client_id=...&redirect_uri=...&scope=openid email
  2. User logs in and consents
  3. Auth server redirects to app with ?code=AUTHORIZATION_CODE
  4. App exchanges code for tokens (server-side POST to /token)
  5. App validates id_token, creates session
```

### Implementation (Next.js + NextAuth.js)
```typescript
import NextAuth from "next-auth"
import GitHub from "next-auth/providers/github"

export const { handlers, auth } = NextAuth({
  providers: [
    GitHub({ clientId: process.env.GITHUB_ID!, clientSecret: process.env.GITHUB_SECRET! }),
  ],
  callbacks: {
    authorized: async ({ auth }) => !!auth,
  },
})
```

### Common Mistakes
- Storing tokens in localStorage (use httpOnly cookies)
- Not validating `state` parameter (CSRF attack)
- Not checking token `aud` claim (token confusion)
- Using implicit flow (deprecated — use PKCE)

## Content Security Policy (Framework-Specific)

### Next.js (next.config.js)
```javascript
const cspHeader = `
  default-src 'self';
  script-src 'self' 'nonce-{nonce}';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: https:;
  connect-src 'self' https://api.example.com;
  frame-ancestors 'none';
  form-action 'self';
`
```

### Express.js (helmet)
```javascript
import helmet from "helmet"
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"],
    }
  }
}))
```

## Supply Chain Security

```bash
# Audit dependencies
npm audit                         # Node
pip audit                         # Python
gh secret-scanning                # GitHub repo scan

# Lock file integrity
npm ci                           # always use ci, not install, in CI
pip install --require-hashes     # verify package hashes

# Automated updates
# Use Dependabot or Renovate for automated PRs
```

### .npmrc Security
```
ignore-scripts=true              # prevent postinstall attacks
audit-level=high                 # fail on high severity
```

## Security Audit Checklist

- [ ] All endpoints require authentication (except public ones explicitly listed)
- [ ] Authorization checked server-side on every request
- [ ] Input validated with schema (Pydantic, Zod, Joi)
- [ ] No secrets in code, logs, or error responses
- [ ] HTTPS enforced (HSTS header set)
- [ ] CORS configured with explicit origins (no `*` in production)
- [ ] SQL queries use parameterized statements
- [ ] File uploads: validate type, limit size, scan for malware
- [ ] Rate limiting on auth endpoints
- [ ] Dependency audit passes with no critical/high vulnerabilities
- [ ] CSP headers configured
- [ ] Sensitive cookies: httpOnly, secure, sameSite=strict
- [ ] Password requirements: min 8 chars, bcrypt/argon2 hashing
- [ ] Session invalidated on password change / logout
