---
name: growth
description: Use when optimizing funnels, improving activation/retention, running experiments, analyzing cohorts, reducing churn, or building growth loops. Also use for onboarding optimization and viral mechanics.
---

# Growth Engineering

## Growth Funnel

```
Traffic → Signup → Activation → Retention → Revenue → Referral
  100%     10%       40%          25%         5%        0.3
  1000     100        40           10          2         0.3

Fix the WORST step first — that's your biggest lever.
```

## Activation

### Definition
The moment a user first experiences your core value ("aha moment").

| Product | Aha Moment |
|---------|------------|
| Slack | Send 2000 messages as a team |
| Dropbox | Save first file to Dropbox folder |
| Facebook | Add 7 friends in 10 days |
| Your SaaS | [User does the ONE thing that proves value] |

### Activation Checklist
- [ ] Aha moment defined and measurable
- [ ] Time-to-value < 5 minutes (ideally < 2)
- [ ] Onboarding guides to aha moment (not feature tour)
- [ ] Empty states have clear CTAs ("Create your first X")
- [ ] Progress indicator shows completion (3/5 steps done)
- [ ] Can skip optional steps (don't block activation)
- [ ] Friction removed: social login, pre-filled defaults, templates
- [ ] Follow-up email if user doesn't activate in 24h

### Onboarding Patterns
| Pattern | Best for |
|---------|----------|
| **Checklist** | Multi-step setup (Notion, Linear) |
| **Interactive tutorial** | Complex products (Figma) |
| **Template gallery** | Creative tools ("Start with a template") |
| **Empty state CTA** | Simple products ("Create your first project") |
| **Video walkthrough** | Visual products (< 90 seconds) |
| **Progressive disclosure** | Feature-rich products (show basics first) |

## Retention

### Cohort Analysis
```
         Week 0  Week 1  Week 2  Week 4  Week 8  Week 12
Jan      100%    35%     28%     22%     18%     15%
Feb      100%    40%     32%     26%     21%     —
Mar      100%    42%     35%     29%     —       —
                              ↑
                    Improvements working!
```

### Retention Benchmarks (SaaS)
| Metric | Poor | OK | Good | Great |
|--------|------|-----|------|-------|
| D1 retention | < 20% | 20-30% | 30-50% | > 50% |
| D7 retention | < 10% | 10-20% | 20-35% | > 35% |
| D30 retention | < 5% | 5-15% | 15-25% | > 25% |
| Monthly churn | > 10% | 5-10% | 3-5% | < 3% |

### Reducing Churn
| Churn signal | Intervention |
|-------------|-------------|
| No login in 3 days | Email: "Quick tip" with value |
| No login in 7 days | Email: "Here's what you're missing" |
| No login in 14 days | Email: "Need help?" + personal outreach |
| Payment failed | Dunning sequence: retry + email + grace period |
| Cancel intent | Exit survey + offer (discount, pause, downgrade) |
| Feature request | "We built what you asked for!" email when shipped |

## Growth Loops

### Viral Loop
```
User creates content → Content is shared/discovered → New user signs up → Creates content
Example: Notion templates, Figma community files, Canva designs
```

### Content Loop
```
Create SEO content → Ranks in Google → User discovers → Signs up → Uses product
Example: HubSpot blog → CRM signups
```

### Paid Loop
```
Revenue → Reinvest in ads → New users → Revenue
Only works if: LTV > CAC × 3 (rule of thumb)
```

### Product-Led Growth Loop
```
Free users → Hit limits → Upgrade to paid → Invite team → Team upgrades
Example: Slack, Notion, Figma
```

## Experimentation

### A/B Test Process
1. **Hypothesis**: "Changing [X] will improve [metric] by [Y]% because [reason]"
2. **Design**: Control (A) vs variant (B), one change only
3. **Sample size**: Calculate before starting (use Evan Miller calculator)
4. **Run**: Minimum 1-2 weeks, full business cycle
5. **Analyze**: Statistical significance ≥ 95%, practical significance matters
6. **Document**: Win or lose, record the learning

### What to Test (Priority Order)
1. **Pricing page** — plan names, prices, feature comparison
2. **Signup flow** — fields, social login, value proposition
3. **Onboarding** — steps, guidance, time-to-value
4. **CTA copy** — button text, placement, color
5. **Email subject lines** — open rates
6. **Landing page headline** — bounce rate

### Common Mistakes
- Ending test too early (need statistical significance)
- Testing too many things at once (can't attribute results)
- Ignoring segments (overall flat, but 2x lift for new users)
- Not tracking downstream metrics (signup ↑ but activation ↓)

## Analytics Setup

### Essential Events to Track
```javascript
// PostHog / Mixpanel / Amplitude
analytics.capture("user_signed_up", { method: "google" })
analytics.capture("onboarding_step_completed", { step: 3, total: 5 })
analytics.capture("core_action_performed", { type: "create_project" })
analytics.capture("upgrade_started", { plan: "pro", trigger: "limit_hit" })
analytics.capture("feature_used", { feature: "export", first_time: true })
```

### Key Dashboards
1. **Acquisition**: traffic sources, signup rate, cost per signup
2. **Activation**: onboarding completion, time to first value
3. **Engagement**: DAU/MAU ratio, core actions per session
4. **Retention**: cohort curves, churn by segment
5. **Revenue**: MRR, ARPU, expansion revenue, churn revenue

### Tools
| Tool | Best for | Price |
|------|----------|-------|
| **PostHog** | All-in-one (analytics, experiments, surveys) | Free < 1M events |
| **Mixpanel** | Event analytics, funnels | Free < 20M events |
| **Amplitude** | Product analytics, cohorts | Free tier |
| **LaunchDarkly** | Feature flags | Free < 1K users |
| **Statsig** | Feature flags + experiments | Free tier |
| **GrowthBook** | Open-source experiments | Free (self-hosted) |

## Growth Checklist

- [ ] Aha moment defined and time-to-value < 5 minutes
- [ ] Key funnel metrics tracked (acquisition → activation → retention → revenue)
- [ ] Cohort retention curves generated weekly
- [ ] Biggest funnel drop-off identified and being fixed
- [ ] At least 1 experiment running at all times
- [ ] Onboarding optimized for activation (not feature discovery)
- [ ] Churn signals identified with automated interventions
- [ ] At least 1 growth loop identified and reinforced
- [ ] Analytics dashboard reviewed daily by team
- [ ] Experiment results documented (wins AND losses)
