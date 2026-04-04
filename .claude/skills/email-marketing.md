---
name: email-marketing
description: Use when writing email campaigns, welcome sequences, newsletters, transactional emails, subject lines, or setting up email automation flows.
---

# Email Marketing

## Subject Lines

### Formulas
- **Curiosity gap**: "The one mistake killing your conversions"
- **Benefit + specificity**: "3 ways to cut your AWS bill by 40%"
- **Question**: "Are you making this pricing mistake?"
- **Urgency (real only)**: "Last day: 50% off annual plans"
- **Personal**: "Quick question about your project"
- **How-to**: "How to ship 2x faster with fewer bugs"

### Rules
- 30-50 characters (mobile-friendly)
- No ALL CAPS, no excessive !!!
- Preview text (preheader) complements, doesn't repeat
- A/B test subject lines on 10-20% before full send
- Avoid spam triggers: "free", "act now", "limited time", "congratulations"

## Email Types & Templates

### Welcome Email (send immediately)
```
Subject: Welcome to [Product] — here's your first step

Hey [Name],

You just signed up for [Product] — great choice.

Here's the one thing to do right now:
→ [Single CTA: "Set up your first project"]

It takes about 2 minutes, and you'll immediately see
[specific benefit].

If you need help, reply to this email — I read every one.

— [Name], Founder of [Product]
```

### Onboarding Sequence (days 1-7)
| Day | Email | Goal |
|-----|-------|------|
| 0 | Welcome + first action | Activation |
| 1 | Quick tip / "Did you know?" | Feature discovery |
| 3 | Case study / success story | Social proof |
| 5 | "Need help?" check-in | Reduce churn |
| 7 | Key feature highlight | Deeper engagement |

### Newsletter
```
Subject: [Brand] Weekly: [Top story hook]

# [Main story headline]
[2-3 sentences + link]

## Quick links
• [Link 1: title] — one-line description
• [Link 2: title] — one-line description
• [Link 3: title] — one-line description

## Tip of the week
[Actionable advice in 2-3 sentences]

---
[Unsubscribe] | [Preferences] | [View in browser]
```

### Re-engagement (inactive users)
```
Subject: We miss you (and have something new)

Hey [Name],

It's been a while since you logged in.

Since you left, we've added:
✓ [Feature 1]
✓ [Feature 2]
✓ [Feature 3]

Come take a look → [CTA: "See what's new"]

If [Product] isn't for you anymore, no hard feelings.
[Unsubscribe link]

— [Team]
```

### Transactional Emails
```
Subject: Your receipt from [Product]

Your payment of $29.00 was successful.

Plan: Pro (monthly)
Date: April 4, 2026
Next billing: May 4, 2026

[View receipt] | [Manage subscription]

Questions? Reply to this email.
```

## Email Design Rules

### Layout
- **Single column** — 600px max width
- **Mobile-first** — 50%+ opens are on mobile
- **F-pattern** — important content top-left
- **One primary CTA** — big button, contrasting color
- **Short paragraphs** — 2-3 sentences max

### Typography
- Font size: 16px body, 22-28px headlines
- Line height: 1.5-1.6
- System fonts (or web-safe fallbacks)
- Left-aligned (never justified or centered body text)

### Images
- Alt text on every image (many clients block images)
- Don't rely on images for key information
- Optimize: < 200KB total
- Retina-ready: 2x resolution

## Automation Flows

### Welcome Flow
```
Signup → Welcome email (immediate)
  → Day 1: Tip email
    → Did they activate?
      → Yes: Feature discovery email (Day 3)
      → No: "Need help?" email (Day 2)
        → Still no? "Here's what you're missing" (Day 5)
```

### Cart Abandonment
```
Cart abandoned → Wait 1 hour → "You left something behind"
  → Wait 24 hours → "Still interested?" + social proof
    → Wait 48 hours → "Last chance" + discount (optional)
```

## Metrics to Track

| Metric | Good | Great |
|--------|------|-------|
| Open rate | 20-25% | 30%+ |
| Click rate | 2-3% | 5%+ |
| Unsubscribe | < 0.5% | < 0.2% |
| Bounce rate | < 2% | < 0.5% |
| Spam complaints | < 0.1% | < 0.05% |

## Compliance
- **Unsubscribe link** — required in every marketing email
- **Physical address** — required by CAN-SPAM
- **Double opt-in** — recommended for GDPR compliance
- **No purchased lists** — ever
- **Honor unsubscribes** — within 10 business days (legal requirement)

## Deliverability

### DNS Setup (Required)
```
# SPF — who can send on your behalf
TXT  @  "v=spf1 include:_spf.google.com include:sendgrid.net ~all"

# DKIM — cryptographic signature
CNAME  s1._domainkey  s1.domainkey.u1234.wl567.sendgrid.net

# DMARC — policy for failed checks
TXT  _dmarc  "v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com; pct=100"
```

### Deliverability Checklist
- [ ] SPF, DKIM, DMARC all configured and passing
- [ ] Sending domain matches From address
- [ ] Warm up new domain/IP (start with 50/day, increase 2x weekly)
- [ ] List hygiene: remove bounces, inactive (>6 months) subscribers
- [ ] Spam score < 5 (check with mail-tester.com before sending)
- [ ] Unsubscribe in first line of email (Gmail promotes this)
- [ ] Text-to-image ratio ≥ 60:40 (too many images = spam folder)

## Segmentation Strategies

| Segment | Criteria | Use for |
|---------|----------|---------|
| **New users** | Signed up < 7 days | Welcome sequence |
| **Active** | Used product this week | Feature announcements |
| **At risk** | No login in 14 days | Re-engagement |
| **Power users** | Top 10% by usage | Upsell, referral asks |
| **Churned** | Cancelled/inactive 30+ days | Win-back campaigns |
| **By plan** | Free / Pro / Enterprise | Tier-specific features |

## Email Tools Comparison

| Tool | Best for | Price |
|------|----------|-------|
| **Resend** | Developer-first, transactional | Free < 3K/month |
| **Postmark** | Transactional reliability | From $15/month |
| **ConvertKit** | Creators, newsletters | Free < 1K subs |
| **Loops** | SaaS, product emails | Free < 1K contacts |
| **Mailchimp** | Small business, simple | Free < 500 contacts |
| **Customer.io** | Complex automation | From $100/month |
