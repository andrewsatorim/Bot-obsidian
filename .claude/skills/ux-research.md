---
name: ux-research
description: Use when conducting user research, usability testing, creating personas, journey maps, or making design decisions based on user data. Also use when the user asks "how should this flow work" or "what do users expect."
---

# UX Research

## Research Methods (When to Use What)

| Method | When | Time | Sample |
|--------|------|------|--------|
| **User interviews** | Discovery, understanding needs | 1-2 weeks | 5-10 users |
| **Usability testing** | Validate design/flow | 3-5 days | 5 users (finds 85% of issues) |
| **Surveys** | Quantitative validation | 1 week | 100+ responses |
| **Card sorting** | Information architecture | 2-3 days | 15-30 users |
| **A/B testing** | Optimize conversions | 1-4 weeks | 1000+ visitors |
| **Analytics review** | Find drop-offs, patterns | 1 day | Existing data |
| **Heatmaps** | Where users look/click | 1 week | 1000+ sessions |
| **Session recordings** | Debug UX issues | Ongoing | 50-100 sessions |

## User Personas

### Template
```markdown
## Persona: [Name]

**Demographics**
- Role: Senior Developer at a startup (50-200 employees)
- Age: 28-35
- Tech comfort: Expert
- Tools: VS Code, GitHub, Linear, Slack

**Goals**
1. Ship features faster without compromising quality
2. Reduce time spent on repetitive tasks
3. Keep codebase maintainable as team grows

**Pain Points**
1. Code review bottleneck — PRs sit for days
2. Context switching between too many tools
3. Writing tests feels slow but skipping them is risky

**Behavior**
- Tries free tools first, upgrades when hitting limits
- Reads dev Twitter and Hacker News daily
- Trusts peer recommendations over marketing

**Quote**
"I'd rather spend 10 minutes automating something than do it manually twice."
```

### Rules
- Based on real interviews, not assumptions
- 2-4 personas max (more = nobody uses them)
- Include anti-persona (who you're NOT building for)
- Update quarterly based on new data

## User Journey Map

```
STAGE:    Awareness → Consideration → Signup → Onboarding → Active Use → Expansion
           |              |             |          |             |            |
DOING:    Googles      Reads landing   Creates    Follows       Daily       Invites
          problem      page, pricing   account    setup wizard  workflow    team
           |              |             |          |             |            |
THINKING: "There must    "Does this    "Hope this "This is      "This       "Team
          be a better    solve MY       isn't      taking too    actually    should
          way"           problem?"      complex"   long..."      saves time" use this"
           |              |             |          |             |            |
FEELING:  Frustrated   → Hopeful    → Cautious → Impatient  → Satisfied → Enthusiastic
           |              |             |          |             |            |
PAIN:     Can't find   → Unclear     → Too many → Confusing  → Missing   → No team
          solution       pricing       fields     jargon        feature      features
           |              |             |          |             |            |
FIX:      SEO +        → Transparent → Social   → Progressive→ Feature   → Team
          content        pricing       login      disclosure    request     onboarding
```

## Usability Testing

### Test Script
```markdown
## Pre-test
"I'm testing the product, not you. There are no wrong answers.
Think out loud — tell me what you're looking at and thinking."

## Tasks (3-5 max)
1. "You want to [goal]. Starting from this page, show me how you'd do that."
2. "Find [specific thing] and [do action with it]."
3. "You just received [notification]. What would you do?"

## Post-task Questions
- "On a scale of 1-5, how easy was that?" (SUS)
- "What was confusing?"
- "What did you expect to happen?"

## Post-test
- "What was the best part of the experience?"
- "What was the most frustrating?"
- "Would you use this? Why / why not?"
```

### 5-Second Test
1. Show the page for 5 seconds
2. Hide it
3. Ask: "What was this page about?" "What can you do here?"
4. If they can't answer → redesign

### Severity Rating
| Rating | Meaning | Action |
|--------|---------|--------|
| **4 - Catastrophe** | User cannot complete task | Fix before launch |
| **3 - Major** | User struggles significantly | Fix in current sprint |
| **2 - Minor** | User is annoyed but succeeds | Fix in next sprint |
| **1 - Cosmetic** | User notices but isn't affected | Backlog |

## Information Architecture

### Card Sorting
1. Write each feature/page on a card (30-60 cards)
2. Ask 15-30 users to group them into categories
3. Ask them to name each category
4. Analyze: which items are always grouped together?
5. Result → navigation structure

### Navigation Rules
- Max 7 items in primary nav (Miller's law)
- Most important items first and last (serial position effect)
- Use user language, not internal jargon
- Every page reachable in ≤ 3 clicks
- Breadcrumbs for deep hierarchies

## UX Heuristics (Nielsen's 10)

| # | Heuristic | Check |
|---|-----------|-------|
| 1 | **Visibility of system status** | Loading indicators, progress bars, confirmations |
| 2 | **Match real world** | Familiar language, logical order |
| 3 | **User control** | Undo, cancel, go back, escape |
| 4 | **Consistency** | Same action = same result everywhere |
| 5 | **Error prevention** | Confirm destructive actions, validate inline |
| 6 | **Recognition > recall** | Show options, don't make users remember |
| 7 | **Flexibility** | Keyboard shortcuts, customization |
| 8 | **Minimal design** | Remove what doesn't help the user |
| 9 | **Help with errors** | Plain language, suggest fix, no codes |
| 10 | **Help & docs** | Searchable, task-oriented, concise |

## Research Tools

| Tool | Purpose | Price |
|------|---------|-------|
| **Hotjar** | Heatmaps, recordings, surveys | Free tier |
| **Maze** | Unmoderated usability tests | Free tier |
| **Lyssna** | 5-second tests, card sorting | Free tier |
| **Calendly** | Schedule user interviews | Free |
| **Notion** | Research repository, synthesis | Free |
| **Dovetail** | Research analysis, tagging | Free tier |
| **PostHog** | Analytics, session recordings | Free < 1M events |

## UX Research Checklist

- [ ] Talked to 5+ real users before designing
- [ ] Personas based on interview data (not assumptions)
- [ ] User journey mapped with pain points identified
- [ ] Key flows usability-tested with 5 users
- [ ] Critical issues (severity 3-4) fixed before launch
- [ ] Analytics tracking core user actions
- [ ] Feedback mechanism in-app (survey, chat, or email)
- [ ] Research findings documented and shared with team
- [ ] Quarterly check-in interviews scheduled
- [ ] Anti-persona defined (who we're NOT building for)
