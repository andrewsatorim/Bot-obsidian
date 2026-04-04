---
name: product
description: Use when defining product strategy, building MVPs, prioritizing features, creating roadmaps, setting metrics, or making product decisions. Also use when user asks "what should I build" or "how to validate an idea."
---

# Product Management

## Idea Validation (Before Writing Code)

### Validation Ladder
```
1. Problem exists?     → Talk to 10+ people with the problem
2. They'll pay?        → Pre-sell or waitlist (measure commitment)
3. Solution works?     → Prototype / wizard-of-oz test
4. You can build it?   → Technical spike (1-2 days)
5. Unit economics?     → CAC < LTV with realistic assumptions
```

### Customer Interview Script
```
1. "Tell me about the last time you [did the thing your product helps with]."
2. "What was the hardest part?"
3. "How do you solve that today?"
4. "What have you tried that didn't work?"
5. "If you had a magic wand, what would it do?"
6. "How much time/money does this problem cost you?"

RULES:
- Never pitch your solution
- Never ask "Would you use X?" (everyone says yes)
- Ask about past behavior, not future intentions
- Record (with permission) and take notes
- 20 interviews = patterns emerge
```

### Signals That Validate
| Signal | Strength |
|--------|----------|
| "Interesting idea" | Weak — polite noise |
| "Send me updates" | Weak — no commitment |
| "Can I get early access?" | Medium — shows interest |
| "Here's my email for the waitlist" | Medium |
| "I'd pay $X for that" | Strong — stated willingness |
| "Take my credit card now" | Strongest — actual commitment |
| "I built a hacky solution myself" | Very strong — proven pain |

## MVP Strategy

### What to Build First
```
Full vision → Strip to core value → Remove 80% → That's your MVP

Example:
  Vision: "AI-powered project management with Gantt charts,
           time tracking, resource planning, and reporting"
  MVP:    "One shared task list with AI prioritization"
```

### MVP Types
| Type | Speed | Validation |
|------|-------|------------|
| **Landing page** | 1 day | Interest, positioning |
| **Concierge** (manual backend) | 1 week | Value, willingness to pay |
| **Wizard of Oz** (fake automation) | 1-2 weeks | UX, workflow |
| **Single feature** | 2-4 weeks | Core value proposition |
| **Vertical slice** | 4-8 weeks | End-to-end experience |

### What NOT to Build in MVP
- User settings / preferences
- Admin panel
- Multi-language support
- Advanced permissions / roles
- Email notifications (beyond essentials)
- Social features (unless core)
- Mobile app (use responsive web)
- Analytics dashboard (use PostHog/Mixpanel)

## Metrics Framework (AARRR Pirate Metrics)

```
Acquisition → Activation → Retention → Revenue → Referral
```

| Stage | Question | Key Metric | Example |
|-------|----------|------------|---------|
| **Acquisition** | How do users find you? | Visitors, signups | 1,000 visitors/week |
| **Activation** | Do they get value? | Activation rate | 40% complete onboarding |
| **Retention** | Do they come back? | D7/D30 retention | 25% use weekly after 30 days |
| **Revenue** | Do they pay? | Conversion to paid | 5% free → paid |
| **Referral** | Do they tell others? | Viral coefficient | 0.3 (each user brings 0.3) |

### North Star Metric
One metric that captures core value delivery:
- **Slack:** Messages sent per team per day
- **Airbnb:** Nights booked
- **Spotify:** Time spent listening
- **Your SaaS:** [The action that proves users get value]

## Prioritization Frameworks

### ICE Score
```
Impact (1-10) × Confidence (1-10) × Ease (1-10) = ICE Score

Feature A: 8 × 7 × 3 = 168
Feature B: 5 × 9 × 8 = 360  ← Build this first
Feature C: 9 × 4 × 2 = 72
```

### RICE Score
```
(Reach × Impact × Confidence) / Effort = RICE

Reach: users affected per quarter
Impact: 0.25 (minimal) → 3 (massive)
Confidence: 50-100%
Effort: person-weeks
```

### MoSCoW
- **Must have** — product doesn't work without it
- **Should have** — important but workaround exists
- **Could have** — nice to have, easy win
- **Won't have** — explicitly out of scope (this round)

## Roadmap

### Now / Next / Later Format
```
NOW (this sprint/month)     NEXT (1-3 months)       LATER (3-6 months)
├── Core auth flow          ├── Team workspaces      ├── API / integrations
├── Dashboard MVP           ├── Billing (Stripe)     ├── Mobile app
└── Onboarding              ├── Email notifications  └── Enterprise features
                            └── Export / import
```

**Rules:**
- NOW = committed, detailed
- NEXT = planned, flexible
- LATER = directional, may change entirely
- Never put dates on LATER items
- Review and update bi-weekly

## Feature Spec Template

```markdown
## Feature: [Name]
**Goal:** [What user outcome does this enable?]
**Metric:** [How do we know it worked?]
**Target:** [Who is this for?]

### User Story
As a [persona], I want to [action] so that [benefit].

### Requirements
- [ ] Requirement 1
- [ ] Requirement 2
- [ ] Requirement 3

### Out of Scope
- Thing we're NOT building
- Thing that can come later

### Design
[Link to Figma / wireframe / screenshot]

### Technical Notes
[API changes, data model, dependencies]

### Success Criteria
- [ ] Metric X improves by Y%
- [ ] No increase in support tickets
- [ ] < 200ms response time
```

## Product-Market Fit Indicators

| Signal | Pre-PMF | Post-PMF |
|--------|---------|----------|
| Growth | Pushing (paid ads, outreach) | Pulling (organic, word of mouth) |
| Retention | < 20% week 4 | > 40% week 4 |
| NPS | < 30 | > 50 |
| Sean Ellis test | < 25% "very disappointed" | > 40% "very disappointed" |
| Support | "How does X work?" | "Can you add Y?" |
| Churn reason | "I don't need this" | "Too expensive" (pricing, not value) |

### Sean Ellis Survey
> "How would you feel if you could no longer use [product]?"
> - Very disappointed
> - Somewhat disappointed
> - Not disappointed
> - N/A — I don't use it anymore

**40%+ "Very disappointed" = Product-Market Fit**

## Product Checklist (Launch Readiness)

- [ ] Core value proposition works end-to-end
- [ ] Onboarding: new user reaches "aha moment" in < 5 minutes
- [ ] Error handling: graceful failures, never blank screens
- [ ] Performance: page loads < 2s, API < 200ms
- [ ] Mobile: responsive and usable on phone
- [ ] Analytics: key events tracked (signup, activation, core action)
- [ ] Feedback channel: in-app feedback or support email
- [ ] Legal: privacy policy + terms of service
- [ ] Billing: works correctly (if paid product)
- [ ] Landing page: clearly explains value + has CTA
