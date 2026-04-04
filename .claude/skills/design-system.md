---
name: design-system
description: Use when creating or working with design systems, design tokens, component libraries, theming, style guides, or brand consistency.
---

# Design Systems

## Design Tokens

Tokens are the atomic values of a design system. Define them once, use everywhere.

### Token Hierarchy

```
Global tokens (raw values)
  → Alias tokens (semantic meaning)
    → Component tokens (scoped usage)

Example:
  blue-500: #3b82f6           (global)
  color-primary: blue-500      (alias)
  button-bg-primary: primary   (component)
```

### Token Categories

| Category | Examples | Format |
|----------|---------|--------|
| **Color** | primary, neutral, semantic | hex, hsl, oklch |
| **Typography** | font-family, size, weight, line-height | px, rem, unitless |
| **Spacing** | padding, margin, gap | 4px scale (4, 8, 12, 16, 24, 32, 48, 64) |
| **Border** | width, radius, style | px |
| **Shadow** | elevation levels (sm, md, lg, xl) | box-shadow values |
| **Motion** | duration, easing | ms, cubic-bezier |
| **Breakpoint** | sm, md, lg, xl, 2xl | px |
| **Z-index** | base, dropdown, modal, toast | integers (0, 10, 20, 30, 40, 50) |

### Token Implementation

**CSS Custom Properties:**
```css
:root {
  --color-primary: #3b82f6;
  --color-on-primary: #ffffff;
  --space-4: 1rem;
  --radius-md: 0.375rem;
  --font-sans: system-ui, sans-serif;
}
[data-theme="dark"] {
  --color-primary: #60a5fa;
  --color-on-primary: #0a0a0a;
}
```

**Tailwind Config:**
```js
theme: {
  extend: {
    colors: {
      primary: { DEFAULT: 'var(--color-primary)', on: 'var(--color-on-primary)' },
    }
  }
}
```

## Component Library Structure

```
components/
├── primitives/        # Base building blocks
│   ├── Button.tsx
│   ├── Input.tsx
│   ├── Badge.tsx
│   └── Avatar.tsx
├── composites/        # Composed from primitives
│   ├── Card.tsx
│   ├── Dialog.tsx
│   ├── Dropdown.tsx
│   └── DataTable.tsx
├── layouts/           # Page-level structures
│   ├── Container.tsx
│   ├── Stack.tsx
│   ├── Grid.tsx
│   └── Sidebar.tsx
└── patterns/          # Domain-specific
    ├── AuthForm.tsx
    ├── PricingCard.tsx
    └── FeatureGrid.tsx
```

## Component API Conventions

- **Variant** — visual style: `variant="primary" | "secondary" | "ghost" | "destructive"`
- **Size** — dimensions: `size="sm" | "md" | "lg"`
- **State** — behavior: `disabled`, `loading`, `error`
- **Composition** — slots or children: `<Card><Card.Header /><Card.Body /></Card>`
- **Polymorphism** — `as` prop: `<Button as="a" href="/link">` renders as `<a>`
- **Ref forwarding** — always use `forwardRef` for DOM access
- **className** — always accept and merge with internal classes via `cn()`

## Theming Strategy

### Multi-theme approach

```tsx
// Theme provider with CSS variables
<ThemeProvider theme="dark">  // sets [data-theme="dark"] on root
  <App />
</ThemeProvider>
```

### Required theme surfaces

| Surface | Light | Dark |
|---------|-------|------|
| Background (primary) | white | gray-950 |
| Background (secondary) | gray-50 | gray-900 |
| Background (tertiary) | gray-100 | gray-800 |
| Foreground (primary) | gray-900 | gray-50 |
| Foreground (muted) | gray-500 | gray-400 |
| Border (default) | gray-200 | gray-800 |
| Border (light) | gray-100 | gray-900 |

## Brand Consistency Rules

1. **Single source of truth** — all values come from tokens, never hardcoded
2. **Naming by purpose** — `color-error` not `color-red`, `space-section` not `space-64`
3. **Constrained choices** — limit options to prevent inconsistency (3-5 font sizes, 5-6 spacing values)
4. **Documentation** — every component has usage guidelines, do/don't examples
5. **Visual regression testing** — screenshot tests catch unintended changes

## Storybook

### Setup
```bash
npx storybook@latest init
npm run storybook  # opens at localhost:6006
```

### Story File
```tsx
// Button.stories.tsx
import type { Meta, StoryObj } from "@storybook/react"
import { Button } from "./Button"

const meta: Meta<typeof Button> = {
  component: Button,
  tags: ["autodocs"],
  argTypes: {
    variant: { control: "select", options: ["primary", "secondary", "ghost"] },
    size: { control: "select", options: ["sm", "md", "lg"] },
  },
}
export default meta
type Story = StoryObj<typeof Button>

export const Primary: Story = { args: { variant: "primary", children: "Click me" } }
export const Secondary: Story = { args: { variant: "secondary", children: "Cancel" } }
export const Loading: Story = { args: { variant: "primary", loading: true, children: "Saving..." } }
```

### Visual Regression (Chromatic)
```bash
npx chromatic --project-token=YOUR_TOKEN
# Captures screenshots of every story, diffs against baseline
```

## Component Versioning

### Semantic Versioning for Components
- **PATCH** (1.0.x) — bug fix, no API change
- **MINOR** (1.x.0) — new prop or variant, backwards compatible
- **MAJOR** (x.0.0) — breaking API change (renamed prop, removed variant)

### Migration Guide Template
```markdown
## Migrating Button from v2 to v3

### Breaking Changes
- `color` prop renamed to `variant`
- `size="xs"` removed (use `size="sm"` instead)

### Migration Steps
1. Find & replace: `color=` → `variant=`
2. Find & replace: `size="xs"` → `size="sm"`

### Codemod (automated)
npx jscodeshift -t ./codemods/button-v3.ts src/
```

## Design System Audit Checklist

- [ ] All colors defined as tokens (no hardcoded hex in components)
- [ ] Typography scale: max 5-6 sizes used consistently
- [ ] Spacing uses 4/8px grid only
- [ ] All components have Storybook stories
- [ ] Light and dark theme tokens defined
- [ ] Components are accessible (keyboard, screen reader, contrast)
- [ ] Component API is consistent (same prop names across components)
- [ ] Visual regression tests catch unintended changes
- [ ] Documentation includes do/don't examples
- [ ] Versioned with changelog and migration guides
