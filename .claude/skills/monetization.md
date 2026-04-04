---
name: monetization
description: Use when implementing payments, designing pricing, setting up subscriptions, calculating unit economics, or integrating Stripe/payment providers.
---

# Monetization

## Pricing Strategy

### Pricing Models
| Model | Best for | Example |
|-------|----------|---------|
| **Freemium** | Wide market, viral potential | Notion, Slack, Figma |
| **Free trial** | Complex products, clear value | Salesforce (14 days) |
| **Usage-based** | Variable consumption | AWS, Twilio, Vercel |
| **Per-seat** | Team collaboration tools | Linear, GitHub |
| **Flat rate** | Simple products | Basecamp ($99/mo flat) |
| **Hybrid** | Seats + usage | Snowflake, Datadog |

### Pricing Psychology
- **Anchor high** — show expensive plan first (makes mid-tier feel reasonable)
- **3 tiers** — Free / Pro / Enterprise (most buy middle)
- **Annual discount** — 15-20% off (improves cash flow + retention)
- **Remove the $ sign** — "29/mo" converts better than "$29/mo"
- **Odd pricing** — $29 not $30 (perceived as calculated, not arbitrary)
- **End in 9** — $49 outperforms $47 and $50
- **Don't punish growth** — price on value delivered, not usage that punishes success

### How to Set Your Price
```
1. Cost floor: What does it cost you per user? (hosting, support, tools)
2. Value ceiling: What's the user's alternative cost? (time, other tools, manual work)
3. Price = somewhere between, closer to value
4. Start higher — you can always lower, but raising is hard

Example:
  Cost per user: $3/month
  Alternative cost: $200/month (manual process) or $50/month (competitor)
  Your price: $19-39/month
```

## Unit Economics

### Key Metrics
```
LTV (Lifetime Value) = ARPU × Average Lifespan
  = $50/mo × 24 months = $1,200

CAC (Customer Acquisition Cost) = Marketing Spend / New Customers
  = $10,000 / 100 = $100

LTV:CAC Ratio = $1,200 / $100 = 12:1
  Target: > 3:1 (healthy business)
  
Payback Period = CAC / ARPU = $100 / $50 = 2 months
  Target: < 12 months
```

### SaaS Quick Health Check
| Metric | Red | Yellow | Green |
|--------|-----|--------|-------|
| LTV:CAC | < 1:1 | 1-3:1 | > 3:1 |
| Monthly churn | > 10% | 5-10% | < 5% |
| Payback months | > 18 | 12-18 | < 12 |
| Gross margin | < 50% | 50-70% | > 70% |
| Net revenue retention | < 90% | 90-110% | > 120% |

## Stripe Integration

### Setup
```bash
npm install stripe @stripe/stripe-js @stripe/react-stripe-js
```

### Server: Create Checkout Session
```typescript
// app/api/checkout/route.ts
import Stripe from "stripe"

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)

export async function POST(req: Request) {
  const { priceId, userId } = await req.json()
  
  const session = await stripe.checkout.sessions.create({
    mode: "subscription",
    payment_method_types: ["card"],
    line_items: [{ price: priceId, quantity: 1 }],
    success_url: `${process.env.APP_URL}/dashboard?success=true`,
    cancel_url: `${process.env.APP_URL}/pricing`,
    client_reference_id: userId,
    metadata: { userId },
  })

  return Response.json({ url: session.url })
}
```

### Webhook: Handle Events
```typescript
// app/api/webhooks/stripe/route.ts
import Stripe from "stripe"

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)

export async function POST(req: Request) {
  const body = await req.text()
  const sig = req.headers.get("stripe-signature")!
  
  const event = stripe.webhooks.constructEvent(
    body, sig, process.env.STRIPE_WEBHOOK_SECRET!
  )

  switch (event.type) {
    case "checkout.session.completed": {
      const session = event.data.object as Stripe.Checkout.Session
      await activateSubscription(session.client_reference_id!, session.subscription as string)
      break
    }
    case "customer.subscription.updated": {
      const sub = event.data.object as Stripe.Subscription
      await updateSubscription(sub.id, sub.status, sub.current_period_end)
      break
    }
    case "customer.subscription.deleted": {
      const sub = event.data.object as Stripe.Subscription
      await cancelSubscription(sub.id)
      break
    }
    case "invoice.payment_failed": {
      const invoice = event.data.object as Stripe.Invoice
      await handleFailedPayment(invoice.customer as string)
      break
    }
  }

  return new Response("OK")
}
```

### Client: Redirect to Checkout
```tsx
async function handleUpgrade(priceId: string) {
  const res = await fetch("/api/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ priceId, userId: currentUser.id }),
  })
  const { url } = await res.json()
  window.location.href = url
}
```

### Customer Portal (Manage Subscription)
```typescript
const portalSession = await stripe.billingPortal.sessions.create({
  customer: customerId,
  return_url: `${process.env.APP_URL}/settings/billing`,
})
// Redirect to portalSession.url
```

## Subscription Lifecycle

```
Free User → Checkout → Active Subscription → Renewal (auto)
                                ↓
                          Payment Failed → Dunning (3 retries) → Grace Period → Cancelled
                                ↓
                          Cancel Request → End of Period → Downgrade to Free
                                ↓
                          Upgrade/Downgrade → Prorated Amount → New Plan Active
```

### Dunning (Failed Payments)
```
Day 0: Payment fails → Retry automatically
Day 3: Email "Update your payment method" + retry
Day 7: Email "Your access may be interrupted" + retry
Day 14: Email "Last chance" + retry
Day 21: Downgrade to free plan, email "We'll miss you"
```

## Revenue Optimization

### Expansion Revenue
- **Upsell**: Free → Pro → Enterprise
- **Cross-sell**: Add-ons (extra storage, priority support, API access)
- **Usage upgrades**: Hit plan limit → prompt upgrade
- **Seat expansion**: Team grows → more seats

### Pricing Page Best Practices
- Highlight recommended plan (visual border + "Most popular" badge)
- Show annual toggle with savings percentage
- Feature comparison table below plans
- Enterprise = "Contact sales" (custom pricing)
- FAQ section addressing payment concerns
- Money-back guarantee badge ("30-day money-back guarantee")

## Payment Providers

| Provider | Best for | Fees |
|----------|----------|------|
| **Stripe** | SaaS, subscriptions, global | 2.9% + 30¢ |
| **Paddle** | SaaS as Merchant of Record (handles tax) | 5% + 50¢ |
| **Lemon Squeezy** | Digital products, simple setup | 5% + 50¢ |
| **Gumroad** | Creators, digital products | 10% |

**Merchant of Record** (Paddle, LemonSqueezy): they handle sales tax, VAT, invoicing. You don't need to register for tax in every country. Higher fees but much less complexity.

## Monetization Checklist

- [ ] Pricing model chosen and justified by market research
- [ ] 3 pricing tiers defined with clear differentiation
- [ ] Unit economics calculated (LTV, CAC, payback, margins)
- [ ] LTV:CAC ratio > 3:1
- [ ] Stripe (or alternative) integrated with webhooks
- [ ] Subscription lifecycle handles: create, upgrade, downgrade, cancel, failed payment
- [ ] Dunning sequence configured (3-4 retry emails)
- [ ] Customer portal for self-service billing management
- [ ] Receipts/invoices sent automatically
- [ ] Revenue dashboard tracking MRR, churn, expansion
- [ ] Tax compliance handled (Stripe Tax or MoR like Paddle)
