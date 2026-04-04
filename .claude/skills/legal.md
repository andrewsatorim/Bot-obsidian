---
name: legal
description: Use when creating privacy policies, terms of service, cookie consent, GDPR compliance, data handling, or any legal/compliance requirements for web products.
---

# Legal & Compliance

**Disclaimer:** This skill provides templates and guidance, not legal advice. Consult a lawyer for your specific situation.

## Privacy Policy

### Required Sections
```markdown
# Privacy Policy
Last updated: [Date]

## What We Collect
- Account data: name, email address
- Usage data: pages visited, features used, timestamps
- Payment data: processed by Stripe (we don't store card numbers)
- Device data: browser type, IP address, operating system

## How We Use Your Data
- Provide and improve our service
- Send transactional emails (receipts, password resets)
- Marketing emails (only with your consent, unsubscribe anytime)
- Analytics to understand usage patterns (PostHog / Plausible)
- Fraud prevention and security

## Who We Share With
- Payment processor: Stripe (for billing)
- Hosting: Vercel / AWS (for infrastructure)
- Analytics: PostHog (for product analytics)
- We NEVER sell your personal data

## Data Retention
- Account data: kept while account is active + 30 days after deletion
- Usage logs: 90 days
- Payment records: 7 years (legal requirement)

## Your Rights
- Access: request a copy of your data
- Correction: update inaccurate data
- Deletion: request account and data deletion
- Portability: export your data
- Objection: opt out of marketing

## Contact
[Company Name]
[Email for privacy requests]
[Physical address — required by CAN-SPAM]
```

### Privacy Policy Tools
| Tool | What it does | Price |
|------|-------------|-------|
| **Iubenda** | Auto-generated policies, cookie consent | From $29/year |
| **Termly** | Policy generator + cookie consent | Free tier |
| **Termageddon** | Auto-updating policies | From $99/year |
| **Lawyer** | Custom, jurisdiction-specific | $500-2000+ |

## Terms of Service

### Required Sections
```markdown
# Terms of Service
Last updated: [Date]

## Acceptance
By using [Product], you agree to these terms.

## Account
- You must be 13+ (16+ in EU) to use this service
- You are responsible for your account security
- One person per account (no shared accounts)

## Acceptable Use
You may NOT:
- Use the service for illegal purposes
- Attempt to access other users' data
- Reverse-engineer, scrape, or abuse the API
- Upload malware or malicious content
- Resell access without written permission

## Intellectual Property
- Your data remains yours
- Our code, design, and brand remain ours
- You grant us a license to host and display your content

## Payment & Billing
- Prices may change with 30 days notice
- Refunds handled per our refund policy
- Failed payment → 14 days to resolve → account downgraded

## Termination
- You can cancel anytime
- We can terminate for TOS violations (with notice)
- Upon termination: data export available for 30 days

## Limitation of Liability
- Service provided "as is"
- We are not liable for data loss (but we do our best to prevent it)
- Maximum liability limited to fees paid in last 12 months

## Governing Law
These terms are governed by the laws of [Jurisdiction].

## Changes
We may update these terms. Material changes notified by email.
```

## GDPR Compliance (EU Users)

### Requirements
| Requirement | Implementation |
|-------------|----------------|
| **Lawful basis** | Consent (marketing), Contract (service delivery), Legitimate interest (analytics) |
| **Consent** | Explicit opt-in for marketing, no pre-checked boxes |
| **Right to access** | "Download my data" feature |
| **Right to delete** | "Delete my account" feature (within 30 days) |
| **Data portability** | Export in machine-readable format (JSON/CSV) |
| **Breach notification** | Notify authority within 72 hours, users without undue delay |
| **DPO** | Required if processing large-scale sensitive data |
| **Privacy by design** | Minimize data collection, encrypt, pseudonymize |

### Consent Implementation
```tsx
// Cookie consent banner
function CookieConsent() {
  return (
    <div className="fixed bottom-0 inset-x-0 bg-white border-t p-4">
      <p>We use cookies to improve your experience.</p>
      <div className="flex gap-2 mt-2">
        <button onClick={() => acceptAll()}>Accept all</button>
        <button onClick={() => acceptEssential()}>Essential only</button>
        <button onClick={() => openPreferences()}>Customize</button>
      </div>
    </div>
  )
}
```

### Cookie Categories
| Category | Examples | Consent needed? |
|----------|---------|----------------|
| **Essential** | Session, auth, CSRF | No (always allowed) |
| **Analytics** | PostHog, GA4, Plausible | Yes (opt-in in EU) |
| **Marketing** | Facebook Pixel, Google Ads | Yes (opt-in) |
| **Preferences** | Theme, language | No (functional) |

## CCPA (California)

- **"Do Not Sell My Information"** link in footer (if applicable)
- Users can opt out of data "sale" (broadly defined)
- Delete user data within 45 days of request
- Don't discriminate against users who exercise rights

## Data Handling Best Practices

### Data Minimization
```
COLLECT only what you need:
✓ Email (for auth + communication)
✓ Name (for personalization)
✗ Phone number (unless needed)
✗ Date of birth (unless required)
✗ Address (unless shipping)
```

### Data Deletion Flow
```
User requests deletion
  → Confirm via email
    → Queue deletion job (30-day grace period)
      → Delete user record
      → Delete associated data
      → Anonymize analytics (keep aggregated, remove PII)
      → Remove from email lists
      → Confirm completion via email
```

### Encryption
```python
# At rest: encrypt PII in database
from cryptography.fernet import Fernet

key = os.environ["ENCRYPTION_KEY"]
f = Fernet(key)

# Encrypt before storing
encrypted_ssn = f.encrypt(ssn.encode())

# Decrypt when reading
ssn = f.decrypt(encrypted_ssn).decode()
```

### Data Processing Agreements (DPA)
Required when using third-party processors for EU user data:
- **Stripe** → has standard DPA (sign in dashboard)
- **Vercel** → DPA available on request
- **PostHog** → DPA included (EU hosting available)
- **AWS** → DPA auto-included in service terms

## Open-Source Legal

| License | Commercial use | Must share source | Attribution |
|---------|---------------|-------------------|-------------|
| **MIT** | Yes | No | Yes (include license) |
| **Apache 2.0** | Yes | No | Yes + state changes |
| **GPL v3** | Yes | Yes (if distributed) | Yes |
| **AGPL v3** | Yes | Yes (even SaaS) | Yes |
| **BSL** | After change date | No | Yes |

**For your product:** MIT or Apache 2.0 if open-sourcing. No license = all rights reserved.

## Compliance Checklist

- [ ] Privacy Policy published and linked in footer
- [ ] Terms of Service published and linked in footer
- [ ] Cookie consent banner with opt-in (EU requirement)
- [ ] "Delete my account" functionality works
- [ ] "Export my data" functionality works (GDPR portability)
- [ ] No PII in logs or error messages
- [ ] Sensitive data encrypted at rest
- [ ] DPA signed with all third-party processors
- [ ] Payment data handled by PCI-compliant provider (Stripe)
- [ ] Marketing emails have unsubscribe link + physical address
- [ ] Breach response plan documented
- [ ] Under-13 users blocked (COPPA) or parental consent obtained
- [ ] Accessibility statement (if required in your jurisdiction)
