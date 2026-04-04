---
name: figma-to-code
description: Use when converting Figma designs, mockups, screenshots, or visual references into code. Also use when the user shares an image of a UI they want built.
---

# Figma to Code

## Workflow

1. **Analyze the visual** — identify layout structure, component hierarchy, spacing, colors, typography, and interactive elements.
2. **Map to components** — break the design into reusable React/HTML components. Name them by purpose, not appearance.
3. **Build structure first** — semantic HTML with correct nesting before any styling.
4. **Apply styles** — use Tailwind utilities or CSS matching the design tokens exactly.
5. **Add interactions** — hover states, focus rings, transitions, responsive behavior.
6. **Verify fidelity** — compare output against the original pixel by pixel.

## Reading a Design

When analyzing a screenshot or Figma export:

- **Spacing** — estimate in 4px increments (Tailwind: 1=4px, 2=8px, 3=12px, 4=16px, 6=24px, 8=32px)
- **Font sizes** — map to Tailwind scale: `text-xs`(12), `text-sm`(14), `text-base`(16), `text-lg`(18), `text-xl`(20), `text-2xl`(24)
- **Font weight** — normal(400), medium(500), semibold(600), bold(700)
- **Border radius** — none(0), sm(2), default(4), md(6), lg(8), xl(12), 2xl(16), full(9999)
- **Shadows** — `shadow-sm`, `shadow`, `shadow-md`, `shadow-lg`, `shadow-xl`
- **Colors** — extract hex values and map to nearest Tailwind color or define custom tokens

## Component Decomposition

```
Page
├── Header (sticky, blur backdrop)
│   ├── Logo
│   ├── Navigation
│   └── UserMenu
├── Main
│   ├── Hero / PageHeader
│   ├── ContentSection
│   │   ├── Card[]
│   │   └── EmptyState
│   └── Sidebar (optional)
└── Footer
```

## Translation Rules

| Figma concept | Code equivalent |
|---------------|----------------|
| Frame | `<div>` with flex/grid |
| Auto Layout (vertical) | `flex flex-col gap-*` |
| Auto Layout (horizontal) | `flex flex-row gap-*` |
| Fill container | `w-full` or `flex-1` |
| Hug contents | `w-fit` or default |
| Fixed size | `w-[Npx]` or `h-[Npx]` |
| Constraints (center) | `mx-auto` or `place-items-center` |
| Component instance | React component with props |
| Variants | Props or conditional classes |
| Prototype interaction | Event handler + state |

## Precision Checklist

- [ ] Spacing matches design (within 2px)
- [ ] Colors are exact hex matches
- [ ] Typography (family, size, weight, line-height) matches
- [ ] Border radius matches
- [ ] Shadows match
- [ ] Icons are correct (Lucide, Heroicons, or SVG)
- [ ] Responsive behavior is defined
- [ ] Hover/focus/active states exist
- [ ] Dark mode variant exists (if applicable)

## Figma Dev Mode & Inspect

When user provides Figma inspect values:
- **Width/Height** → map to Tailwind: `w-[Npx]` or closest utility
- **Padding** → `p-[top] pr-[right] pb-[bottom] pl-[left]` or shorthand
- **Gap** → `gap-[N]` in flex/grid
- **Fill** → `bg-[#hex]` or design token
- **Stroke** → `border border-[#hex]`
- **Effects** → `shadow-[value]` or `blur-[N]`
- **Text** → `text-[size] font-[weight] leading-[lineHeight] tracking-[letterSpacing]`

## Icon Libraries

| Library | Style | Package | Count |
|---------|-------|---------|-------|
| **Lucide** | Line (clean) | `lucide-react` | 1,500+ |
| **Heroicons** | Line + solid | `@heroicons/react` | 300+ |
| **Phosphor** | 6 weights | `@phosphor-icons/react` | 1,200+ |
| **Tabler** | Line (consistent) | `@tabler/icons-react` | 4,500+ |

```tsx
// Lucide (recommended — tree-shakeable)
import { ArrowRight, Check, X } from "lucide-react"
<ArrowRight className="h-4 w-4" />

// Heroicons
import { ArrowRightIcon } from "@heroicons/react/24/outline"
```

## Screenshot Analysis Tips

When analyzing a screenshot or mockup image:
1. **Zoom in** — identify exact spacing between elements
2. **Color pick** — extract all unique colors, create a palette
3. **Font identification** — check Google Fonts or system fonts
4. **Grid system** — determine column count and gutter width
5. **Component patterns** — recognize shadcn/Radix/MUI components
6. **Responsive clues** — is this mobile, tablet, or desktop view?
7. **Interaction hints** — hover states, dropdowns, modals visible

## Common Conversion Mistakes

| Mistake | Fix |
|---------|-----|
| Using fixed px for everything | Use relative units (rem, %, Tailwind utilities) |
| Ignoring touch targets | Ensure 44px minimum on mobile |
| Missing hover/focus states | Add for every interactive element |
| No loading/empty states | Design them even if not in mockup |
| Pixel-perfect but not responsive | Design must adapt across breakpoints |
| Hardcoded colors | Use CSS variables or Tailwind config |
